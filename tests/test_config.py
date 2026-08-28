from pathlib import Path

from scripts.config import load_env, write_env


def test_env_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    write_env({"S3_BUCKET": "test-bucket", "DATABASE_URL": "postgres://localhost/db"})
    load_env()
    import os

    assert os.environ["S3_BUCKET"] == "test-bucket"
