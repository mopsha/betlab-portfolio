"""The wind watch (Nov 4): does a windy NFL game's total go under against the close? scripts/nfl_wind_refs_study.py found a lead, not proof:
at a forecast of 15+ mph at kickoff the under hit 59.6% in 2021-25 (47 games, +/- 14) and 57.0% on game-day readings since 1999 (674). So
this logs it forward and bets nothing: not a pick, not a lean, no weight anywhere. Each NFL day's 9:55 daily: outdoor games today with
12+ mph forecast, FanDuel's total and under price and Pinnacle's no-vig chance of the under, then the close and the result once graded.
Free: Open-Meteo, the morning's saved pull and nflverse. Judge at about 50 graded 15+ mph games, against 52.4%; don't act on less.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
LEAST_MPH = 12.0
COLUMNS = ["game_id", "commence_time", "matchup", "logged_at", "wind_mph", "gust_mph", "total_fd", "under_fd", "total_sharp", "p_under_sharp",
           "total_close", "final_total", "under_won", "graded_at"]


def _path():
    from betlab import config

    return config.DATA_DIR / "ledger" / "wind_watch.csv"


def load() -> pd.DataFrame:
    p = _path()
    return pd.read_csv(p, dtype={"game_id": str}) if p.exists() else pd.DataFrame(columns=COLUMNS)


def _prices(snap: pd.DataFrame | None, home: str, away: str) -> dict:
    """FanDuel's main total and under price, and the first sharp book's total and no-vig under chance, for one game."""
    from betlab import odds_math as om
    from betlab.sources.nflverse import team_abbr_by_name

    out = {"total_fd": None, "under_fd": None, "total_sharp": None, "p_under_sharp": None}
    if snap is None or snap.empty:
        return out
    abbr = team_abbr_by_name()
    t = snap[(snap["market"] == "totals") & (snap["home_team"].map(abbr) == home) & (snap["away_team"].map(abbr) == away)]
    fd = t[t["bookmaker"] == "fanduel"]
    u = fd[fd["outcome"] == "Under"]
    if len(u):
        out["total_fd"], out["under_fd"] = float(u["point"].iloc[0]), float(u["price"].iloc[0])
    for book in ("pinnacle", "lowvig", "betonlineag"):
        x = t[t["bookmaker"] == book]
        o, n = x[x["outcome"] == "Over"], x[x["outcome"] == "Under"]
        if len(o) and len(n):
            out["total_sharp"], out["p_under_sharp"] = float(n["point"].iloc[0]), round(om.no_vig_two_way(n["price"].iloc[0], o["price"].iloc[0])[0], 4)
            break
    return out


def record(games: pd.DataFrame, snap: pd.DataFrame | None, now: datetime, forecast=None, venue=None) -> pd.DataFrame:
    """Today's windy outdoor games, each logged once."""
    from betlab.sources import weather

    forecast, venue = forecast or weather.forecast, venue or weather.venue
    d = load()
    day = now.astimezone(ET).strftime("%Y-%m-%d")
    rows = []
    for g in games[games["gameday"].astype(str) == day].itertuples():
        if g.game_id in set(d["game_id"]):
            continue
        v = venue(getattr(g, "stadium_id", None), getattr(g, "stadium", None))
        if not v or v.get("roof") != "outdoors":
            continue
        kick = pd.Timestamp(f"{g.gameday} {g.gametime}").tz_localize("America/New_York")
        wx = forecast(v["lat"], v["lon"], kick)
        if not wx or (wx.get("wind_mph") or 0) < LEAST_MPH:
            continue
        rows.append({"game_id": g.game_id, "commence_time": kick.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "matchup": f"{g.away_team} @ {g.home_team}",
                     "logged_at": now.isoformat(timespec="seconds"), "wind_mph": round(wx["wind_mph"], 1), "gust_mph": wx.get("gust_mph"),
                     **_prices(snap, g.home_team, g.away_team)})
    if rows:
        d = pd.concat([d.astype(object), pd.DataFrame(rows).astype(object)], ignore_index=True).reindex(columns=COLUMNS)
    return d


def grade(d: pd.DataFrame, games: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """The close and the result from nflverse's schedule: the under against the close, a push is neither."""
    d = d.copy().astype(object)
    by = games.drop_duplicates("game_id").set_index("game_id")
    for i, r in d[d["graded_at"].isna()].iterrows():
        if r["game_id"] not in by.index:
            continue
        g = by.loc[r["game_id"]]
        if pd.isna(g.get("total")) or pd.isna(g.get("total_line")):
            continue
        d.at[i, "total_close"], d.at[i, "final_total"] = float(g["total_line"]), float(g["total"])
        d.at[i, "under_won"] = None if g["total"] == g["total_line"] else bool(g["total"] < g["total_line"])
        d.at[i, "graded_at"] = now.isoformat(timespec="seconds")
    return d


def run(now: datetime | None = None) -> str:
    from betlab import config
    from betlab.sources import nflverse

    now = now or datetime.now(ET)
    games = nflverse.load_games()
    files = sorted((config.DATA_DIR / "odds" / "americanfootball_nfl").glob("*/*_pick.parquet"))
    snap = pd.read_parquet(files[-1]) if files else None
    before = len(load())
    d = grade(record(games, snap, now), games, now)
    _path().parent.mkdir(parents=True, exist_ok=True)
    d.reindex(columns=COLUMNS).to_csv(_path(), index=False)
    g = d[d["graded_at"].notna() & d["under_won"].notna()]
    hard = g[pd.to_numeric(g["wind_mph"]) >= 15]
    return (f"wind watch: {len(d) - before} logged today, {len(d)} in all; graded {len(g)} (under {g['under_won'].astype(bool).mean():.0%}), "
            f"15+ mph {len(hard)}" if len(g) else f"wind watch: {len(d) - before} logged today, {len(d)} in all; none graded yet")
