from pathlib import Path

from observability.health import liveness, readiness


def test_liveness() -> None:
    report = liveness()
    assert report.ok
    assert report.checks[0].name == "process"


def test_readiness_all_ok(monkeypatch) -> None:
    monkeypatch.setattr("observability.health.ping", lambda _url: None)
    monkeypatch.setattr("observability.health.s3.check_reachable", lambda _cfg: None)

    from config import Config, DatabaseTarget

    cfg = Config(
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
        config_path=Path("backupper.toml"),
    )
    report = readiness(cfg)
    assert report.ok
    assert len(report.checks) == 2


def test_readiness_db_failure(monkeypatch) -> None:
    def fail_ping(_url: str) -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr("observability.health.ping", fail_ping)
    monkeypatch.setattr("observability.health.s3.check_reachable", lambda _cfg: None)

    from config import Config, DatabaseTarget

    cfg = Config(
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
        config_path=Path("backupper.toml"),
    )
    report = readiness(cfg)
    assert not report.ok
    assert report.checks[0].name == "database:shop"
    assert not report.checks[0].ok
