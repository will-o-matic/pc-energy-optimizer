"""Tests for Plex session parsing and the disabled default — no network."""
import sys

from pc_energy_optimizer import plex
from pc_energy_optimizer.config import PlexConfig

SESSIONS = """<?xml version="1.0" encoding="UTF-8"?>
<MediaContainer size="2">
  <Video type="movie" title="Some Movie" ratingKey="103">
    <User title="will"/>
    <Player address="192.0.2.15" platform="Android" product="Plex for Android (TV)" state="paused"/>
  </Video>
  <Track type="track" title="Song">
    <Player address="192.0.2.20" title="Kitchen" product="Plexamp" state="playing"/>
  </Track>
</MediaContainer>"""


def test_parse_sessions():
    assert plex.parse_sessions(SESSIONS) == [
        {"name": "Plex", "detail": "movie paused on Android (192.0.2.15)"},
        {"name": "Plex", "detail": "track playing on Plexamp (192.0.2.20)"},
    ]
    assert plex.parse_sessions('<MediaContainer size="0"/>') == []
    print("OK: parse Plex sessions")


def test_detail_capped():
    long = SESSIONS.replace('platform="Android"', 'platform="' + "X" * 100 + '"')
    assert all(len(b["detail"]) <= 60 for b in plex.parse_sessions(long))
    print("OK: detail capped at 60 chars")


def test_disabled_by_default():
    assert plex.blockers(PlexConfig()) == []
    print("OK: Plex lookup off by default")


def test_unreachable_is_empty():
    cfg = PlexConfig(enabled=True, url="http://127.0.0.1:9", timeout_seconds=0.5)
    assert plex.blockers(cfg) == []
    print("OK: unreachable Plex yields no blockers")


if __name__ == "__main__":
    test_parse_sessions()
    test_detail_capped()
    test_disabled_by_default()
    test_unreachable_is_empty()
    print("OK: test_plex")
    sys.exit(0)
