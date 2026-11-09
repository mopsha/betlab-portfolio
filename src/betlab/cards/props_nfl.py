"""NFL player props on the card (paper): FanDuel's and DraftKings' main over/unders against the market.

For each book's two-way main line (FanDuel and DraftKings, books.targets(); Oct 12) (receptions, receiving, rushing and passing yards)
in a fresh props snapshot:
- p_market: the market's no-vig chance at that book's own line (Pinnacle, else a consensus),
  corrected for the props market's lean toward overs (props_market.fair_main).
- p_model: props model v0.2's own chance from the joint game simulation, before any
  market anchoring. Its weight is 0: against real 2025 lines it didn't beat the
  over-corrected market (docs/MODELS.md), so picks come from FanDuel's price vs. the
  market only, and they stay paper until live closing-line value shows an edge.
Rows follow the card's offer columns (cards/README.md) with kind "prop" and the book; books.select keeps the
better book per bet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import books as B
from betlab import config
from betlab import explain
from betlab import odds_math as om
from betlab import props_market as PM
from betlab.cards import fun_nfl

W_MODEL = 0.0          # no weight until it beats the market (rule 3)
MAX_AGE_HOURS = 3      # never price props from a stale snapshot
LABEL = PM.STAT_LABEL
MOVED = ", moved to the book's number: a lean at most until that's tested"   # rule 1 (Oct 12)


def SHIFT() -> bool:
    """Whether picks use the over-lean shift (settings props.shift_in_picks; off since Sep 28)."""
    return bool((config.settings().get("props") or {}).get("shift_in_picks", True))


def evaluate(snap: pd.DataFrame, asof: pd.Timestamp, books: list[str] | None = None) -> pd.DataFrame:
    """Offer rows for every main-line prop at each of Mike's books in games that haven't started. The game is
    simulated once; each book is priced at its own numbers (docs/DRAFTKINGS_PLAN.md rule 1)."""
    if snap is None or snap.empty:
        return pd.DataFrame()
    age = asof - pd.to_datetime(snap["snapshot_ts"], utc=True).max()
    if age > pd.Timedelta(hours=MAX_AGE_HOURS):
        return pd.DataFrame()
    snap = snap[pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof]
    if snap.empty:
        return pd.DataFrame()
    ctx = fun_nfl.load_context(int(pd.Timestamp(snap["commence_time"].min()).year))
    sharp = config.settings()["odds_api"]["sharp_books"]
    teams = sorted(set(ctx["abbr"].values()))
    defenses = {}
    rows = []
    for _, ev in snap.groupby("event_id", sort=False):
        prep = fun_nfl.prepare_game(ev, ctx, sims=10000)
        if not prep["ok"]:
            continue
        raw = prep["simulate"]({})
        if prep["kickoff"] not in defenses:
            defenses[prep["kickoff"]] = explain.defense_table(ctx["hist"], prep["kickoff"], teams)
        for book in books or B.targets("props"):
            rows += _book_rows(ev, prep, raw, ctx, defenses[prep["kickoff"]], sharp, book)
    return pd.DataFrame(rows)


def _book_rows(ev, prep, raw, ctx, defense, sharp, book: str) -> list[dict]:
    """One book's offer rows for one game, each line priced at that book's number."""
    rows = []
    fair = PM.fair_main(raw, ev, prep["ids"], sharp, shift=SHIFT(), target=book)
    for r in PM.book_main(ev, book).itertuples():
        q = fair[(fair["player"] == r.player) & (fair["stat"] == r.stat)]
        pid = prep["ids"].get(r.player)
        d = raw.get(pid, r.stat) if pid else None
        if q.empty or d is None:
            continue
        facts = explain.prop_facts(prep, ctx["hist"], pid, r.stat, d, defense, ctx["abbr"])
        p_over_market = float(q["p_over"].iloc[0])
        moved = bool(q["moved"].iloc[0])
        p_over_model = float(np.mean(d > r.point))
        median = float(np.median(d))
        market = next(k for k, v in PM.MAIN.items() if v == r.stat)
        for side, price, pm, pmod in (("Over", r.over, p_over_market, p_over_model),
                                      ("Under", r.under, 1 - p_over_market, 1 - p_over_model)):
            p_final = pm if W_MODEL == 0 else float(
                1 / (1 + np.exp(-(W_MODEL * np.log(pmod / (1 - pmod)) + (1 - W_MODEL) * np.log(pm / (1 - pm))))))
            rows.append({
                "league": "nfl", "event_id": prep["event_id"], "game_ref": prep["game_ref"],
                "commence_time": prep["commence_time"], "matchup": prep["matchup"], "market": market,
                "side": side, "player": r.player, "player_key": pid,
                "label": f"{r.player} {side.lower()} {r.point:g} {LABEL[r.stat]}", "point": float(r.point),
                "price": float(price), "book": book, "kind": "prop",
                "model_number": f"model median {median:.1f} {LABEL[r.stat]}",
                "p_model": round(pmod, 4), "p_market": round(pm, 4), "p_final": round(p_final, 4),
                "p_push": 0.0, "ev": round(om.expected_value(p_final, float(price)), 4),
                "market_source": (f"{q['source'].iloc[0]}, corrected for the over lean"
                if SHIFT() and r.stat in (config.settings().get("props") or {}).get("market_shift", {})
                else q["source"].iloc[0]) + (MOVED if moved else ""),
                "w_model": W_MODEL, "lean_only": moved,
                "context": explain.prop_story(facts, side, r.point, W_MODEL, shifted=SHIFT()) if facts else "",
            })
    return rows
