"""The ban list (Mike, Oct 25): players and teams BetLab never gives bets on.

Games and players stay visible; a banned player's props and a banned team's side (moneyline, spread, to win) are left
out of tickets, slips and pick alerts. Totals, both-teams-to-score and a draw are on no one, so a ban never touches
them. The list lives on the account (`user_settings.bans`, entries {"kind": "player" | "team", "name", "league"?}).

Ported to web/lib/bans.ts and ios/BetLab/Bans.swift; all three run tests/fixtures/bans.json, and teams.json (NFL, NBA,
NHL names with the abbreviations the feeds use) is the same file in all three. **Change them together.**
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from betlab.live_legs import norm_name, parse_leg, plain

CLUB = {"fc", "cf", "afc", "sc", "ac"}


@lru_cache(maxsize=1)
def teams() -> dict[str, list[dict]]:
    return json.loads((Path(__file__).parent / "teams.json").read_text(encoding="utf-8"))


def clean(bans) -> list[dict]:
    """The stored list as entries we can match: a kind, a name, maybe a league."""
    out = []
    for b in bans or []:
        if isinstance(b, dict) and b.get("kind") in ("player", "team") and plain(b.get("name")):
            out.append({"kind": b["kind"], "name": str(b["name"]).strip(), "league": b.get("league") or None})
    return out


def _words(s) -> list[str]:
    return [t for t in plain(s).split() if t not in CLUB]


def team_keys(text, league: str | None = None) -> set[str]:
    """The NFL/NBA/NHL teams a text names ("NYJ", "Jets", "New York Jets"), as "league:Full Name"; empty when none."""
    t = _words(text)
    if not t:
        return set()
    out = set()
    for lg, rows in teams().items():
        if league and lg != league:
            continue
        for r in rows:
            full = _words(r["name"])
            if t == full or (len(t) == 1 and t[0] in {plain(a) for a in r["abbr"]}) or full[-len(t):] == t or full[:len(t)] == t:
                out.add(f"{lg}:{r['name']}")
    return out


def team_hit(ban: str, ours: str, league: str | None = None, ban_league: str | None = None) -> bool:
    """Does our team text name the banned team? Through the table when either side is in it, else by the words:
    the ban is the start or the end of our name ("Bayern" in "Bayern Munich", "Buckeyes" in "Ohio State Buckeyes")."""
    if ban_league and league and ban_league != league:
        return False
    b_keys = team_keys(ban, ban_league or league)
    o_keys = team_keys(ours, league or ban_league)
    if b_keys or o_keys:
        return bool(b_keys & o_keys)
    b, o = _words(ban), _words(ours)
    return bool(b) and len(b) <= len(o) and (o[: len(b)] == b or o[-len(b):] == b)


def player_hit(ban: str, ours: str) -> bool:
    """The same player: the same name, or the same last name with a matching first name or initial ("J. Allen")."""
    b, o = norm_name(ban).split(), norm_name(ours).split()
    if not b or not o:
        return False
    if b == o:
        return True
    if len(b) == 1:
        return o[-1] == b[0]
    if b[-1] != o[-1]:
        return False
    fb, fo = b[0], o[0]
    return (len(fb) == 1 or len(fo) == 1) and fb[0] == fo[0]


def _contains(label: str, name: str) -> bool:
    return re.search(rf"(^| ){re.escape(plain(name))}( |$)", plain(label)) is not None


def hit(bans, label: str, league: str | None = None, player: str | None = None) -> dict | None:
    """The ban a leg or bet runs into, else None. `player` is the leg's player when the feed gives one."""
    bans = clean(bans)
    if not bans:
        return None
    leg = parse_leg(label) or {}
    kind = leg.get("kind")
    if kind in ("total", "btts", "btts_no", "draw", "no_draw") or plain(label) == "draw":
        return None
    who = player or leg.get("player")
    for b in bans:
        if b["kind"] == "player":
            if who and player_hit(b["name"], who):
                return b
            if not who and not leg and _contains(label, b["name"]):
                return b
        elif kind in ("ml", "spread", "draw_or", "not_win"):
            if team_hit(b["name"], leg["team"], league, b["league"]):
                return b
        elif not leg and not who and _contains(label, b["name"]):
            return b
    return None


def banned(bans, label: str, league: str | None = None, player: str | None = None) -> bool:
    return hit(bans, label, league, player) is not None


def any_leg(bans, legs: list, league: str | None = None) -> bool:
    """A parlay with any banned leg: legs are labels or leg dicts ({label, player})."""
    for l in legs or []:
        if isinstance(l, dict):
            if banned(bans, l.get("label", ""), league, l.get("player") or None):
                return True
        elif banned(bans, str(l), league):
            return True
    return False


def owner_bans(db_url: str | None = None, owner: str | None = None) -> list[dict]:
    """The owner's ban list from the app's database; empty when it can't be read (no ban beats no card)."""
    from betlab import config

    db_url = db_url or config.secret("SUPABASE_DB_URL")
    owner = owner or config.owner_user_id()
    if not (db_url and owner):
        return []
    try:
        import psycopg

        with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
            row = c.execute("select bans from user_settings where user_id = %s", [owner]).fetchone()
        return clean(row[0]) if row else []
    except Exception as e:  # noqa: BLE001
        print(f"ban list not read ({type(e).__name__})")
        return []


# ------------------------------------------------------------------------------------------- the fun card

ACTIVE: list[dict] = []     # the owner's list while a fun build runs (`use`); sgp_plus.ticket skips banned minis


def use(ban_list) -> list[dict]:
    """Set the list the builders read (the worker reads the owner's once per build)."""
    ACTIVE[:] = clean(ban_list)
    return ACTIVE


def ticket_hit(bans, t: dict, league: str | None = None) -> bool:
    """A ticket, slip or over with a banned leg: its own legs, else its games' legs, else its label."""
    if not isinstance(t, dict):
        return False
    legs = t.get("legs") or [l for g in t.get("games") or [] for l in g.get("legs") or []]
    if legs:
        return any_leg(bans, legs, league)
    return bool(t.get("label")) and banned(bans, t["label"], league, t.get("player") or None)


def scrub(doc: dict, bans) -> int:
    """Take banned tickets, slips and overs out of a fun document (slates and games) in place; returns how many.
    Builder packs stay: they're the legs Mike builds from himself."""
    bans = clean(bans)
    if not bans:
        return 0
    n = 0
    for s in doc.get("slates") or []:
        lg = s.get("sport")
        for k in ("plus", "plus_short", "td"):
            if ticket_hit(bans, s.get(k), lg):
                s[k], n = None, n + 1
        for k in ("sgps", "overs"):
            if isinstance(s.get(k), list):
                keep = [t for t in s[k] if not ticket_hit(bans, t, lg)]
                n, s[k] = n + len(s[k]) - len(keep), keep
    for g in doc.get("games") or []:
        for k in ("sgps", "overs"):
            if isinstance(g.get(k), list):
                keep = [t for t in g[k] if not ticket_hit(bans, t, "nfl")]
                n, g[k] = n + len(g[k]) - len(keep), keep
    return n
