"""From priced offers to picks, leans and check-news flags, with stakes and why-notes."""

from __future__ import annotations

import pandas as pd

from betlab import config
from betlab import odds_math as om
from betlab.staking import kelly_units, tier_units

CORRELATED = {"spreads": "side", "h2h": "side", "totals": "total"}  # one pick per group per game


def classify(offers: pd.DataFrame, asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Label each offer: pick, lean, check_news, or '' (nothing). With `asof`, games more
    than picks.horizon_hours away can be leans but never picks."""
    s = config.settings()["picks"]
    out = offers.copy()
    min_ev = out["kind"].map(s["min_ev"])
    # Prop unders need a bigger edge (Mike, 2026-09-26: an all-unders card is no fun to watch, so
    # only the really good ones): below it they stay leans. Stricter only, never looser.
    if "prop_under" in s["min_ev"] and "side" in out:
        under = (out["kind"] == "prop") & (out["side"] == "Under")
        min_ev = min_ev.where(~under, max(s["min_ev"]["prop_under"], s["min_ev"]["prop"]))
    gap = (out["p_model"] - out["p_market"]).abs()
    long_ml = (out["market"] == "h2h") & ((out["price"] > 250) | (out["price"] < -250))
    out["gap"] = gap
    out["group"] = out["event_id"] + ":" + out["market"].map(CORRELATED).fillna(out["market"]) \
        + ":" + out["player"].fillna("")
    # Props group per player: one player's receptions and receiving yards move together.
    is_prop = out.get("kind", pd.Series("", index=out.index)) == "prop"
    if is_prop.any():
        out.loc[is_prop, "group"] = (out.loc[is_prop, "event_id"].astype(str) + ":prop:"
                                     + out.loc[is_prop, "player"].fillna("").astype(str))
    out["tier"] = ""
    too_far = gap > s["max_model_market_gap"]
    # No lean on a long dog either (2026-11-03: above +250 they lost to the close, -3.67% on 58, 38% beat).
    # Big favorites stay: they beat it (+0.15% on 61, +1.23% on 16).
    long_dog = long_ml & (out["price"] > 250)
    out.loc[(out["ev"] >= s["lean_ev"]) & ~too_far & ~long_dog, "tier"] = "lean"
    out.loc[(out["ev"] >= min_ev) & ~too_far & ~long_ml, "tier"] = "pick"
    # An offer priced off a different sharp number (cards/nba.py) is a lean until its CLV says otherwise.
    if "lean_only" in out:
        out.loc[out["lean_only"].eq(True) & (out["tier"] == "pick"), "tier"] = "lean"
    if asof is not None and "commence_time" in out and s.get("horizon_hours"):
        starts = pd.to_datetime(out["commence_time"], utc=True, errors="coerce", format="ISO8601")
        early = starts > pd.Timestamp(asof) + pd.Timedelta(hours=s["horizon_hours"])
        out.loc[early & (out["tier"] == "pick"), "tier"] = "lean"
    # A big disagreement is a question, not a bet: flag the side our model likes, once per group.
    # Only where backtests gave the model real weight (10%+), and only from check_news_min_gap:
    # smaller gaps carried no information in the backtest, so flagging them was noise.
    trusted = out.get("w_model", pd.Series(1.0, index=out.index)).fillna(1.0) >= 0.10
    flag_gap = gap >= s.get("check_news_min_gap", s["max_model_market_gap"])
    flagged = out[too_far & flag_gap & trusted & (out["p_model"] > out["p_market"])]
    keep = flagged.sort_values("gap", ascending=False).drop_duplicates("group").index
    out.loc[keep, "tier"] = "check_news"

    # one pick per correlated group per game: keep the best EV, demote the rest to leans
    picks = out[out["tier"] == "pick"]
    keep = picks.sort_values("ev", ascending=False).drop_duplicates("group").index
    out.loc[picks.index.difference(keep), "tier"] = "lean"
    return out


def stake(picks: pd.DataFrame) -> pd.DataFrame:
    """Add units_flat (always 1), units_tier (by EV) and units_kelly (quarter-Kelly, capped)."""
    b, st = config.settings()["bankroll"], config.settings()["staking"]
    out = picks.copy()
    out["units_flat"] = 1.0
    out["units_tier"] = [tier_units(ev, st["tiers"]) for ev in out["ev"]]
    out["units_kelly"] = [
        kelly_units(pf * (1 - pp), price, pp, b["unit_pct"], st["kelly_fraction"], st["kelly_cap_units"])
        for pf, pp, price in zip(out["p_final"], out["p_push"], out["price"])
    ]
    return out


def why_note(r) -> str:
    """The plain-English explanation shown with each pick, lean or flag."""
    implied = om.implied_prob(r["price"])
    w = r.get("w_model", 0.0)
    from betlab.books import name as book_name

    parts = [
        f"{r['label']} at {r['price']:+.0f} on {book_name(r.get('book'))} needs {implied:.1%} to break even.",
        f"The sharp market ({r['market_source']}) makes it {r['p_market']:.1%} once the vig is removed;"
        f" our model says {r['p_model']:.1%} ({r['model_number']}).",
        f"Blended ({w:.0%} model, {1 - w:.0%} market): {r['p_final']:.1%}, "
        f"so EV is {r['ev']:+.1%} per unit.",
    ]
    if r.get("p_push", 0) > 0.01:
        parts.append(f"Push chance {r['p_push']:.1%} (you get your stake back).")
    if r["tier"] == "pick":
        parts.append(f"Stake: {r['units_flat']:g}u flat (tiers would say {r['units_tier']:g}u, "
                     f"quarter-Kelly {r['units_kelly']:g}u).")
    elif r["tier"] == "check_news":
        gap = config.settings()["picks"].get("check_news_min_gap", config.settings()["picks"]["max_model_market_gap"])
        parts.append(f"Our model and the market disagree by {gap:.0%} or more: the market probably knows "
                     "something (injury, weather, lineup). Check the news before trusting this. In the college "
                     "backtest, when our ratings disagreed this much, the side they liked won a few points more "
                     "often than the market said, but far less often than the ratings said.")
    other = r.get("other_book")
    if isinstance(other, str) and other and pd.notna(r.get("other_price")):
        at = "" if pd.isna(r.get("other_point")) or r.get("other_point") == r.get("point") else f" at {float(r['other_point']):+g}" if r.get("market") == "spreads" else f" at {float(r['other_point']):g}"
        parts.append(f"{book_name(other)} has it{at} at {float(r['other_price']):+.0f} (EV {float(r['other_ev']):+.1%}).")
    return " ".join(parts)
