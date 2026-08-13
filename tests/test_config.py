"""Tests for config loading. Passes by printing OK: lines and exiting 0."""
import sys
import tempfile
from pathlib import Path

from pc_energy_optimizer.config import Config, ConfigError, load_config


def write_toml(tmp: str, text: str) -> Path:
    p = Path(tmp) / "config.toml"
    p.write_text(text, encoding="utf-8")
    return p


MINIMAL = """
[server]
token = "secret-token"
"""

FULL = """
[server]
bind_host = "100.64.0.11"
port = 9999
token = "tok"

[guardrails]
min_idle_minutes = 5
max_cpu_percent = 80
cpu_sample_seconds = 0.5

[sleep]
response_delay_seconds = 1

[logging]
level = "DEBUG"
"""


def test_defaults_applied():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(write_toml(tmp, MINIMAL))
    assert isinstance(cfg, Config)
    assert cfg.server.token == "secret-token"
    assert cfg.server.port == 8787
    assert cfg.server.bind_host == "127.0.0.1"
    assert cfg.guardrails.min_idle_minutes == 10
    assert cfg.guardrails.max_cpu_percent == 50
    assert cfg.guardrails.cpu_sample_seconds == 1.0
    assert cfg.sleep.response_delay_seconds == 3
    assert cfg.logging.level == "INFO"
    print("OK: defaults applied")


def test_overrides():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(write_toml(tmp, FULL))
    assert cfg.server.bind_host == "100.64.0.11"
    assert cfg.server.port == 9999
    assert cfg.guardrails.min_idle_minutes == 5
    assert cfg.guardrails.max_cpu_percent == 80
    assert cfg.guardrails.cpu_sample_seconds == 0.5
    assert cfg.sleep.response_delay_seconds == 1
    assert cfg.logging.level == "DEBUG"
    print("OK: overrides from toml")


def test_missing_token_fatal():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            load_config(write_toml(tmp, "[server]\nport = 8787\n"))
        except ConfigError as e:
            assert "token" in str(e)
            print("OK: missing token raises ConfigError")
            return
    raise AssertionError("missing token did not raise")


def test_placeholder_token_fatal():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            load_config(write_toml(tmp, '[server]\ntoken = "CHANGE-ME"\n'))
        except ConfigError as e:
            assert "token" in str(e)
            print("OK: placeholder token raises ConfigError")
            return
    raise AssertionError("placeholder token did not raise")


def test_bad_type_fatal():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            load_config(write_toml(tmp, '[server]\ntoken = "t"\nport = "not-a-port"\n'))
        except ConfigError as e:
            assert "port" in str(e)
            print("OK: bad type raises ConfigError")
            return
    raise AssertionError("bad type did not raise")


def test_missing_file_fatal():
    try:
        load_config(Path("Z:/does/not/exist/config.toml"))
    except ConfigError as e:
        assert "config" in str(e).lower()
        print("OK: missing file raises ConfigError")
        return
    raise AssertionError("missing file did not raise")


if __name__ == "__main__":
    test_defaults_applied()
    test_overrides()
    test_missing_token_fatal()
    test_placeholder_token_fatal()
    test_bad_type_fatal()
    test_missing_file_fatal()
    print("OK: test_config")
    sys.exit(0)
