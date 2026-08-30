from __future__ import annotations

import tempfile
from pathlib import Path

import zstandard as zstd
from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts import backup, db, pg_tools, s3
from scripts.config import Config, with_database_url
from scripts.database import session

SCRATCH_DB = "backupper_anonymize"

RULES: tuple[tuple[str, str], ...] = (
    ("users", "email"),
    ("users", "name"),
)


def anonymize_session(sess: Session) -> None:
    for table, column in RULES:
        rows = sess.execute(text(f"SELECT id FROM {db.quote_ident(table)} ORDER BY id")).fetchall()
        table_ident = db.quote_ident(table)
        col_ident = db.quote_ident(column)
        for (row_id,) in rows:
            value = f"user{row_id}@example.test" if column == "email" else f"User {row_id}"
            sess.execute(
                text(
                    f"UPDATE {table_ident} SET {col_ident} = :value "
                    f"WHERE {db.quote_ident('id')} = :id"
                ),
                {"value": value, "id": row_id},
            )


def anonymize_database(cfg: Config, source_url: str, target_url: str) -> None:
    with pg_tools.temp_dump_file(source_url) as path:
        pg_tools.restore_from_file(target_url, path)
    with session(target_url) as sess:
        anonymize_session(sess)


def anonymize_backup(cfg: Config, key: str, out_key: str) -> str:
    data, _checksum = s3.download(cfg, key)
    raw = zstd.ZstdDecompressor().decompress(data)
    target_url = pg_tools.database_url_with_name(cfg.database_url, SCRATCH_DB)
    pg_tools.ensure_database(cfg.database_url, SCRATCH_DB)
    try:
        with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as dump_fh:
            dump_fh.write(raw)
            dump_path = dump_fh.name
        try:
            pg_tools.restore_from_file(target_url, dump_path)
        finally:
            Path(dump_path).unlink(missing_ok=True)
        with session(target_url) as sess:
            anonymize_session(sess)
        scratch_cfg = with_database_url(cfg, target_url)
        uploaded_key = backup.backup(scratch_cfg)
        body, checksum = s3.download(scratch_cfg, uploaded_key)
        s3.upload(cfg, out_key, body, checksum=checksum)
        s3.delete_object(scratch_cfg, uploaded_key)
        return out_key
    finally:
        pg_tools.drop_database(cfg.database_url, SCRATCH_DB)
