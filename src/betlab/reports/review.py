"""Performance summary: record, units, ROI and CLV, overall and per market.

The standard error of ROI over n even-money bets is about 1/sqrt(n): over 100
bets that's +/-10%, so small samples say little. CLV settles much faster,
which is why the go-live checklist leans on it.
"""

from __future__ import annotations

import json
import math

import pandas as pd

from betlab import config, ledger


def summarize(df: pd.DataFrame) -> dict:
    """Record, units, ROI (with its noise) and CLV stats for a set of ledger rows."""
    settled = df[df["status"].isin(["won", "lost", "push"])]
    n = len(settled)
    wins, losses = (settled["status"] == "won").sum(), (settled["status"] == "lost").sum()
    staked = settled["units_flat"].astype(float).sum()
    units = settled["profit_flat"].astype(float).sum()
    from betlab.golive import checked_clv

    clv = checked_clv(settled).dropna().astype(float)   # raw CLV for props, as the go-live checklist judges
    return {
        "bets": int(n), "record": f"{wins}-{losses}-{n - wins - losses}", "open": int((df["status"] == "open").sum()),
        "units": round(units, 2), "roi": round(units / staked, 4) if staked else None,
        "roi_noise": round(1 / math.sqrt(n), 3) if n else None,
        "clv_bets": int(len(clv)), "avg_clv": round(clv.mean(), 4) if len(clv) else None,
        "beat_close_pct": round((clv > 0).mean(), 3) if len(clv) else None,
    }


def build() -> dict:
    """Overall, per-market and taken-only summaries of the ledger, current rules only
    (Mike, 2026-09-30: picks from the retired over-lean props rule stay in the CSV but
    leave the record; golive.current_rule)."""
    from betlab.golive import current_rule, real_closes

    picks = real_closes(current_rule(ledger.load()))[0]     # CLV only from real closes (golive module note)
    if picks.empty:
        return {"overall": summarize(picks), "by_market": {}}
    from betlab.golive import market_key

    picks["market_key"] = market_key(picks)     # "NFL props", "NCAAF spreads": the checklist's markets
    return {
        "overall": summarize(picks),
        "by_market": {k: summarize(g) for k, g in picks.groupby("market_key")},
        "taken": summarize(picks[picks["taken"].fillna(False).astype(bool)]),
    }


def write(results: dict) -> None:
    """Write exports/results.json."""
    config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.EXPORTS_DIR / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
