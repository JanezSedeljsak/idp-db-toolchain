from __future__ import annotations

import logging

import httpx

from scripts.config import Config

log = logging.getLogger(__name__)


def notify_failure(cfg: Config, message: str) -> None:
    if not cfg.notify_webhook_url:
        return
    try:
        httpx.post(
            cfg.notify_webhook_url,
            json={"text": message},
            timeout=10,
        ).raise_for_status()
    except Exception as exc:
        log.warning("notification failed: %s", exc)
