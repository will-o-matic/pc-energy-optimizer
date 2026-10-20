"""Tests for pure guardrail evaluation logic."""
import sys

from pc_energy_optimizer.config import GuardrailsConfig
from pc_energy_optimizer.guardrails import evaluate

CFG = GuardrailsConfig(min_idle_minutes=10, wake_grace_minutes=10, max_cpu_percent=50)


def test_allowed_when_idle_and_calm():
    d = evaluate(idle_s=601, cpu_percent=10.0, cfg=CFG, force=False)
    assert d.allowed and d.reasons == []
    print("OK: allowed when idle and calm")


def test_refused_user_active():
    d = evaluate(idle_s=42.0, cpu_percent=10.0, cfg=CFG, force=False)
    assert not d.allowed
    assert d.reasons == [
        {"code": "user_active", "idle_s": 42.0, "threshold_s": 600.0}
    ]
    print("OK: refused when user active")


def test_refused_cpu_high():
    d = evaluate(idle_s=9999, cpu_percent=87.2, cfg=CFG, force=False)
    assert not d.allowed
    assert d.reasons == [
        {"code": "cpu_high", "cpu_percent": 87.2, "threshold": 50.0}
    ]
    print("OK: refused when cpu high")


def test_both_reasons_in_order():
    d = evaluate(idle_s=1.0, cpu_percent=99.0, cfg=CFG, force=False)
    assert [r["code"] for r in d.reasons] == ["user_active", "cpu_high"]
    print("OK: both reasons, user_active first")


def test_force_bypasses_everything():
    d = evaluate(idle_s=0.0, cpu_percent=100.0, cfg=CFG, force=True)
    assert d.allowed and d.reasons == []
    print("OK: force bypasses guardrails")


def test_boundaries():
    # exactly at idle threshold -> allowed (idle_s >= threshold)
    d = evaluate(idle_s=600.0, cpu_percent=10.0, cfg=CFG, force=False)
    assert d.allowed
    # exactly at cpu threshold -> allowed (cpu <= threshold)
    d = evaluate(idle_s=601.0, cpu_percent=50.0, cfg=CFG, force=False)
    assert d.allowed
    print("OK: boundary equality allowed")


def test_refused_recently_woke():
    # Stale idle from before sleep: idle looks huge, but woke 5 min ago.
    d = evaluate(idle_s=9999, cpu_percent=10.0, cfg=CFG, force=False,
                 since_wake_s=300.0)
    assert not d.allowed
    assert d.reasons == [
        {"code": "recently_woke", "since_wake_s": 300.0, "threshold_s": 1200.0}
    ]
    print("OK: refused when recently woke")


def test_wake_grace_boundary():
    # 10 min grace + 10 min idle: allowed at exactly 20 min after wake
    d = evaluate(idle_s=9999, cpu_percent=10.0, cfg=CFG, force=False,
                 since_wake_s=1199.0)
    assert not d.allowed
    d = evaluate(idle_s=9999, cpu_percent=10.0, cfg=CFG, force=False,
                 since_wake_s=1200.0)
    assert d.allowed
    print("OK: wake grace boundary at grace + min_idle")


def test_force_bypasses_recently_woke():
    d = evaluate(idle_s=0.0, cpu_percent=10.0, cfg=CFG, force=True,
                 since_wake_s=0.0)
    assert d.allowed
    print("OK: force bypasses wake grace")


REQ = {"type": "SYSTEM", "kind": "PROCESS", "name": "x.exe", "reason": ""}


def test_refused_power_request():
    d = evaluate(idle_s=9999, cpu_percent=10.0, cfg=CFG, force=False,
                 power_requests=[REQ])
    assert not d.allowed
    assert d.reasons == [{"code": "power_request", "requests": [REQ]}]
    print("OK: refused on power request")


def test_power_request_unreadable_or_empty_allows():
    for reqs in (None, []):
        d = evaluate(idle_s=9999, cpu_percent=10.0, cfg=CFG, force=False,
                     power_requests=reqs)
        assert d.allowed
    print("OK: unreadable/empty power requests allow")


def test_force_bypasses_power_request():
    d = evaluate(idle_s=0, cpu_percent=10.0, cfg=CFG, force=True,
                 power_requests=[REQ])
    assert d.allowed
    print("OK: force bypasses power request")


if __name__ == "__main__":
    test_allowed_when_idle_and_calm()
    test_refused_recently_woke()
    test_wake_grace_boundary()
    test_force_bypasses_recently_woke()
    test_refused_user_active()
    test_refused_cpu_high()
    test_both_reasons_in_order()
    test_force_bypasses_everything()
    test_boundaries()
    test_refused_power_request()
    test_power_request_unreadable_or_empty_allows()
    test_force_bypasses_power_request()
    print("OK: test_guardrails")
    sys.exit(0)
