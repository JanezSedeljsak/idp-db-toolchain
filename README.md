# idp-db-backupper

Production database platform for backups, exports, anonymized test copies, and observability. Connects to **external** Postgres in the cloud — schema and migrations live in the main application, not here.

```bash
./dev.sh wizard
./dev.sh test
```

## What this is

| In scope | Out of scope |
|----------|--------------|
| Scheduled `pg_dump` → zstd → S3 | Alembic / schema migrations |
| Restore, verify, prune backups | Mutating prod DB on deploy |
| DB export / import (`export_to_target`) | Bundled Postgres in production |
| Simple anonymization (swap user names/ids) | Heavy PII redaction pipelines |
| Job run log (JSONL), DB metrics, slow queries | Application business logic |
| Prometheus `/metrics` on port 8080 | |

**Publish / CI-CD only rolls out the workload image.** It never runs migrations, seeds, or restores against production.

## Commands

| Command | What |
|---------|------|
| `setup` | `.env` + local k8s + dev schema + optional seed |
| `k8s-up` / `k8s-down` | start / stop local cluster workloads |
| `seed` | sample data (local dev only) |
| `backup` | pg_dump + zstd + upload |
| `restore --key` | download + pg_restore (with confirmation) |
| `verify --key` | checksum-verify a backup |
| `prune --older-than 30d` | delete old backups (with confirmation) |
| `anonymize --key --out` | scrub a backup artifact |
| `anonymize --from-db --to-db` | copy DB with swapped user names/ids |
| `daily` | backup + metrics + slow-query capture |
| `jobs` | show recent job runs from JSONL log |
| `metrics` | snapshot DB size, connections, table estimates |
| `list` | show backups in S3 |
| `status` | last backup success/failure |
| `schedule` | cron loop for `daily` + metrics HTTP server |

Local dev uses kind + bundled Postgres/LocalStack (`k8s/`). Production uses `k8s/deploy/` with platform-managed secrets and external DB/S3.

## Observability

- **Job log**: `$BACKUPPER_DATA_DIR/.backupper-jobs.jsonl` — every backup, prune, anonymize, etc.
- **Metrics snapshot**: `.backupper-metrics.json` (size, connections, table row estimates)
- **Slow queries**: `.backupper-slow-queries.jsonl` from `pg_stat_activity` (+ `pg_stat_statements` when available)
- **Prometheus**: scrape `http://backupper:8080/metrics` — import `k8s/grafana-dashboard.json`
- **Status**: `.backupper-status.json` + optional `NOTIFY_WEBHOOK_URL` on failure

Tune slow-query threshold with `SLOW_QUERY_MS` (default 5000).

## Platform deploy

- CI builds and pushes `ghcr.io/<repo>:<sha>` on merges to `main`
- Create `backupper-env` secret in the target namespace (see `k8s/backupper-secret.yaml`)
- Manual **Publish** workflow: `kubectl apply -k k8s/deploy` → rolling image update → optional smoke `backup` Job
- No database preparation runs on deploy

```bash
export IMAGE=ghcr.io/your-org/idp-db-backupper:abc123
export KUBECONFIG=~/.kube/platform
PUBLISH_TARGET=remote ./dev.sh ci-publish-deploy
```

## Dev

```bash
./dev.sh wizard
./dev.sh lint
./dev.sh test
./dev.sh test-integration   # export→import compare + backup roundtrip
./dev.sh publish            # kind: full stack + rolling deploy
```

Postgres and LocalStack expose NodePorts **30433** / **30456**. Dev schema is applied via `k8s/dev-schema.sql` (postgres init + `apply_dev_schema`).

CI: `./dev.sh ci-lint` → `ci-build` → `ci-test` → `ci-integration` (on PR/main).

## Future ideas

- Backup verification reports stored in S3
- Replication lag / standby health checks
- Point-in-time recovery orchestration
- Scheduled anonymized exports to a staging bucket
- Connection pool saturation alerts
- Index bloat / vacuum stats panels in Grafana

## Terraform

`terraform/` is LocalStack-only for the dev S3 bucket. Not for real AWS accounts as-is.

## Production safety

Set `APP_ENV=prod` with real `DATABASE_URL` and AWS credentials. The app refuses dev defaults in prod mode.
