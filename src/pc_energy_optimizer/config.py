"""Config loading: dataclass defaults overridden by config.toml."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass
class ServerConfig:
    bind_host: str = "127.0.0.1"
    port: int = 8787
    token: str = ""


@dataclass
class GuardrailsConfig:
    min_idle_minutes: float = 10
    wake_grace_minutes: float = 10
    max_cpu_percent: float = 50
    cpu_sample_seconds: float = 1.0
    # powercfg /requests categories that block a polite sleep
    power_request_types: list = field(
        default_factory=lambda: ["SYSTEM", "AWAYMODE", "EXECUTION"]
    )
    # case-insensitive substrings; matching requests are ignored
    ignore_power_requests: list = field(default_factory=list)


@dataclass
class SleepConfig:
    response_delay_seconds: float = 3


@dataclass
class WebhookConfig:
    url: str = ""  # empty disables push events
    timeout_seconds: float = 2.0
    retry_seconds: float = 60.0  # how long started/woke events keep retrying


@dataclass
class PowerConfig:
    # estimated_watts = base_watts + cpu_watts * (cpu/100) ** cpu_exponent
    #                   + gpu_watts / psu_efficiency (or gpu_fallback_watts)
    base_watts: float = 60.0
    cpu_watts: float = 120.0
    cpu_exponent: float = 1.0
    gpu_fallback_watts: float = 0.0
    psu_efficiency: float = 0.9
    sample_seconds: float = 10.0


@dataclass
class PlexConfig:
    # Report active Plex sessions as the reason a sleep didn't happen.
    enabled: bool = False
    url: str = "http://127.0.0.1:32400"
    token: str = ""  # X-Plex-Token; empty works only if Plex allows this host without auth
    timeout_seconds: float = 2.0


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    guardrails: GuardrailsConfig = field(default_factory=GuardrailsConfig)
    sleep: SleepConfig = field(default_factory=SleepConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    power: PowerConfig = field(default_factory=PowerConfig)
    plex: PlexConfig = field(default_factory=PlexConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


_SECTIONS = {
    "server": ServerConfig,
    "guardrails": GuardrailsConfig,
    "sleep": SleepConfig,
    "webhook": WebhookConfig,
    "power": PowerConfig,
    "plex": PlexConfig,
    "logging": LoggingConfig,
}


def _build_section(cls, data: dict, section: str):
    obj = cls()
    valid = {f.name: f for f in fields(cls)}
    for key, value in data.items():
        if key not in valid:
            raise ConfigError(f"unknown key [{section}].{key}")
        current = getattr(obj, key)
        if isinstance(current, bool) or isinstance(value, bool):
            ok = isinstance(value, bool) and isinstance(current, bool)
        elif isinstance(current, float):
            ok = isinstance(value, (int, float))
            value = float(value)
        elif isinstance(current, int):
            ok = isinstance(value, int)
        elif isinstance(current, list):
            ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
        else:
            ok = isinstance(value, type(current))
        if not ok:
            raise ConfigError(f"bad type for [{section}].{key}: {value!r}")
        setattr(obj, key, value)
    return obj


def load_config(path: Path | str) -> Config:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(
            f"config file not found: {path} — copy config.example.toml to config.toml and edit it"
        )
    with path.open("rb") as f:
        try:
            raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"invalid TOML in {path}: {e}") from e

    kwargs = {}
    for section, cls in _SECTIONS.items():
        data = raw.get(section, {})
        if not isinstance(data, dict):
            raise ConfigError(f"[{section}] must be a table")
        kwargs[section] = _build_section(cls, data, section)
    for section in raw:
        if section not in _SECTIONS:
            raise ConfigError(f"unknown section [{section}]")

    cfg = Config(**kwargs)
    if not cfg.server.token or cfg.server.token == "CHANGE-ME":
        raise ConfigError(
            "[server].token is missing or still the placeholder — set a real token in config.toml"
        )
    if cfg.webhook.url and not cfg.webhook.url.startswith(("http://", "https://")):
        raise ConfigError("[webhook].url must start with http:// or https://")
    if not 0 < cfg.power.psu_efficiency <= 1:
        raise ConfigError("[power].psu_efficiency must be in (0, 1]")
    if cfg.power.sample_seconds <= 0:
        raise ConfigError("[power].sample_seconds must be positive")
    return cfg
