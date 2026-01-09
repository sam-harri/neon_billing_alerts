from dataclasses import dataclass
from typing import Literal

PlanName = Literal["scale", "launch"]
AlertMode = Literal["always", "thresholds"]
WebHookProvider = Literal["slack", "discord"]


@dataclass(frozen=True)
class UsagePricing:
    storage_gb_month: float
    compute_cu_hour: float
    egress_gb: float
    free_storage_gb_month: float
    free_compute_cu_hour: float
    free_egress_gb: float


@dataclass(frozen=True)
class UsageTotals:
    compute_cu_hours: float
    storage_gb_month: float
    egress_gb: float


@dataclass(frozen=True)
class CostBreakdown:
    compute_cost: float
    storage_cost: float
    egress_cost: float


@dataclass(frozen=True)
class AlertThresholds:
    max_spend_usd: float | None
    max_cu_usage: float | None
    max_storage_gb_month: float | None
    max_egress_gb: float | None


PLAN_CATALOG: dict[PlanName, UsagePricing] = {
    "scale": UsagePricing(
        storage_gb_month=0.35,
        compute_cu_hour=0.222,
        egress_gb=0.10,
        free_storage_gb_month=0.0,
        free_compute_cu_hour=0.0,
        free_egress_gb=100.0,
    ),
    "launch": UsagePricing(
        storage_gb_month=0.35,
        compute_cu_hour=0.106,
        egress_gb=0.10,
        free_storage_gb_month=0.0,
        free_compute_cu_hour=0.0,
        free_egress_gb=100.0,
    ),
}
