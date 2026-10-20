"""Pure sleep-guardrail logic. No I/O, no Windows APIs."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import GuardrailsConfig


@dataclass
class Decision:
    allowed: bool
    reasons: list[dict] = field(default_factory=list)


def evaluate(
    idle_s: float,
    cpu_percent: float,
    cfg: GuardrailsConfig,
    force: bool,
    since_wake_s: float = float("inf"),
    power_requests: list[dict] | None = None,
) -> Decision:
    if force:
        return Decision(allowed=True)

    reasons: list[dict] = []
    threshold_s = cfg.min_idle_minutes * 60.0
    if idle_s < threshold_s:
        reasons.append(
            {"code": "user_active", "idle_s": idle_s, "threshold_s": threshold_s}
        )
    # The idle clock only starts counting wake_grace_minutes after resume, so
    # a remote wake (no input, stale idle_s) isn't immediately slept again.
    required_s = cfg.wake_grace_minutes * 60.0 + threshold_s
    if since_wake_s < required_s:
        reasons.append(
            {
                "code": "recently_woke",
                "since_wake_s": since_wake_s,
                "threshold_s": required_s,
            }
        )
    if cpu_percent > cfg.max_cpu_percent:
        reasons.append(
            {
                "code": "cpu_high",
                "cpu_percent": cpu_percent,
                "threshold": float(cfg.max_cpu_percent),
            }
        )
    # power_requests is already filtered to blocking ones; None means
    # powercfg couldn't be read and the check is skipped.
    if power_requests:
        reasons.append({"code": "power_request", "requests": power_requests})
    return Decision(allowed=not reasons, reasons=reasons)
