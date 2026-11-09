"""Each account's alert settings (Mike's #47, Nov 2): `user_settings.notify`, read here for every alert the worker sends.

Keys, all optional: `picks` (on), `leans` (off), `locks` (on), `legs` (on), `news` (on), `reactions` (on; friends' reactions
to your bets, Nov 6), `min_ev` (percent; picks and leans
under it stay quiet), `sports` ({"nfl": false} turns a sport off for picks, leans and locks), `quiet` ({"from": "23:00",
"to": "08:00"}, Eastern). During quiet hours pick, lean, lock, player-news and reaction alerts wait (alerts_held) and leg alerts are
dropped, since by morning they're old news. The bets, the card and Live Activities don't change.
"""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SOCCER = {"epl", "la_liga", "serie_a", "bundesliga", "ligue_1", "mls", "ucl", "uel", "uecl", "soccer"}


def sport_of(league) -> str:
    """The sport a setting names: every soccer competition is "soccer"."""
    k = str(league or "").lower()
    return "soccer" if k in SOCCER else k


def _minutes(v) -> int | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(v or ""))
    return int(m[1]) * 60 + int(m[2]) if m and int(m[1]) < 24 and int(m[2]) < 60 else None


def clean(notify) -> dict:
    """A notify value (or nothing) as settings with their defaults; a bad value counts as not set."""
    n = notify if isinstance(notify, dict) else {}
    try:
        min_ev = float(n["min_ev"]) if n.get("min_ev") is not None else None
    except (TypeError, ValueError):
        min_ev = None
    q = n.get("quiet") if isinstance(n.get("quiet"), dict) else {}
    start, end = _minutes(q.get("from")), _minutes(q.get("to"))
    sports = n.get("sports") if isinstance(n.get("sports"), dict) else {}
    return {"picks": n.get("picks") is not False, "leans": n.get("leans") is True, "locks": n.get("locks") is not False,
            "legs": n.get("legs") is not False, "news": n.get("news") is not False,
            "reactions": n.get("reactions") is not False, "min_ev": min_ev,
            "off": {str(k) for k, v in sports.items() if v is False},
            "quiet": (start, end) if start is not None and end is not None and start != end else None}


def in_quiet(p: dict, now) -> bool:
    """Is it quiet hours for these settings? A window may cross midnight; the end minute is outside it."""
    if not p["quiet"]:
        return False
    t = now.astimezone(ET)
    m, (start, end) = t.hour * 60 + t.minute, p["quiet"]
    return start <= m < end if start < end else m >= start or m < end


def wants(p: dict, league, ev=None, tier: str = "pick") -> bool:
    """Does this account want an alert on this pick or lean?"""
    if not p["leans" if tier == "lean" else "picks"] or sport_of(league) in p["off"]:
        return False
    return p["min_ev"] is None or ev is None or float(ev) * 100 >= p["min_ev"]


def wants_lock(p: dict, sport) -> bool:
    return p["locks"] and sport_of(sport or "nfl") not in p["off"]
