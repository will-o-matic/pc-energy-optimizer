"""Entry point: config -> logging -> providers -> retry-bind -> serve_forever."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from . import __version__, metrics, winapi
from .config import ConfigError, load_config
from .logging_setup import setup_logging
from .server import create_server

log = logging.getLogger("pc_energy_optimizer")

BIND_RETRY_SECONDS = 5
BIND_RETRY_LIMIT_SECONDS = 600


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    try:
        cfg = load_config(project_root / "config.toml")
    except ConfigError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1

    setup_logging(cfg.logging.level, project_root / "logs")
    log.info("pc-energy-optimizer %s starting", __version__)
    winapi.log_sleep_states()

    def cpu_fn() -> float:
        return metrics.cpu_percent(cfg.guardrails.cpu_sample_seconds)

    # Retry bind: at logon tailscaled may not have brought the tailnet IP up yet.
    deadline = time.monotonic() + BIND_RETRY_LIMIT_SECONDS
    while True:
        try:
            srv = create_server(
                cfg,
                idle_fn=winapi.get_idle_seconds,
                cpu_fn=cpu_fn,
                sleep_fn=winapi.request_sleep,
            )
            break
        except OSError as e:
            if time.monotonic() >= deadline:
                log.error("could not bind %s:%s after %ss, giving up: %s",
                          cfg.server.bind_host, cfg.server.port,
                          BIND_RETRY_LIMIT_SECONDS, e)
                return 1
            log.warning("bind %s:%s failed (%s), retrying in %ss",
                        cfg.server.bind_host, cfg.server.port, e,
                        BIND_RETRY_SECONDS)
            time.sleep(BIND_RETRY_SECONDS)

    log.info("listening on http://%s:%s", cfg.server.bind_host, cfg.server.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("interrupted, shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
