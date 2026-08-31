from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEV_CREDENTIAL_MARKERS = {
    "database_url": "db-toolchain:db-toolchain@localhost",
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
}

_BUNDLED_CONFIG = Path(__file__).resolve().parents[1] / "db-toolchain.toml"


@dataclass(frozen=True)
class DatabaseTarget:
    id: str
    database_url: str


@dataclass
class Config:
    databases: list[DatabaseTarget]
    database_id: str
    database_url: str
    s3_bucket: str
    s3_prefix: str
    aws_region: str
    aws_endpoint: str
    aws_access_key_id: str
    aws_secret_access_key: str
    app_env: str
    zstd_level: int
    notify_webhook_url: str
    max_schedule_failures: int
    slow_query_ms: int
    metrics_port: int
    anonymize_salt: str
    backup_cron: str
    retention_cron: str
    config_path: Path

    def require_database(self, db_id: str) -> DatabaseTarget:
        for target in self.databases:
            if target.id == db_id:
                return target
        known = ", ".join(t.id for t in self.databases)
        raise KeyError(f"unknown database {db_id!r} (configured: {known})")


def cfg_for_db(cfg: Config, db_id: str) -> Config:
    target = cfg.require_database(db_id)
    return replace(cfg, database_id=target.id, database_url=target.database_url)


def with_database_url(cfg: Config, database_url: str) -> Config:
    return replace(cfg, database_url=database_url)


def resolve_config_path() -> Path:
    if env := os.getenv("DB_TOOLCHAIN_CONFIG"):
        path = Path(env)
        if not path.is_file():
            raise FileNotFoundError(f"DB_TOOLCHAIN_CONFIG not found: {path}")
        return path
    local = Path.cwd() / "db-toolchain.toml"
    if local.is_file():
        return local
    if _BUNDLED_CONFIG.is_file():
        return _BUNDLED_CONFIG
    raise FileNotFoundError(
        "db-toolchain.toml not found - create one in the project root or set DB_TOOLCHAIN_CONFIG"
    )


def load_toml(path: Path | None = None) -> tuple[dict[str, Any], Path]:
    config_path = path or resolve_config_path()
    with config_path.open("rb") as fh:
        return tomllib.load(fh), config_path


def load_env() -> None:
    path = Path.cwd() / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip("'\"")


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    section = data.get(name, {})
    return section if isinstance(section, dict) else {}


def _pick_str(env_name: str, toml_value: Any, default: str = "") -> str:
    env = os.getenv(env_name)
    if env is not None and env != "":
        return env
    if toml_value is not None:
        return str(toml_value)
    return default


def _pick_int(env_name: str, toml_value: Any, default: int) -> int:
    env = os.getenv(env_name)
    if env is not None and env != "":
        return int(env)
    if toml_value is not None:
        return int(toml_value)
    return default


def _db_id_from_url(url: str) -> str:
    path = urlparse(url).path.lstrip("/")
    name = path.split("?")[0] or "default"
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name)


def load_databases_from_toml(data: dict[str, Any]) -> list[DatabaseTarget]:
    raw = os.getenv("DATABASES", "").strip()
    if raw:
        items = json.loads(raw)
        return [DatabaseTarget(id=str(item["id"]), database_url=str(item["url"])) for item in items]
    if single := os.getenv("DATABASE_URL"):
        return [DatabaseTarget(id=_db_id_from_url(single), database_url=single)]
    rows = data.get("databases", [])
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("db-toolchain.toml must define at least one [[databases]] entry")
    return [
        DatabaseTarget(id=str(row["id"]), database_url=str(row["url"]))
        for row in rows
        if isinstance(row, dict)
    ]


def ensure_dev_config(target_dir: Path | None = None, *, force: bool = False) -> Path:
    root = target_dir or Path.cwd()
    path = root / "db-toolchain.toml"
    if path.is_file() and not force:
        return path
    if not _BUNDLED_CONFIG.is_file():
        raise FileNotFoundError("bundled db-toolchain.toml missing from package")
    path.write_text(_BUNDLED_CONFIG.read_text())
    return path


def load_config(*, require_prod_safe: bool = True) -> Config:
    load_env()
    toml_data, config_path = load_toml()
    s3 = _section(toml_data, "s3")
    schedule = _section(toml_data, "schedule")
    backup = _section(toml_data, "backup")
    metrics = _section(toml_data, "metrics")
    anonymize = _section(toml_data, "anonymize")
    scheduler = _section(toml_data, "scheduler")
    notify = _section(toml_data, "notify")

    databases = load_databases_from_toml(toml_data)
    primary = databases[0]
    cfg = Config(
        databases=databases,
        database_id=primary.id,
        database_url=primary.database_url,
        s3_bucket=_pick_str("S3_BUCKET", s3.get("bucket"), "db-backups"),
        s3_prefix=_pick_str("S3_PREFIX", s3.get("prefix"), "backups"),
        aws_region=_pick_str("AWS_REGION", s3.get("region"), "us-east-1"),
        aws_endpoint=_pick_str("AWS_ENDPOINT_URL", s3.get("endpoint"), ""),
        aws_access_key_id=_pick_str("AWS_ACCESS_KEY_ID", None, "test"),
        aws_secret_access_key=_pick_str("AWS_SECRET_ACCESS_KEY", None, "test"),
        app_env=_pick_str("APP_ENV", toml_data.get("app_env"), "dev").lower(),
        zstd_level=_pick_int("ZSTD_LEVEL", backup.get("zstd_level"), 3),
        notify_webhook_url=_pick_str("NOTIFY_WEBHOOK_URL", notify.get("webhook_url"), ""),
        max_schedule_failures=_pick_int("MAX_SCHEDULE_FAILURES", scheduler.get("max_failures"), 5),
        slow_query_ms=_pick_int("SLOW_QUERY_MS", metrics.get("slow_query_ms"), 5000),
        metrics_port=_pick_int("METRICS_PORT", metrics.get("port"), 8080),
        anonymize_salt=_pick_str("ANONYMIZE_SALT", anonymize.get("salt"), "db-toolchain"),
        backup_cron=_pick_str("BACKUP_CRON", schedule.get("backup"), "0 2 * * *"),
        retention_cron=_pick_str("RETENTION_CRON", schedule.get("retention"), "0 3 1 * *"),
        config_path=config_path,
    )
    data_dir = _pick_str("DB_TOOLCHAIN_DATA_DIR", _section(toml_data, "data").get("dir"), ".")
    os.environ.setdefault("DB_TOOLCHAIN_DATA_DIR", data_dir)
    if require_prod_safe:
        validate_prod_safe(cfg)
    return cfg


def validate_prod_safe(cfg: Config) -> None:
    if cfg.app_env not in ("prod", "production"):
        return
    for target in cfg.databases:
        if DEV_CREDENTIAL_MARKERS["database_url"] in target.database_url:
            raise RuntimeError(
                f"APP_ENV={cfg.app_env} but {target.id} still uses dev database defaults"
            )
    if cfg.aws_access_key_id == DEV_CREDENTIAL_MARKERS["aws_access_key_id"]:
        raise RuntimeError(f"APP_ENV={cfg.app_env} but AWS_ACCESS_KEY_ID is still the dev default")
    if cfg.aws_secret_access_key == DEV_CREDENTIAL_MARKERS["aws_secret_access_key"]:
        raise RuntimeError(
            f"APP_ENV={cfg.app_env} but AWS_SECRET_ACCESS_KEY is still the dev default"
        )
