"""Detect resume-from-sleep with a wall-clock heartbeat. No Windows APIs.

A process can't run while the machine is suspended, so a heartbeat that
ticks every few seconds sees the wall clock jump forward by the sleep
duration. Any gap well beyond the tick interval is treated as a wake.
Process start also counts as a wake (the PC just booted or logged on).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

TICK_SECONDS = 5.0
GAP_SECONDS = 30.0


class WakeTracker:
    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        gap_s: float = GAP_SECONDS,
        on_wake: Callable[[float], None] | None = None,
    ):
        self._clock = clock
        self._gap_s = gap_s
        self._on_wake = on_wake
        self._lock = threading.Lock()
        now = clock()
        self._last_tick = now
        self._woke_at = now

    def tick(self) -> None:
        woke = False
        with self._lock:
            now = self._clock()
            gap = now - self._last_tick
            if gap > self._gap_s:
                self._woke_at = now
                woke = True
                log.info("resume from sleep detected (clock gap %.0fs)", gap)
            self._last_tick = now
        # outside the lock: the callback may call back into the tracker
        if woke and self._on_wake is not None:
            try:
                self._on_wake(gap)
            except Exception:
                log.exception("on_wake callback failed")

    def seconds_since_wake(self) -> float:
        # Tick first so a request arriving right after resume, before the
        # heartbeat thread has run, still sees the wake.
        self.tick()
        with self._lock:
            return max(0.0, self._clock() - self._woke_at)

    def start(self, interval_s: float = TICK_SECONDS) -> None:
        def loop():
            while True:
                time.sleep(interval_s)
                self.tick()

        threading.Thread(target=loop, name="wake-heartbeat", daemon=True).start()
