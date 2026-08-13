"""psutil-backed system metrics. Future telemetry lives here."""
from __future__ import annotations

import socket
import time

import psutil


def cpu_percent(sample_seconds: float = 1.0) -> float:
    return psutil.cpu_percent(interval=sample_seconds)


def uptime_s() -> float:
    return time.time() - psutil.boot_time()


def hostname() -> str:
    return socket.gethostname()
