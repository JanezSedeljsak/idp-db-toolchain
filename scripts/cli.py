from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Annotated

import typer
from croniter import croniter

from scripts import anonymize as anonymize_mod
from scripts import backup, k8s, metrics, notify, s3, setup, status
from scripts import seed as seed_data
from scripts.config import Config, load_config
from scripts.database import session
from scripts.jobs import job_run, list_jobs
from scripts.logging_config import setup_logging
from scripts.metrics_server import serve_metrics

app = typer.Typer(help="PostgreSQL backup → zstd → S3", no_args_is_help=True)
log = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"^(\d+)([dhm])$")


def _parse_duration(value: str) -> timedelta:
    match = _DURATION_RE.match(value.strip().lower())
    if not match:
        raise typer.BadParameter("use e.g. 30d, 12h, 90m")
    amount, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        return timedelta(days=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(minutes=amount)


def _confirm(message: str, *, yes: bool) -> None:
    if yes:
        return
    answer = typer.prompt(f"{message} [y/N]", default="n")
    if answer.strip().lower() not in ("y", "yes"):
        raise typer.Abort()


@app.callback()
def main(
    log_level: Annotated[str, typer.Option("--log-level", envvar="LOG_LEVEL")] = "INFO",
) -> None:
    setup_logging(log_level)


@app.command("setup")
def setup_cmd(
    yes: Annotated[bool, typer.Option("-y", "--yes")] = False,
    force: Annotated[bool, typer.Option()] = False,
    skip_k8s: Annotated[bool, typer.Option()] = False,
    with_seed: Annotated[bool, typer.Option("--seed")] = False,
) -> None:
    setup.run(yes=yes, force=force, skip_k8s=skip_k8s, do_seed=with_seed)


@app.command("k8s-up")
def k8s_up(
    build: Annotated[
        bool, typer.Option("--build", help="Build and load Docker image first")
    ] = False,
) -> None:
    k8s.up(build_image_first=build)
    log.info("k8s ready (postgres :30433, localstack :30456)")


@app.command("k8s-down")
def k8s_down() -> None:
    k8s.down()


@app.command()
def seed(
    job: Annotated[str | None, typer.Option()] = None,
    count: Annotated[int, typer.Option()] = 50,
) -> None:
    cfg = load_config()
    with session(cfg.database_url) as s:
        seed_data.run(s, job=job, count=count)
    log.info("seed done")


@app.command("backup")
def backup_cmd() -> None:
    cfg = load_config()
    try:
        with job_run("backup"):
            key = backup.backup(cfg)
    except Exception as exc:
        notify.notify_failure(cfg, f"backup failed: {exc}")
        raise
    log.info("s3://%s/%s", cfg.s3_bucket, key)


@app.command()
def restore(
    key: Annotated[str, typer.Option("--key")],
    yes: Annotated[bool, typer.Option("-y", "--yes")] = False,
    list_keys: Annotated[bool, typer.Option("--list", help="List backups and exit")] = False,
) -> None:
    cfg = load_config()
    if list_keys:
        for obj in s3.list_backups(cfg):
            log.info("%s\t%s\t%s", obj["Key"], obj["Size"], obj["LastModified"])
        return
    _confirm(
        f"restore {key} into {cfg.database_url} (overwrites data). Continue",
        yes=yes,
    )
    with job_run("restore", key=key):
        backup.restore(cfg, key)
    log.info("restored %s", key)


@app.command("verify")
def verify_cmd(key: Annotated[str, typer.Option("--key")]) -> None:
    cfg = load_config()
    with job_run("verify", key=key):
        ok = backup.verify(cfg, key)
    if ok:
        log.info("backup %s OK", key)
        return
    raise typer.Exit(code=1)


@app.command("list")
def list_cmd() -> None:
    cfg = load_config()
    items = s3.list_backups(cfg)
    if not items:
        log.info("no backups")
        return
    for obj in items:
        log.info("%s\t%s\t%s", obj["Key"], obj["Size"], obj["LastModified"])


@app.command("prune")
def prune_cmd(
    older_than: Annotated[str, typer.Option("--older-than")],
    yes: Annotated[bool, typer.Option("-y", "--yes")] = False,
) -> None:
    cfg = load_config()
    keys = s3.prune_backups(cfg, _parse_duration(older_than))
    if not keys:
        log.info("nothing to prune")
        return
    for key in keys:
        log.info("would delete %s", key)
    _confirm(f"delete {len(keys)} backup(s)", yes=yes)
    with job_run("prune", count=len(keys)):
        for key in keys:
            s3.delete_object(cfg, key)
            log.info("deleted %s", key)


@app.command()
def anonymize(
    key: Annotated[str | None, typer.Option("--key")] = None,
    out: Annotated[str | None, typer.Option("--out")] = None,
    from_db: Annotated[bool, typer.Option("--from-db")] = False,
    to_db: Annotated[str | None, typer.Option("--to-db")] = None,
) -> None:
    cfg = load_config()
    if from_db:
        if not to_db:
            raise typer.BadParameter("--to-db is required with --from-db")
        with job_run("anonymize-db", target=to_db):
            anonymize_mod.anonymize_database(cfg, cfg.database_url, to_db)
        log.info("anonymized database -> %s", to_db)
        return
    if not key or not out:
        raise typer.BadParameter("--key and --out are required")
    with job_run("anonymize-backup", source=key, dest=out):
        result = anonymize_mod.anonymize_backup(cfg, key, out)
    log.info("anonymized backup -> s3://%s/%s", cfg.s3_bucket, result)


def run_backup_cycle(cfg: Config) -> str:
    s3.ensure_bucket(cfg)
    with job_run("scheduled-backup"):
        return backup.backup(cfg)


def run_observability_cycle(cfg) -> None:
    with job_run("db-metrics"):
        snapshot = metrics.persist_metrics(cfg)
        log.info(
            "metrics: size=%s bytes connections=%s",
            snapshot["database_size_bytes"],
            snapshot["connection_count"],
        )
    with job_run("slow-queries"):
        slow = metrics.persist_slow_queries(cfg)
        if slow:
            log.warning("slow queries captured: %s", len(slow))


@app.command()
def daily() -> None:
    cfg = load_config()
    try:
        key = run_backup_cycle(cfg)
        run_observability_cycle(cfg)
    except Exception as exc:
        notify.notify_failure(cfg, f"daily backup failed: {exc}")
        raise
    log.info("daily done: s3://%s/%s", cfg.s3_bucket, key)


@app.command()
def schedule(cron: Annotated[str, typer.Option()] = "0 2 * * *") -> None:
    cfg = load_config()
    failures = 0
    serve_metrics(cfg, port=cfg.metrics_port)
    log.info("scheduler: %s metrics :%s (Ctrl+C to stop)", cron, cfg.metrics_port)
    while True:
        nxt = croniter(cron, datetime.now()).get_next(datetime)
        time.sleep(max(0, (nxt - datetime.now()).total_seconds()))
        try:
            daily()
            failures = 0
        except Exception as exc:
            failures += 1
            log.exception("scheduled backup failed (%s/%s)", failures, cfg.max_schedule_failures)
            notify.notify_failure(cfg, f"scheduled backup failed: {exc}")
            if failures >= cfg.max_schedule_failures:
                raise SystemExit(1) from exc


@app.command()
def jobs(
    limit: Annotated[int, typer.Option("--limit")] = 20,
) -> None:
    for record in reversed(list_jobs(limit=limit)):
        log.info(
            "%s %s %s started=%s finished=%s error=%s",
            record.id,
            record.name,
            record.status,
            record.started_at,
            record.finished_at,
            record.error,
        )


@app.command()
def metrics_cmd() -> None:
    cfg = load_config()
    snapshot = metrics.persist_metrics(cfg)
    for key, value in snapshot.items():
        log.info("%s: %s", key, value)


@app.command()
def status_cmd() -> None:
    st = status.load_status()
    for key in status.BackupStatus.__dataclass_fields__:
        log.info("%s: %s", key, getattr(st, key))
