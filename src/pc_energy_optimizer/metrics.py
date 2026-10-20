"""psutil-backed system metrics. Future telemetry lives here."""
from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import threading
import time

import psutil

log = logging.getLogger(__name__)

# Keep console tools from flashing a window when running under pythonw.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def cpu_percent(sample_seconds: float = 1.0) -> float:
    return psutil.cpu_percent(interval=sample_seconds)


class CpuSampler:
    """Non-blocking CPU percent since the previous call, from cpu_times deltas.

    Kept separate from cpu_percent() so the energy meter's interval and the
    blocking /status sample never disturb each other.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._last = psutil.cpu_times()

    def __call__(self) -> float:
        with self._lock:
            now = psutil.cpu_times()
            last, self._last = self._last, now
        total = sum(now) - sum(last)
        idle = (now.idle - last.idle)
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, (1 - idle / total) * 100))


class GpuPower:
    """Total NVIDIA board power in watts via nvidia-smi, or None."""

    def __init__(self):
        self._exe = shutil.which("nvidia-smi")
        if self._exe is None:
            log.info("nvidia-smi not found; gpu_watts will be null")

    def __call__(self) -> float | None:
        if self._exe is None:
            return None
        try:
            out = subprocess.run(
                [self._exe, "--query-gpu=power.draw",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
                creationflags=NO_WINDOW,
            )
            if out.returncode != 0:
                return None
            return sum(float(line) for line in out.stdout.split())
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None


def uptime_s() -> float:
    return time.time() - psutil.boot_time()


def hostname() -> str:
    return socket.gethostname()
