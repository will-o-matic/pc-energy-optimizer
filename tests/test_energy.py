"""Tests for the power estimate and energy integration with fake inputs."""
import json
import sys
import tempfile
from pathlib import Path

from pc_energy_optimizer.config import PowerConfig
from pc_energy_optimizer.energy import EnergyMeter, estimate_watts

CFG = PowerConfig(base_watts=50, cpu_watts=100, cpu_exponent=1.0,
                  gpu_fallback_watts=20, psu_efficiency=0.8, sample_seconds=10)


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_estimate():
    assert estimate_watts(0, None, CFG) == 70.0          # base + gpu fallback
    assert estimate_watts(50, None, CFG) == 120.0
    assert estimate_watts(100, 80.0, CFG) == 250.0       # 50 + 100 + 80/0.8
    assert estimate_watts(150, None, CFG) == 170.0       # clamped to 100%
    sq = PowerConfig(base_watts=0, cpu_watts=100, cpu_exponent=2.0)
    assert estimate_watts(50, None, sq) == 25.0
    print("OK: estimate_watts curve")


def test_integrates_and_skips_sleep_gap():
    clock = FakeClock()
    m = EnergyMeter(CFG, cpu_fn=lambda: 0.0, gpu_fn=lambda: None, clock=clock)
    for _ in range(360):  # one hour of 10s samples at 70 W
        clock.t += 10
        m.sample()
    snap = m.snapshot()
    assert abs(snap["energy_kwh"] - 0.07) < 1e-9, snap
    assert snap["estimated_watts"] == 70.0 and snap["gpu_watts"] is None
    clock.t += 8 * 3600  # asleep overnight: must not count
    m.sample()
    assert abs(m.snapshot()["energy_kwh"] - 0.07) < 1e-9
    print("OK: energy integrates while awake, not across sleep")


def test_persists_and_resumes():
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "state" / "energy.json"
        clock = FakeClock()
        m = EnergyMeter(CFG, cpu_fn=lambda: 0.0, gpu_fn=lambda: 40.0,
                        store_path=store, clock=clock)
        for _ in range(30):  # 30th sample triggers a persist
            clock.t += 10
            m.sample()
        saved = json.loads(store.read_text())["energy_kwh"]
        assert saved > 0
        m2 = EnergyMeter(CFG, cpu_fn=lambda: 0.0, gpu_fn=lambda: None,
                         store_path=store, clock=clock)
        assert m2.snapshot()["energy_kwh"] == round(saved, 4)
        assert m.snapshot()["gpu_watts"] == 40.0
        store.write_text("garbage")
        m3 = EnergyMeter(CFG, cpu_fn=lambda: 0.0, gpu_fn=lambda: None,
                         store_path=store, clock=clock)
        assert m3.snapshot()["energy_kwh"] == 0.0
    print("OK: energy persists across restarts; corrupt file restarts at 0")


if __name__ == "__main__":
    test_estimate()
    test_integrates_and_skips_sleep_gap()
    test_persists_and_resumes()
    print("OK: test_energy")
    sys.exit(0)
