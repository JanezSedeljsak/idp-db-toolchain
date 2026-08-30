import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import zstandard as zstd

from db import inspect as db
from storage import streaming


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
    raw = b"hello backup"
    assert zstd.ZstdDecompressor().decompress(zstd.ZstdCompressor().compress(raw)) == raw


def test_compress_chunks_to_file_roundtrip(tmp_path: Path) -> None:
    raw = b"x" * 200_000

    def chunks():
        for offset in range(0, len(raw), 4096):
            yield raw[offset : offset + 4096]

    archive = tmp_path / "backup.dump.zst"
    size, digest = streaming.compress_chunks_to_file(chunks(), archive, level=3)
    assert size == archive.stat().st_size
    assert digest == streaming.hash_file(archive)
    out = b"".join(streaming.iter_decompressed_file(archive))
    assert out == raw


def test_iter_reader() -> None:
    reader = streaming.IterReader(iter([b"abc", b"def"]))
    assert reader.read(2) == b"ab"
    assert reader.read(4) == b"cdef"
    assert reader.read() == b""


def test_prod_guard_rejects_defaults(monkeypatch) -> None:
    from config import load_config

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv(
        "DATABASES",
        json.dumps([{"id": "shop", "url": "postgres://backupper:backupper@localhost/shop"}]),
    )
    with pytest.raises(RuntimeError, match="dev"):
        load_config()
