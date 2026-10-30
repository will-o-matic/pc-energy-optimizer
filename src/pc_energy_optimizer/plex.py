"""Active Plex sessions as sleep blockers, via the local server's
/status/sessions API. Opt-in: needs [plex] enabled and, unless Plex allows
this host without auth, a token in config.toml. The token is never logged.
"""
from __future__ import annotations

import logging
import urllib.request
import xml.etree.ElementTree as ET

from .config import PlexConfig

log = logging.getLogger(__name__)

DETAIL_MAX = 60
_ITEMS = ("Video", "Track", "Photo")


def parse_sessions(text: str) -> list[dict]:
    """Blockers like {"name": "Plex", "detail": "movie paused on Android (192.0.2.15)"}."""
    root = ET.fromstring(text)
    out = []
    for item in root:
        if item.tag not in _ITEMS:
            continue
        player = item.find("Player")
        if player is None:
            continue
        kind = item.get("type") or item.tag.lower()
        state = player.get("state", "active")
        device = player.get("platform") or player.get("product") or player.get("title") or "a device"
        addr = player.get("address")
        detail = f"{kind} {state} on {device}" + (f" ({addr})" if addr else "")
        out.append({"name": "Plex", "detail": detail[:DETAIL_MAX]})
    return out


def blockers(cfg: PlexConfig) -> list[dict]:
    if not cfg.enabled:
        return []
    headers = {"Accept": "application/xml"}
    if cfg.token:
        headers["X-Plex-Token"] = cfg.token
    req = urllib.request.Request(cfg.url.rstrip("/") + "/status/sessions", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
            return parse_sessions(resp.read().decode("utf-8", "replace"))
    except Exception as e:
        # str(e) for urllib errors is the status/reason, never the URL or token
        log.warning("Plex sessions unavailable: %s", e)
        return []
