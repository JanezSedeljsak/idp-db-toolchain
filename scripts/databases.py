from __future__ import annotations

from scripts.config import Config, DatabaseTarget, cfg_for_db


def resolve_targets(cfg: Config, db_id: str | None) -> list[DatabaseTarget]:
    if db_id:
        return [cfg.require_database(db_id)]
    return list(cfg.databases)


def resolve_cfg(cfg: Config, db_id: str | None) -> Config:
    if db_id:
        return cfg_for_db(cfg, db_id)
    return cfg_for_db(cfg, cfg.databases[0].id)
