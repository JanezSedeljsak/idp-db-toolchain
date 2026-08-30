from __future__ import annotations

import os

import pytest

from scripts import backup, pg_tools
from scripts import seed as seed_data
from scripts.config import Config, cfg_for_db, load_config
from scripts.database import session
from scripts.dev_schema import apply_dev_schema

INTEGRATION_DB = "backupper_integration"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run integration tests (require postgres + localstack)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: integration tests requiring live postgres/localstack",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration") or os.environ.get("RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="use --run-integration or RUN_INTEGRATION=1")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="module")
def live_cfg() -> Config:
    return load_config()


@pytest.fixture(scope="module")
def seeded_databases(live_cfg: Config):
    apply_dev_schema()
    targets = []
    for target in live_cfg.databases:
        db_cfg = cfg_for_db(live_cfg, target.id)
        with session(db_cfg.database_url) as s:
            seed_data.run(
                s,
                counts=seed_data.INTEGRATION_COUNTS,
                rng_seed=seed_data.INTEGRATION_RNG_SEED,
                prefix=target.id,
            )
        targets.append(db_cfg)
    yield targets


@pytest.fixture(scope="module")
def seeded_shop(seeded_databases):
    return seeded_databases[0]


@pytest.fixture(scope="module")
def golden_db(seeded_shop):
    pg_tools.ensure_database(seeded_shop.database_url, INTEGRATION_DB)
    url = pg_tools.database_url_with_name(seeded_shop.database_url, INTEGRATION_DB)
    backup.export_to_target(seeded_shop.database_url, url)
    yield url
    pg_tools.drop_database(seeded_shop.database_url, INTEGRATION_DB)
