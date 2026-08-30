from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from scripts.config import load_config
from scripts.database import get_engine


def apply_dev_schema(database_url: str | None = None) -> None:
    url = database_url or load_config().database_url
    schema = Path(__file__).resolve().parents[1] / "k8s" / "dev-schema.sql"
    engine = get_engine(url)
    with engine.begin() as conn:
        conn.execute(text(schema.read_text()))
