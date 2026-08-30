from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paths import data_dir


@dataclass
class JobRecord:
    id: str
    name: str
    status: str
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    details: dict[str, Any] | None = None


def jobs_log_path() -> Path:
    return data_dir() / ".backupper-jobs.jsonl"


def append_job(record: JobRecord) -> None:
    with jobs_log_path().open("a") as fh:
        fh.write(json.dumps(asdict(record), default=str) + "\n")


@contextmanager
def job_run(name: str, **details: Any) -> Iterator[JobRecord]:
    record = JobRecord(
        id=uuid.uuid4().hex[:12],
        name=name,
        status="running",
        started_at=datetime.now(UTC).isoformat(),
        details=details or None,
    )
    append_job(record)
    try:
        yield record
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)
        record.finished_at = datetime.now(UTC).isoformat()
        append_job(record)
        raise
    else:
        record.status = "success"
        record.finished_at = datetime.now(UTC).isoformat()
        append_job(record)


def list_jobs(*, limit: int = 50) -> list[JobRecord]:
    path = jobs_log_path()
    if not path.is_file():
        return []
    lines = path.read_text().splitlines()
    out: list[JobRecord] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        data = json.loads(line)
        out.append(JobRecord(**data))
    return out


def run_named(name: str, fn: Callable[[], Any], **details: Any) -> Any:
    with job_run(name, **details):
        return fn()
