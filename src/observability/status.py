from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from paths import data_dir


@dataclass
class BackupStatus:
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_key: str | None = None
    last_size_bytes: int | None = None
    last_checksum: str | None = None
    success_streak: int = 0
    failure_streak: int = 0
    last_error: str | None = None


def status_path(db_id: str) -> Path:
    return data_dir() / f".db-toolchain-status-{db_id}.json"


def load_status(db_id: str) -> BackupStatus:
    path = status_path(db_id)
    if not path.is_file():
        return BackupStatus()
    return BackupStatus(**json.loads(path.read_text()))


def save_status(db_id: str, status: BackupStatus) -> None:
    status_path(db_id).write_text(json.dumps(asdict(status), indent=2) + "\n")


def record_success(*, db_id: str, key: str, size_bytes: int, checksum: str) -> BackupStatus:
    status = load_status(db_id)
    status.last_success_at = datetime.now(UTC).isoformat()
    status.last_key = key
    status.last_size_bytes = size_bytes
    status.last_checksum = checksum
    status.success_streak += 1
    status.failure_streak = 0
    status.last_error = None
    save_status(db_id, status)
    return status


def record_failure(db_id: str, error: str) -> BackupStatus:
    status = load_status(db_id)
    status.last_failure_at = datetime.now(UTC).isoformat()
    status.last_error = error
    status.failure_streak += 1
    status.success_streak = 0
    save_status(db_id, status)
    return status
