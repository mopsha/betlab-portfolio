"""Does FanDuel's morning prop price lag the sharp market? (`betlab backtest lag`)

At the close, FanDuel's main prop lines showed no edge against the sharp market (2025,
docs/MODELS.md). The open question (to-do c-props-clv) is whether its *morning* prices
lag: a side that looks +EV against the sharp market in the morning, does it still beat
the sharp close, or does the edge vanish because the sharp side moves toward FanDuel?

From the committed props snapshots (data/odds/<sport>/<date>/*_props.parquet), for each
game with a morning snapshot (3+ hours before kickoff) and a closing one (the last within
2 hours of kickoff), and each FanDuel two-way main line in the morning:
- fair: the no-vig chance at FanDuel's exact point from the first sharp book quoting that
  point (Pinnacle, LowVig, BetOnline), else the median of 2+ other books there. Quotes
  at a different point are skipped rather than translated: this is a price test.
- ev_morning: the morning fair chance x FanDuel's morning payout - 1, per side.
- clv: the *close's* fair chance x FanDuel's morning payout - 1. This is the plain sharp
  close (clv_raw): correcting the close for the over lean would hand unders ~4 points.
- fd_moved: FanDuel's own chance at the close minus its morning chance (no-vig), to see
  whether FanDuel moves toward where the sharp books were.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config
from betlab import odds_math as om
from betlab import props_market as PM

SHARP = ("pinnacle", "lowvig", "betonlineag")
MORNING_HOURS = 3.0   # a morning snapshot is at least this long before kickoff
CLOSE_HOURS = 2.0     # the close is the last snapshot within this long before kickoff


def load(sport: str = "americanfootball_nfl") -> pd.DataFrame:
    """Every committed props snapshot for the sport: the pre-game ones (`_props`) and, from the new
    schedule (Oct 4), the data-only morning pulls (`_props_am`). Pre-game snapshots carry earlier
    rows forward for games outside their window (cli._merge_latest), so repeats are dropped."""
    files = sorted((config.DATA_DIR / "odds" / sport).glob("*/*_props*.parquet"))
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.drop_duplicates([c for c in ("snapshot_ts", "event_id", "bookmaker", "market", "outcome", "player", "point")
                             if c in df])
    df["snapshot_ts"] = pd.to_datetime(df["snapshot_ts"], utc=True)
    df["commence_time"] = pd.to_datetime(df["commence_time"], utc=True, format="ISO8601")
    return df[df["market"].isin(list(PM.MAIN))]


def _fair(rows: pd.DataFrame, point: float, target: str = "fanduel") -> tuple[float, str] | None:
    """(no-vig P(over) at this point, source) from one snapshot's rows for a player's stat."""
    quotes = [q for q in PM._two_way(rows[rows["point"] == point], "Over", "Under") if q[0] != target]
    for book in SHARP:
        for b, _, p in quotes:
            if b == book:
                return p, book
    if len(quotes) >= 2:
        return float(np.median([p for _, _, p in quotes])), f"consensus of {len(quotes)}"
    return None


def _fd(rows: pd.DataFrame, target: str = "fanduel"):
    """FanDuel's (point, over price, under price) in one snapshot's rows, or None."""
    fd = rows[rows["bookmaker"] == target]
    o, u = fd[fd["outcome"] == "Over"], fd[fd["outcome"] == "Under"]
    if o.empty or u.empty or float(o["point"].iloc[0]) != float(u["point"].iloc[0]):
        return None
    return float(o["point"].iloc[0]), float(o["price"].iloc[0]), float(u["price"].iloc[0])


def pairs(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (FanDuel morning line, side) with its morning EV and closing CLV."""
    rows = []
    for eid, ev in df.groupby("event_id"):
        kick = ev["commence_time"].iloc[0]
        hours = (kick - ev["snapshot_ts"]).dt.total_seconds() / 3600
        morning_ts = ev.loc[hours >= MORNING_HOURS, "snapshot_ts"]
        close_ts = ev.loc[(hours > 0) & (hours <= CLOSE_HOURS), "snapshot_ts"]
        if morning_ts.empty or close_ts.empty:
            continue
        m_ts = morning_ts.max()            # the latest morning look: the price we'd actually bet
        c_ts = close_ts.max()
        m, c = ev[ev["snapshot_ts"] == m_ts], ev[ev["snapshot_ts"] == c_ts]
        matchup = f"{ev['away_team'].iloc[0]} @ {ev['home_team'].iloc[0]}"
        for (player, market), g in m.groupby(["player", "market"]):
            fd = _fd(g)
            if fd is None:
                continue
            point, over, under = fd
            fm = _fair(g, point)
            gc = c[(c["player"] == player) & (c["market"] == market)]
            fc = _fair(gc, point)
            if fm is None or fc is None:
                continue
            fd_m = om.no_vig_two_way(over, under)[0]
            fdc = _fd(gc)
            fd_c = om.no_vig_two_way(fdc[1], fdc[2])[0] if fdc and fdc[0] == point else None
            for side, price, p_m, p_c in (("over", over, fm[0], fc[0]), ("under", under, 1 - fm[0], 1 - fc[0])):
                dec = om.american_to_decimal(price)
                rows.append({"event_id": eid, "matchup": matchup, "kickoff": kick, "player": player,
                             "stat": PM.MAIN[market], "point": point, "side": side, "price": price,
                             "hours_before": round(float((kick - m_ts).total_seconds() / 3600), 1),
                             "p_morning": p_m, "p_close": p_c, "ev_morning": p_m * dec - 1, "clv": p_c * dec - 1,
                             "source_morning": fm[1], "source_close": fc[1],
                             "fd_morning": fd_m if side == "over" else 1 - fd_m,
                             "fd_close": None if fd_c is None else (fd_c if side == "over" else 1 - fd_c)})
    return pd.DataFrame(rows)


def _boot(x: pd.DataFrame, col: str, reps: int = 1000, seed: int = 0) -> float:
    """Game-bootstrap SE of the mean of col."""
    if x.empty:
        return float("nan")
    rng = np.random.default_rng(seed)
    by = [g[col].to_numpy() for _, g in x.groupby("event_id")]
    means = []
    for _ in range(reps):
        pick = rng.integers(0, len(by), len(by))
        means.append(np.concatenate([by[i] for i in pick]).mean())
    return float(np.std(means))


def report(p: pd.DataFrame, thresholds=(0.0, 0.02, 0.03, 0.05)) -> pd.DataFrame:
    """Sides that looked +EV against the sharp market in the morning: how they did against
    the sharp close. A lag edge means their CLV stays clearly positive."""
    out = []
    for t in thresholds:
        for side in ("all", "over", "under"):
            x = p[p["ev_morning"] >= t] if side == "all" else p[(p["ev_morning"] >= t) & (p["side"] == side)]
            if x.empty:
                continue
            moved = x.dropna(subset=["fd_close"])
            out.append({"morning_ev_at_least": t, "side": side, "n": len(x), "games": x["event_id"].nunique(),
                        "ev_morning": round(x["ev_morning"].mean(), 4), "clv": round(x["clv"].mean(), 4),
                        "clv_se": round(_boot(x, "clv"), 4), "beat_close": round(float((x["clv"] > 0).mean()), 3),
                        "sharp_moved_to_fd": round(float((x["p_close"] - x["p_morning"]).mean()), 4),
                        "fd_moved_to_sharp": round(float((moved["fd_close"] - moved["fd_morning"]).mean()), 4)
                        if len(moved) else None})
    base = p.assign(ev_morning=0)
    out.append({"morning_ev_at_least": "every side", "side": "all", "n": len(p), "games": p["event_id"].nunique(),
                "ev_morning": round(p["ev_morning"].mean(), 4), "clv": round(p["clv"].mean(), 4),
                "clv_se": round(_boot(base, "clv"), 4), "beat_close": round(float((p["clv"] > 0).mean()), 3),
                "sharp_moved_to_fd": round(float((p["p_close"] - p["p_morning"]).mean()), 4), "fd_moved_to_sharp": None})
    return pd.DataFrame(out)
