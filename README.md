# Neon Billing Alerts (GitHub Action)

Send Neon usage/cost alerts to Slack or Discord.

*NOTE* The calculated cost is an estimate, and does not include storage costs from PITR.

## Inputs (action `with:`)
- `neon_api_key` (required): Neon API key. Create one via the [Neon docs](https://neon.com/docs/manage/api-keys#creating-api-keys).
- `neon_project_id` (required): ID of the Neon project to monitor (find it in the project Settings page).
- `webhook_url` (required): Slack or Discord webhook URL. Slack setup: [docs](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/). Discord setup: [docs](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks).
- `alert_mode` (optional): `always` or `thresholds` (default `thresholds`).
  - `always`: send every run.
  - `thresholds`: send only when any threshold below is met; if none provided, the run fails fast.
- Thresholds (optional, any combination):
  - `max_spend_usd`: Approximate cost based on compute, storage, and egress for current billing period.
  - `max_cu_usage`: Compute units used in current billing period.
  - `max_storage_gb_month`: Storage-time used in current billing period.
  - `max_egress_gb`: Egress used in current billing period.

## Example workflows

### Threshold-based alert
```yaml
name: Check Billing (thresholds)
on:
  schedule:
    - cron: "0 9 * * *"
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: sam-harri/neon-billing-alerts@v1
        with:
          neon_api_key: ${{ secrets.NEON_API_KEY }}
          neon_project_id: ${{ secrets.NEON_PROJECT_ID }}
          webhook_url: ${{ secrets.WEBHOOK_URL }} # Slack or Discord
          alert_mode: thresholds
          max_spend_usd: 50
          max_cu_usage: 50
          max_storage_gb_month: 200
          max_egress_gb: 20
```

### Always alert
```yaml
name: Check Billing (always)
on:
  schedule:
    - cron: "0 12 * * *"
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: sam-harri/neon-billing-alerts@v1
        with:
          neon_api_key: ${{ secrets.NEON_API_KEY }}
          neon_project_id: ${{ secrets.NEON_PROJECT_ID }}
          webhook_url: ${{ secrets.WEBHOOK_URL }}
          alert_mode: always
```