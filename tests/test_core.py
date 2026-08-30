import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from scripts import db


def test_format_sql_value_datetime() -> None:
    ts = datetime(2026, 8, 28, 11, 1, 10, tzinfo=UTC)
    assert db.format_sql_value(ts).startswith("'")


def test_format_sql_value_types() -> None:
    assert db.format_sql_value(None) == "NULL"
    assert db.format_sql_value(True) == "TRUE"
    assert db.format_sql_value(Decimal("1.5")) == "1.5"
    assert db.format_sql_value(uuid.UUID(int=0)) == "'00000000-0000-0000-0000-000000000000'"
    assert db.format_sql_value({"a": 1}) == "'{\"a\": 1}'"
    assert db.format_sql_value(b"\xff\xfe") == "'\\xfffe'"


def test_split_sql() -> None:
    stmts = db.split_sql_statements("TRUNCATE t;\nINSERT INTO t VALUES (1);")
    assert len(stmts) == 2


def test_zstd_roundtrip() -> None:
    import zstandard as zstd

    raw = b"hello backup"
    assert zstd.ZstdDecompressor().decompress(zstd.ZstdCompressor().compress(raw)) == raw


def test_prod_guard_rejects_defaults(monkeypatch) -> None:
    from scripts.config import load_config

    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(RuntimeError, match="dev default"):
        load_config()
