from pathlib import Path

import pytest

from config import ensure_dev_config
from db import registry as db_registry


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    ensure_dev_config()
    return tmp_path


def test_add_and_remove_database(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("db.registry.ping", lambda _url: None)
    monkeypatch.setattr("storage.s3.delete_database_backups", lambda _cfg, _db: ["k1"])

    db_registry.validate_connection("postgres://localhost/warehouse")

    target = db_registry.add_database("warehouse", "postgres://localhost/warehouse")
    assert target.id == "warehouse"

    _, _, databases = db_registry.read_registry()
    assert any(db.id == "warehouse" for db in databases)

    deleted = db_registry.remove_database("warehouse", prune_backups=True)
    assert deleted == ["k1"]

    _, _, databases = db_registry.read_registry()
    assert all(db.id != "warehouse" for db in databases)


def test_validate_connection_fails(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_ping(_url: str) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr("db.registry.ping", fail_ping)
    with pytest.raises(ConnectionError, match="could not connect"):
        db_registry.validate_connection("postgres://localhost/nope")


def test_cannot_remove_last_database(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, path, databases = db_registry.read_registry()
    data, _, _ = db_registry.read_registry()
    db_registry.write_databases(path, data, [databases[0]])
    with pytest.raises(RuntimeError, match="last"):
        db_registry.remove_database(databases[0].id)
