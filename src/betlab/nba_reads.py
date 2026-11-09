"""The NBA game read and its track record: data/ledger/nba_reads.csv (Oct 12, before opening night).

Each morning the night's games are listed for the app (reports/nba.schedule) with the team model's
projection (models/team_nba: opponent-adjusted offense, defense and pace from the last 400 days, rest):
margin, total, pace, each team's points and ranks. The game page shows it against the market's line.
It has no weight in prices: there were no historical NBA lines to test it on (docs/NBA_PLAN.md), so this
is its test.

One row per (game, kind), kind = spread or total, logged once at the first listing: the market's line
then (books' median: the home team's expected margin, the total), the model's number, the gap and the
model's side. After the game: the market's last line before tip (our latest game-line pull), whether the
line moved toward the model (points), and whether the model's side won at the first line. `early` marks
games where either team has fewer than 10 games this season: the ratings are mostly last season's, and
rosters change (the same reason the football models get no weight in their first weeks).

Absences (Oct 12): the team model uses season ratings, so it can't see tonight's injuries. Until an adjustment
is backtested, each read lists the regulars ESPN has out (20+ minutes a game over their last 40 games) and
`key_out` counts those at 25+, so the record can be split by nights with key players out, and the game page
says plainly that the read doesn't adjust for them.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

PATH = config.DATA_DIR / "ledger" / "nba_reads.csv"
COLUMNS = ["read_id", "event_id", "tipoff", "matchup", "home", "away", "kind", "first_seen", "market", "model", "gap",
           "side", "early", "key_out", "close", "moved_pts", "final", "result", "status", "graded_at"]
TEXT = ["read_id", "event_id", "tipoff", "matchup", "home", "away", "kind", "first_seen", "side", "result", "status",
        "graded_at"]
EARLY_GAMES = 10


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def _history(asof: pd.Timestamp):
    """(schedules, team box) for last season and this one (this season's files appear once games are played)."""
    from betlab.sources import nba

    season = nba.current_season(asof.tz_convert("America/New_York"))
    sch, tb = [], []
    for s in (season - 1, season):
        try:
            sch.append(nba.load_schedules([s]))
            tb.append(nba.load_team_box([s]))
        except Exception:  # noqa: BLE001 - no file yet for a season that hasn't started
            continue
    return pd.concat(sch, ignore_index=True), pd.concat(tb, ignore_index=True)


def project(entries: list[dict], asof: pd.Timestamp, data=None) -> dict[str, dict]:
    """{event_id: the model's projection} for listing entries (home/away as ESPN abbreviations)."""
    from betlab.models import team_nba as T

    if not entries:
        return {}
    sch, tb = data if data is not None else _history(asof)
    tg = T.team_games(tb, sch)
    day = asof.tz_convert("America/New_York").tz_localize(None).normalize()
    r = T.fit_ratings(tg, day)
    rk = T.ranks(r)
    past = tg[tg["date"] < day]
    last = past.groupby("team")["date"].max()
    from betlab.sources import nba

    season = nba.current_season(asof.tz_convert("America/New_York"))      # this season's games only
    played = past[past["season"] == season].groupby("team").size()
    out = {}
    for e in entries:
        h, a = e.get("home"), e.get("away")
        if h not in r.off.index or a not in r.off.index:
            continue
        rest = {t: float((day - last[t]).days) if t in last.index else None for t in (h, a)}
        rest = {t: v if v is not None and v <= 14 else None for t, v in rest.items()}   # the offseason isn't rest
        p = T.project(r, h, a, rest_home=rest[h], rest_away=rest[a])
        out[e["event_id"]] = {
            "margin": round(float(p["margin"]), 1), "total": round(float(p["total"]), 1), "pace": round(float(p["pace"]), 1),
            "home_points": round(float(p["home_points"]), 1), "away_points": round(float(p["away_points"]), 1),
            "ranks": {t: {k: int(rk.loc[t, k]) for k in ("off_ortg", "def_ortg", "pace")} for t in (h, a) if t in rk.index},
            "rest": rest, "early": bool(min(int(played.get(h, 0)), int(played.get(a, 0))) < EARLY_GAMES)}
    return out


REGULAR_MIN, KEY_MIN = 20.0, 25.0


def absences(entries: list[dict], asof: pd.Timestamp, injuries: pd.DataFrame | None = None,
             player_box: pd.DataFrame | None = None) -> dict[str, dict]:
    """{event_id: {"home": [...], "away": [...], "key_out": n}}: regulars ESPN has out tonight (sits), each
    {name, minutes} from their last 40 games, sorted by minutes. Teams are matched by nickname."""
    from betlab.reports.nba import _nick
    from betlab.sources import nba

    if injuries is None:
        injuries = nba.injuries_now()
    if player_box is None:
        season = nba.current_season(asof.tz_convert("America/New_York"))
        frames = []
        for s_ in (season - 1, season):
            try:
                frames.append(nba.load_player_box([s_]))
            except Exception:  # noqa: BLE001 - this season's file appears once games are played
                continue
        player_box = pd.concat(frames, ignore_index=True)
    pb = player_box[pd.to_numeric(player_box["minutes"], errors="coerce") > 0]
    if "game_date" in pb:
        # sportsdataverse's game_date is a date, the ESPN fill's a "YYYY-MM-DD" string (Oct 24: mixed, the sort failed)
        pb = pb.assign(_d=pd.to_datetime(pb["game_date"].astype(str))).sort_values("_d")
    mins = pb.groupby("athlete_id")["minutes"].apply(lambda m: float(pd.to_numeric(m).tail(40).mean()))
    out_now = injuries[injuries["sits"].astype(bool)] if len(injuries) else injuries
    by_team: dict[str, list[dict]] = {}
    for r in out_now.itertuples():
        m = float(mins.get(int(r.athlete_id), 0.0))
        if m >= REGULAR_MIN:
            by_team.setdefault(_nick(r.team), []).append({"name": r.athlete_display_name, "minutes": round(m, 1)})
    out = {}
    for e in entries:
        away_name, _, home_name = str(e.get("matchup", "")).partition(" @ ")
        sides = {side: sorted(by_team.get(_nick(name), []), key=lambda x: -x["minutes"])
                 for side, name in (("home", home_name), ("away", away_name))}
        sides["key_out"] = sum(1 for side in ("home", "away") for x in sides[side] if x["minutes"] >= KEY_MIN)
        out[e["event_id"]] = sides
    return out

def rows(entries: list[dict], asof: pd.Timestamp) -> list[dict]:
    """Tracker rows for listed games that have both a market line and a model projection."""
    now = asof.isoformat(timespec="seconds")
    out = []
    for e in entries:
        m = e.get("model")
        if not m:
            continue
        for kind, mkt, mod in (("spread", e.get("spread_home"), m["margin"]), ("total", e.get("total"), m["total"])):
            if mkt is None or pd.isna(mkt):
                continue
            gap = round(float(mod) - float(mkt), 1)
            side = (e["home"] if gap > 0 else e["away"]) if kind == "spread" else ("Over" if gap > 0 else "Under")
            out.append({"read_id": f"{e['event_id']}:{kind}", "event_id": e["event_id"], "tipoff": e["tipoff"],
                        "matchup": e["matchup"], "home": e["home"], "away": e["away"], "kind": kind, "first_seen": now,
                        "market": float(mkt), "model": float(mod), "gap": gap, "side": side, "early": m.get("early"),
                        "key_out": m.get("key_out", 0),
                        "status": "open"})
    return out


def record(new_rows: list[dict], asof: pd.Timestamp) -> int:
    """Log reads once, at their first listing; returns how many were new."""
    if not new_rows:
        return 0
    df = load()
    seen = set(df["read_id"]) if len(df) else set()
    new = [r for r in new_rows if r["read_id"] not in seen and pd.Timestamp(r["tipoff"]) > asof]
    if new:
        save(pd.concat([x for x in (df, pd.DataFrame(new).reindex(columns=COLUMNS)) if len(x)], ignore_index=True))
    return len(new)


def _close(event_id: str, tipoff: pd.Timestamp, snaps: list[pd.DataFrame]) -> tuple[float, float] | None:
    """(home margin, total) from the last game-line pull before tip (books' median)."""
    from betlab.cards import fun_nba

    best = None
    for snap in snaps:
        ev = snap[snap["event_id"] == event_id]
        if len(ev) and pd.to_datetime(ev["snapshot_ts"], utc=True, format="ISO8601").max() < tipoff and (
                best is None or ev["snapshot_ts"].max() > best["snapshot_ts"].max()):
            best = ev
    if best is None:
        return None
    return fun_nba._center(best, best["home_team"].iloc[0], best["away_team"].iloc[0])


def _result(kind: str, side: str, home: str, line: float, final: float) -> str:
    """The model's side at the first line: spread lines are the home team's expected margin."""
    diff = final - line
    if kind == "spread" and side != home:
        diff = -diff
    if kind == "total" and side == "Under":
        diff = -diff
    return "won" if diff > 0 else "lost" if diff < 0 else "push"


def grade(finals: dict | None = None, snaps: list[pd.DataFrame] | None = None, now: pd.Timestamp | None = None) -> int:
    """Fill the close, the line move toward the model and the result once a game is final. finals:
    {(home display name, away display name, ET day): (home points, away points)} (tests pass them)."""
    df = load()
    now = now or pd.Timestamp.now(tz="UTC")
    todo = df[(df["status"] == "open") & (pd.to_datetime(df["tipoff"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=3))]
    if todo.empty:
        return 0
    if finals is None:
        from betlab.sources import nba

        seasons = sorted({nba.current_season(pd.Timestamp(t).tz_convert("America/New_York")) for t in todo["tipoff"]})
        sched = nba.load_schedules(seasons, max_age_hours=1.0)
        sched = sched[sched["status_type_completed"].fillna(False).astype(bool)]
        day = pd.to_datetime(sched["tipoff"], utc=True, format="ISO8601").dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
        finals = {(h, a, d): (float(hs), float(as_)) for h, a, d, hs, as_ in
                  zip(sched["home_display_name"], sched["away_display_name"], day, sched["home_score"], sched["away_score"])}
    if snaps is None:
        sport = config.settings()["leagues"]["nba"]["sport_key"]
        snaps = [pd.read_parquet(f) for f in sorted((config.DATA_DIR / "odds" / sport).glob("*/*_pick.parquet"))]
    stamp, n = now.isoformat(timespec="seconds"), 0
    for i, r in todo.iterrows():
        away, _, home = str(r["matchup"]).partition(" @ ")
        tip = pd.Timestamp(r["tipoff"])
        score = finals.get((home, away, tip.tz_convert("America/New_York").strftime("%Y-%m-%d")))
        if score is None:
            continue
        final = score[0] - score[1] if r["kind"] == "spread" else score[0] + score[1]
        close = _close(r["event_id"], tip, snaps)
        c = None if close is None else (close[0] if r["kind"] == "spread" else close[1])
        toward = 1 if float(r["gap"]) > 0 else -1
        df.loc[i, ["final", "result", "status", "graded_at"]] = [final, _result(r["kind"], r["side"], r["home"],
                                                                                 float(r["market"]), final), "graded", stamp]
        if c is not None:
            df.loc[i, ["close", "moved_pts"]] = [c, round(toward * (c - float(r["market"])), 2)]
        n += 1
    if n:
        save(df)
    return n


def summary(df: pd.DataFrame | None = None, min_gap: float = 2.0) -> dict:
    """Graded reads by kind: how often the model's side won at the first line, and the average line move
    toward it, for all reads and for gaps of `min_gap`+ points."""
    df = load() if df is None else df
    g = df[df["status"] == "graded"].copy()
    out = {}
    for kind, x in g.groupby("kind"):
        x = x[x["result"].isin(["won", "lost"])]
        big = x[pd.to_numeric(x["gap"]).abs() >= min_gap]
        mv = lambda y: None if y["moved_pts"].dropna().empty else round(float(pd.to_numeric(y["moved_pts"]).mean()), 2)
        out[kind] = {"n": len(x), "won": round(float((x["result"] == "won").mean()), 3) if len(x) else None,
                     "moved": mv(x), f"n_{min_gap:g}+": len(big),
                     f"won_{min_gap:g}+": round(float((big["result"] == "won").mean()), 3) if len(big) else None,
                     f"moved_{min_gap:g}+": mv(big) if len(big) else None}
    return out
