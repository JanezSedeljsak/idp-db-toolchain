import pytest
from sqlalchemy import text

from scripts import backup, db, pg_tools, s3
from scripts import seed as seed_data
from scripts.config import load_config
from scripts.database import session
from scripts.dev_schema import apply_dev_schema

INTEGRATION_DB = "backupper_integration"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def source_db(cfg):
    apply_dev_schema()
    with session(cfg.database_url) as s:
        seed_data.run(s, count=5)
    yield cfg.database_url


@pytest.fixture(scope="module")
def target_db(cfg, source_db):
    pg_tools.ensure_database(cfg.database_url, INTEGRATION_DB)
    url = pg_tools.database_url_with_name(cfg.database_url, INTEGRATION_DB)
    yield url
    pg_tools.drop_database(cfg.database_url, INTEGRATION_DB)


@pytest.mark.integration
def test_export_import_databases_match(source_db: str, target_db: str) -> None:
    backup.export_to_target(source_db, target_db)
    diffs = db.compare_databases(source_db, target_db)
    assert diffs == []


@pytest.mark.integration
def test_backup_restore_roundtrip(cfg, source_db: str, target_db: str) -> None:
    backup.export_to_target(source_db, target_db)
    s3.ensure_bucket(cfg)
    key = backup.backup(cfg)
    assert backup.verify(cfg, key)

    with session(source_db) as s:
        for table in db.list_tables(s):
            s.execute(text(f"TRUNCATE {db.quote_ident(table)} RESTART IDENTITY CASCADE"))

    backup.restore(cfg, key)
    diffs = db.compare_databases(target_db, source_db)
    assert diffs == []
