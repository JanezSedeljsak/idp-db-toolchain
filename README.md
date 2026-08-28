# idp-db-backupper

PostgreSQL backup → zstd → S3. LocalStack on k8s for local dev.

```bash
uv sync
uv run python manage.py setup -y --force --seed
uv run python manage.py daily
uv run python manage.py list
```

## Commands

| Command | What |
|---------|------|
| `setup` | `.env` + k8s + migrate |
| `k8s-up` / `k8s-down` | start / stop cluster workloads |
| `migrate` | alembic upgrade head |
| `seed` | sample data |
| `backup` | dump + upload |
| `restore --key` | download + restore |
| `daily` | seed + backup |
| `list` | show backups |

Services expose **NodePort** `30433` (postgres) and `30456` (localstack) — no port-forward.

## Dev

```bash
uv run ruff check . && uv run ruff format .
uv run pytest
```
