from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from scripts.config import load_config


def db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


@contextmanager
def session(database_url: str | None = None) -> Iterator[Session]:
    url = database_url or load_config().database_url
    factory = sessionmaker(bind=create_engine(db_url(url), pool_pre_ping=True))
    s = factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def ping(database_url: str) -> None:
    with create_engine(db_url(database_url)).connect() as conn:
        conn.execute(text("SELECT 1"))


def migrate() -> None:
    cfg = load_config()
    alembic = AlembicConfig(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic.set_main_option("sqlalchemy.url", db_url(cfg.database_url))
    command.upgrade(alembic, "head")
