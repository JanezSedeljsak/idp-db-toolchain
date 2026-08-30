from pathlib import Path

import pytest

from backup import core as backup
from config import Config, DatabaseTarget


def _cfg() -> Config:
    return Config(
        databases=[DatabaseTarget(id="shop", database_url="postgres://localhost/shop")],
        database_id="shop",
        database_url="postgres://localhost/shop",
        s3_bucket="db-backups",
        s3_prefix="backups",
        aws_region="us-east-1",
        aws_endpoint="http://localhost:4566",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        app_env="dev",
        zstd_level=3,
        notify_webhook_url="",
        max_schedule_failures=5,
        slow_query_ms=5000,
        metrics_port=8080,
        anonymize_salt="backupper",
        backup_cron="0 2 * * *",
        retention_cron="0 3 1 * *",
        config_path=Path("backupper.toml"),
    )


def test_restore_downloads_verifies_and_restores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = _cfg()
    key = "backups/shop/2026-08-30/backup-120000.dump.zst"
    archive = tmp_path / "backup.dump.zst"
    archive.write_bytes(b"compressed")
    restored: list[str] = []

    def fake_download(_cfg: Config, _key: str, dest: Path) -> str:
        dest.write_bytes(archive.read_bytes())
        return "abc123"

    monkeypatch.setattr("backup.core.s3.download_to_file", fake_download)
    monkeypatch.setattr("backup.core.s3.object_checksum", lambda _cfg, _key: "abc123")
    monkeypatch.setattr("backup.core._restore_archive", lambda url, _path: restored.append(url))
    monkeypatch.setattr(
        "backup.core.streaming.iter_decompressed_file",
        lambda path: iter([path.read_bytes()]),
    )

    backup.restore(cfg, key)

    assert restored == ["postgres://localhost/shop"]


def test_restore_checksum_mismatch_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg()
    key = "backups/shop/2026-08-30/backup-120000.dump.zst"

    monkeypatch.setattr("backup.core.s3.download_to_file", lambda _cfg, _key, dest: "bad")
    monkeypatch.setattr("backup.core.s3.object_checksum", lambda _cfg, _key: "expected")
    monkeypatch.setattr(
        "backup.core._restore_archive",
        lambda *_args: (_ for _ in ()).throw(AssertionError("should not restore")),
    )

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        backup.restore(cfg, key)


def test_restore_without_verify_streams_from_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg()
    key = "backups/shop/2026-08-30/backup-120000.dump.zst"
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "backup.core._pipe_restore",
        lambda database_url, restore_cfg, restore_key: calls.append((database_url, restore_key)),
    )

    backup.restore(cfg, key, verify=False)

    assert calls == [("postgres://localhost/shop", key)]
