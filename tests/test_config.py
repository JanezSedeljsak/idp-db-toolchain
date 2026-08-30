from pathlib import Path

import pytest

from config import ensure_dev_config, load_config, load_env


def test_toml_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    ensure_dev_config()
    cfg = load_config()
    assert cfg.s3_bucket == "db-backups"
    assert cfg.backup_cron == "0 2 * * *"
    assert cfg.retention_cron == "0 3 1 * *"
    assert len(cfg.databases) == 3
    assert cfg.databases[0].id == "shop"


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    ensure_dev_config()
    env_path = tmp_path / ".env"
    env_path.write_text("S3_BUCKET=override-bucket\n")
    load_env()
    cfg = load_config()
    assert cfg.s3_bucket == "override-bucket"
    assert cfg.backup_cron == "0 2 * * *"
