from __future__ import annotations

from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError

from scripts.config import Config


def _client(cfg: Config):
    return boto3.client(
        "s3",
        region_name=cfg.aws_region,
        endpoint_url=cfg.aws_endpoint,
        aws_access_key_id=cfg.aws_access_key_id,
        aws_secret_access_key=cfg.aws_secret_access_key,
    )


def ensure_bucket(cfg: Config) -> None:
    client = _client(cfg)
    try:
        client.head_bucket(Bucket=cfg.s3_bucket)
    except ClientError:
        client.create_bucket(Bucket=cfg.s3_bucket)


def backup_key(cfg: Config) -> str:
    ts = datetime.now(UTC)
    p = cfg.s3_prefix.rstrip("/")
    return f"{p}/{ts:%Y-%m-%d}/backup-{ts:%H%M%S}.sql.zst"


def upload(cfg: Config, key: str, data: bytes) -> None:
    _client(cfg).put_object(
        Bucket=cfg.s3_bucket, Key=key, Body=data, ContentType="application/zstd"
    )


def download(cfg: Config, key: str) -> bytes:
    return _client(cfg).get_object(Bucket=cfg.s3_bucket, Key=key)["Body"].read()


def list_backups(cfg: Config) -> list[dict]:
    prefix = cfg.s3_prefix.rstrip("/") + "/"
    out = []
    for page in (
        _client(cfg).get_paginator("list_objects_v2").paginate(Bucket=cfg.s3_bucket, Prefix=prefix)
    ):
        out.extend(page.get("Contents", []))
    return sorted(out, key=lambda o: o["LastModified"], reverse=True)
