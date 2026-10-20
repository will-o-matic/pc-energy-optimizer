"""Parse `powercfg /requests` output. Pure text handling, no Windows APIs.

The output is one block per request type, e.g.:

    SYSTEM:
    [DRIVER] Realtek High Definition Audio (HDAUDIO\\FUNC_01...)
    An audio stream is currently in use.

    EXECUTION:
    [PROCESS] \\Device\\HarddiskVolume3\\Program Files\\App\\app.exe
    Playing audio

    AWAYMODE:
    None.
"""
from __future__ import annotations

import re

_HEADER = re.compile(r"^([A-Z]+):\s*$")
_ENTRY = re.compile(r"^\[([A-Z]+)\]\s*(.*)$")


def parse(text: str) -> list[dict]:
    """Every request as {"type", "kind", "name", "reason"}."""
    requests: list[dict] = []
    current_type = None
    entry = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            entry = None
            continue
        header = _HEADER.match(line)
        if header:
            current_type = header.group(1)
            entry = None
            continue
        if current_type is None or line == "None.":
            continue
        m = _ENTRY.match(line)
        if m:
            entry = {
                "type": current_type,
                "kind": m.group(1),
                "name": m.group(2),
                "reason": "",
            }
            requests.append(entry)
        elif entry is not None and not entry["reason"]:
            entry["reason"] = line
    return requests


def blocking(
    requests: list[dict],
    types: list[str],
    ignore: list[str],
    own_exe: str = "",
) -> list[dict]:
    """Requests that should refuse a polite sleep.

    own_exe is this agent's executable (e.g. C:\\...\\pythonw.exe). powercfg
    prints device paths (\\Device\\HarddiskVolumeN\\...), so it is matched by
    its drive-less tail.
    """
    wanted = {t.upper() for t in types}
    ignore_l = [s.lower() for s in ignore if s]
    own_tail = re.sub(r"^[A-Za-z]:", "", own_exe).lower()
    out = []
    for r in requests:
        if r["type"] not in wanted:
            continue
        name_l = r["name"].lower()
        if own_tail and r["kind"] == "PROCESS" and name_l.endswith(own_tail):
            continue
        if any(s in name_l or s in r["reason"].lower() for s in ignore_l):
            continue
        out.append(r)
    return out
