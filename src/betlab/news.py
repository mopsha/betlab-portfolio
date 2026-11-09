"""Free news checks for the pre-game re-pulls (Mike, 2026-10-04: props and line updates only after
the news, and again if the news changes).

`fingerprints(league, games)` reads the free sources once per league and returns, per game, a short
fingerprint of each source's news for its two teams:
- `injuries`: ESPN's live injury report (NFL, NBA, NHL): every listed player and status.
- `goalies` (NHL): ESPN's scoreboard, each side's starting goalie and whether he's confirmed.
- `lineups` (NBA): nba.com's lineup file, the starters with Expected/Confirmed and the inactives.

pregame.py stores them at each game's pull and compares on every later run until the start: a
changed source re-pulls that game. A source that fails to load is left out, and only sources
present both times are compared, so an outage never looks like news.
"""

from __future__ import annotations

import hashlib
import unicodedata

import pandas as pd
import requests

ESPN = "https://site.api.espn.com/apis/site/v2/sports"
PATH = {"nfl": "football/nfl", "nba": "basketball/nba", "nhl": "hockey/nhl", "ufc": "mma/ufc"}
TIMEOUT = 20


def team_key(name: str | None) -> str:
    """'Montréal Canadiens' and 'Montreal Canadiens' -> 'canadiens'; 'LA Clippers' and 'Los Angeles
    Clippers' -> 'clippers'. The nickname is unique within each of these leagues."""
    plain = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower().split()
    return plain[-1] if plain else ""


def _injuries(league: str) -> dict[str, list[str]]:
    r = requests.get(f"{ESPN}/{PATH[league]}/injuries", timeout=TIMEOUT)
    r.raise_for_status()
    out: dict[str, list[str]] = {}
    for team in r.json().get("injuries", []):
        out[team_key(team.get("displayName"))] = sorted(
            f"{(i.get('athlete') or {}).get('displayName')}:{i.get('status')}" for i in team.get("injuries", []))
    return out


def _nhl_goalies(day: str) -> dict[str, list[str]]:
    from betlab.sources import nhl

    board = nhl.scoreboard(day)
    out = {}
    for _, g in board.iterrows():
        for side in ("home", "away"):
            out[team_key(g.get(f"{side}_name"))] = [f"{g.get(f'{side}_goalie')}:{g.get(f'{side}_goalie_status')}"]
    return out


def _nba_lineups(day: str) -> dict[str, list[str]]:
    from betlab.cards.props_nba import NBA_TO_ESPN, team_abbr_by_name
    from betlab.sources import nba

    lu = nba.lineups(day)
    if lu.empty:
        return {}
    sch = nba.load_schedules([nba.current_season()])
    by_espn = {abbr: team_key(name) for name, abbr in team_abbr_by_name(sch).items()}
    out: dict[str, list[str]] = {}
    for team, rows in lu.groupby("team"):
        key = by_espn.get(NBA_TO_ESPN.get(team, team))
        if key:
            out[key] = sorted([f"{p}:start:{s}" for p, s in zip(rows.loc[rows["starter"], "player"],
                                                                rows.loc[rows["starter"], "lineup_status"])]
                              + [f"{p}:inactive" for p in rows.loc[rows["roster_status"] == "Inactive", "player"]])
    return out


def _ufc_card(day: str) -> dict[str, list[str]]:
    """{fighter key: [their fight's listing]} from ESPN's UFC card (Oct 23): the note (weight class, or a catchweight
    after a missed weight), the segment, the opponent and the fight's status, so a late replacement, a missed weight
    or a cancellation re-pulls the fight. Keys are last names, as cards/ufc matches fights."""
    from betlab.sources import espn_ufc as src

    out: dict[str, list[str]] = {}
    for eid in src.scheduled(day)["espn_event"].dropna().unique():
        d = src._get(f"{src.FIGHTCENTER}/{eid}", {"region": "us", "lang": "en"})
        for seg, c in src._comps(d):
            comp = c.get("competitors") or []
            names = [((x.get("athlete") or {}).get("displayName") or "") for x in comp]
            status = ((c.get("status") or {}).get("type") or {}).get("detail") or ""
            for me, opp in ((0, 1), (1, 0)) if len(names) == 2 else ():
                out.setdefault(team_key(names[me]), []).append(f"{c.get('note')}|{seg}|{team_key(names[opp])}|{status}")
    return out


def sources(league: str, now: pd.Timestamp) -> dict[str, dict[str, list[str]]]:
    """{source: {team key: entries}} for the league; a source that fails is simply missing."""
    if league not in PATH:
        return {}
    day = now.tz_convert("America/New_York").strftime("%Y%m%d")
    readers = {"injuries": lambda: _injuries(league)} if league != "ufc" else {"card": lambda: _ufc_card(day)}
    if league == "nhl":
        readers["goalies"] = lambda: _nhl_goalies(day)
    if league == "nba":
        readers["lineups"] = lambda: _nba_lineups(day)
    out = {}
    for name, read in readers.items():
        try:
            out[name] = read()
        except Exception as exc:   # an outage must never look like news
            print(f"news: {league} {name} unavailable ({type(exc).__name__})")
    return out


def fingerprint(src: dict[str, dict[str, list[str]]], home: str, away: str) -> dict[str, str]:
    """{source: short hash of both teams' entries} for one game."""
    out = {}
    for name, teams in src.items():
        text = "|".join(";".join(teams.get(team_key(t), [])) for t in (home, away))
        out[name] = hashlib.sha1(text.encode()).hexdigest()[:12]
    return out


def changed(before: dict[str, str] | None, now: dict[str, str]) -> list[str]:
    """Sources whose news differs, comparing only sources present both times."""
    if not before:
        return []
    return sorted(k for k in before.keys() & now.keys() if before[k] != now[k])
