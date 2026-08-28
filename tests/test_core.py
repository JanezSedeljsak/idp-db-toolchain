from datetime import UTC, datetime

from scripts import db


def test_format_sql_value() -> None:
    ts = datetime(2026, 8, 28, 11, 1, 10, tzinfo=UTC)
    assert db.format_sql_value(ts).startswith("'")


def test_split_sql() -> None:
    stmts = db.split_sql_statements("TRUNCATE t;\nINSERT INTO t VALUES (1);")
    assert len(stmts) == 2


def test_zstd_roundtrip() -> None:
    import zstandard as zstd

    raw = b"hello backup"
    assert zstd.ZstdDecompressor().decompress(zstd.ZstdCompressor().compress(raw)) == raw
