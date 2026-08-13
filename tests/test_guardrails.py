"""Tests for pure guardrail evaluation logic."""
import sys

from pc_energy_optimizer.config import GuardrailsConfig
from pc_energy_optimizer.guardrails import evaluate

CFG = GuardrailsConfig(min_idle_minutes=10, max_cpu_percent=50)


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


if __name__ == "__main__":
    test_allowed_when_idle_and_calm()
    test_refused_user_active()
    test_refused_cpu_high()
    test_both_reasons_in_order()
    test_force_bypasses_everything()
    test_boundaries()
    print("OK: test_guardrails")
    sys.exit(0)
