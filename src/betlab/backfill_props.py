"""Historical NFL prop lines, to test the props model against the market (paid key only).

`betlab backfill props --season 2025 --weeks 3-18 [--limit N]`

For each regular-season game, one snapshot of every book's main prop lines (receptions,
receiving, rushing and passing yards) about an hour before kickoff, from the historical
event-odds endpoint. That costs 10x a live call: about 40 credits a game. Rows are the
odds_api.flatten columns plus game_id and week, appended to
data/odds_history/americanfootball_nfl/props_<season>.parquet after every game, so a run
can stop and resume: games already saved are skipped.
"""

from __future__ import annotations

import pandas as pd

from betlab import config
from betlab.sources import nflverse, odds_api

SPORT = "americanfootball_nfl"
MARKETS = odds_api.NFL_PROP_MARKETS


def path(season: int):
    return config.DATA_DIR / "odds_history" / SPORT / f"props_{season}.parquet"


def _iso(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def run(season: int, weeks: range, limit: int | None = None, minutes_before: int = 60) -> pd.DataFrame:
    """Backfill the given weeks; returns everything saved for the season."""
    out = path(season)
    out.parent.mkdir(parents=True, exist_ok=True)
    have = pd.read_parquet(out) if out.exists() else pd.DataFrame()
    done = set(have["game_id"]) if len(have) else set()
    games = nflverse.load_games()
    games = games[(games["season"] == season) & (games["game_type"] == "REG") & games["week"].isin(weeks)]
    games = games[~games["game_id"].isin(done)].sort_values("kickoff")
    if limit:
        games = games.head(limit)
    if games.empty:
        print("nothing to backfill")
        return have
    names = {abbr: name for name, abbr in nflverse.team_abbr_by_name().items()}
    # Relocated teams have several names for one code; the Odds API uses the current one.
    names |= {"LV": "Las Vegas Raiders", "LAC": "Los Angeles Chargers", "LA": "Los Angeles Rams"}
    client = odds_api.OddsApiClient()
    client.sync_balance()
    events_by_week: dict[int, list[dict]] = {}
    frames = [have] if len(have) else []
    for g in games.itertuples():
        if g.week not in events_by_week:
            first = games[games["week"] == g.week]["kickoff"].min() - pd.Timedelta(hours=3)
            resp = client.historical_events(SPORT, _iso(first))
            events_by_week[g.week] = resp.get("data", resp) if isinstance(resp, dict) else resp
        home, away = names.get(g.home_team), names.get(g.away_team)
        ev = next((e for e in events_by_week[g.week] if e["home_team"] == home and e["away_team"] == away), None)
        if ev is None:
            print(f"{g.game_id}: no matching event, skipped")
            continue
        when = g.kickoff - pd.Timedelta(minutes=minutes_before)
        resp = client.historical_event_odds(SPORT, ev["id"], MARKETS, _iso(when))
        data = resp.get("data") if isinstance(resp, dict) and "data" in resp else resp
        if not data:
            print(f"{g.game_id}: no odds at {_iso(when)}")
            continue
        df = odds_api.flatten(data, SPORT, resp.get("timestamp", _iso(when)))
        df["game_id"], df["week"] = g.game_id, g.week
        frames.append(df)
        pd.concat(frames, ignore_index=True).to_parquet(out, index=False)
        print(f"{g.game_id}: {len(df)} prices | credits: {client.balance_note()}")
    return pd.concat(frames, ignore_index=True) if frames else have
