"""Every NHL game the Games tab has priced: data/ledger/nhl_lines.csv.

One row per game. The **first** look is kept as it was (DraftKings' line then, the goalies
then, our model then): if the model knows something, the line should move toward it by
puck drop, and the first number is the one that could be bet. The **last** look before
the start updates on every build. After the game: the result, and DraftKings' closing
line from ESPN (free), so each read gets its closing-line value.

This is the NHL's track record and the training set for anything we learn later. Nothing
here is a pick: the lines are free DraftKings numbers, not FanDuel's, and no sharp book is
in the feed (sources/nhl.py).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config
from betlab import odds_math as om

PATH = config.DATA_DIR / "ledger" / "nhl_lines.csv"
FIRST = ["ml_home", "ml_away", "total", "over", "under", "p_mkt", "p_model", "p_over_mkt", "p_over_model",
         "home_goalie", "away_goalie", "home_goalie_status", "away_goalie_status"]
COLUMNS = (["game_id", "espn_id", "start", "home", "away", "book"]
           + ["first_seen"] + [f"first_{c}" for c in FIRST]
           + ["updated_at"] + [f"last_{c}" for c in FIRST]
           + ["home_xg", "away_xg", "exp_total",
              "close_ml_home", "close_ml_away", "close_total", "close_over", "close_under", "p_close",
              "home_goals", "away_goals", "home_win", "final_total", "extra",
              "read_side", "read_gap", "read_won", "read_clv", "status", "graded_at"])
TEXT = ["game_id", "espn_id", "start", "home", "away", "book", "first_seen", "updated_at", "status", "graded_at",
        "first_home_goalie", "first_away_goalie", "first_home_goalie_status", "first_away_goalie_status",
        "last_home_goalie", "last_away_goalie", "last_home_goalie_status", "last_away_goalie_status", "read_side"]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(rows: list[dict], asof: pd.Timestamp) -> int:
    """Rows from cards/preview_nhl.py (games not yet started): first look kept, last updated."""
    now = asof.isoformat(timespec="seconds")
    df = load().set_index("game_id", drop=False)
    n = 0
    for r in rows:
        if pd.Timestamp(r["start"]) <= asof:
            continue
        gid = str(r["game_id"])
        vals = {c: r.get(c) for c in FIRST}
        if gid in df.index:
            df.at[gid, "updated_at"] = now
            # a game is seen before it has a line: the first look is its first price (Nov 1: a row made priceless kept an
            # empty first look for good, so from Oct 12 to Nov 1 no game had a read or a first market chance)
            if pd.isna(pd.to_numeric(df.at[gid, "first_ml_home"], errors="coerce")) and pd.notna(vals["ml_home"]):
                df.at[gid, "first_seen"], df.at[gid, "book"] = now, r.get("book")
                for c, v in vals.items():
                    df.at[gid, f"first_{c}"] = v
            for c, v in vals.items():
                df.at[gid, f"last_{c}"] = v
            for c in ("home_xg", "away_xg", "exp_total"):
                df.at[gid, c] = r.get(c)
        else:
            row = {c: np.nan for c in COLUMNS} | {
                "game_id": gid, "espn_id": str(r.get("espn_id") or ""), "start": r["start"], "home": r["home"],
                "away": r["away"], "book": r.get("book"), "first_seen": now, "updated_at": now, "status": "open",
                "home_xg": r.get("home_xg"), "away_xg": r.get("away_xg"), "exp_total": r.get("exp_total"),
                **{f"first_{c}": v for c, v in vals.items()}, **{f"last_{c}": v for c, v in vals.items()}}
            df = pd.concat([df, pd.DataFrame([row]).set_index("game_id", drop=False)])
        n += 1
    save(df.reset_index(drop=True))
    return n


def grade(team_games: pd.DataFrame | None = None, closes: dict | None = None, now: pd.Timestamp | None = None,
          read_min: float | None = None) -> int:
    """Results (NHL stats API) and DraftKings' close (ESPN) for finished games."""
    df = load()
    if df.empty:
        return 0
    now = now or pd.Timestamp.now(tz="UTC")
    todo = df[(df["status"] == "open") & (pd.to_datetime(df["start"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4))]
    if todo.empty:
        return 0
    from betlab.sources import nhl

    if team_games is None:
        seasons = sorted({nhl.current_season(pd.Timestamp(s).tz_convert("America/New_York")) for s in todo["start"]})
        team_games = nhl.load_team_games(seasons, max_age_hours=1.0)
    if read_min is None:
        read_min = float(config.settings().get("nhl", {}).get("read_min", 0.04))
    home = team_games[team_games["home"] == 1].set_index(team_games[team_games["home"] == 1]["game_id"].astype(str))
    stamp, n = now.isoformat(timespec="seconds"), 0
    for i, r in todo.iterrows():
        gid = str(r["game_id"])
        if gid not in home.index:
            continue
        g = home.loc[gid]
        df.at[i, "home_goals"], df.at[i, "away_goals"] = g["gf"], g["ga"]
        df.at[i, "home_win"], df.at[i, "final_total"], df.at[i, "extra"] = int(g["win"]), g["gf"] + g["ga"], int(g["extra"])
        close = (closes or {}).get(str(r["espn_id"])) if closes is not None else nhl._summary_lines(str(r["espn_id"]))
        if close and close.get("ml_home_close") and close.get("ml_away_close"):
            df.at[i, "close_ml_home"], df.at[i, "close_ml_away"] = close["ml_home_close"], close["ml_away_close"]
            df.at[i, "close_total"], df.at[i, "close_over"], df.at[i, "close_under"] = (
                close.get("total_close"), close.get("over_close"), close.get("under_close"))
            df.at[i, "p_close"] = om.no_vig_two_way(close["ml_home_close"], close["ml_away_close"])[0]
        # The read: the first look's gap between our model and DraftKings' no-vig price.
        gap = pd.to_numeric(r["first_p_model"], errors="coerce") - pd.to_numeric(r["first_p_mkt"], errors="coerce")
        if np.isfinite(gap) and abs(gap) >= read_min:
            home_side = gap > 0
            df.at[i, "read_side"] = r["home"] if home_side else r["away"]
            df.at[i, "read_gap"] = round(float(gap), 4)
            df.at[i, "read_won"] = int(g["win"]) if home_side else 1 - int(g["win"])
            price = float(r["first_ml_home"] if home_side else r["first_ml_away"])
            if pd.notna(df.at[i, "p_close"]):
                pc = float(df.at[i, "p_close"])
                df.at[i, "read_clv"] = round(om.clv(price, pc if home_side else 1 - pc), 4)
        df.at[i, "status"], df.at[i, "graded_at"] = "graded", stamp
        n += 1
    save(df)
    return n


def summary(df: pd.DataFrame | None = None) -> dict:
    """The running record: games graded, the model's and DraftKings' log loss on the
    moneyline at the first look and at the close, and the reads' results and CLV."""
    df = load() if df is None else df
    g = df[df["status"] == "graded"] if len(df) else df
    out = {"games": int(len(df)), "graded": int(len(g)), "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if g.empty:
        return out
    y = pd.to_numeric(g["home_win"], errors="coerce")

    def ll(p, ok):
        p = np.clip(pd.to_numeric(p, errors="coerce"), 1e-6, 1 - 1e-6)
        return round(float(-np.mean(y[ok] * np.log(p[ok]) + (1 - y[ok]) * np.log(1 - p[ok]))), 4)

    def vs(market):
        # the model and the market on the same games (Oct 20: the model's 135 games sat beside the first look's 32,
        # since DraftKings-via-ESPN games have no first market chance)
        ok = y.notna() & pd.to_numeric(g["first_p_model"], errors="coerce").notna() & pd.to_numeric(g[market], errors="coerce").notna()
        return {"n": int(ok.sum()), "model": ll(g["first_p_model"], ok), "market": ll(g[market], ok)} if ok.any() else None

    out |= {"vs_first_look": vs("first_p_mkt"), "vs_close": vs("p_close")}
    reads = g[g["read_side"].notna()]
    if len(reads):
        clv = pd.to_numeric(reads["read_clv"], errors="coerce").dropna()
        out["reads"] = {"n": int(len(reads)), "won": int(pd.to_numeric(reads["read_won"]).sum()),
                        "avg_clv": round(float(clv.mean()), 4) if len(clv) else None,
                        "beat_close": round(float((clv > 0).mean()), 3) if len(clv) else None}
    return out
