from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from scripts.config import Config

_RETRY = BotoConfig(retries={"max_attempts": 5, "mode": "adaptive"})


def _client(cfg: Config):
    return boto3.client(
        "s3",
        region_name=cfg.aws_region,
        endpoint_url=cfg.aws_endpoint,
        aws_access_key_id=cfg.aws_access_key_id,
        aws_secret_access_key=cfg.aws_secret_access_key,
        config=_RETRY,
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
    return f"{p}/{ts:%Y-%m-%d}/backup-{ts:%H%M%S}.dump.zst"


def upload(cfg: Config, key: str, data: bytes, *, checksum: str | None = None) -> None:
    digest = checksum or hashlib.sha256(data).hexdigest()
    _client(cfg).put_object(
        Bucket=cfg.s3_bucket,
        Key=key,
        Body=data,
        ContentType="application/zstd",
        Metadata={"sha256": digest},
    )


def download(cfg: Config, key: str) -> tuple[bytes, str]:
    obj = _client(cfg).get_object(Bucket=cfg.s3_bucket, Key=key)
    data = obj["Body"].read()
    checksum = obj.get("Metadata", {}).get("sha256") or hashlib.sha256(data).hexdigest()
    return data, checksum


def object_checksum(cfg: Config, key: str) -> str | None:
    try:
        obj = _client(cfg).head_object(Bucket=cfg.s3_bucket, Key=key)
    except ClientError:
        return None
    meta = obj.get("Metadata", {}).get("sha256")
    return str(meta) if meta else None


def list_backups(cfg: Config) -> list[dict]:
    prefix = cfg.s3_prefix.rstrip("/") + "/"
    out = []
    for page in (
        _client(cfg).get_paginator("list_objects_v2").paginate(Bucket=cfg.s3_bucket, Prefix=prefix)
    ):
        out.extend(page.get("Contents", []))
    return sorted(out, key=lambda o: o["LastModified"], reverse=True)


def delete_object(cfg: Config, key: str) -> None:
    _client(cfg).delete_object(Bucket=cfg.s3_bucket, Key=key)


def prune_backups(cfg: Config, older_than: timedelta) -> list[str]:
    cutoff = datetime.now(UTC) - older_than
    keys: list[str] = []
    for obj in list_backups(cfg):
        modified = obj["LastModified"]
        if modified.tzinfo is None:
            modified = modified.replace(tzinfo=UTC)
        if modified < cutoff:
            keys.append(obj["Key"])
    return keys
