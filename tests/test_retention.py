from datetime import date, datetime
from pathlib import Path

from backup import retention
from backup.retention import pick_monthly_keeper, pick_weekly_keepers, plan_retention
from config import Config, DatabaseTarget, cfg_for_db
from storage import s3


def _obj(key: str, day: date) -> dict:
    return {"Key": key, "LastModified": datetime.combine(day, datetime.min.time())}


def test_backup_key_layout() -> None:
    key = "backups/shop/2026-01-15/backup-120000.dump.zst"
    parsed = s3.parse_backup_key(key)
    assert parsed is not None
    assert parsed["db"] == "shop"
    assert s3.backup_date_from_key(key) == date(2026, 1, 15)


def test_retention_target_month() -> None:
    assert retention.retention_target_month(date(2026, 3, 1)) == date(2026, 1, 1)
    assert retention.last_month_start(date(2026, 3, 1)) == date(2026, 2, 1)
    assert retention.retention_expiry_cutoff(date(2026, 3, 1)) == date(2025, 3, 1)


def test_pick_weekly_keepers() -> None:
    objs = [
        _obj("backups/shop/2026-01-01/backup-010000.dump.zst", date(2026, 1, 1)),
        _obj("backups/shop/2026-01-02/backup-010000.dump.zst", date(2026, 1, 2)),
        _obj("backups/shop/2026-01-08/backup-010000.dump.zst", date(2026, 1, 8)),
    ]
    keepers = pick_weekly_keepers(objs)
    assert len(keepers) == 2
    assert {obj["Key"] for obj in keepers} == {
        "backups/shop/2026-01-02/backup-010000.dump.zst",
        "backups/shop/2026-01-08/backup-010000.dump.zst",
    }


def test_pick_monthly_keeper_prefers_last_week() -> None:
    month = date(2026, 1, 1)
    early = _obj("backups/shop/2026-01-05/backup-010000.dump.zst", date(2026, 1, 5))
    late = _obj("backups/shop/2026-01-28/backup-010000.dump.zst", date(2026, 1, 28))
    keeper = pick_monthly_keeper([early, late], month)
    assert keeper["Key"] == "backups/shop/2026-01-28/backup-010000.dump.zst"


def test_plan_retention_weekly_and_monthly(monkeypatch) -> None:
    cfg = Config(
        databases=[DatabaseTarget(id="shop", database_url="postgres://localhost/shop")],
        database_id="shop",
        database_url="postgres://localhost/shop",
        s3_bucket="b",
        s3_prefix="backups",
        aws_region="us-east-1",
        aws_endpoint="http://localhost:4566",
        aws_access_key_id="k",
        aws_secret_access_key="s",
        app_env="dev",
        zstd_level=3,
        notify_webhook_url="",
        max_schedule_failures=5,
        slow_query_ms=5000,
        metrics_port=8080,
        anonymize_salt="x",
        backup_cron="0 2 * * *",
        retention_cron="0 3 1 * *",
        config_path=Path("backupper.toml"),
    )
    db_cfg = cfg_for_db(cfg, "shop")
    today = date(2026, 3, 1)

    backups = [
        _obj("backups/shop/2026-01-10/backup-010000.dump.zst", date(2026, 1, 10)),
        _obj("backups/shop/2026-01-28/backup-010000.dump.zst", date(2026, 1, 28)),
        _obj("backups/shop/2026-02-03/backup-010000.dump.zst", date(2026, 2, 3)),
        _obj("backups/shop/2026-02-05/backup-020000.dump.zst", date(2026, 2, 5)),
        _obj("backups/shop/2026-02-10/backup-010000.dump.zst", date(2026, 2, 10)),
        _obj("backups/shop/2026-03-02/backup-010000.dump.zst", date(2026, 3, 2)),
    ]

    monkeypatch.setattr(s3, "list_backups", lambda _cfg: backups)
    plan = plan_retention(db_cfg, today=today)

    assert "backups/shop/2026-01-10/backup-010000.dump.zst" in plan.monthly_collapsed
    assert "backups/shop/2026-01-28/backup-010000.dump.zst" not in plan.to_delete
    assert "backups/shop/2026-02-03/backup-010000.dump.zst" in plan.weekly_collapsed
    assert "backups/shop/2026-02-05/backup-020000.dump.zst" not in plan.to_delete
    assert "backups/shop/2026-02-10/backup-010000.dump.zst" not in plan.to_delete
    assert "backups/shop/2026-03-02/backup-010000.dump.zst" not in plan.to_delete
