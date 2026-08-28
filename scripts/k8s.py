"""Minimal k8s helpers: apply manifests and wait. Services use NodePort (no port-forward)."""

from __future__ import annotations

import subprocess

NS = "idp-db-backupper"


def up() -> None:
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
