from __future__ import annotations

import tempfile
from pathlib import Path

from config import Config
from db import pg_tools
from observability.status import record_failure, record_success
from storage import s3, streaming


def backup(cfg: Config) -> str:
    s3.ensure_bucket(cfg)
    key = s3.backup_key(cfg)
    with tempfile.NamedTemporaryFile(suffix=".dump.zst", delete=False) as tmp:
        archive = Path(tmp.name)
    try:
        with pg_tools.stream_dump(cfg.database_url) as chunks:
            size, checksum = streaming.compress_chunks_to_file(
                chunks, archive, level=cfg.zstd_level
            )
        s3.upload_file(cfg, key, archive, checksum=checksum)
        record_success(
            db_id=cfg.database_id,
            key=key,
            size_bytes=size,
            checksum=checksum,
        )
        return key
    except Exception as exc:
        record_failure(cfg.database_id, str(exc))
        raise
    finally:
        archive.unlink(missing_ok=True)


def _restore_archive(database_url: str, archive: Path) -> None:
    pg_tools.stream_restore(database_url, streaming.iter_decompressed_file(archive))


def _pipe_restore(database_url: str, cfg: Config, key: str) -> None:
    compressed = s3.iter_object_chunks(cfg, key)
    pg_tools.stream_restore(database_url, streaming.iter_decompressed_chunks(compressed))


def restore(cfg: Config, key: str, *, verify: bool = True) -> None:
    if verify:
        with tempfile.NamedTemporaryFile(suffix=".dump.zst", delete=False) as tmp:
            archive = Path(tmp.name)
        try:
            checksum = s3.download_to_file(cfg, key, archive)
            expected = s3.object_checksum(cfg, key)
            if expected and checksum != expected:
                raise RuntimeError(f"checksum mismatch for {key}")
            _restore_archive(cfg.database_url, archive)
        finally:
            archive.unlink(missing_ok=True)
        return
    _pipe_restore(cfg.database_url, cfg, key)


def verify(cfg: Config, key: str) -> bool:
    expected = s3.object_checksum(cfg, key)
    digest = s3.hash_object(cfg, key)
    return not (expected and digest != expected)


def export_to_target(source_url: str, target_url: str) -> None:
    with pg_tools.temp_dump_file(source_url) as path:
        pg_tools.restore_from_file(target_url, path)
