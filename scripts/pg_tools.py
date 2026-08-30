from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from sqlalchemy import text

from scripts.database import get_engine


def _require_pg_bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} not found — install postgresql-client")
    return path


def parse_pg_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError(f"unsupported database URL scheme: {parsed.scheme}")
    dbname = parsed.path.lstrip("/") or "postgres"
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": dbname,
        "sslmode": params.get("sslmode", "prefer"),
    }


def _conn_env(conn: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    if conn["password"]:
        env["PGPASSWORD"] = conn["password"]
    return env


def _pg_dump_args(conn: dict[str, str]) -> list[str]:
    return [
        _require_pg_bin("pg_dump"),
        "-Fc",
        "--no-owner",
        "--no-acl",
        "-h",
        conn["host"],
        "-p",
        conn["port"],
        "-U",
        conn["user"],
        "-d",
        conn["dbname"],
    ]


def _pg_restore_args(conn: dict[str, str], *, clean: bool = True) -> list[str]:
    args = [
        _require_pg_bin("pg_restore"),
        "--no-owner",
        "--no-acl",
        "--single-transaction",
        "-h",
        conn["host"],
        "-p",
        conn["port"],
        "-U",
        conn["user"],
        "-d",
        conn["dbname"],
    ]
    if clean:
        args.append("--clean")
        args.append("--if-exists")
    return args


def dump_to_file(database_url: str, path: str) -> None:
    conn = parse_pg_url(database_url)
    env = _conn_env(conn)
    result = subprocess.run(_pg_dump_args(conn), env=env, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode().strip() or "pg_dump failed")
    Path(path).write_bytes(result.stdout)


def restore_from_file(database_url: str, path: str) -> None:
    conn = parse_pg_url(database_url)
    env = _conn_env(conn)
    with Path(path).open("rb") as fh:
        result = subprocess.run(
            _pg_restore_args(conn),
            env=env,
            stdin=fh,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode != 0:
        stderr = result.stderr.decode().strip()
        if result.returncode != 1 or "error" in stderr.lower():
            raise RuntimeError(stderr or "pg_restore failed")


@contextmanager
def stream_dump(database_url: str) -> Iterator[Iterator[bytes]]:
    conn = parse_pg_url(database_url)
    env = _conn_env(conn)
    proc = subprocess.Popen(
        _pg_dump_args(conn),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def _iter() -> Iterator[bytes]:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            yield chunk

    try:
        yield _iter()
        proc.wait()
        if proc.returncode != 0:
            err = (proc.stderr.read() if proc.stderr else b"").decode().strip()
            raise RuntimeError(err or "pg_dump failed")
    finally:
        if proc.poll() is None:
            proc.kill()


def stream_restore(database_url: str, chunks: Iterator[bytes]) -> None:
    conn = parse_pg_url(database_url)
    env = _conn_env(conn)
    proc = subprocess.Popen(
        _pg_restore_args(conn),
        env=env,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None
    try:
        for chunk in chunks:
            proc.stdin.write(chunk)
        proc.stdin.close()
        proc.wait()
        if proc.returncode not in (0, 1):
            err = (proc.stderr.read() if proc.stderr else b"").decode().strip()
            raise RuntimeError(err or "pg_restore failed")
        if proc.returncode == 1:
            err = (proc.stderr.read() if proc.stderr else b"").decode().strip()
            if err and "error" in err.lower():
                raise RuntimeError(err)
    finally:
        if proc.poll() is None:
            proc.kill()


def admin_database_url(database_url: str) -> str:
    conn = parse_pg_url(database_url)
    conn["dbname"] = "postgres"
    return (
        f"postgresql://{conn['user']}:{conn['password']}@"
        f"{conn['host']}:{conn['port']}/{conn['dbname']}?sslmode={conn['sslmode']}"
    )


def ensure_database(database_url: str, name: str) -> None:
    admin = admin_database_url(database_url)
    safe = name.replace('"', "")
    engine = get_engine(admin)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": safe},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{safe}"'))


def drop_database(database_url: str, name: str) -> None:
    admin = admin_database_url(database_url)
    safe = name.replace('"', "")
    engine = get_engine(admin)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(
            text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = :name AND pid <> pg_backend_pid()
                """
            ),
            {"name": safe},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{safe}"'))


def database_url_with_name(database_url: str, name: str) -> str:
    conn = parse_pg_url(database_url)
    safe = name.replace('"', "")
    return (
        f"postgresql://{conn['user']}:{conn['password']}@"
        f"{conn['host']}:{conn['port']}/{safe}?sslmode={conn['sslmode']}"
    )


@contextmanager
def temp_dump_file(database_url: str) -> Iterator[str]:
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as fh:
        path = fh.name
    try:
        dump_to_file(database_url, path)
        yield path
    finally:
        Path(path).unlink(missing_ok=True)
