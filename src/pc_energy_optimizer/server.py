"""HTTP API: routing, bearer auth, JSON responses.

Providers (idle_fn, cpu_fn, sleep_fn, since_wake_fn, power_fn,
power_requests_fn) and the on_sleep hook are injected so tests never touch
Windows APIs or the network.
"""
from __future__ import annotations

import hmac
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from . import __version__, metrics
from .config import Config
from .guardrails import evaluate

log = logging.getLogger(__name__)

FEATURES = ["since_wake", "webhook", "power_estimate", "power_request"]


def create_server(
    cfg: Config,
    idle_fn: Callable[[], float],
    cpu_fn: Callable[[], float],
    sleep_fn: Callable[[], bool],
    since_wake_fn: Callable[[], float],
    power_fn: Callable[[], dict],
    power_requests_fn: Callable[[], list[dict] | None] = lambda: None,
    on_sleep: Callable[[bool], None] = lambda forced: None,
) -> ThreadingHTTPServer:
    token = cfg.server.token

    class Handler(BaseHTTPRequestHandler):
        server_version = f"pc-energy-optimizer/{__version__}"

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization", "")
            supplied = header.removeprefix("Bearer ")
            return hmac.compare_digest(supplied.encode(), token.encode())

        def do_GET(self):
            if self.path == "/health":
                self._send_json(
                    200,
                    {"status": "ok", "version": __version__, "features": FEATURES},
                )
                return
            if self.path == "/status":
                if not self._authorized():
                    self._send_json(401, {"error": "unauthorized"})
                    return
                self._send_json(
                    200,
                    {
                        "hostname": metrics.hostname(),
                        "idle_s": idle_fn(),
                        "cpu_percent": cpu_fn(),
                        "uptime_s": metrics.uptime_s(),
                        "since_wake_s": since_wake_fn(),
                        **power_fn(),
                        "version": __version__,
                    },
                )
                return
            if self.path == "/sleep":
                self._send_json(405, {"error": "method not allowed"})
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/sleep":
                self._send_json(404, {"error": "not found"})
                return
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return

            force = False
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                try:
                    payload = json.loads(self.rfile.read(length))
                    force = bool(payload.get("force", False))
                except (json.JSONDecodeError, AttributeError):
                    self._send_json(400, {"error": "invalid JSON body"})
                    return

            decision = evaluate(
                idle_s=idle_fn(),
                cpu_percent=cpu_fn(),
                cfg=cfg.guardrails,
                force=force,
                since_wake_s=since_wake_fn(),
                # powercfg takes a moment; don't bother when forcing
                power_requests=None if force else power_requests_fn(),
            )
            if not decision.allowed:
                log.info("sleep refused: %s", decision.reasons)
                self._send_json(
                    409, {"result": "refused", "reasons": decision.reasons}
                )
                return

            delay = cfg.sleep.response_delay_seconds
            log.info("sleep accepted (forced=%s), suspending in %ss", force, delay)
            try:
                # announce first; it must never delay or block the suspend
                on_sleep(force)
            except Exception:
                log.exception("on_sleep hook failed")
            threading.Timer(delay, _do_sleep).start()
            self._send_json(
                202, {"result": "sleeping", "delay_s": delay, "forced": force}
            )

    def _do_sleep():
        try:
            if not sleep_fn():
                log.error("sleep_fn reported failure")
        except Exception:
            log.exception("sleep_fn raised")

    return ThreadingHTTPServer((cfg.server.bind_host, cfg.server.port), Handler)
