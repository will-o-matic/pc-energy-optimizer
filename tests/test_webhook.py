"""Tests for webhook push with a fake transport — no network."""
import json
import sys
from datetime import datetime

from pc_energy_optimizer import __version__
from pc_energy_optimizer.config import WebhookConfig
from pc_energy_optimizer.webhook import Notifier

URL = "https://ha.example/api/webhook/abc"


class FakeTransport:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.calls = []
        self.t = 0.0

    def post(self, url, body, timeout):
        self.calls.append((url, json.loads(body), timeout))
        if len(self.calls) <= self.fail_times:
            raise OSError("network unreachable")

    def sleep(self, s):
        self.t += s

    def clock(self):
        return self.t


def make(transport, url=URL, retry_seconds=60.0):
    cfg = WebhookConfig(url=url, timeout_seconds=2.0, retry_seconds=retry_seconds)
    return Notifier(cfg, "DESK", post=transport.post, sleep=transport.sleep,
                    clock=transport.clock)


def test_payload_shape():
    tr = FakeTransport()
    make(tr).send("sleeping", forced=True).join()
    url, body, timeout = tr.calls[0]
    assert url == URL and timeout == 2.0
    assert body["event"] == "sleeping" and body["forced"] is True
    assert body["hostname"] == "DESK" and body["version"] == __version__
    assert datetime.fromisoformat(body["ts"]).utcoffset() is not None
    print("OK: payload shape with offset timestamp")


def test_no_retry_gives_up_after_one():
    tr = FakeTransport(fail_times=5)
    make(tr).send("sleeping", forced=False).join()
    assert len(tr.calls) == 1
    print("OK: sleeping event is a single attempt")


def test_retry_until_success():
    tr = FakeTransport(fail_times=3)
    make(tr).send("woke", retry=True, slept_s=3600.0).join()
    assert len(tr.calls) == 4 and tr.calls[-1][1]["slept_s"] == 3600.0
    print("OK: woke retries with backoff until delivered")


def test_retry_window_bounded():
    tr = FakeTransport(fail_times=1000)
    make(tr, retry_seconds=60).send("started", retry=True).join()
    assert tr.t <= 60 and 3 <= len(tr.calls) <= 10, (tr.t, len(tr.calls))
    print("OK: retry stops within retry_seconds")


def test_disabled_without_url():
    tr = FakeTransport()
    assert make(tr, url="").send("started") is None and tr.calls == []
    print("OK: no url, no send")


if __name__ == "__main__":
    test_payload_shape()
    test_no_retry_gives_up_after_one()
    test_retry_until_success()
    test_retry_window_bounded()
    test_disabled_without_url()
    print("OK: test_webhook")
    sys.exit(0)
