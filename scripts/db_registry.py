from __future__ import annotations

import re
import shutil
from pathlib import Path

import tomli_w

from scripts.config import DatabaseTarget, _db_id_from_url, load_databases_from_toml, load_toml
from scripts.database import ping

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


def _validate_id(db_id: str) -> str:
    db_id = db_id.strip()
    if not _ID_RE.match(db_id):
        raise ValueError("database id must be alphanumeric (dash/underscore ok)")
    return db_id


def read_registry() -> tuple[dict, Path, list[DatabaseTarget]]:
    data, path = load_toml()
    databases = load_databases_from_toml(data)
    return data, path, databases


def write_databases(path: Path, data: dict, databases: list[DatabaseTarget]) -> None:
    if not databases:
        raise RuntimeError("at least one database must remain registered")
    data["databases"] = [{"id": target.id, "url": target.database_url} for target in databases]
    if path.is_file():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


def validate_connection(url: str) -> None:
    url = url.strip()
    if not url:
        raise ValueError("database url is required")
    try:
        ping(url)
    except Exception as exc:
        raise ConnectionError(f"could not connect: {exc}") from exc


def add_database(
    db_id: str,
    url: str,
    *,
    apply_schema: bool = False,
) -> DatabaseTarget:
    db_id = _validate_id(db_id)
    url = url.strip()
    if not url:
        raise ValueError("database url is required")

    data, path, databases = read_registry()
    if any(target.id == db_id for target in databases):
        raise RuntimeError(f"database {db_id!r} is already registered")

    validate_connection(url)
    target = DatabaseTarget(id=db_id, database_url=url)
    write_databases(path, data, [*databases, target])

    if apply_schema:
        from scripts.dev_schema import apply_dev_schema

        apply_dev_schema(url)

    return target


def remove_database(
    db_id: str,
    *,
    prune_backups: bool = False,
    cfg=None,
) -> list[str]:
    db_id = _validate_id(db_id)
    data, path, databases = read_registry()
    remaining = [target for target in databases if target.id != db_id]
    if len(remaining) == len(databases):
        raise KeyError(f"database {db_id!r} is not registered")
    if not remaining:
        raise RuntimeError("cannot remove the last registered database")

    deleted_keys: list[str] = []
    if prune_backups:
        from scripts import s3
        from scripts.config import load_config

        cfg = cfg or load_config()
        deleted_keys = s3.delete_database_backups(cfg, db_id)

    write_databases(path, data, remaining)
    return deleted_keys


def suggest_id(url: str) -> str:
    return _db_id_from_url(url)
