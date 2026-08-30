from __future__ import annotations

import os
import subprocess
import sys

NS = "idp-db-backupper"
IMAGE = "idp-db-backupper:local"
KIND_CLUSTER = "idp-db-backupper"

_WAIT_TIMEOUT = "300s"
_INFRA_SELECTORS = (
    ("app=postgres", "600s"),
    ("app=localstack", _WAIT_TIMEOUT),
)


def build_image() -> None:
    subprocess.run(
        ["docker", "build", "-t", IMAGE, "."],
        check=True,
        env={**os.environ, "DOCKER_BUILDKIT": "1"},
    )


def load_image(cluster: str = KIND_CLUSTER) -> None:
    subprocess.run(
        ["kind", "load", "docker-image", IMAGE, "--name", cluster],
        check=True,
    )


def _diagnose_wait_failure(selector: str) -> None:
    for args in (
        ["kubectl", "get", "pods", "-n", NS, "-l", selector, "-o", "wide"],
        ["kubectl", "describe", "pods", "-n", NS, "-l", selector],
        [
            "kubectl",
            "logs",
            "-n",
            NS,
            "-l",
            selector,
            "--all-containers",
            "--tail=80",
        ],
    ):
        subprocess.run(args, check=False)


def _wait_ready(selector: str, *, timeout: str = _WAIT_TIMEOUT) -> None:
    try:
        subprocess.run(
            [
                "kubectl",
                "wait",
                "-n",
                NS,
                "--for=condition=ready",
                "pod",
                "-l",
                selector,
                f"--timeout={timeout}",
            ],
            check=True,
        )
    except subprocess.CalledProcessError:
        print(f"kubectl wait timed out for selector {selector!r}", file=sys.stderr)
        _diagnose_wait_failure(selector)
        raise


def up(*, build_image_first: bool = False) -> None:
    if build_image_first:
        build_image()
        load_image()
    subprocess.run(["kubectl", "apply", "-k", "k8s"], check=True)
    for selector, timeout in _INFRA_SELECTORS:
        _wait_ready(selector, timeout=timeout)


def down() -> None:
    subprocess.run(["kubectl", "delete", "-k", "k8s", "--ignore-not-found"], check=True)
