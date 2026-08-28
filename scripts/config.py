from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULTS = {
    "DATABASE_URL": "postgres://backupper:backupper@localhost:30433/backupper?sslmode=disable",
    "AWS_ENDPOINT_URL": "http://localhost:30456",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_REGION": "us-east-1",
    "S3_BUCKET": "db-backups",
    "S3_PREFIX": "daily",
}


@dataclass
class Config:
    database_url: str
    s3_bucket: str
    s3_prefix: str
    aws_region: str
    aws_endpoint: str
    aws_access_key_id: str
    aws_secret_access_key: str


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


def load_config() -> Config:
    load_env()
    return Config(
        database_url=os.getenv("DATABASE_URL", DEFAULTS["DATABASE_URL"]),
        s3_bucket=os.getenv("S3_BUCKET", DEFAULTS["S3_BUCKET"]),
        s3_prefix=os.getenv("S3_PREFIX", DEFAULTS["S3_PREFIX"]),
        aws_region=os.getenv("AWS_REGION", DEFAULTS["AWS_REGION"]),
        aws_endpoint=os.getenv("AWS_ENDPOINT_URL", DEFAULTS["AWS_ENDPOINT_URL"]),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", DEFAULTS["AWS_ACCESS_KEY_ID"]),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", DEFAULTS["AWS_SECRET_ACCESS_KEY"]),
    )
