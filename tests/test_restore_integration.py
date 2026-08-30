import pytest
from sqlalchemy import text

from backup import core as backup
from db import inspect as db
from db.session import session
from storage import s3


@pytest.mark.integration
def test_restore_from_s3_after_wipe(live_cfg, seeded_shop, golden_db: str) -> None:
    """Backup to S3, wipe the live database, restore, and match the golden copy."""
    s3.ensure_bucket(live_cfg)

    with session(seeded_shop.database_url) as s:
        expected_counts = db.table_row_counts(s)
    assert sum(expected_counts.values()) > 0

    key = backup.backup(seeded_shop)
    assert backup.verify(seeded_shop, key)

    with session(seeded_shop.database_url) as s:
        for table in db.list_tables(s):
            s.execute(text(f"TRUNCATE {db.quote_ident(table)} RESTART IDENTITY CASCADE"))
        assert sum(db.table_row_counts(s).values()) == 0

    backup.restore(seeded_shop, key)

    with session(seeded_shop.database_url) as s:
        assert db.table_row_counts(s) == expected_counts

    assert db.compare_databases(golden_db, seeded_shop.database_url) == []
