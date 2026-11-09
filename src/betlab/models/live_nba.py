"""Tonight's NBA players, priced with the backtested player model (models/player_nba.py).

The live rows go through the same feature code as the backtest: tonight's players are
appended to the box-score history as "pending" rows (no minutes yet), teammates ruled out
on the injury report are appended as did-not-play rows, and tonight's team rows get their
rest and back-to-back flags. `player_games` then computes every feature from earlier games
only, exactly as it did in the backtest. `validate_on` replays a past night and checks
that the live path reproduces the backtest's features.

- **Roster:** ESPN's current roster when given (`nba.rosters_now`), else players whose
  latest game was for that team, within the team's last 15 games.
- **Injuries:** ESPN's report (latest entry per player): "Out" sits; "Day-To-Day" plays
  and is flagged.
- **Blowout risk:** the market spread (|home spread|), as the backtest used the team model's margin.
- **Lineups:** when nba.com has confirmed a game's starting lineups (`nba.lineups`), that
  game is priced with the `lineup` settings and each player's starter_now; otherwise with
  `pre_lineup` (cards/props_nba.py decides per game).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from betlab import config
from betlab.models import player_nba as P
from betlab.models import team_nba as T

PARAMS_PATH = config.DATA_DIR / "models" / "nba_player.json"
ROSTER_GAMES = 15
PENDING_BASE = 9_000_000_000  # synthetic game ids for tonight (ESPN ids are far smaller)


def load_params(kind: str = "pre_lineup") -> dict:
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8"))[kind]


def rosters(pb: pd.DataFrame, sch: pd.DataFrame, teams, before) -> pd.DataFrame:
    """Players whose latest game before `before` was for one of `teams`, within that team's
    last ROSTER_GAMES games: athlete_id, name, team_id, team_abbreviation, position."""
    before = pd.Timestamp(before)
    h = pb.merge(sch[["game_id", "tipoff"]], on="game_id")
    h = h[(h["tipoff"] < before) & (pd.to_numeric(h["minutes"], errors="coerce").fillna(0) > 0)]
    latest = h.sort_values("tipoff").groupby("athlete_id").tail(1)
    out = []
    for team in teams:
        tgames = h[h["team_abbreviation"] == team].drop_duplicates("game_id").nlargest(ROSTER_GAMES, "tipoff")
        keep = latest[(latest["team_abbreviation"] == team) & latest["game_id"].isin(tgames["game_id"])]
        out.append(keep)
    cols = ["athlete_id", "athlete_display_name", "team_id", "team_abbreviation", "athlete_position_abbreviation"]
    return pd.concat(out)[cols] if out else pd.DataFrame(columns=cols)


def tonight(pb: pd.DataFrame, tb: pd.DataFrame, sch: pd.DataFrame, games: pd.DataFrame,
            out_ids: set | None = None, questionable_ids: set | None = None, params: dict | None = None,
            roster: pd.DataFrame | None = None, starters: set | None = None) -> pd.DataFrame:
    """Feature rows and projections for tonight's players.

    games: one row per game with game_id, tipoff (UTC), home, away (ESPN abbreviations),
    spread_home (points the home team is favored by, from the market; may be NaN).
    out_ids / questionable_ids: athlete ids ruled out / day-to-day tonight.
    roster: current rosters (nba.rosters_now); None rebuilds them from box scores.
    starters: athlete ids in tonight's confirmed starting lineups, for games priced with the
    `lineup` settings (their starter_now feature); None leaves it unknown (`pre_lineup`).
    Returns one row per player expected to play, with mu_<stat>, minutes projection and flags.
    """
    params = params or load_params()
    out_ids, questionable_ids = out_ids or set(), questionable_ids or set()
    first = games["tipoff"].min()
    hist_pb = pb.merge(sch[["game_id", "tipoff"]], on="game_id")
    hist_pb = hist_pb[hist_pb["tipoff"] < first].drop(columns="tipoff")
    hist_sch = sch[sch["tipoff"] < first]
    ids = {abbr: tid for abbr, tid in hist_pb[["team_abbreviation", "team_id"]].drop_duplicates("team_abbreviation").itertuples(index=False)}
    teams = set(games["home"]) | set(games["away"])
    ros = rosters(pb, sch, teams, first) if roster is None else roster[roster["team_abbreviation"].isin(teams)]
    season = int(hist_pb["season"].max())
    new_pb, new_sch, new_tb = [], [], []
    for g in games.itertuples():
        gid = PENDING_BASE + int(g.Index) if not isinstance(g.game_id, (int, np.integer)) else int(g.game_id)
        new_sch.append({"game_id": gid, "tipoff": g.tipoff, "neutral_site": False, "periods": np.nan})
        for team, opp, ha in ((g.home, g.away, "home"), (g.away, g.home, "away")):
            new_tb.append({"game_id": gid, "season": season, "season_type": 2, "team_id": ids.get(team),
                           "opponent_team_id": ids.get(opp), "team_abbreviation": team, "opponent_team_abbreviation": opp,
                           "team_home_away": ha})
            for r in ros[ros["team_abbreviation"] == team].itertuples():
                sits = r.athlete_id in out_ids
                new_pb.append({"game_id": gid, "season": season, "season_type": 2, "athlete_id": r.athlete_id,
                               "athlete_display_name": r.athlete_display_name, "team_id": r.team_id,
                               "team_abbreviation": team, "opponent_team_id": ids.get(opp),
                               "athlete_position_abbreviation": r.athlete_position_abbreviation,
                               "minutes": np.nan,
                               "starter": np.nan if starters is None else float(r.athlete_id in starters),
                               "did_not_play": sits,
                               "reason": "OUT (INJURY REPORT)" if sits else None, "pending": not sits})
    pb2 = pd.concat([hist_pb.assign(pending=False), pd.DataFrame(new_pb)], ignore_index=True)
    sch2 = pd.concat([hist_sch, pd.DataFrame(new_sch)], ignore_index=True)
    tg = T.team_games(pd.concat([tb[tb["game_id"].isin(hist_sch["game_id"])], pd.DataFrame(new_tb)], ignore_index=True), sch2)
    pg = P.player_games(pb2, tg, sch2)
    live = pg[pg["pending"]].copy()
    spread = {}
    for g in games.itertuples():
        gid = PENDING_BASE + int(g.Index) if not isinstance(g.game_id, (int, np.integer)) else int(g.game_id)
        spread[gid] = abs(float(g.spread_home)) if pd.notna(g.spread_home) else np.nan
    live = P.with_blowout(live, live["game_id"].map(spread))
    mu = P.predict(live, params)
    for k, v in mu.items():
        live[f"mu_{k}"] = v
    live["questionable"] = live["athlete_id"].isin(questionable_ids)
    live["event_key"] = live["game_id"]
    return live.reset_index(drop=True)


def validate_on(pb: pd.DataFrame, tb: pd.DataFrame, sch: pd.DataFrame, date, params: dict | None = None) -> pd.DataFrame:
    """Replay a past night through the live path and compare its features with the backtest's.

    The night's own did-not-play reasons stand in for that day's injury report. Returns one
    row per feature: how many players matched and the largest absolute difference."""
    date = pd.Timestamp(date)
    et = sch["tipoff"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    night = sch[et == date]
    games = pd.DataFrame({"game_id": night["game_id"].to_numpy(), "tipoff": night["tipoff"].to_numpy(),
                          "home": night["home_abbreviation"].to_numpy(), "away": night["away_abbreviation"].to_numpy(),
                          "spread_home": np.nan})
    box = pb[pb["game_id"].isin(night["game_id"])]
    out = set(box.loc[box["did_not_play"].fillna(False) & ~box["reason"].fillna("").isin(P.OUT_REASONS_EXCLUDE), "athlete_id"])
    live = tonight(pb[~pb["game_id"].isin(night["game_id"])].pipe(lambda d: pd.concat([d, box])),
                   tb, sch, games, out_ids=out, params=params)
    tg = T.team_games(tb, sch)
    full = P.player_games(pb, tg, sch)
    full = full[full["game_id"].isin(night["game_id"])]
    both = live.merge(full, on=["athlete_id", "game_id"], suffixes=("_live", "_full"))
    rows = []
    for f in ["ewm_min", "avg10_min", "start_share", "missing_min", "missing_points_share", "returning", "b2b", "home",
              "rate_points", "rate_rebounds", "opp_points", "opp_assists", "pace_factor"]:
        a, b = both[f"{f}_live"].astype(float), both[f"{f}_full"].astype(float)
        ok = a.notna() & b.notna()
        rows.append({"feature": f, "players": int(ok.sum()), "max_abs_diff": float((a[ok] - b[ok]).abs().max()) if ok.any() else None})
    return pd.DataFrame(rows)
