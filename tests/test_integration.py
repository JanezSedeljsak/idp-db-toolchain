import pytest

from db import inspect as db


@pytest.mark.integration
def test_export_import_databases_match(seeded_shop, golden_db: str) -> None:
    diffs = db.compare_databases(seeded_shop.database_url, golden_db)
    assert diffs == []
