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

Set `DATABASES` as JSON (all backups land in the same `S3_BUCKET`):

```json
[
  {"id": "shop", "url": "postgres://user:pass@host:5432/shop?sslmode=require"},
  {"id": "billing", "url": "postgres://user:pass@host:5432/billing?sslmode=require"},
  {"id": "analytics", "url": "postgres://user:pass@host:5432/analytics?sslmode=require"}
]
```

Local demo defaults to **shop**, **billing**, and **analytics** on the kind Postgres NodePort.

S3 key layout: `backups/{db_id}/{YYYY-MM-DD}/backup-{HHMMSS}.dump.zst`

## Commands

| Command | What |
|---------|------|
| `databases` | list configured targets |
| `backup [--db shop]` | backup one or all databases |
| `export --db shop --to-db <url>` | pg_dump prod → restore elsewhere |
| `restore --db shop --key …` | restore from S3 |
| `anonymize --from-db shop --to-db <url>` | export + apply registry anonymization |
| `retention [--db shop]` | monthly cleanup (see below) |
| `prune --older-than 30d` | **manual** delete — always confirms |
| `daily` | backup all + metrics + retention (on 1st of month) |
| `schedule` | cron loop + Prometheus `:8080/metrics` |

## Retention policy

Conservative by design — nothing deleted without the retention job:

- **Last ~2 months**: all daily backups kept
- **On the 1st of each month**: process backups from **2 months ago** — if multiple exist that month, keep the newest, delete the rest
- **Older than 12 months**: all backups deleted

Run manually: `manage.py retention --force` (dry-run preview still asks for confirmation before delete).

## Anonymization

Each database can register columns in `backupper.anonymize_columns`. Postgres functions `backupper.anonymize_text()` and `backupper.anonymize_integer()` transform values; foreign keys are left alone.

Default registry (dev): `users.name`, `users.email`, `orders.amount_cents`.

Exports with `--from-db` only anonymize columns listed in the registry for that database.

## Observability

- Job log: `$BACKUPPER_DATA_DIR/.backupper-jobs.jsonl`
- Per-DB status: `.backupper-status-{db_id}.json`
- Prometheus: `backupper_*{database="shop"}` — import `k8s/grafana-dashboard.json`

## Platform deploy

```bash
export IMAGE=ghcr.io/your-org/idp-db-backupper:abc123
export KUBECONFIG=~/.kube/platform
PUBLISH_TARGET=remote ./dev.sh ci-publish-deploy
```

Create `backupper-env` secret with `DATABASES` JSON + AWS credentials. Workload manifests: `k8s/deploy/`.

## Dev

```bash
./dev.sh wizard
./dev.sh test
./dev.sh test-integration
```

Postgres `:30433`, LocalStack `:30456`. Three demo databases seeded via wizard.

## Future ideas

- Backup verification reports in S3
- Replication lag / standby health per database
- Scheduled anonymized exports to a staging bucket
- Per-tenant retention overrides
