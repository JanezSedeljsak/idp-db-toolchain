"""Setup wizard."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import httpx

from config import ensure_dev_config, load_config
from db.dev_schema import apply_dev_schema
from db.session import ping, session
from ops import k8s, seed
from storage import s3


def _ensure_env_file() -> None:
    env_path = Path.cwd() / ".env"
    example = Path.cwd() / ".env.example"
    if env_path.is_file() or not example.is_file():
        return
    shutil.copy2(example, env_path)
    print(f"wrote {env_path} from .env.example")


def run(
    *, yes: bool = False, force: bool = False, skip_k8s: bool = False, do_seed: bool = False
) -> None:
    if not shutil.which("kubectl"):
        raise RuntimeError("kubectl not found")

    config_path = Path.cwd() / "backupper.toml"
    if config_path.exists() and not force:
        raise RuntimeError(f"{config_path} exists — use --force to re-copy defaults")

    if config_path.exists() and force:
        backup_path = config_path.with_suffix(".toml.bak")
        shutil.copy2(config_path, backup_path)
        print(f"backed up existing backupper.toml -> {backup_path}")

    if not config_path.exists() or force:
        ensure_dev_config(force=force)
        print(f"wrote {config_path}")

    _ensure_env_file()

    if not yes:
        cfg = load_config()
        bucket = input(f"S3 bucket [{cfg.s3_bucket}]: ").strip()
        if bucket and bucket != cfg.s3_bucket:
            text = config_path.read_text()
            config_path.write_text(
                text.replace(f'bucket = "{cfg.s3_bucket}"', f'bucket = "{bucket}"')
            )
        if not do_seed:
            do_seed = input("Seed sample data? (y/N): ").strip().lower() in ("y", "yes")

    if skip_k8s:
        print("skipped k8s — run: uv run python manage.py k8s-up")
        return

    print("starting k8s...")
    k8s.up()
    _wait()
    cfg = load_config()
    s3.ensure_bucket(cfg)
    apply_dev_schema()
    if do_seed:
        for target in cfg.databases:
            with session(target.database_url) as s:
                seed.run(s)
    print("setup done")


def _wait(timeout: int = 180) -> None:
    cfg = load_config()
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            httpx.get(f"{cfg.aws_endpoint}/_localstack/health", timeout=2).raise_for_status()
            ping(cfg.database_url)
            return
        except Exception as exc:
            last_err = exc
            time.sleep(2)
    hint = " (on kind: create cluster with k8s/kind-config.yaml)"
    detail = f": {last_err}" if last_err else ""
    raise TimeoutError(f"postgres or localstack not ready{detail}{hint}")
