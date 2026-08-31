# idp-db-toolchain

Multi-database PostgreSQL management platform: one k8s service, one S3 bucket, compressed backups for every database you register.

```bash
./dev.sh wizard
./dev.sh test
```

## What this is

A single **IDP service** that connects to many production Postgres instances (or many databases on one cluster), backs them all up to **one S3 bucket**, and gives you exports, anonymized copies, metrics, and retention — without touching schema migrations.

| In scope | Out of scope |
|----------|--------------|
| Multi-DB backup → zstd → S3 (`backups/{db_id}/…`) | Alembic / schema migrations |
| Scheduled backups for all registered databases | Mutating prod DB on deploy |
| Export / import between databases | Bundled Postgres in production |
| Postgres-driven anonymization registry | Heavy PII pipelines |
| Monthly retention (safe, conservative) | Aggressive auto-delete |
| Job log, metrics, slow queries, Grafana | Application business logic |

**Publish / CI-CD only rolls out the workload image** — no migrations, seeds, or restores on deploy.

## Configure databases

Primary config lives in **`db-toolchain.toml`** (schedules, databases, S3 settings, metrics). Load order:

1. `db-toolchain.toml` — from `DB_TOOLCHAIN_CONFIG`, `./db-toolchain.toml`, or the bundled default
2. `.env` — optional secrets and overrides (`AWS_*`, `S3_BUCKET`, `DATABASES`, …)

Dev defaults are in the committed `db-toolchain.toml`. Copy and edit for other environments, or mount a ConfigMap in k8s (`k8s/db-toolchain-config.yaml`).

```toml
app_env = "dev"

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

`.env` is for secrets only in prod:

```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
# optional: DATABASES='[{"id":"shop","url":"..."}]'
```

S3 key layout: `backups/{db_id}/{YYYY-MM-DD}/backup-{HHMMSS}.dump.zst`

## Commands

| Command | What |
|---------|------|
| `databases list` | list registered targets |
| `databases add` | wizard: register a new database in `db-toolchain.toml` |
| `databases remove` | wizard: unregister (+ optional S3 backup prune) |
| `backup [--db shop]` | backup one or all databases |
| `export --db shop --to-db <url>` | pg_dump prod → restore elsewhere |
| `restore --db shop --key …` | restore from S3 |
| `anonymize --from-db shop --to-db <url>` | export + apply registry anonymization |
| `retention [--db shop]` | monthly cleanup (see below) |
| `prune --older-than 30d` | **manual** delete — always confirms |
| `daily` | backup all + metrics |
| `health` | readiness check (all DBs + S3) |
| `schedule` | backup cron + retention cron + HTTP health on `:8080` |

## Retention policy

Retention runs on its **own cron** (default `0 3 1 * *` — 03:00 on the 1st of each month), separate from daily backups. Configure with `RETENTION_CRON`.

| Age | What we keep |
|-----|----------------|
| **Current month** | All daily backups |
| **Last month** | One backup per ISO week |
| **Older than 2 months** | One backup per calendar month (prefer last week of that month) |
| **Older than 12 months** | Deleted |

`schedule` runs backup and retention independently — cron expressions live in `db-toolchain.toml` under `[schedule]`. Manual `retention` still previews deletes and asks for confirmation (use `-y` to skip the prompt).

```bash
manage.py retention          # preview + confirm
manage.py schedule           # uses [schedule] from db-toolchain.toml
```

## Anonymization

Each database can register columns in `"db-toolchain".anonymize_columns`. Postgres functions `"db-toolchain".anonymize_text()` and `"db-toolchain".anonymize_integer()` transform values; foreign keys are left alone.

Default registry (dev): `users.name`, `users.email`, `orders.amount_cents`.

Exports with `--from-db` only anonymize columns listed in the registry for that database.

## Observability

- Job log: `$DB_TOOLCHAIN_DATA_DIR/.db-toolchain-jobs.jsonl`
- Per-DB status: `.db-toolchain-status-{db_id}.json`
- Prometheus metrics: `db_toolchain_*{database="shop"}` on `:8080/metrics`

### Grafana (dev stack only)

The full `k8s/` stack includes **Prometheus** + **Grafana** (not deployed via `k8s/deploy/`):

| Service | URL | Notes |
|---------|-----|--------|
| Grafana | http://localhost:30300 | `admin` / `admin` — dashboard auto-provisioned |
| Prometheus | http://localhost:30909 | scrapes `db-toolchain:8080/metrics`; **alerts** at `/alerts` |
| Alert rules | `k8s/prometheus-rules.yaml` | stale backup, failures, `/ready`, S3 errors |

Import `k8s/grafana-dashboard.json` manually if you run db-toolchain outside this stack.

### Health checks

HTTP on the metrics port (default `8080`):

| Path | Use |
|------|-----|
| `/health` | Liveness — process is up |
| `/ready` | Readiness — all configured databases + S3 bucket |
| `/health/full` | JSON detail (same checks as `/ready`) |
| `/metrics` | Prometheus scrape |

```bash
manage.py health              # readiness (all DBs + S3)
manage.py health --liveness   # process only
```

k8s uses `startupProbe` + `livenessProbe` → `/health`, `readinessProbe` → `/ready`.

## Platform deploy

```bash
export IMAGE=ghcr.io/your-org/idp-db-toolchain:abc123
export KUBECONFIG=~/.kube/platform
PUBLISH_TARGET=remote ./dev.sh ci-publish-deploy
```

Create the `db-toolchain-secrets` Secret (database URLs via `DATABASES` JSON) and IRSA ServiceAccount — see `k8s/deploy/README.md`. Workload manifests: `k8s/deploy/`.

## Dev

```bash
./dev.sh wizard
./dev.sh test
./dev.sh test-integration
```

Postgres `:30433`, LocalStack `:30456`. Three demo databases seeded via wizard.

## Terraform

| Path | When to use |
|------|-------------|
| `terraform/local/` | Optional LocalStack S3/IAM bootstrap — **not required** for `./dev.sh wizard` |
| `terraform/prod/` | **Production AWS** — S3 bucket, EKS IRSA, Prometheus + Grafana on EC2 |

Production:

```bash
cd terraform/prod
cp terraform.tfvars.example terraform.tfvars   # eks_cluster_name, admin_cidr, metrics target
terraform init && terraform apply
```

Then patch `k8s/deploy/serviceaccount.yaml` with `db_toolchain_irsa_role_arn` and deploy the workload. See [`terraform/prod/README.md`](terraform/prod/README.md).

## Backup format

Backups use **`pg_dump -Fc`** (PostgreSQL custom archive), compressed with **zstd**. Restore with **`pg_restore`** on the target cluster.

For major-version moves (e.g. pg12 → pg19), use logical dump/restore: **`pg_dump` with the source major’s client**, **`pg_restore` with the target major’s client** (the Docker image should include clients for the versions you still restore from).
