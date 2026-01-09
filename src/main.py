import json
import logging
import os
from typing import cast
from urllib import request

from dotenv import load_dotenv
from neon_api import NeonAPI
from neon_api.schema import Project

from models import (
    PLAN_CATALOG,
    AlertMode,
    AlertThresholds,
    CostBreakdown,
    PlanName,
    UsageTotals,
    WebHookProvider,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("neon_billing_alerts")


def _parse_threshold(name: str) -> float | None:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        return float(raw_value.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a number, got {raw_value!r}") from error


def _compute_usage(project: Project) -> UsageTotals:
    compute_cu_hours = project.compute_time_seconds / 3600.0
    storage_gb_month = (project.data_storage_bytes_hour / (1024.0**3)) / 730.0
    egress_gb = project.data_transfer_bytes / (1024.0**3)
    return UsageTotals(
        compute_cu_hours=compute_cu_hours,
        storage_gb_month=storage_gb_month,
        egress_gb=egress_gb,
    )


def _compute_costs(plan: PlanName, usage: UsageTotals) -> CostBreakdown:
    pricing = PLAN_CATALOG[plan]
    # if usage is less than amount of free usage, don't bill
    billable_compute = max(0.0, usage.compute_cu_hours - pricing.free_compute_cu_hour)
    billable_storage = max(0.0, usage.storage_gb_month - pricing.free_storage_gb_month)
    billable_egress = max(0.0, usage.egress_gb - pricing.free_egress_gb)

    return CostBreakdown(
        compute_cost=billable_compute * pricing.compute_cu_hour,
        storage_cost=billable_storage * pricing.storage_gb_month,
        egress_cost=billable_egress * pricing.egress_gb,
    )


def _evaluate_alerts(
    mode: AlertMode,
    thresholds: AlertThresholds,
    usage: UsageTotals,
    costs: CostBreakdown,
) -> list[str]:
    if mode == "always":
        return ["alert_mode=always"]

    if (
        thresholds.max_spend_usd is None
        and thresholds.max_cu_usage is None
        and thresholds.max_storage_gb_month is None
        and thresholds.max_egress_gb is None
    ):
        raise ValueError(
            "alert_mode=thresholds requires at least one threshold input.",
        )

    triggers: list[str] = []
    total_cost_value = costs.compute_cost + costs.storage_cost + costs.egress_cost

    # Cost threshold
    if (
        thresholds.max_spend_usd is not None
        and total_cost_value >= thresholds.max_spend_usd
    ):
        triggers.append(f"total_cost>={thresholds.max_spend_usd}")

    # Compute usage threshold
    if (
        thresholds.max_cu_usage is not None
        and usage.compute_cu_hours >= thresholds.max_cu_usage
    ):
        triggers.append(f"compute_cu_hours>={thresholds.max_cu_usage}")

    # Storage usage threshold
    if (
        thresholds.max_storage_gb_month is not None
        and usage.storage_gb_month >= thresholds.max_storage_gb_month
    ):
        triggers.append(f"storage_gb_month>={thresholds.max_storage_gb_month}")

    # Egress usage threshold
    if (
        thresholds.max_egress_gb is not None
        and usage.egress_gb >= thresholds.max_egress_gb
    ):
        triggers.append(f"egress_gb>={thresholds.max_egress_gb}")

    return triggers


def _send_webhook(
    webhook_url: str,
    provider: WebHookProvider,
    message: str,
) -> None:
    payload = {"text": message} if provider == "slack" else {"content": message}

    http_request = request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "neon-billing-alerts-action/1.0.0",
        },
    )

    with request.urlopen(http_request) as response:
        if response.status >= 300:
            raise ValueError(f"Webhook delivery failed with status {response.status}.")
        logger.info("Webhook delivered to %s (status %s)", webhook_url, response.status)


def _render_markdown(
    provider: WebHookProvider,
    usage: UsageTotals,
    costs: CostBreakdown,
    triggers: list[str],
    project_id: str,
) -> str:
    total_cost_value = costs.compute_cost + costs.storage_cost + costs.egress_cost
    trigger_line = ", ".join(triggers) if triggers else "thresholds unmet"
    amount_compute = f"{usage.compute_cu_hours:8.2f}"
    amount_storage = f"{usage.storage_gb_month:8.2f}"
    amount_egress = f"{usage.egress_gb:8.2f}"
    cost_compute = f"${costs.compute_cost:7.2f}"
    cost_storage = f"${costs.storage_cost:7.2f}"
    cost_egress = f"${costs.egress_cost:7.2f}"
    cost_total = f"${total_cost_value:7.2f}"
    header = (
        f"**Neon billing alert — {project_id}**"
        if provider == "discord"
        else f"*Neon billing alert — {project_id}*"
    )
    return (
        f"{header}\n"
        f"- Trigger: {trigger_line}\n"
        "```\n"
        "| Usage        |  Amount  |   Cost   |\n"
        "|--------------|----------|----------|\n"
        f"| Compute CU-h | {amount_compute} | {cost_compute} |\n"
        f"| Storage GB-m | {amount_storage} | {cost_storage} |\n"
        f"| Egress GB    | {amount_egress} | {cost_egress} |\n"
        f"| Total        |    —     | {cost_total} |\n"
        "```"
    )


def main() -> None:
    load_dotenv()

    neon_api_key_raw = os.getenv("NEON_API_KEY")
    if neon_api_key_raw is None or neon_api_key_raw.strip() == "":
        raise ValueError("Environment variable NEON_API_KEY is required.")
    neon_api_key = neon_api_key_raw.strip()

    project_id_raw = os.getenv("NEON_PROJECT_ID")
    if project_id_raw is None or project_id_raw.strip() == "":
        raise ValueError("Environment variable NEON_PROJECT_ID is required.")
    project_id = project_id_raw.strip()

    webhook_url_raw = os.getenv("WEBHOOK_URL")
    if webhook_url_raw is None or webhook_url_raw.strip() == "":
        raise ValueError("Environment variable WEBHOOK_URL is required.")
    webhook_url = webhook_url_raw.strip()

    alert_mode_env = os.getenv("ALERT_MODE", "always")
    alert_mode_value = alert_mode_env.strip().lower()
    if alert_mode_value not in ("always", "thresholds"):
        raise ValueError("ALERT_MODE must be 'always' or 'thresholds'.")
    logger.info("Alert mode: %s", alert_mode_value)

    thresholds = AlertThresholds(
        max_spend_usd=_parse_threshold("MAX_SPEND_USD"),
        max_cu_usage=_parse_threshold("MAX_CU_USAGE"),
        max_storage_gb_month=_parse_threshold("MAX_STORAGE_GB_MONTH"),
        max_egress_gb=_parse_threshold("MAX_EGRESS_GB"),
    )

    if alert_mode_value == "always" and any(
        threshold is not None
        for threshold in (
            thresholds.max_spend_usd,
            thresholds.max_cu_usage,
            thresholds.max_storage_gb_month,
            thresholds.max_egress_gb,
        )
    ):
        raise ValueError("alert_mode=always cannot be combined with thresholds.")
    logger.info(
        "Thresholds - spend: %s, cu: %s, storage: %s, egress: %s",
        thresholds.max_spend_usd,
        thresholds.max_cu_usage,
        thresholds.max_storage_gb_month,
        thresholds.max_egress_gb,
    )

    neon_api = NeonAPI(api_key=neon_api_key)
    project = neon_api.project(project_id).project
    plan_value = project.owner.subscription_type.value.lower()
    if plan_value not in PLAN_CATALOG:
        raise ValueError(
            f"Invalid plan: {plan_value}, expected one of {list(PLAN_CATALOG.keys())}"
        )
    plan = cast(PlanName, plan_value)

    usage = _compute_usage(project)
    costs = _compute_costs(plan, usage)
    triggers = _evaluate_alerts(alert_mode_value, thresholds, usage, costs)
    lowered = webhook_url.lower()
    if "slack" in lowered:
        provider: WebHookProvider = "slack"
    elif "discord" in lowered:
        provider = "discord"
    else:
        raise ValueError(f"Unsupported webhook URL: {webhook_url}")
    logger.info(
        "Usage - compute CU-h: %.2f, storage GB-m: %.2f, egress GB: %.2f",
        usage.compute_cu_hours,
        usage.storage_gb_month,
        usage.egress_gb,
    )
    logger.info(
        "Costs - compute: $%.2f, storage: $%.2f, egress: $%.2f",
        costs.compute_cost,
        costs.storage_cost,
        costs.egress_cost,
    )
    logger.info("Plan: %s, Project: %s", plan, project_id)

    if not triggers:
        logger.info("No alert: thresholds not met.")
        return

    message = _render_markdown(provider, usage, costs, triggers, project_id)
    _send_webhook(webhook_url, provider, message)


if __name__ == "__main__":
    main()
