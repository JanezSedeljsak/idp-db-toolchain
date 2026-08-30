import pytest

from scripts import backup, db, s3
from scripts import seed as seed_data
from scripts.config import Config
from scripts.database import session


@pytest.mark.integration
def test_all_databases_have_seed_data(seeded_databases) -> None:
    expected = seed_data.INTEGRATION_COUNTS
    for db_cfg in seeded_databases:
        with session(db_cfg.database_url) as s:
            counts = db.table_row_counts(s)
        assert counts["users"] == expected["users"]
        assert counts["orders"] == expected["orders"]
        assert counts["audit_log"] == expected["audit"]


@pytest.mark.integration
def test_backup_all_seeded_databases(live_cfg: Config, seeded_databases) -> None:
    s3.ensure_bucket(live_cfg)
    for db_cfg in seeded_databases:
        key = backup.backup(db_cfg)
        assert backup.verify(db_cfg, key)
