from __future__ import annotations

import hashlib
import io
import tempfile
from collections.abc import Iterator

import zstandard as zstd

from scripts import pg_tools, s3
from scripts.config import Config
from scripts.status import record_failure, record_success


def _compress_stream(chunks: Iterator[bytes], level: int) -> tuple[bytes, str]:
    out = io.BytesIO()
    compressor = zstd.ZstdCompressor(level=level)
    with compressor.stream_writer(out) as writer:
        for chunk in chunks:
            writer.write(chunk)
    data = out.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def backup(cfg: Config) -> str:
    s3.ensure_bucket(cfg)
    key = s3.backup_key(cfg)
    try:
        with pg_tools.stream_dump(cfg.database_url) as chunks:
            compressed, checksum = _compress_stream(chunks, cfg.zstd_level)
        s3.upload(cfg, key, compressed, checksum=checksum)
        record_success(key=key, size_bytes=len(compressed), checksum=checksum)
        return key
    except Exception as exc:
        record_failure(str(exc))
        raise


def restore(cfg: Config, key: str, *, verify: bool = True) -> None:
    from pathlib import Path

    data, checksum = s3.download(cfg, key)
    if verify and hashlib.sha256(data).hexdigest() != checksum:
        raise RuntimeError(f"checksum mismatch for {key}")
    raw = zstd.ZstdDecompressor().decompress(data)
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as fh:
        fh.write(raw)
        dump_path = fh.name
    try:
        pg_tools.restore_from_file(cfg.database_url, dump_path)
    finally:
        Path(dump_path).unlink(missing_ok=True)


def verify(cfg: Config, key: str) -> bool:
    data, checksum = s3.download(cfg, key)
    expected = s3.object_checksum(cfg, key)
    if expected and checksum != expected:
        return False
    return hashlib.sha256(data).hexdigest() == checksum


def export_to_target(source_url: str, target_url: str) -> None:
    with pg_tools.temp_dump_file(source_url) as path:
        pg_tools.restore_from_file(target_url, path)
