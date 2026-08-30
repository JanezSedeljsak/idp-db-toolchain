from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text

from config import load_config
from db import pg_tools
from db.session import get_engine


def _schema_files() -> list[Path]:
    root = Path(__file__).resolve().parents[1] / "k8s"
    return [root / "dev-schema.sql", root / "anonymize-schema.sql"]


def _database_name(url: str) -> str:
    return urlparse(url).path.lstrip("/").split("?")[0]


def apply_dev_schema(database_url: str | None = None) -> None:
    cfg = load_config()
    targets = [database_url] if database_url else [db.database_url for db in cfg.databases]
    admin_url = pg_tools.database_url_with_name(cfg.databases[0].database_url, "postgres")
    for url in targets:
        name = _database_name(url)
        if name != "postgres":
            pg_tools.ensure_database(admin_url, name)
        engine = get_engine(url)
        with engine.begin() as conn:
            for schema_file in _schema_files():
                conn.execute(text(schema_file.read_text()))
