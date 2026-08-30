from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import load_config

_engines: dict[str, Engine] = {}


def db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def get_engine(database_url: str) -> Engine:
    key = db_url(database_url)
    engine = _engines.get(key)
    if engine is None:
        engine = create_engine(key, pool_pre_ping=True)
        _engines[key] = engine
    return engine


def dispose_engines() -> None:
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


@contextmanager
def session(database_url: str | None = None) -> Iterator[Session]:
    url = database_url or load_config().database_url
    factory = sessionmaker(bind=get_engine(url))
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
    with get_engine(database_url).connect() as conn:
        conn.execute(text("SELECT 1"))
