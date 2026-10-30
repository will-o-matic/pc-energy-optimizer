"""Detect sleep attempts that didn't suspend. No Windows APIs.

Windows logs Kernel-Power events to the System log for every sleep attempt,
whoever started it (this agent, the Start menu, the power button):

    187  a process called SetSuspendState/SetSystemPowerState (has its PID)
     59  the system entered Away Mode instead of sleeping
     42  the system is entering sleep (written just before suspend)

SetSuspendState still returns success when Windows turns the request into
Away Mode, so the only reliable signal is what follows the 187. Each
attempt gets window_s seconds; if neither a 42 nor a resume (clock gap)
arrives, it is reported once as a failed sleep.
"""
from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger(__name__)

EV_SLEEP = 42
EV_AWAY_MODE = 59
EV_ATTEMPT = 187

WINDOW_SECONDS = 20.0
POLL_SECONDS = 5.0

_NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}


def parse_events_xml(text: str) -> list[dict]:
    """wevtutil /f:xml output (concatenated <Event> elements) as
    {"record_id", "event_id", "pid", "caller"} dicts, oldest first."""
    if not text.strip():
        return []
    root = ET.fromstring(f"<Events>{text}</Events>")
    out = []
    for ev in root.findall("e:Event", _NS):
        system = ev.find("e:System", _NS)
        execution = system.find("e:Execution", _NS)
        caller = ""
        for data in ev.findall("e:EventData/e:Data", _NS):
            if data.get("Name") == "ApiCallerName":
                caller = data.text or ""
        out.append({
            "record_id": int(system.findtext("e:EventRecordID", namespaces=_NS)),
            "event_id": int(system.findtext("e:EventID", namespaces=_NS)),
            "pid": int(execution.get("ProcessID", "0")) if execution is not None else 0,
            "caller": caller,
        })
    return sorted(out, key=lambda e: e["record_id"])


@dataclass
class _Attempt:
    started: float
    initiated_by: str
    saw_187: bool = False
    saw_away: bool = False
    slept: bool = False
    caller: str = field(default="")


class SleepWatcher:
    def __init__(
        self,
        events_fn: Callable[[int], list[dict] | None],
        latest_id_fn: Callable[[], int | None],
        blockers_fn: Callable[[], list[dict]],
        notify_fn: Callable[..., None],
        own_pid: int,
        clock: Callable[[], float] = time.time,
        window_s: float = WINDOW_SECONDS,
    ):
        self._events_fn = events_fn
        self._latest_id_fn = latest_id_fn
        self._blockers_fn = blockers_fn
        self._notify_fn = notify_fn
        self._own_pid = own_pid
        self._clock = clock
        self._window_s = window_s
        self._lock = threading.Lock()
        self._last_id: int | None = None
        self._in_away = False
        self._pending: list[_Attempt] = []

    def note_agent_sleep(self) -> None:
        """Called just before this agent calls SetSuspendState, so an attempt
        that never even produces a 187 is still reported."""
        with self._lock:
            self._pending.append(_Attempt(self._clock(), "agent"))

    def on_wake(self, slept_s: float) -> None:
        """A clock gap means a real suspend happened."""
        # pick up the pre-suspend 187 first, or it would look like a new attempt
        self.poll()
        with self._lock:
            self._in_away = False
            for a in self._pending:
                a.slept = True

    def poll(self) -> None:
        if self._last_id is None:
            # start from "now": history before the agent started isn't ours
            self._last_id = self._latest_id_fn()
            if self._last_id is None:
                return
        events = self._events_fn(self._last_id)
        if not events:
            return
        with self._lock:
            for ev in events:
                self._last_id = max(self._last_id, ev["record_id"])
                self._apply(ev)

    def _apply(self, ev: dict) -> None:
        eid = ev["event_id"]
        if eid == EV_ATTEMPT:
            by = "agent" if ev["pid"] == self._own_pid else "other"
            # attach to the agent's own announced attempt if it has no 187 yet
            target = next(
                (a for a in self._pending if a.initiated_by == by and not a.saw_187),
                None,
            )
            if target is None or by == "other":
                target = _Attempt(self._clock(), by)
                self._pending.append(target)
            target.saw_187 = True
            target.caller = ev.get("caller", "")
        elif eid == EV_AWAY_MODE:
            self._in_away = True
            for a in self._pending:
                a.saw_away = True
        elif eid == EV_SLEEP:
            self._in_away = False
            for a in self._pending:
                a.slept = True

    def resolve(self) -> None:
        """Report attempts whose window has passed without a real sleep."""
        # refresh first: after a real suspend the 42 is already in the log
        self.poll()
        now = self._clock()
        due = []
        with self._lock:
            keep = []
            for a in self._pending:
                if a.slept:
                    continue
                if now - a.started >= self._window_s:
                    due.append((a, self._in_away))
                else:
                    keep.append(a)
            self._pending = keep
        for a, in_away in due:
            if a.saw_away or (a.saw_187 and in_away):
                reason = "away_mode"  # entered now, or Away Mode still holding
            elif a.saw_187:
                reason = "aborted"
            else:
                reason = "unknown"
            try:
                blockers = self._blockers_fn()
            except Exception:
                log.exception("collecting sleep blockers failed")
                blockers = []
            log.warning("sleep did not happen: reason=%s initiated_by=%s blockers=%s",
                        reason, a.initiated_by, blockers)
            self._notify_fn(reason=reason, initiated_by=a.initiated_by,
                            blockers=blockers)

    def start(self, interval_s: float = POLL_SECONDS) -> None:
        def loop():
            while True:
                time.sleep(interval_s)
                try:
                    self.resolve()
                except Exception:
                    log.exception("sleep watcher poll failed")

        threading.Thread(target=loop, name="sleep-watch", daemon=True).start()
