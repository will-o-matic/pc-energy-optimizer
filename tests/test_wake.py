"""Tests for resume-from-sleep detection with a fake clock."""
import sys

from pc_energy_optimizer.wake import WakeTracker


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_start_counts_as_wake():
    clock = FakeClock()
    w = WakeTracker(clock=clock, gap_s=30)
    assert w.seconds_since_wake() == 0.0
    print("OK: process start counts as wake")


def test_regular_ticks_accumulate():
    clock = FakeClock()
    w = WakeTracker(clock=clock, gap_s=30)
    for _ in range(120):  # 10 minutes of 5s ticks
        clock.t += 5
        w.tick()
    assert w.seconds_since_wake() == 600.0
    print("OK: normal heartbeat keeps counting")


def test_gap_resets_wake():
    clock = FakeClock()
    w = WakeTracker(clock=clock, gap_s=30)
    clock.t += 5
    w.tick()
    clock.t += 3600  # slept an hour
    w.tick()
    clock.t += 5
    w.tick()
    assert w.seconds_since_wake() == 5.0
    print("OK: clock gap detected as wake")


def test_query_detects_wake_before_heartbeat():
    clock = FakeClock()
    w = WakeTracker(clock=clock, gap_s=30)
    clock.t += 5
    w.tick()
    clock.t += 3600  # request arrives before the heartbeat thread runs
    assert w.seconds_since_wake() == 0.0
    print("OK: seconds_since_wake ticks itself")


def test_gap_at_threshold_not_wake():
    clock = FakeClock()
    w = WakeTracker(clock=clock, gap_s=30)
    clock.t += 30
    assert w.seconds_since_wake() == 30.0
    print("OK: gap equal to threshold is not a wake")


if __name__ == "__main__":
    test_start_counts_as_wake()
    test_regular_ticks_accumulate()
    test_gap_resets_wake()
    test_query_detects_wake_before_heartbeat()
    test_gap_at_threshold_not_wake()
    print("OK: test_wake")
    sys.exit(0)
