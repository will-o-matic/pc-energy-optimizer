"""All Windows-only ctypes code. Nothing else in the package touches Win32."""
from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
from ctypes import wintypes

from . import powerreq
from .metrics import NO_WINDOW

log = logging.getLogger(__name__)


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def get_idle_seconds() -> float:
    """Seconds since last keyboard/mouse input in this interactive session."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32")
    lii = _LASTINPUTINFO(cbSize=ctypes.sizeof(_LASTINPUTINFO))
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        log.error("GetLastInputInfo failed: %s", ctypes.get_last_error())
        return 0.0  # fail closed: "just active" so guardrails refuse
    tick = kernel32.GetTickCount()
    # GetTickCount wraps at 49.7 days; unsigned subtraction stays correct
    return ((tick - lii.dwTime) & 0xFFFFFFFF) / 1000.0


def request_sleep() -> bool:
    """Suspend the machine (S3/Modern Standby), not hibernate.

    Direct call with bHibernate=FALSE — do NOT use rundll32, which passes
    garbage args and hibernates instead.
    """
    powrprof = ctypes.WinDLL("PowrProf.dll", use_last_error=True)
    powrprof.SetSuspendState.restype = ctypes.c_ubyte
    powrprof.SetSuspendState.argtypes = [ctypes.c_ubyte] * 3
    ok = powrprof.SetSuspendState(0, 0, 0)
    if not ok:
        log.error("SetSuspendState failed: %s", ctypes.get_last_error())
    return bool(ok)


def log_sleep_states() -> None:
    """Log `powercfg /a` so the log records which sleep states this PC supports."""
    try:
        out = subprocess.run(
            ["powercfg", "/a"], capture_output=True, text=True, timeout=10,
            creationflags=NO_WINDOW,
        ).stdout.strip()
        log.info("powercfg /a:\n%s", out)
    except Exception:
        log.exception("could not run powercfg /a")


def get_power_requests() -> list[dict] | None:
    """All active power requests from `powercfg /requests`, or None if they
    can't be read (it needs an elevated process)."""
    try:
        out = subprocess.run(
            ["powercfg", "/requests"], capture_output=True, text=True,
            timeout=10, creationflags=NO_WINDOW,
        )
    except Exception:
        log.exception("could not run powercfg /requests")
        return None
    if out.returncode != 0:
        log.warning("powercfg /requests failed (exit %s, needs admin): %s",
                    out.returncode, (out.stdout or out.stderr).strip())
        return None
    return powerreq.parse(out.stdout)


def own_exe() -> str:
    return sys.executable
