"""The soccer lineup goals read and its track record: data/ledger/soccer_goal_reads.csv (Oct 12).

The soccer analysis (cards/analysis_soccer.py) projects each starter's goals with the shots model, which takes
the market's expected goals as an input and adjusts for who actually starts. The read is the starters' goals
over the share of goals starters score (the rest come from substitutes): a lineup-adjusted version of the
market, not an independent view. It differs from the market mostly when a team rotates or a scorer sits,
which is what a bulk price might miss. From the two teams' expected goals (independent Poisson):
over 2.5 goals and both teams to score, ours against the market's.

One row per match, logged once at the first build with a confirmed lineup; graded from the final score
(fun_ledger._soccer_result: football-data, else ESPN). Tracked only, no weight: it reaches the goals card
(cards/soccer_goals.py) only if its log loss beats the market's here.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

PATH = config.DATA_DIR / "ledger" / "soccer_goal_reads.csv"
COLUMNS = ["event_id", "league", "matchup", "home", "away", "commence_time", "first_seen", "xg_home_mkt", "xg_away_mkt",
           "xg_home", "xg_away", "p_over25_mkt", "p_over25", "p_btts_mkt", "p_btts", "home_goals", "away_goals",
           "status", "graded_at"]
TEXT = ["event_id", "league", "matchup", "home", "away", "commence_time", "first_seen", "status", "graded_at"]


def probs(xg_home: float, xg_away: float) -> tuple[float, float]:
    """(P(3+ goals), P(both score)) for independent Poisson team goals."""
    total = xg_home + xg_away
    p_le2 = math.exp(-total) * (1 + total + total ** 2 / 2)
    return 1 - p_le2, (1 - math.exp(-xg_home)) * (1 - math.exp(-xg_away))


def read(teams: list[dict]) -> dict | None:
    """The match's read from the analysis's two teams (`xg` the market's, `goals_model` the lineup's)."""
    if len(teams) != 2 or any(t.get("xg") is None or t.get("goals_model") is None for t in teams):
        return None
    h, a = teams
    o_mkt, b_mkt = probs(h["xg"], a["xg"])
    o, b = probs(h["goals_model"], a["goals_model"])
    return {"xg_home": h["goals_model"], "xg_away": a["goals_model"], "xg_home_mkt": h["xg"], "xg_away_mkt": a["xg"],
            "p_over25": round(o, 4), "p_over25_mkt": round(o_mkt, 4), "p_btts": round(b, 4), "p_btts_mkt": round(b_mkt, 4)}


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(rows: list[dict], asof: pd.Timestamp) -> int:
    """Log reads once (confirmed lineups only, before kickoff); returns how many were new."""
    df = load()
    seen = set(df["event_id"].astype(str)) if len(df) else set()
    new = [r | {"first_seen": asof.isoformat(timespec="seconds"), "status": "open"} for r in rows
           if str(r["event_id"]) not in seen and pd.Timestamp(r["commence_time"]) > asof]
    if new:
        save(pd.concat([x for x in (df, pd.DataFrame(new).reindex(columns=COLUMNS)) if len(x)], ignore_index=True))
    return len(new)


def grade(result=None, now: pd.Timestamp | None = None) -> int:
    """Fill the final score once it's out (football-data, else ESPN)."""
    from betlab.fun_ledger import _soccer_result

    result = result or _soccer_result
    df = load()
    now = now or pd.Timestamp.now(tz="UTC")
    todo = df[(df["status"] == "open") & (pd.to_datetime(df["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=3))]
    stamp, n = now.isoformat(timespec="seconds"), 0
    for i, r in todo.iterrows():
        try:
            res = result(r["league"], r["home"], r["away"], pd.Timestamp(r["commence_time"]))
        except Exception:  # noqa: BLE001 - a source down: try tomorrow
            res = None
        if res is None:
            continue
        df.loc[i, ["home_goals", "away_goals", "status", "graded_at"]] = [res["hg"], res["ag"], "graded", stamp]
        n += 1
    if n:
        save(df)
    return n


def summary(df: pd.DataFrame | None = None) -> dict:
    """Log loss of the read vs the market on over 2.5 and both teams to score (lower is better)."""
    df = load() if df is None else df
    g = df[df["status"] == "graded"].copy()
    if g.empty:
        return {"graded": 0}
    cols = ["p_over25", "p_over25_mkt", "p_btts", "p_btts_mkt", "home_goals", "away_goals"]
    g = g[g[cols].apply(pd.to_numeric, errors="coerce").notna().all(axis=1)]   # the read and the market on the same matches
    if g.empty:
        return {"graded": 0}
    hg, ag = pd.to_numeric(g["home_goals"]), pd.to_numeric(g["away_goals"])
    ll = lambda p, y: float(-np.mean(y * np.log(np.clip(p, 1e-4, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-4, 1))))
    over, btts = ((hg + ag) > 2.5).astype(float), ((hg > 0) & (ag > 0)).astype(float)
    num = lambda c: pd.to_numeric(g[c])
    return {"graded": len(g), "over25": {"read": round(ll(num("p_over25"), over), 4), "market": round(ll(num("p_over25_mkt"), over), 4)},
            "btts": {"read": round(ll(num("p_btts"), btts), 4), "market": round(ll(num("p_btts_mkt"), btts), 4)}}
