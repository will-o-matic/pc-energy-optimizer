"""Fire-and-forget event push to a Home Assistant webhook.

Every send runs on its own daemon thread; failures are logged and never
raised. The URL embeds the webhook id, so it is never logged.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from datetime import datetime
from typing import Callable

from . import __version__
from .config import WebhookConfig

log = logging.getLogger(__name__)

FIRST_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 15.0


def _default_post(url: str, body: bytes, timeout: float) -> None:
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout):
        pass


class Notifier:
    def __init__(
        self,
        cfg: WebhookConfig,
        hostname: str,
        post: Callable[[str, bytes, float], None] = _default_post,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._cfg = cfg
        self._hostname = hostname
        self._post = post
        self._sleep = sleep
        self._clock = clock

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.url)

    def payload(self, event: str, **extra) -> dict:
        return {
            "event": event,
            "hostname": self._hostname,
            "version": __version__,
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            **extra,
        }

    def send(self, event: str, retry: bool = False, **extra) -> threading.Thread | None:
        """Post in the background. retry=True keeps trying with backoff for
        retry_seconds (used at start and resume, before the network is up)."""
        if not self.enabled:
            return None
        body = json.dumps(self.payload(event, **extra)).encode()
        t = threading.Thread(
            target=self._deliver, args=(event, body, retry),
            name=f"webhook-{event}", daemon=True,
        )
        t.start()
        return t

    def _deliver(self, event: str, body: bytes, retry: bool) -> None:
        deadline = self._clock() + (self._cfg.retry_seconds if retry else 0)
        backoff = FIRST_BACKOFF_SECONDS
        attempt = 0
        while True:
            attempt += 1
            try:
                self._post(self._cfg.url, body, self._cfg.timeout_seconds)
                log.info("webhook %s delivered (attempt %d)", event, attempt)
                return
            except Exception as e:
                if self._clock() + backoff > deadline:
                    log.warning("webhook %s failed after %d attempt(s): %s",
                                event, attempt, e)
                    return
                log.debug("webhook %s attempt %d failed: %s", event, attempt, e)
            self._sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
