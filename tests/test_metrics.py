from pathlib import Path
from unittest.mock import patch

from config import Config, DatabaseTarget
from observability.metrics import prometheus_text


def _cfg() -> Config:
    return Config(
        databases=[DatabaseTarget(id="shop", database_url="postgres://localhost/shop")],
        database_id="shop",
        database_url="postgres://localhost/shop",
        s3_bucket="b",
        s3_prefix="backups",
        aws_region="us-east-1",
        aws_endpoint="http://localhost:4566",
        aws_access_key_id="k",
        aws_secret_access_key="s",
        app_env="dev",
        zstd_level=3,
        notify_webhook_url="",
        max_schedule_failures=5,
        slow_query_ms=5000,
        metrics_port=8080,
        anonymize_salt="x",
        backup_cron="0 2 * * *",
        retention_cron="0 3 1 * *",
        config_path=Path("db-toolchain.toml"),
    )


def test_prometheus_exports_readiness_metrics(monkeypatch) -> None:
    monkeypatch.setattr("observability.metrics.load_config", lambda: _cfg())
    monkeypatch.setattr(
        "observability.metrics.persist_metrics",
        lambda _cfg: {
            "database_size_bytes": 1,
            "connection_count": 0,
            "active_queries": 0,
            "backup_failure_streak": 0,
        },
    )

    def fake_status(_db: str):
        return type("S", (), {"failure_streak": 0, "last_error": None, "last_failure_at": None})()

    monkeypatch.setattr("observability.metrics.load_status", fake_status)

    with patch("observability.metrics.readiness") as readiness:
        from observability.health import HealthCheck, HealthReport

        readiness.return_value = HealthReport(
            ok=True,
            checks=[
                HealthCheck(name="database:shop", ok=True),
                HealthCheck(name="s3", ok=True),
            ],
        )
        body = prometheus_text(_cfg())

    assert "db_toolchain_ready 1" in body
    assert 'db_toolchain_readiness_check{check="s3"} 1' in body
    assert "db_toolchain_last_backup_timestamp_seconds" in body
