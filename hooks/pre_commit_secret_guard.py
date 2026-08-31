#!/usr/bin/env python3
"""Block committing env secret files and obvious hardcoded credentials."""

from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN_ENV_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.prod",
        ".env.production",
        ".env.staging",
        ".env.dev",
    }
)

SKIP_BASENAMES = frozenset(
    {
        ".env.example",
        "uv.lock",
        "pre_commit_secret_guard.py",
    }
)

SKIP_SUFFIXES = frozenset(
    {
        ".lock",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".zip",
        ".gz",
        ".tar",
        ".jar",
        ".woff",
        ".woff2",
    }
)

ALLOWLIST_SUBSTRINGS = (
    "changeme",
    "example",
    "your-",
    "placeholder",
    "replace",
    "account_id",
    "${",
    "<",
    "xxx",
    "dummy",
    "not-a-real",
    "os.getenv",
    "os.environ",
    "getenv(",
    "typer.option",
    "envvar=",
    "secretkeyref",
    "secretref",
    "valuefrom",
    "optional: true",
)

SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r'(?i)(api[_-]?key|secret[_-]?key|private[_-]?key)\s*[:=]\s*["\'][^"\']{12,}["\']'
        ),
        "hardcoded api/secret key",
    ),
    (
        re.compile(
            r'(?i)(password|passwd|auth[_-]?token|access[_-]?token)\s*[:=]\s*["\'][^"\']{8,}["\']'
        ),
        "hardcoded password/token",
    ),
    (
        re.compile(r'(?i)AWS_SECRET_ACCESS_KEY\s*=\s*["\']?(?!test\b)[A-Za-z0-9/+=]{20,}'),
        "AWS secret access key",
    ),
    (
        re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
        "private key PEM block",
    ),
)

DEPLOY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?im)^\s*COPY\s+\.env(?:\s|$)"), "Dockerfile copies .env"),
    (re.compile(r"(?im)^\s*ADD\s+\.env(?:\s|$)"), "Dockerfile adds .env"),
)


def is_forbidden_env(path: Path) -> bool:
    name = path.name
    if name in FORBIDDEN_ENV_NAMES:
        return True
    return name.startswith(".env.") and name != ".env.example"


def should_skip(path: Path) -> bool:
    if path.name in SKIP_BASENAMES:
        return True
    return path.suffix.lower() in SKIP_SUFFIXES


def line_allowed(line: str) -> bool:
    lowered = line.lower()
    return any(fragment in lowered for fragment in ALLOWLIST_SUBSTRINGS)


def check_file(path: Path) -> list[str]:
    errors: list[str] = []

    if is_forbidden_env(path):
        return [f"{path}: refusing to commit env secret file (use .env.example for templates)"]

    if should_skip(path):
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    rel = path.as_posix()
    is_deploy = path.name == "Dockerfile"

    if is_deploy:
        for pattern, label in DEPLOY_PATTERNS:
            if pattern.search(text):
                if ".env.example" in pattern.pattern:
                    continue
                if label.startswith("compose") and ".env.example" in text:
                    continue
                errors.append(f"{rel}: {label}")

    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_allowed(line):
            continue
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(line):
                errors.append(f"{rel}:{lineno}: possible {label}")
                break

    return errors


def main(argv: list[str]) -> int:
    errors: list[str] = []
    for arg in argv:
        path = Path(arg)
        if not path.is_file():
            continue
        errors.extend(check_file(path))

    if not errors:
        return 0

    print("secret guard: blocked commit\n", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    print(
        "\nUse .env.example for templates; keep real secrets in .env (gitignored) "
        "or a secret manager.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
