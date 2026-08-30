from __future__ import annotations

import os
import subprocess

NS = "idp-db-backupper"
IMAGE = "idp-db-backupper:local"
KIND_CLUSTER = "idp-db-backupper"

_INFRA_SELECTORS = ("app=postgres", "app=localstack")
_WAIT_TIMEOUT = "300s"


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


def _wait_ready(selector: str) -> None:
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
            f"--timeout={_WAIT_TIMEOUT}",
        ],
        check=True,
    )


def up(*, build_image_first: bool = False) -> None:
    if build_image_first:
        build_image()
        load_image()
    subprocess.run(["kubectl", "apply", "-k", "k8s"], check=True)
    for selector in _INFRA_SELECTORS:
        _wait_ready(selector)


def down() -> None:
    subprocess.run(["kubectl", "delete", "-k", "k8s", "--ignore-not-found"], check=True)
