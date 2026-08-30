from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from scripts.config import Config

_RETRY = BotoConfig(retries={"max_attempts": 5, "mode": "adaptive"})
CHUNK_SIZE = 64 * 1024
_KEY_RE = re.compile(
    r"^(?P<prefix>.+)/(?P<db>[^/]+)/(?P<day>\d{4}-\d{2}-\d{2})/backup-(?P<time>\d{6})\.dump\.zst$"
)


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


def check_bucket(cfg: Config) -> None:
    _client(cfg).head_bucket(Bucket=cfg.s3_bucket)


def check_reachable(cfg: Config) -> None:
    """Verify the S3 API is reachable; the backup bucket may not exist yet."""
    _client(cfg).list_buckets()


def backup_key(cfg: Config) -> str:
    ts = datetime.now(UTC)
    p = cfg.s3_prefix.rstrip("/")
    return f"{p}/{cfg.database_id}/{ts:%Y-%m-%d}/backup-{ts:%H%M%S}.dump.zst"


def parse_backup_key(key: str) -> dict[str, str] | None:
    match = _KEY_RE.match(key)
    if not match:
        return None
    return match.groupdict()


def backup_date_from_key(key: str) -> date | None:
    parsed = parse_backup_key(key)
    if not parsed:
        return None
    try:
        return date.fromisoformat(parsed["day"])
    except ValueError:
        return None


def db_prefix(cfg: Config, db_id: str | None = None) -> str:
    return f"{cfg.s3_prefix.rstrip('/')}/{db_id or cfg.database_id}/"


def upload(cfg: Config, key: str, data: bytes, *, checksum: str | None = None) -> None:
    digest = checksum or hashlib.sha256(data).hexdigest()
    _client(cfg).put_object(
        Bucket=cfg.s3_bucket,
        Key=key,
        Body=data,
        ContentType="application/zstd",
        Metadata={"sha256": digest, "database": cfg.database_id},
    )


def upload_file(cfg: Config, key: str, path: str | Path, *, checksum: str) -> None:
    _client(cfg).upload_file(
        str(path),
        cfg.s3_bucket,
        key,
        ExtraArgs={
            "ContentType": "application/zstd",
            "Metadata": {"sha256": checksum, "database": cfg.database_id},
        },
    )


def iter_object_chunks(cfg: Config, key: str, *, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    obj = _client(cfg).get_object(Bucket=cfg.s3_bucket, Key=key)
    yield from obj["Body"].iter_chunks(chunk_size=chunk_size)


def hash_object(cfg: Config, key: str, *, chunk_size: int = CHUNK_SIZE) -> str:
    hasher = hashlib.sha256()
    for chunk in iter_object_chunks(cfg, key, chunk_size=chunk_size):
        hasher.update(chunk)
    return hasher.hexdigest()


def download_to_file(cfg: Config, key: str, path: str | Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("wb") as fh:
        for chunk in iter_object_chunks(cfg, key):
            hasher.update(chunk)
            fh.write(chunk)
    return hasher.hexdigest()


def copy_object(cfg: Config, src_key: str, dest_key: str) -> None:
    _client(cfg).copy_object(
        Bucket=cfg.s3_bucket,
        Key=dest_key,
        CopySource={"Bucket": cfg.s3_bucket, "Key": src_key},
        MetadataDirective="COPY",
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


def list_backups(cfg: Config, *, db_id: str | None = None) -> list[dict]:
    prefix = db_prefix(cfg, db_id)
    out = []
    for page in (
        _client(cfg).get_paginator("list_objects_v2").paginate(Bucket=cfg.s3_bucket, Prefix=prefix)
    ):
        out.extend(page.get("Contents", []))
    return sorted(out, key=lambda o: o["LastModified"], reverse=True)


def list_all_backups(cfg: Config) -> list[dict]:
    prefix = cfg.s3_prefix.rstrip("/") + "/"
    out = []
    for page in (
        _client(cfg).get_paginator("list_objects_v2").paginate(Bucket=cfg.s3_bucket, Prefix=prefix)
    ):
        out.extend(page.get("Contents", []))
    return sorted(out, key=lambda o: o["LastModified"], reverse=True)


def delete_object(cfg: Config, key: str) -> None:
    _client(cfg).delete_object(Bucket=cfg.s3_bucket, Key=key)


def delete_database_backups(cfg: Config, db_id: str) -> list[str]:
    keys = [obj["Key"] for obj in list_backups(cfg, db_id=db_id)]
    for key in keys:
        delete_object(cfg, key)
    return keys


def prune_backups(cfg: Config, older_than: timedelta, *, db_id: str | None = None) -> list[str]:
    cutoff = datetime.now(UTC) - older_than
    keys: list[str] = []
    for obj in list_backups(cfg, db_id=db_id):
        modified = obj["LastModified"]
        if modified.tzinfo is None:
            modified = modified.replace(tzinfo=UTC)
        if modified < cutoff:
            keys.append(obj["Key"])
    return keys
