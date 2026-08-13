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
    max_cpu_percent: float = 50
    cpu_sample_seconds: float = 1.0


@dataclass
class SleepConfig:
    response_delay_seconds: float = 3


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    guardrails: GuardrailsConfig = field(default_factory=GuardrailsConfig)
    sleep: SleepConfig = field(default_factory=SleepConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


_SECTIONS = {
    "server": ServerConfig,
    "guardrails": GuardrailsConfig,
    "sleep": SleepConfig,
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
    return cfg
