from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated

import typer
from croniter import croniter

from scripts import backup, k8s, s3, setup
from scripts import seed as seed_data
from scripts.config import load_config
from scripts.database import migrate, session

app = typer.Typer(help="PostgreSQL backup → zstd → S3", no_args_is_help=True)


@app.command("setup")
def setup_cmd(
    yes: Annotated[bool, typer.Option("-y", "--yes")] = False,
    force: Annotated[bool, typer.Option()] = False,
    skip_k8s: Annotated[bool, typer.Option()] = False,
    with_seed: Annotated[bool, typer.Option("--seed")] = False,
) -> None:
    """Write .env, start k8s, migrate, optional seed."""
    setup.run(yes=yes, force=force, skip_k8s=skip_k8s, do_seed=with_seed)


@app.command("k8s-up")
def k8s_up() -> None:
    """Apply k8s manifests and wait for pods."""
    k8s.up()
    print("k8s ready (postgres :30433, localstack :30456)")


@app.command("k8s-down")
def k8s_down() -> None:
    """Delete k8s resources."""
    k8s.down()


@app.command("migrate")
def migrate_cmd() -> None:
    """Alembic upgrade head."""
    migrate()
    print("migrated")


@app.command()
def seed(
    job: Annotated[str | None, typer.Option()] = None,
    count: Annotated[int, typer.Option()] = 50,
) -> None:
    """Insert sample data."""
    cfg = load_config()
    migrate()
    with session(cfg.database_url) as s:
        seed_data.run(s, job=job, count=count)
    print("seed done")


@app.command("backup")
def backup_cmd() -> None:
    """Dump, compress, upload to S3."""
    cfg = load_config()
    key = backup.backup(cfg)
    print(f"s3://{cfg.s3_bucket}/{key}")


@app.command()
def restore(key: Annotated[str, typer.Option("--key")]) -> None:
    """Restore from S3 backup."""
    cfg = load_config()
    backup.restore(cfg, key)
    print(f"restored {key}")


@app.command("list")
def list_cmd() -> None:
    """List S3 backups."""
    cfg = load_config()
    items = s3.list_backups(cfg)
    if not items:
        print("no backups")
        return
    for obj in items:
        print(f"{obj['Key']}\t{obj['Size']}\t{obj['LastModified']}")


@app.command()
def daily() -> None:
    """Seed + backup."""
    cfg = load_config()
    migrate()
    s3.ensure_bucket(cfg)
    with session(cfg.database_url) as s:
        seed_data.run(s)
    key = backup.backup(cfg)
    print(f"daily done: s3://{cfg.s3_bucket}/{key}")


@app.command()
def schedule(cron: Annotated[str, typer.Option()] = "0 2 * * *") -> None:
    """Run daily on a cron schedule."""
    print(f"scheduler: {cron} (Ctrl+C to stop)")
    while True:
        nxt = croniter(cron, datetime.now()).get_next(datetime)
        time.sleep(max(0, (nxt - datetime.now()).total_seconds()))
        try:
            daily()
        except Exception as exc:
            print(f"failed: {exc}")
