from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Annotated

import typer
from croniter import croniter

from scripts import anonymize as anonymize_mod
from scripts import backup, k8s, metrics, notify, retention, s3, setup, status
from scripts import seed as seed_data
from scripts.config import Config, cfg_for_db, load_config
from scripts.database import session
from scripts.databases import resolve_cfg, resolve_targets
from scripts.jobs import job_run, list_jobs
from scripts.logging_config import setup_logging
from scripts.metrics_server import serve_metrics

app = typer.Typer(help="Multi-database PostgreSQL backup platform", no_args_is_help=True)
log = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"^(\d+)([dhm])$")


def _parse_duration(value: str):
    from datetime import timedelta

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


def _validate_db(db: str | None) -> str | None:
    return db


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
def databases() -> None:
    cfg = load_config()
    for target in cfg.databases:
        log.info("%s\t%s", target.id, target.database_url)


@app.command()
def seed(
    db: Annotated[str | None, typer.Option("--db")] = None,
    job: Annotated[str | None, typer.Option()] = None,
    count: Annotated[int, typer.Option()] = 50,
) -> None:
    cfg = load_config()
    for target in resolve_targets(cfg, db):
        with session(target.database_url) as s:
            seed_data.run(s, job=job, count=count)
        log.info("seed done: %s", target.id)


@app.command("backup")
def backup_cmd(
    db: Annotated[str | None, typer.Option("--db")] = None,
) -> None:
    cfg = load_config()
    for target in resolve_targets(cfg, db):
        db_cfg = cfg_for_db(cfg, target.id)
        try:
            with job_run("backup", database=target.id):
                key = backup.backup(db_cfg)
        except Exception as exc:
            notify.notify_failure(cfg, f"backup failed for {target.id}: {exc}")
            raise
        log.info("%s s3://%s/%s", target.id, cfg.s3_bucket, key)


@app.command()
def export(
    to_db: Annotated[str, typer.Option("--to-db")],
    db: Annotated[str | None, typer.Option("--db")] = None,
) -> None:
    cfg = load_config()
    source = resolve_cfg(cfg, db)
    with job_run("export", database=source.database_id, target=to_db):
        backup.export_to_target(source.database_url, to_db)
    log.info("exported %s -> %s", source.database_id, to_db)


@app.command()
def restore(
    key: Annotated[str, typer.Option("--key")],
    db: Annotated[str | None, typer.Option("--db")] = None,
    yes: Annotated[bool, typer.Option("-y", "--yes")] = False,
    list_keys: Annotated[bool, typer.Option("--list", help="List backups and exit")] = False,
) -> None:
    cfg = load_config()
    db_cfg = resolve_cfg(cfg, db)
    if list_keys:
        for obj in s3.list_backups(db_cfg):
            log.info("%s\t%s\t%s", obj["Key"], obj["Size"], obj["LastModified"])
        return
    _confirm(
        f"restore {key} into {db_cfg.database_id} ({db_cfg.database_url}). Continue",
        yes=yes,
    )
    with job_run("restore", database=db_cfg.database_id, key=key):
        backup.restore(db_cfg, key)
    log.info("restored %s into %s", key, db_cfg.database_id)


@app.command("verify")
def verify_cmd(
    key: Annotated[str, typer.Option("--key")],
    db: Annotated[str | None, typer.Option("--db")] = None,
) -> None:
    cfg = resolve_cfg(load_config(), db)
    with job_run("verify", database=cfg.database_id, key=key):
        ok = backup.verify(cfg, key)
    if ok:
        log.info("backup %s OK", key)
        return
    raise typer.Exit(code=1)


@app.command("list")
def list_cmd(
    db: Annotated[str | None, typer.Option("--db")] = None,
) -> None:
    cfg = load_config()
    targets = [cfg.require_database(db)] if db else cfg.databases
    found = False
    for target in targets:
        items = s3.list_backups(cfg_for_db(cfg, target.id))
        if not items:
            continue
        found = True
        for obj in items:
            log.info("%s\t%s\t%s\t%s", target.id, obj["Key"], obj["Size"], obj["LastModified"])
    if not found:
        log.info("no backups")


@app.command("prune")
def prune_cmd(
    older_than: Annotated[str, typer.Option("--older-than")],
    db: Annotated[str | None, typer.Option("--db")] = None,
    yes: Annotated[bool, typer.Option("-y", "--yes")] = False,
) -> None:
    cfg = load_config()
    delta = _parse_duration(older_than)
    keys: list[tuple[str, str]] = []
    for target in resolve_targets(cfg, db):
        for key in s3.prune_backups(cfg_for_db(cfg, target.id), delta):
            keys.append((target.id, key))
    if not keys:
        log.info("nothing to prune")
        return
    for db_id, key in keys:
        log.info("would delete %s %s", db_id, key)
    _confirm(f"delete {len(keys)} backup(s)", yes=yes)
    with job_run("prune", count=len(keys)):
        for db_id, key in keys:
            s3.delete_object(cfg, key)
            log.info("deleted %s %s", db_id, key)


@app.command()
def retention_cmd(
    db: Annotated[str | None, typer.Option("--db")] = None,
    yes: Annotated[bool, typer.Option("-y", "--yes")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Run even if not the 1st of month")
    ] = False,
) -> None:
    cfg = load_config()
    if not force and not retention.should_run_scheduled_retention():
        log.info("retention only runs on the 1st of each month (use --force to override)")
        return
    targets = resolve_targets(cfg, db)
    planned: list[tuple[str, list[str]]] = []
    for target in targets:
        db_cfg = cfg_for_db(cfg, target.id)
        month = retention.retention_target_month()
        in_month = [
            obj["Key"]
            for obj in s3.list_backups(db_cfg)
            if (day := s3.backup_date_from_key(obj["Key"])) is not None
            and retention.month_bounds(month)[0] <= day <= retention.month_bounds(month)[1]
        ]
        cutoff = retention.retention_expiry_cutoff()
        expired = [
            obj["Key"]
            for obj in s3.list_backups(db_cfg)
            if (day := s3.backup_date_from_key(obj["Key"])) is not None and day < cutoff
        ]
        collapse = in_month[1:] if len(in_month) > 1 else []
        keys = collapse + expired
        if keys:
            planned.append((target.id, keys))
    if not planned:
        log.info("nothing to delete")
        return
    for db_id, keys in planned:
        for key in keys:
            log.info("would delete %s %s", db_id, key)
    _confirm(f"delete {sum(len(k) for _, k in planned)} backup(s)", yes=yes)
    with job_run("retention"):
        for target in targets:
            result = retention.apply_retention(cfg, target.id)
            for key in result.deleted:
                log.info("deleted %s %s", target.id, key)


@app.command()
def anonymize(
    key: Annotated[str | None, typer.Option("--key")] = None,
    out: Annotated[str | None, typer.Option("--out")] = None,
    from_db: Annotated[bool, typer.Option("--from-db")] = False,
    db: Annotated[str | None, typer.Option("--db")] = None,
    to_db: Annotated[str | None, typer.Option("--to-db")] = None,
) -> None:
    cfg = load_config()
    if from_db:
        if not to_db:
            raise typer.BadParameter("--to-db is required with --from-db")
        source = resolve_cfg(cfg, db)
        with job_run("anonymize-db", database=source.database_id, target=to_db):
            updated = anonymize_mod.anonymize_database(cfg, source.database_id, to_db)
        log.info("anonymized %s -> %s (%s columns updated)", source.database_id, to_db, updated)
        return
    if not key or not out:
        raise typer.BadParameter("--key and --out are required")
    with job_run("anonymize-backup", source=key, dest=out):
        result = anonymize_mod.anonymize_backup(cfg, key, out)
    log.info("anonymized backup -> s3://%s/%s", cfg.s3_bucket, result)


def run_backup_cycle(cfg: Config) -> list[tuple[str, str]]:
    s3.ensure_bucket(cfg)
    keys: list[tuple[str, str]] = []
    for target in cfg.databases:
        db_cfg = cfg_for_db(cfg, target.id)
        with job_run("scheduled-backup", database=target.id):
            keys.append((target.id, backup.backup(db_cfg)))
    return keys


def run_observability_cycle(cfg: Config) -> None:
    for target in cfg.databases:
        db_cfg = cfg_for_db(cfg, target.id)
        with job_run("db-metrics", database=target.id):
            snapshot = metrics.persist_metrics(db_cfg)
            log.info(
                "%s metrics: size=%s bytes connections=%s",
                target.id,
                snapshot["database_size_bytes"],
                snapshot["connection_count"],
            )
        with job_run("slow-queries", database=target.id):
            slow = metrics.persist_slow_queries(db_cfg)
            if slow:
                log.warning("%s slow queries captured: %s", target.id, len(slow))


def run_retention_cycle(cfg: Config) -> None:
    if not retention.should_run_scheduled_retention():
        return
    with job_run("retention"):
        for target in cfg.databases:
            result = retention.apply_retention(cfg, target.id)
            if result.deleted:
                log.info(
                    "%s retention: collapsed=%s expired=%s",
                    target.id,
                    len(result.collapsed),
                    len(result.expired),
                )


@app.command()
def daily() -> None:
    cfg = load_config()
    try:
        keys = run_backup_cycle(cfg)
        run_observability_cycle(cfg)
        run_retention_cycle(cfg)
    except Exception as exc:
        notify.notify_failure(cfg, f"daily backup failed: {exc}")
        raise
    for db_id, key in keys:
        log.info("daily done %s: s3://%s/%s", db_id, cfg.s3_bucket, key)


@app.command()
def schedule(cron: Annotated[str, typer.Option()] = "0 2 * * *") -> None:
    cfg = load_config()
    failures = 0
    serve_metrics(cfg, port=cfg.metrics_port)
    log.info(
        "scheduler: %s databases=%s metrics :%s",
        cron,
        ",".join(d.id for d in cfg.databases),
        cfg.metrics_port,
    )
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
            "%s %s %s started=%s finished=%s error=%s details=%s",
            record.id,
            record.name,
            record.status,
            record.started_at,
            record.finished_at,
            record.error,
            json.dumps(record.details) if record.details else None,
        )


@app.command()
def metrics_cmd(
    db: Annotated[str | None, typer.Option("--db")] = None,
) -> None:
    cfg = load_config()
    for target in resolve_targets(cfg, db):
        db_cfg = cfg_for_db(cfg, target.id)
        snapshot = metrics.persist_metrics(db_cfg)
        log.info("%s metrics:", target.id)
        for key, value in snapshot.items():
            log.info("  %s: %s", key, value)


@app.command()
def status_cmd(
    db: Annotated[str | None, typer.Option("--db")] = None,
) -> None:
    cfg = load_config()
    for target in resolve_targets(cfg, db):
        st = status.load_status(target.id)
        log.info("%s status:", target.id)
        for key in status.BackupStatus.__dataclass_fields__:
            log.info("  %s: %s", key, getattr(st, key))
