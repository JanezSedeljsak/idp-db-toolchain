# idp-db-toolchain

Internal IDP demo for Kubernetes: register Postgres databases, backup to S3 (zstd), retention, Prometheus metrics, Grafana alerts.

**Stack:** Terraform/AWS, Kustomize, Python (`uv`), GitHub Actions, kind, LocalStack.

```bash
./dev.sh wizard        # local
./dev.sh wizard-aws    # AWS demo (tear down: ./dev.sh aws-down)
./dev.sh test
pre-commit install     # secret guard + ruff
```

## Scope

| In | Out |
|----|-----|
| Multi-DB backup → S3 | Schema migrations |
| Scheduled backup + retention | DB changes on deploy |
| Export, anonymize, metrics | Bundled prod Postgres |

Deploy only rolls the **image** (no migrations/seeds/restores on publish).

## Config

`db-toolchain.toml` for databases, schedules, S3. `.env` for secrets (`AWS_*`, `DATABASES`, …).

```toml
[[databases]]
id = "shop"
url = "postgres://user:pass@host:5432/shop?sslmode=require"

[schedule]
backup = "0 2 * * *"
retention = "0 3 1 * *"

[s3]
bucket = "db-backups"
prefix = "backups"
region = "us-east-1"
```

S3 layout: `backups/{db_id}/{YYYY-MM-DD}/backup-{HHMMSS}.dump.zst`

## Commands

| Command | What |
|---------|------|
| `backup` / `daily` | backup one or all DBs |
| `restore --key …` | restore from S3 |
| `export` / `anonymize` | copy or anonymized copy |
| `retention` | monthly cleanup (preview; `-y` to skip confirm) |
| `schedule` | cron backup + retention + `:8080` health/metrics |
| `health` | readiness (DBs + S3) |
| `databases add\|remove\|list` | manage `db-toolchain.toml` |

Retention (separate cron, default monthly): keep all dailies this month, weekly last month, monthly older; drop after 12 months.

Anonymization uses `"db-toolchain".anonymize_columns` in Postgres (dev seeds: `users.name`, `users.email`, `orders.amount_cents`).

## Observability

Metrics on `:8080` (`/metrics`, `/health`, `/ready`). Local kind: Grafana `:30300`, Prometheus `:30909` (`admin`/`admin`). AWS demo: `kubectl port-forward` to `svc/grafana` and `svc/prometheus`.

## CI/CD

On push/PR to `main` (skips docs-only): **lint** → **build** (+ GHCR on main) → **scan** (Trivy) → **test** / **coverage** → **integration** (kind + smoke). **publish** is manual (`workflow_dispatch`).

## Deploy

**Local:** `./dev.sh wizard` (Postgres `:30433`, LocalStack `:30456`, DBs: shop, billing, analytics).

**Platform:** `terraform/prod` then `k8s/deploy/`. Rolling image:

```bash
export IMAGE=ghcr.io/your-org/idp-db-toolchain:<tag>
PUBLISH_TARGET=remote ./dev.sh ci-publish-deploy
```

**AWS demo:** `./dev.sh wizard-aws` (see `terraform/demo/`). Budget alert ~€20; run `./dev.sh aws-down` when done.

| Terraform | Use |
|-----------|-----|
| `demo/` | Ephemeral EKS + in-cluster stack |
| `prod/` | S3, IRSA, optional observability EC2 |
| `local/` | Optional LocalStack bootstrap |

Backups: `pg_dump -Fc` + zstd; restore with `pg_restore` (use target-major client for upgrades).
