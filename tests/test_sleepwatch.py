"""Tests for failed-sleep detection with fake events and a fake clock."""
import sys

from pc_energy_optimizer.sleepwatch import SleepWatcher, parse_events_xml

# Trimmed from real wevtutil output on 2026-10-29 (Start menu 187, Away Mode 59).
XML = (
    "<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>"
    "<Provider Name='Microsoft-Windows-Kernel-Power'/><EventID>187</EventID>"
    "<EventRecordID>120668</EventRecordID><Execution ProcessID='115012' ThreadID='1'/>"
    "</System><EventData><Data Name='ApiCallerNameLength'>126</Data>"
    r"<Data Name='ApiCallerName'>\Device\HarddiskVolume3\Windows\SystemApps"
    r"\StartMenuExperienceHost.exe</Data></EventData></Event>"
    "<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>"
    "<Provider Name='Microsoft-Windows-Kernel-Power'/><EventID>59</EventID>"
    "<EventRecordID>120669</EventRecordID><Execution ProcessID='4' ThreadID='2'/>"
    "</System><EventData></EventData></Event>"
)

OWN_PID = 24236
PLEX = [{"name": "Plex", "detail": "movie paused on Android (192.0.2.15)"}]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Harness:
    def __init__(self, blockers=PLEX):
        self.clock = Clock()
        self.log = []          # events not yet returned
        self.next_id = 500
        self.sent = []
        self.w = SleepWatcher(
            events_fn=self.events_after, latest_id_fn=lambda: 499,
            blockers_fn=lambda: list(blockers), notify_fn=self.notify,
            own_pid=OWN_PID, clock=self.clock, window_s=20,
        )
        self.w.poll()  # baseline

    def emit(self, event_id, pid=4):
        self.log.append({"record_id": self.next_id, "event_id": event_id,
                         "pid": pid, "caller": ""})
        self.next_id += 1

    def events_after(self, rid):
        return [e for e in self.log if e["record_id"] > rid]

    def notify(self, **kw):
        self.sent.append(kw)

    def step(self, seconds):
        self.w.poll()  # the real loop polls every few seconds
        self.clock.t += seconds
        self.w.resolve()


def test_parse_real_xml():
    evs = parse_events_xml(XML)
    assert [(e["event_id"], e["record_id"], e["pid"]) for e in evs] == [
        (187, 120668, 115012), (59, 120669, 4)]
    assert evs[0]["caller"].endswith("StartMenuExperienceHost.exe")
    assert parse_events_xml("") == []
    print("OK: parse real Kernel-Power XML")


def test_agent_sleep_into_away_mode():
    h = Harness()
    h.w.note_agent_sleep()
    h.emit(187, pid=OWN_PID)
    h.emit(59)
    h.step(5)
    assert h.sent == []
    h.step(16)
    assert h.sent == [{"reason": "away_mode", "initiated_by": "agent", "blockers": PLEX}]
    h.step(60)
    assert len(h.sent) == 1  # one report per attempt, no repeats in Away Mode
    print("OK: agent sleep -> Away Mode reported once")


def test_start_menu_attempt_while_away_mode_holds():
    h = Harness()
    h.emit(187, pid=999); h.emit(59)
    h.step(21)
    h.emit(187, pid=999)  # second attempt, no new 59: still in Away Mode
    h.step(21)
    assert [s["reason"] for s in h.sent] == ["away_mode", "away_mode"]
    assert {s["initiated_by"] for s in h.sent} == {"other"}
    print("OK: Start-menu attempts in Away Mode, initiated_by other")


def test_aborted_and_unknown():
    h = Harness(blockers=[])
    h.emit(187, pid=999)
    h.step(21)
    h.w.note_agent_sleep()  # agent called SetSuspendState, no 187 ever logged
    h.step(21)
    assert h.sent == [
        {"reason": "aborted", "initiated_by": "other", "blockers": []},
        {"reason": "unknown", "initiated_by": "agent", "blockers": []},
    ]
    print("OK: aborted (187 only) and unknown (no 187)")


def test_real_sleep_not_reported():
    h = Harness()
    h.w.note_agent_sleep()
    h.emit(187, pid=OWN_PID); h.emit(42)
    h.step(3600)  # asleep; resolve after resume sees the 42
    h.emit(187, pid=999)
    h.w.on_wake(3600)  # clock gap also counts as slept
    h.step(30)
    assert h.sent == []
    print("OK: real sleeps (42 or clock gap) are not reported")


def test_42_clears_away_state():
    h = Harness(blockers=[])
    h.emit(187, pid=999); h.emit(59)
    h.step(21)
    h.emit(187, pid=999); h.emit(42)  # Plex stopped, this one really slept
    h.step(21)
    h.emit(187, pid=999)  # later attempt with neither: aborted, not away_mode
    h.step(21)
    assert [s["reason"] for s in h.sent] == ["away_mode", "aborted"]
    print("OK: real sleep clears Away Mode state")


def test_history_ignored_and_unreadable_log():
    h = Harness()
    assert h.w._last_id == 499
    w = SleepWatcher(events_fn=lambda rid: None, latest_id_fn=lambda: None,
                     blockers_fn=list, notify_fn=lambda **k: None, own_pid=1)
    w.poll(); w.resolve()  # wevtutil unavailable: no crash, nothing sent
    print("OK: starts from latest record; tolerates unreadable log")


if __name__ == "__main__":
    test_parse_real_xml()
    test_agent_sleep_into_away_mode()
    test_start_menu_attempt_while_away_mode_holds()
    test_aborted_and_unknown()
    test_real_sleep_not_reported()
    test_42_clears_away_state()
    test_history_ignored_and_unreadable_log()
    print("OK: test_sleepwatch")
    sys.exit(0)
