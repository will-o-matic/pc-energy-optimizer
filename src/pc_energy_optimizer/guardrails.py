"""Pure sleep-guardrail logic. No I/O, no Windows APIs."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import GuardrailsConfig


@dataclass
class Decision:
    allowed: bool
    reasons: list[dict] = field(default_factory=list)


def evaluate(
    idle_s: float, cpu_percent: float, cfg: GuardrailsConfig, force: bool
) -> Decision:
    if force:
        return Decision(allowed=True)

    reasons: list[dict] = []
    threshold_s = cfg.min_idle_minutes * 60.0
    if idle_s < threshold_s:
        reasons.append(
            {"code": "user_active", "idle_s": idle_s, "threshold_s": threshold_s}
        )
    if cpu_percent > cfg.max_cpu_percent:
        reasons.append(
            {
                "code": "cpu_high",
                "cpu_percent": cpu_percent,
                "threshold": float(cfg.max_cpu_percent),
            }
        )
    return Decision(allowed=not reasons, reasons=reasons)
