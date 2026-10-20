"""Entry point: config -> logging -> providers -> retry-bind -> serve_forever."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from . import __version__, metrics, powerreq, winapi
from .config import ConfigError, load_config
from .energy import EnergyMeter
from .logging_setup import setup_logging
from .server import create_server
from .wake import WakeTracker
from .webhook import Notifier

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

    notifier = Notifier(cfg.webhook, metrics.hostname())
    log.info("webhook push %s", "enabled" if notifier.enabled else "disabled")

    meter = EnergyMeter(
        cfg.power,
        cpu_fn=metrics.CpuSampler(),
        gpu_fn=metrics.GpuPower(),
        store_path=project_root / "state" / "energy.json",
    )
    meter.start()

    def on_wake(slept_s: float) -> None:
        # the network is usually not back yet at resume, hence retry
        notifier.send("woke", retry=True, slept_s=round(slept_s, 1))

    def on_sleep(forced: bool) -> None:
        meter.persist()
        notifier.send("sleeping", forced=forced)

    def power_requests_fn():
        reqs = winapi.get_power_requests()
        if reqs is None:
            return None  # unreadable: skip the check rather than refuse
        return powerreq.blocking(
            reqs,
            cfg.guardrails.power_request_types,
            cfg.guardrails.ignore_power_requests,
            own_exe=winapi.own_exe(),
        )

    wake = WakeTracker(on_wake=on_wake)
    wake.start()

    # Retry bind: at logon tailscaled may not have brought the tailnet IP up yet.
    deadline = time.monotonic() + BIND_RETRY_LIMIT_SECONDS
    while True:
        try:
            srv = create_server(
                cfg,
                idle_fn=winapi.get_idle_seconds,
                cpu_fn=cpu_fn,
                sleep_fn=winapi.request_sleep,
                since_wake_fn=wake.seconds_since_wake,
                power_fn=meter.snapshot,
                power_requests_fn=power_requests_fn,
                on_sleep=on_sleep,
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
    notifier.send("started", retry=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("interrupted, shutting down")
        meter.persist()
    return 0


if __name__ == "__main__":
    sys.exit(main())
