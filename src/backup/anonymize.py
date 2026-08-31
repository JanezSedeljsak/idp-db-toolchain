from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backup import core as backup
from config import Config, cfg_for_db, with_database_url
from db import inspect as db
from db import pg_tools
from db.session import session
from storage import s3

SCRATCH_DB = "db_toolchain_anonymize"

ANONYMIZE_COLUMNS_SQL = """
SELECT table_schema, table_name, column_name, data_type
FROM "db-toolchain".anonymize_columns AS ac
JOIN information_schema.columns AS ic
  ON ic.table_schema = ac.table_schema
 AND ic.table_name = ac.table_name
 AND ic.column_name = ac.column_name
WHERE ac.enabled = TRUE
ORDER BY ac.table_schema, ac.table_name, ac.column_name
"""


def registry_available(sess: Session) -> bool:
    row = sess.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'db-toolchain'
                  AND table_name = 'anonymize_columns'
            )
            """
        )
    ).scalar_one()
    return bool(row)


def anonymize_session(sess: Session, *, salt: str) -> int:
    if not registry_available(sess):
        return 0
    rows = sess.execute(text(ANONYMIZE_COLUMNS_SQL)).fetchall()
    for schema, table, column, data_type in rows:
        table_ident = f"{db.quote_ident(schema)}.{db.quote_ident(table)}"
        col_ident = db.quote_ident(column)
        if data_type in ("integer", "bigint", "smallint"):
            expr = f'"db-toolchain".anonymize_integer({col_ident}, :salt)'
        else:
            expr = f'"db-toolchain".anonymize_text({col_ident}::text, :salt)'
        sess.execute(
            text(f"UPDATE {table_ident} SET {col_ident} = {expr} WHERE {col_ident} IS NOT NULL"),
            {"salt": salt},
        )
    return len(rows)


def anonymize_database(cfg: Config, source_db_id: str, target_url: str) -> int:
    source_cfg = cfg_for_db(cfg, source_db_id)
    with pg_tools.temp_dump_file(source_cfg.database_url) as path:
        pg_tools.restore_from_file(target_url, path)
    with session(target_url) as sess:
        return anonymize_session(sess, salt=cfg.anonymize_salt)


def anonymize_backup(cfg: Config, key: str, out_key: str) -> str:
    admin_url = cfg.databases[0].database_url
    target_url = pg_tools.database_url_with_name(admin_url, SCRATCH_DB)
    pg_tools.ensure_database(admin_url, SCRATCH_DB)
    with tempfile.NamedTemporaryFile(suffix=".dump.zst", delete=False) as tmp:
        archive = Path(tmp.name)
    try:
        s3.download_to_file(cfg, key, archive)
        backup._restore_archive(target_url, archive)
        with session(target_url) as sess:
            anonymize_session(sess, salt=cfg.anonymize_salt)
        scratch_cfg = with_database_url(cfg, target_url)
        uploaded_key = backup.backup(scratch_cfg)
        s3.copy_object(scratch_cfg, uploaded_key, out_key)
        s3.delete_object(scratch_cfg, uploaded_key)
        return out_key
    finally:
        archive.unlink(missing_ok=True)
        pg_tools.drop_database(admin_url, SCRATCH_DB)
