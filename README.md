# idp-db-backupper

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

Primary config lives in **`backupper.toml`** (schedules, databases, S3 settings, metrics). Load order:

1. `backupper.toml` — from `BACKUPPER_CONFIG`, `./backupper.toml`, or the bundled default
2. `.env` — optional secrets and overrides (`AWS_*`, `S3_BUCKET`, `DATABASES`, …)

Dev defaults are in the committed `backupper.toml`. Copy and edit for other environments, or mount a ConfigMap in k8s (`k8s/backupper-config.yaml`).

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
| `databases add` | wizard: register a new database in `backupper.toml` |
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

`schedule` runs backup and retention independently — cron expressions live in `backupper.toml` under `[schedule]`. Manual `retention` still previews deletes and asks for confirmation (use `-y` to skip the prompt).

```bash
manage.py retention          # preview + confirm
manage.py schedule           # uses [schedule] from backupper.toml
```

## Anonymization

Each database can register columns in `backupper.anonymize_columns`. Postgres functions `backupper.anonymize_text()` and `backupper.anonymize_integer()` transform values; foreign keys are left alone.

Default registry (dev): `users.name`, `users.email`, `orders.amount_cents`.

Exports with `--from-db` only anonymize columns listed in the registry for that database.

## Observability

- Job log: `$BACKUPPER_DATA_DIR/.backupper-jobs.jsonl`
- Per-DB status: `.backupper-status-{db_id}.json`
- Prometheus metrics: `backupper_*{database="shop"}` on `:8080/metrics`

### Grafana (dev stack only)

The full `k8s/` stack includes **Prometheus** + **Grafana** (not deployed via `k8s/deploy/`):

| Service | URL | Notes |
|---------|-----|--------|
| Grafana | http://localhost:30300 | `admin` / `admin` — dashboard auto-provisioned |
| Prometheus | http://localhost:30909 | scrapes `backupper:8080/metrics` every 30s |

Import `k8s/grafana-dashboard.json` manually if you run backupper outside this stack.

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
export IMAGE=ghcr.io/your-org/idp-db-backupper:abc123
export KUBECONFIG=~/.kube/platform
PUBLISH_TARGET=remote ./dev.sh ci-publish-deploy
```

Create `backupper-env` secret (AWS keys) and `backupper-config` ConfigMap (or mount your `backupper.toml`). Workload manifests: `k8s/deploy/`.

## Dev

```bash
./dev.sh wizard
./dev.sh test
./dev.sh test-integration
```

Postgres `:30433`, LocalStack `:30456`. Three demo databases seeded via wizard.

## Terraform (HCL)

The `terraform/` directory is **local dev only**. The `.tf` files are written in **HCL** (HashiCorp Configuration Language) — a small declarative language for describing infrastructure.

What it does here:

- Creates the **LocalStack S3 bucket** (`db-backups`) and enables versioning
- Creates a minimal **IAM user + policy** for put/get/list/delete on that bucket
- Points the AWS provider at LocalStack (`localhost:30456`), not real AWS

Why it exists:

- Optional bootstrap if you want S3/IAM created outside the app (`manage.py setup` also calls `ensure_bucket` directly)
- Documents the **intended S3 permissions** for production IAM policies (copy the policy shape into your cloud account)
- Keeps cloud-shaped config in version control without touching the backupper runtime

It is **not** part of the k8s deploy path. Do not `terraform apply` against a real AWS account without changing provider, credentials, and remote state. Production buckets and IAM are owned by the platform team.

```bash
cd terraform
terraform init
terraform apply   # LocalStack only
```

## Backup format & Postgres versions

Backups use **`pg_dump -Fc`** (PostgreSQL custom archive), then **zstd** compression. Restore uses **`pg_restore`** on the target cluster.

### Is plain SQL (ANSI-style text) worth it?

There is no true Postgres-agnostic “ANSI dump”. In practice you choose between:

| Format | Tooling | Portability | Size / speed |
|--------|---------|-------------|--------------|
| **Custom `-Fc`** (current) | `pg_restore` | Good across versions when you use **`pg_restore` from the target (newer) major** | Best |
| **Plain SQL `-Fp`** | `psql -f` | Human-readable; still Postgres-specific DDL/DML; slowest, largest | Worst |

**Custom format is the right default** for this IDP: smaller over the wire, faster, and PostgreSQL explicitly supports logical dumps across major versions (e.g. 12 → 19) as long as you restore with a client **at least as new** as the target server.

Plain SQL is useful as an **escape hatch** for odd upgrades, manual inspection, or importing into non-Postgres tools — not as the daily backup format. If we add it later, it would be a separate export mode (`export --format plain`), not a replacement for scheduled backups.

### Upgrade path (pg12 → pg19)

1. **Logical dump/restore** (what this tool does): `pg_dump` on old → `pg_restore` / `psql` on new. Supported for many major jumps; test on a copy first.
2. **`pg_upgrade`**: in-place cluster upgrade, faster for huge DBs, not what backupper orchestrates.
3. **Avoid** the hand-rolled SQL dumper in `scripts/db.py` — it is for small integration tests only and will mishandle real types.

Operational rule: run **`pg_dump` with the source major’s client**, **`pg_restore` with the target major’s client** (our Docker image should ship both or match the oldest source you still restore from).

## Future ideas

- Backup verification reports in S3
- Replication lag / standby health per database
- Scheduled anonymized exports to a staging bucket
- Per-tenant retention overrides
