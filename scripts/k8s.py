from __future__ import annotations

import os
import subprocess

NS = "idp-db-backupper"
IMAGE = "idp-db-backupper:local"
KIND_CLUSTER = "idp-db-backupper"


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


def up(*, build_image_first: bool = False) -> None:
    if build_image_first:
        build_image()
        load_image()
    subprocess.run(["kubectl", "apply", "-k", "k8s"], check=True)
    subprocess.run(
        [
            "kubectl",
            "wait",
            "-n",
            NS,
            "--for=condition=ready",
            "pod",
            "-l",
            "app.kubernetes.io/part-of=idp-db-backupper",
            "--timeout=180s",
        ],
        check=True,
    )


def down() -> None:
    subprocess.run(["kubectl", "delete", "-k", "k8s", "--ignore-not-found"], check=True)
