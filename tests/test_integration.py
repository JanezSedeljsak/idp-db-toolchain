import pytest
from sqlalchemy import text

from scripts import backup, db, pg_tools, s3
from scripts import seed as seed_data
from scripts.config import cfg_for_db, load_config
from scripts.database import session
from scripts.dev_schema import apply_dev_schema

INTEGRATION_DB = "backupper_integration"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def source_db(cfg):
    apply_dev_schema()
    shop = cfg_for_db(cfg, "shop")
    with session(shop.database_url) as s:
        seed_data.run(s, count=5)
    yield shop


@pytest.fixture(scope="module")
def target_db(cfg, source_db):
    pg_tools.ensure_database(source_db.database_url, INTEGRATION_DB)
    url = pg_tools.database_url_with_name(source_db.database_url, INTEGRATION_DB)
    yield url
    pg_tools.drop_database(source_db.database_url, INTEGRATION_DB)


@pytest.mark.integration
def test_export_import_databases_match(source_db, target_db: str) -> None:
    backup.export_to_target(source_db.database_url, target_db)
    diffs = db.compare_databases(source_db.database_url, target_db)
    assert diffs == []


@pytest.mark.integration
def test_backup_restore_roundtrip(cfg, source_db, target_db: str) -> None:
    backup.export_to_target(source_db.database_url, target_db)
    s3.ensure_bucket(cfg)
    key = backup.backup(source_db)
    assert backup.verify(source_db, key)

    with session(source_db.database_url) as s:
        for table in db.list_tables(s):
            s.execute(text(f"TRUNCATE {db.quote_ident(table)} RESTART IDENTITY CASCADE"))

    backup.restore(source_db, key)
    diffs = db.compare_databases(target_db, source_db.database_url)
    assert diffs == []
