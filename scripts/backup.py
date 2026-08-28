from __future__ import annotations

import zstandard as zstd

from scripts import db, s3
from scripts.config import Config
from scripts.database import session


def backup(cfg: Config) -> str:
    with session(cfg.database_url) as s:
        data = zstd.ZstdCompressor(level=3).compress(db.dump(s).encode())
    s3.ensure_bucket(cfg)
    key = s3.backup_key(cfg)
    s3.upload(cfg, key, data)
    return key


def restore(cfg: Config, key: str) -> None:
    raw = zstd.ZstdDecompressor().decompress(s3.download(cfg, key)).decode()
    with session(cfg.database_url) as s:
        db.restore(s, raw)
