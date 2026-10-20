"""Tests for powercfg /requests parsing and filtering."""
import sys

from pc_energy_optimizer import powerreq

SAMPLE = r"""DISPLAY:
[PROCESS] \Device\HarddiskVolume3\Program Files\Google\Chrome\Application\chrome.exe
Video Wake Lock

SYSTEM:
[DRIVER] Realtek High Definition Audio (HDAUDIO\FUNC_01&VEN_10EC)
An audio stream is currently in use.
[PROCESS] \Device\HarddiskVolume3\Users\me\pc-energy-optimizer\.venv\Scripts\pythonw.exe

AWAYMODE:
None.

EXECUTION:
[PROCESS] \Device\HarddiskVolume3\Program Files\Steam\steam.exe
Downloading

PERFBOOST:
None.

ACTIVELOCKSCREEN:
None.
"""

OWN = r"C:\Users\me\pc-energy-optimizer\.venv\Scripts\pythonw.exe"


def test_parse():
    reqs = powerreq.parse(SAMPLE)
    assert [(r["type"], r["kind"]) for r in reqs] == [
        ("DISPLAY", "PROCESS"), ("SYSTEM", "DRIVER"),
        ("SYSTEM", "PROCESS"), ("EXECUTION", "PROCESS"),
    ]
    assert reqs[1]["name"].startswith("Realtek High Definition Audio")
    assert reqs[1]["reason"] == "An audio stream is currently in use."
    assert reqs[2]["reason"] == ""
    assert reqs[3]["reason"] == "Downloading"
    print("OK: parse powercfg /requests")


def test_parse_all_none():
    text = "DISPLAY:\nNone.\n\nSYSTEM:\nNone.\n\nAWAYMODE:\nNone.\n"
    assert powerreq.parse(text) == []
    print("OK: parse empty output")


def test_blocking_filters_type_and_self():
    reqs = powerreq.parse(SAMPLE)
    out = powerreq.blocking(reqs, ["SYSTEM", "AWAYMODE", "EXECUTION"], [], own_exe=OWN)
    names = [r["name"] for r in out]
    assert len(out) == 2, names
    assert names[0].startswith("Realtek") and names[1].endswith("steam.exe")
    print("OK: blocking drops DISPLAY and the agent's own request")


def test_blocking_ignore_list():
    reqs = powerreq.parse(SAMPLE)
    out = powerreq.blocking(reqs, ["SYSTEM", "EXECUTION"], ["realtek", "DOWNLOADING"], own_exe=OWN)
    assert out == []
    print("OK: ignore list matches name or reason, case-insensitive")


if __name__ == "__main__":
    test_parse()
    test_parse_all_none()
    test_blocking_filters_type_and_self()
    test_blocking_ignore_list()
    print("OK: test_powerreq")
    sys.exit(0)
