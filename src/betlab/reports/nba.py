"""The NBA documents for the page: tonight's games (exports/nba.json, app/nba) and the NBA fun
slates (exports/fun_nba.json, app/fun_nba).

The NBA run prices one tip-off window an hour (nba.yml), so each run merges its games and
slate into what the night's earlier runs wrote: a game or slate priced again replaces its old
version, and anything that tipped more than 12 hours ago drops off. They're kept apart from
exports/fun.json because the NFL runs rebuild that file from scratch.

From the morning (schedule, Oct 12) the night's games are listed from the 9:55 AM game-line pull, with
the market's line and national TV and no player lines yet, so the app's Games tab and game pages have
them all day; the pre-tip run replaces each with its priced version.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from betlab import config
from betlab.cards import props_nba as PN

KEEP_HOURS = 12


def _load(name: str) -> dict:
    path = config.EXPORTS_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _fresh(items: list[dict], key: str, asof: pd.Timestamp) -> list[dict]:
    return [x for x in items if pd.Timestamp(x[key]) > asof - pd.Timedelta(hours=KEEP_HOURS)]


def _write(name: str, doc: dict) -> None:
    (config.EXPORTS_DIR / name).write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")


def games_view(rows: list[dict], centers: dict, national: dict) -> list[dict]:
    """One entry per game: the market's line, national TV, and every priced player line (FanDuel's
    prices, the market's no-vig chance, the model's own chance and projection). centers:
    {event_id: (home margin, total)}."""
    df = pd.DataFrame(rows)
    out = []
    for eid, g in df.groupby("event_id", sort=False):
        f = g.iloc[0]
        c = centers.get(eid)
        lines = [{"player": r.player, "team": r.team, "stat": r.stat, "label": PN.LABEL[r.stat], "line": r.line,
                  "fd_over": r.fd_over, "fd_under": r.fd_under, "p_market": r.p_market, "p_model": r.p_model,
                  "model_mean": r.mu, "minutes": r.min_proj, "day_to_day": bool(r.questionable),
                  "gap": round(float(r.p_model) - float(r.p_market), 4)} for r in g.itertuples()]
        out.append({"event_id": eid, "matchup": f["matchup"], "tipoff": str(f["tipoff"]), "home": f["home"], "away": f["away"],
                    "spread_home": None if c is None else c[0], "total": None if c is None else c[1],
                    "national_tv": national.get((f["home"], f["away"]), []), "lines": lines})
    return out


def write(rows: list[dict], slates: list[dict], centers: dict, national: dict, asof: pd.Timestamp,
          tracker: dict | None = None) -> None:
    """Merge this run's games and slates into exports/nba.json and exports/fun_nba.json."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    view = _load("nba.json")
    new = games_view(rows, centers, national) if rows else []
    model = {g["event_id"]: g["model"] for g in view.get("games", []) if g.get("model")}
    for g in new:                     # the morning's team-model read stays with the priced game (nba_reads)
        if g["event_id"] in model:
            g["model"] = model[g["event_id"]]
    ids = {g["event_id"] for g in new}
    games = [g for g in _fresh(view.get("games", []), "tipoff", asof) if g["event_id"] not in ids] + new
    games.sort(key=lambda g: g["tipoff"])
    _write("nba.json", {"generated_at": stamp, "games": games, "tracker": tracker or view.get("tracker"),
                        "note": ("Every FanDuel line we priced tonight: the market's no-vig chance sets the price; "
                                 "our player model's chance is shown for learning and has no weight until it beats "
                                 "the market on logged lines.")})
    fun = _load("fun_nba.json")
    sids = {s["slate"] for s in slates}
    kept = [s for s in _fresh(fun.get("slates", []), "kickoff", asof) if s["slate"] not in sids] + slates
    kept.sort(key=lambda s: s["kickoff"])
    _write("fun_nba.json", {"generated_at": stamp, "slates": kept})


def _nick(name) -> str:
    """'Los Angeles Clippers' and ESPN's 'LA Clippers' -> 'clippers' (every NBA nickname is unique)."""
    return str(name or "").split()[-1].lower() if name else ""


def schedule_games(pick_snap: pd.DataFrame, espn: list[dict], asof: pd.Timestamp, hours: float = 36.0) -> list[dict]:
    """The listing entries for the games in the game-line snapshot tipping within `hours`: the market's
    line (median across books), ESPN's abbreviations and national TV by nickname, no player lines."""
    from betlab.cards import fun_nba

    if pick_snap is None or pick_snap.empty:
        return []
    by_nick = {(_nick(g["home_name"]), _nick(g["away_name"])): g for g in espn}
    out = []
    for eid, g in pick_snap.groupby("event_id", sort=False):
        f = g.iloc[0]
        tip = pd.Timestamp(f["commence_time"])
        if not (asof < tip <= asof + pd.Timedelta(hours=hours)):
            continue
        e = by_nick.get((_nick(f["home_team"]), _nick(f["away_team"])), {})
        c = fun_nba._center(pick_snap, f["home_team"], f["away_team"])
        out.append({"event_id": str(eid), "matchup": f"{f['away_team']} @ {f['home_team']}", "tipoff": str(tip),
                    "home": e.get("home") or f["home_team"], "away": e.get("away") or f["away_team"],
                    "spread_home": None if c is None else c[0], "total": None if c is None else c[1],
                    "national_tv": e.get("national_tv") or [], "lines": [], "priced": False})
    return out


def schedule(pick_snap: pd.DataFrame, espn: list[dict], asof: pd.Timestamp, enrich=None) -> int:
    """Add tonight's unpriced games to exports/nba.json (a priced version is never replaced); returns how many.
    enrich(new entries) adds to them before they're written (the team model's read: nba_reads)."""
    view = _load("nba.json")
    have = {g["event_id"] for g in view.get("games", [])}
    new = [g for g in schedule_games(pick_snap, espn, asof) if g["event_id"] not in have]
    if not new:
        return 0
    if enrich is not None:
        enrich(new)
    games = sorted(_fresh(view.get("games", []), "tipoff", asof) + new, key=lambda g: g["tipoff"])
    _write("nba.json", {**view, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "games": games})
    return len(new)
