from datetime import date

from scripts import retention, s3


def test_backup_key_layout() -> None:
    key = "backups/shop/2026-01-15/backup-120000.dump.zst"
    parsed = s3.parse_backup_key(key)
    assert parsed is not None
    assert parsed["db"] == "shop"
    assert s3.backup_date_from_key(key) == date(2026, 1, 15)


def test_retention_target_month() -> None:
    assert retention.retention_target_month(date(2026, 3, 1)) == date(2026, 1, 1)
    assert retention.retention_expiry_cutoff(date(2026, 3, 1)) == date(2025, 3, 1)


def test_should_run_scheduled_retention() -> None:
    assert retention.should_run_scheduled_retention(date(2026, 3, 1)) is True
    assert retention.should_run_scheduled_retention(date(2026, 3, 2)) is False
