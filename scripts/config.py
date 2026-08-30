from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_DEV_DATABASES = [
    {
        "id": "shop",
        "url": "postgres://backupper:backupper@localhost:30433/shop?sslmode=disable",
    },
    {
        "id": "billing",
        "url": "postgres://backupper:backupper@localhost:30433/billing?sslmode=disable",
    },
    {
        "id": "analytics",
        "url": "postgres://backupper:backupper@localhost:30433/analytics?sslmode=disable",
    },
]

DEFAULTS = {
    "DATABASES": json.dumps(DEFAULT_DEV_DATABASES),
    "DATABASE_URL": DEFAULT_DEV_DATABASES[0]["url"],
    "AWS_ENDPOINT_URL": "http://localhost:30456",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_REGION": "us-east-1",
    "S3_BUCKET": "db-backups",
    "S3_PREFIX": "backups",
    "APP_ENV": "dev",
    "ZSTD_LEVEL": "3",
    "NOTIFY_WEBHOOK_URL": "",
    "MAX_SCHEDULE_FAILURES": "5",
    "SLOW_QUERY_MS": "5000",
    "METRICS_PORT": "8080",
    "ANONYMIZE_SALT": "backupper",
}

DEV_CREDENTIAL_MARKERS = {
    "DATABASE_URL": "backupper:backupper@localhost",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
}


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


def write_env(values: dict[str, str]) -> Path:
    path = Path.cwd() / ".env"
    lines = ["# idp-db-backupper", ""]
    for key in DEFAULTS:
        if key in values:
            lines.append(f"{key}={values[key]}")
    path.write_text("\n".join(lines) + "\n")
    return path


def _env_int(name: str, default: str) -> int:
    return int(os.getenv(name, default))


def _db_id_from_url(url: str) -> str:
    path = urlparse(url).path.lstrip("/")
    name = path.split("?")[0] or "default"
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name)


def load_databases() -> list[DatabaseTarget]:
    raw = os.getenv("DATABASES", "").strip()
    if raw:
        data = json.loads(raw)
        return [DatabaseTarget(id=str(item["id"]), database_url=str(item["url"])) for item in data]
    url = os.getenv("DATABASE_URL", DEFAULTS["DATABASE_URL"])
    return [DatabaseTarget(id=_db_id_from_url(url), database_url=url)]


def load_config(*, require_prod_safe: bool = True) -> Config:
    load_env()
    databases = load_databases()
    primary = databases[0]
    cfg = Config(
        databases=databases,
        database_id=primary.id,
        database_url=primary.database_url,
        s3_bucket=os.getenv("S3_BUCKET", DEFAULTS["S3_BUCKET"]),
        s3_prefix=os.getenv("S3_PREFIX", DEFAULTS["S3_PREFIX"]),
        aws_region=os.getenv("AWS_REGION", DEFAULTS["AWS_REGION"]),
        aws_endpoint=os.getenv("AWS_ENDPOINT_URL", DEFAULTS["AWS_ENDPOINT_URL"]),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", DEFAULTS["AWS_ACCESS_KEY_ID"]),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", DEFAULTS["AWS_SECRET_ACCESS_KEY"]),
        app_env=os.getenv("APP_ENV", DEFAULTS["APP_ENV"]).lower(),
        zstd_level=_env_int("ZSTD_LEVEL", DEFAULTS["ZSTD_LEVEL"]),
        notify_webhook_url=os.getenv("NOTIFY_WEBHOOK_URL", DEFAULTS["NOTIFY_WEBHOOK_URL"]),
        max_schedule_failures=_env_int("MAX_SCHEDULE_FAILURES", DEFAULTS["MAX_SCHEDULE_FAILURES"]),
        slow_query_ms=_env_int("SLOW_QUERY_MS", DEFAULTS["SLOW_QUERY_MS"]),
        metrics_port=_env_int("METRICS_PORT", DEFAULTS["METRICS_PORT"]),
        anonymize_salt=os.getenv("ANONYMIZE_SALT", DEFAULTS["ANONYMIZE_SALT"]),
    )
    if require_prod_safe:
        validate_prod_safe(cfg)
    return cfg


def validate_prod_safe(cfg: Config) -> None:
    if cfg.app_env not in ("prod", "production"):
        return
    for target in cfg.databases:
        if DEV_CREDENTIAL_MARKERS["DATABASE_URL"] in target.database_url:
            raise RuntimeError(
                f"APP_ENV={cfg.app_env} but {target.id} still uses dev DATABASE_URL defaults"
            )
    if cfg.aws_access_key_id == DEV_CREDENTIAL_MARKERS["AWS_ACCESS_KEY_ID"]:
        raise RuntimeError(f"APP_ENV={cfg.app_env} but AWS_ACCESS_KEY_ID is still the dev default")
    if cfg.aws_secret_access_key == DEV_CREDENTIAL_MARKERS["AWS_SECRET_ACCESS_KEY"]:
        raise RuntimeError(
            f"APP_ENV={cfg.app_env} but AWS_SECRET_ACCESS_KEY is still the dev default"
        )
