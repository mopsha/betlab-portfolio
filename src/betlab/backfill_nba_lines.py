"""Historical NBA game lines, to test the team model against the market (paid key only).

`betlab backfill nba-lines --season 2026 [--max-credits 4800] [--limit N]`

Mike approved Sep 28 (docs/DECISIONS.md, "historical odds spending plan"). For each
regular-season game day, spreads and totals for the whole slate (one historical call:
20 credits with our ten books; the moneyline is left out because the team model
predicts margin and total, and it would cost 50% more):
- 15 minutes before the first tip at 6 PM ET or later, and
- 15 minutes before the first West Coast tip (9:30 PM ET or later) when there are 2+.
Afternoon games go uncovered. On the 2025-26 schedule this is 231 snapshots (~4,620
credits): 92% of games, 77% within 2 hours of tip. Each game's line is read from the
last snapshot before its tip (`hours_before` says how close that was).

Rows are the odds_api.flatten columns, appended to
data/odds_history/basketball_nba/lines_<season>.parquet after every snapshot, so a run
can stop and resume. It stops before spending more than max_credits.
"""

from __future__ import annotations

import pandas as pd

from betlab import config
from betlab.sources import nba, odds_api

SPORT = "basketball_nba"
MARKETS = ("spreads", "totals")
EVENING_HOUR = 18.0
LATE_HOUR = 21.5


def path(season: int):
    return config.DATA_DIR / "odds_history" / SPORT / f"lines_{season}.parquet"


def _iso(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def plan(schedule: pd.DataFrame) -> list[pd.Timestamp]:
    """Snapshot times (UTC) for completed regular-season games, per the module rule."""
    s = schedule[(schedule["season_type"] == 2) & schedule["status_type_completed"].astype(bool)].copy()
    s["tip"] = pd.to_datetime(s["start_date"], utc=True, format="ISO8601")
    et = s["tip"].dt.tz_convert("America/New_York")
    s["day"], s["hr"] = et.dt.date, et.dt.hour + et.dt.minute / 60
    times = []
    for _, g in s.groupby("day"):
        evening = g.loc[g["hr"] >= EVENING_HOUR, "tip"]
        if evening.empty:
            continue
        times.append(evening.min() - pd.Timedelta(minutes=15))
        late = g.loc[g["hr"] >= LATE_HOUR, "tip"]
        if len(late) >= 2:
            times.append(late.min() - pd.Timedelta(minutes=15))
    return sorted(times)


def run(season: int, max_credits: int = 4800, limit: int | None = None) -> pd.DataFrame:
    """Backfill the planned snapshots not yet saved; returns everything saved for the season."""
    out = path(season)
    out.parent.mkdir(parents=True, exist_ok=True)
    have = pd.read_parquet(out) if out.exists() else pd.DataFrame()
    done = set(have["requested_at"]) if len(have) else set()
    todo = [t for t in plan(nba.load_schedules([season])) if _iso(t) not in done]
    if limit:
        todo = todo[:limit]
    if not todo:
        print("nothing to backfill")
        return have
    client = odds_api.OddsApiClient()
    client.sync_balance()
    each = odds_api.estimate_cost(len(MARKETS), len(client.bookmakers), historical=True)
    frames, spent = ([have] if len(have) else []), 0
    for t in todo:
        if spent + each > max_credits:
            print(f"stopping: the next snapshot would pass the {max_credits}-credit cap ({spent} spent)")
            break
        resp = client.historical_odds(SPORT, MARKETS, _iso(t))
        spent += each
        data = resp.get("data") if isinstance(resp, dict) else resp
        df = odds_api.flatten(data or [], SPORT, resp.get("timestamp", _iso(t)) if isinstance(resp, dict) else _iso(t))
        df["requested_at"] = _iso(t)
        # Only games that hadn't tipped: the snapshot can include live games' in-play lines.
        df = df[pd.to_datetime(df["commence_time"], utc=True, format="ISO8601") > t]
        if df.empty:  # keep a marker row so a resume doesn't pay for this time again
            df = pd.DataFrame([{c: None for c in odds_api.SNAPSHOT_COLUMNS} | {"requested_at": _iso(t)}])
        frames.append(df)
        pd.concat(frames, ignore_index=True).to_parquet(out, index=False)
        print(f"{_iso(t)}: {df['event_id'].nunique()} games | spent {spent} | credits: {client.balance_note()}")
    return pd.concat(frames, ignore_index=True) if frames else have


def closing_lines(season: int, max_hours: float = 6.0) -> pd.DataFrame:
    """Each game's line from the last saved snapshot before its tip, per book:
    event_id, commence_time, home_team, away_team, bookmaker, market, outcome, point,
    price, hours_before. Every snapshot also lists games days ahead, so a game the plan
    doesn't cover (an afternoon tip) would get a stale line: games whose last look is
    more than max_hours before tip are dropped."""
    df = pd.read_parquet(path(season)).dropna(subset=["event_id"])
    df["snapshot_ts"] = pd.to_datetime(df["snapshot_ts"], utc=True)
    df["commence_time"] = pd.to_datetime(df["commence_time"], utc=True, format="ISO8601")
    df = df[df["snapshot_ts"] < df["commence_time"]]
    last = df.groupby("event_id")["snapshot_ts"].transform("max")
    df = df[df["snapshot_ts"] == last].copy()
    df["hours_before"] = (df["commence_time"] - df["snapshot_ts"]).dt.total_seconds() / 3600
    df = df[df["hours_before"] <= max_hours]
    return df.drop(columns=["requested_at"], errors="ignore")
