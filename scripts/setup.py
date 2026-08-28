"""Setup wizard."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import httpx

from scripts import k8s, s3, seed
from scripts.config import DEFAULTS, load_config, load_env, write_env
from scripts.database import migrate, ping, session


def run(
    *, yes: bool = False, force: bool = False, skip_k8s: bool = False, do_seed: bool = False
) -> None:
    if not shutil.which("kubectl"):
        raise RuntimeError("kubectl not found")

    env_path = Path.cwd() / ".env"
    if env_path.exists() and not force:
        raise RuntimeError(f"{env_path} exists — use --force")

    values = dict(DEFAULTS)
    if not yes:
        print("press Enter for defaults")
        bucket = input(f"S3 bucket [{values['S3_BUCKET']}]: ").strip()
        if bucket:
            values["S3_BUCKET"] = bucket
        if not do_seed:
            do_seed = input("Seed sample data? (y/N): ").strip().lower() in ("y", "yes")

    write_env(values)
    load_env()
    print(f"wrote {env_path}")

    if skip_k8s:
        print("skipped k8s — run: uv run python manage.py k8s-up")
        return

    print("starting k8s...")
    k8s.up()
    _wait()
    cfg = load_config()
    s3.ensure_bucket(cfg)
    migrate()
    if do_seed:
        with session(cfg.database_url) as s:
            seed.run(s)
    print("setup done")


def _wait(timeout: int = 180) -> None:
    cfg = load_config()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(f"{cfg.aws_endpoint}/_localstack/health", timeout=2).raise_for_status()
            ping(cfg.database_url)
            return
        except Exception:
            time.sleep(2)
    raise TimeoutError("postgres or localstack not ready")
