"""Whole-system power estimate and cumulative energy. No Windows APIs.

A background thread samples CPU utilisation (and GPU board power when
available) every sample_seconds, turns it into an estimated wall draw and
integrates it into energy_kwh. The total is persisted so it survives agent
restarts; time spent asleep (a wall-clock gap) is never integrated.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from .config import PowerConfig

log = logging.getLogger(__name__)

PERSIST_EVERY_SAMPLES = 30


def estimate_watts(cpu_percent: float, gpu_watts: float | None, cfg: PowerConfig) -> float:
    cpu_frac = min(max(cpu_percent, 0.0), 100.0) / 100.0
    watts = cfg.base_watts + cfg.cpu_watts * cpu_frac ** cfg.cpu_exponent
    if gpu_watts is None:
        watts += cfg.gpu_fallback_watts
    else:
        watts += gpu_watts / cfg.psu_efficiency
    return watts


class EnergyMeter:
    def __init__(
        self,
        cfg: PowerConfig,
        cpu_fn: Callable[[], float],
        gpu_fn: Callable[[], float | None],
        store_path: Path | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self._cfg = cfg
        self._cpu_fn = cpu_fn
        self._gpu_fn = gpu_fn
        self._store = store_path
        self._clock = clock
        self._lock = threading.Lock()
        self._kwh = self._load()
        self._watts = estimate_watts(0.0, None, cfg)
        self._gpu_watts: float | None = None
        self._last = clock()
        self._samples = 0

    def _load(self) -> float:
        if self._store is None or not self._store.is_file():
            return 0.0
        try:
            return float(json.loads(self._store.read_text())["energy_kwh"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.warning("could not read %s (%s), energy_kwh restarts at 0",
                        self._store, e)
            return 0.0

    def persist(self) -> None:
        if self._store is None:
            return
        with self._lock:
            kwh = self._kwh
        try:
            self._store.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._store.with_suffix(".tmp")
            tmp.write_text(json.dumps({"energy_kwh": kwh}))
            os.replace(tmp, self._store)
        except OSError:
            log.exception("could not persist energy to %s", self._store)

    def sample(self) -> None:
        cpu = self._cpu_fn()
        gpu = self._gpu_fn()
        watts = estimate_watts(cpu, gpu, self._cfg)
        with self._lock:
            now = self._clock()
            dt = now - self._last
            self._last = now
            # A gap well past the sample interval means we were asleep:
            # integrate nothing for it rather than the stale wattage.
            if 0 < dt <= self._cfg.sample_seconds * 3:
                # trapezoid between the previous and current estimate
                self._kwh += (self._watts + watts) / 2 * dt / 3_600_000
            self._watts = watts
            self._gpu_watts = gpu
            self._samples += 1
            due = self._samples % PERSIST_EVERY_SAMPLES == 0
        if due:
            self.persist()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "estimated_watts": round(self._watts, 1),
                "gpu_watts": None if self._gpu_watts is None else round(self._gpu_watts, 1),
                "energy_kwh": round(self._kwh, 4),
            }

    def start(self) -> None:
        def loop():
            while True:
                time.sleep(self._cfg.sample_seconds)
                try:
                    self.sample()
                except Exception:
                    log.exception("energy sample failed")

        threading.Thread(target=loop, name="energy-meter", daemon=True).start()
