from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import Config, cfg_for_db, load_config
from db.session import session
from observability.health import readiness
from observability.status import load_status
from paths import data_dir


def metrics_path(db_id: str) -> Path:
    return data_dir() / f".db-toolchain-metrics-{db_id}.json"


def slow_queries_path(db_id: str) -> Path:
    return data_dir() / f".db-toolchain-slow-queries-{db_id}.jsonl"


def collect_db_metrics(sess: Session, *, db_id: str) -> dict[str, Any]:
    db_size = sess.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
    connections = sess.execute(
        text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
    ).scalar_one()
    active = sess.execute(
        text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
    ).scalar_one()
    table_rows = sess.execute(
        text(
            """
            SELECT relname, n_live_tup
            FROM pg_stat_user_tables
            ORDER BY n_live_tup DESC
            LIMIT 20
            """
        )
    ).fetchall()

    return {
        "database_id": db_id,
        "collected_at": datetime.now(UTC).isoformat(),
        "database_size_bytes": int(db_size),
        "connection_count": int(connections),
        "active_queries": int(active),
        "table_row_estimates": {name: int(rows) for name, rows in table_rows},
    }


def collect_slow_queries(sess: Session, *, min_ms: int, db_id: str) -> list[dict[str, Any]]:
    min_secs = min_ms / 1000
    rows = sess.execute(
        text(
            """
            SELECT pid,
                   EXTRACT(EPOCH FROM (now() - query_start)) * 1000 AS duration_ms,
                   left(query, 1000) AS query,
                   state,
                   usename
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid()
              AND state <> 'idle'
              AND query NOT ILIKE '%pg_stat_activity%'
              AND now() - query_start > make_interval(secs => :min_secs)
            ORDER BY duration_ms DESC
            """
        ),
        {"min_secs": min_secs},
    ).fetchall()

    found = [
        {
            "database_id": db_id,
            "collected_at": datetime.now(UTC).isoformat(),
            "pid": row[0],
            "duration_ms": float(row[1]),
            "query": row[2],
            "state": row[3],
            "user": row[4],
        }
        for row in rows
    ]

    try:
        stmt_rows = sess.execute(
            text(
                """
                SELECT left(query, 1000),
                       round(mean_exec_time::numeric, 2),
                       calls
                FROM pg_stat_statements
                WHERE mean_exec_time >= :min_ms
                ORDER BY mean_exec_time DESC
                LIMIT 20
                """
            ),
            {"min_ms": min_ms},
        ).fetchall()
        for query, mean_ms, calls in stmt_rows:
            found.append(
                {
                    "database_id": db_id,
                    "collected_at": datetime.now(UTC).isoformat(),
                    "source": "pg_stat_statements",
                    "duration_ms": float(mean_ms),
                    "calls": int(calls),
                    "query": query,
                }
            )
    except Exception:
        pass

    return found


def persist_metrics(cfg: Config) -> dict[str, Any]:
    st = load_status(cfg.database_id)
    with session(cfg.database_url) as sess:
        metrics = collect_db_metrics(sess, db_id=cfg.database_id)
    metrics["last_backup_key"] = st.last_key
    metrics["last_backup_at"] = st.last_success_at
    metrics["backup_failure_streak"] = st.failure_streak
    metrics_path(cfg.database_id).write_text(json.dumps(metrics, indent=2) + "\n")
    return metrics


def persist_slow_queries(cfg: Config) -> list[dict[str, Any]]:
    with session(cfg.database_url) as sess:
        slow = collect_slow_queries(sess, min_ms=cfg.slow_query_ms, db_id=cfg.database_id)
    if slow:
        with slow_queries_path(cfg.database_id).open("a") as fh:
            for row in slow:
                fh.write(json.dumps(row, default=str) + "\n")
    return slow


def _append_readiness_metrics(lines: list[str], cfg: Config) -> None:
    report = readiness(cfg)
    lines.extend(
        [
            "# HELP db_toolchain_ready 1 when all readiness checks pass",
            "# TYPE db_toolchain_ready gauge",
            f"db_toolchain_ready {1 if report.ok else 0}",
        ]
    )
    for check in report.checks:
        safe_name = check.name.replace("\\", "\\\\").replace('"', '\\"')
        value = 1 if check.ok else 0
        lines.extend(
            [
                "# HELP db_toolchain_readiness_check Per-check readiness (1=ok)",
                "# TYPE db_toolchain_readiness_check gauge",
                f'db_toolchain_readiness_check{{check="{safe_name}"}} {value}',
            ]
        )


def _s3_error_active(status) -> int:
    if status.failure_streak <= 0 or not status.last_error:
        return 0
    err = status.last_error.lower()
    tokens = ("s3", "bucket", "upload", "boto3", "aws", "head_bucket")
    return int(any(token in err for token in tokens))


def prometheus_text(cfg: Config) -> str:
    root = load_config()
    lines: list[str] = []
    _append_readiness_metrics(lines, root)
    for target in root.databases:
        db_cfg = cfg_for_db(root, target.id)
        metrics = persist_metrics(db_cfg)
        status = load_status(target.id)
        db = target.id
        size = metrics["database_size_bytes"]
        streak = metrics.get("backup_failure_streak", 0)
        lines.extend(
            [
                "# HELP db_toolchain_database_size_bytes Postgres database size",
                "# TYPE db_toolchain_database_size_bytes gauge",
                f'db_toolchain_database_size_bytes{{database="{db}"}} {size}',
                "# HELP db_toolchain_connections Active connections to this database",
                "# TYPE db_toolchain_connections gauge",
                f'db_toolchain_connections{{database="{db}"}} {metrics["connection_count"]}',
                "# HELP db_toolchain_active_queries Currently active queries",
                "# TYPE db_toolchain_active_queries gauge",
                f'db_toolchain_active_queries{{database="{db}"}} {metrics["active_queries"]}',
                "# HELP db_toolchain_backup_failure_streak Consecutive backup failures",
                "# TYPE db_toolchain_backup_failure_streak gauge",
                f'db_toolchain_backup_failure_streak{{database="{db}"}} {streak}',
                "# HELP db_toolchain_last_backup_timestamp_seconds Last successful backup unix time",
                "# TYPE db_toolchain_last_backup_timestamp_seconds gauge",
            ]
        )
        backup_ts = 0.0
        if metrics.get("last_backup_at"):
            backup_ts = datetime.fromisoformat(metrics["last_backup_at"]).timestamp()
        lines.append(f'db_toolchain_last_backup_timestamp_seconds{{database="{db}"}} {backup_ts}')
        if status.last_failure_at:
            fail_ts = datetime.fromisoformat(status.last_failure_at).timestamp()
            lines.extend(
                [
                    "# HELP db_toolchain_last_failure_timestamp_seconds Last backup failure unix time",
                    "# TYPE db_toolchain_last_failure_timestamp_seconds gauge",
                    f'db_toolchain_last_failure_timestamp_seconds{{database="{db}"}} {fail_ts}',
                ]
            )
        lines.extend(
            [
                "# HELP db_toolchain_s3_backup_error 1 when the latest failure looks S3-related",
                "# TYPE db_toolchain_s3_backup_error gauge",
                f'db_toolchain_s3_backup_error{{database="{db}"}} {_s3_error_active(status)}',
            ]
        )
    return "\n".join(lines) + "\n"
