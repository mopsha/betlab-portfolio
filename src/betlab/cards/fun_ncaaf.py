"""College football in the fun bucket: one lines-only SGP+ ticket per kickoff slice (Mike, 2026-09-26;
slices of the day since Oct 10: noon, afternoon, night, each locked 15 minutes before it starts, sgp_plus.keep_tickets).

New York bans college player props, so the legs are each game's FanDuel moneyline, spread
and total, never a game involving a New York school or played in New York (a game whose
venue we can't confirm is skipped too).

- **How lines move together:** in college the favorite covering and the game going over
  are nearly independent for small spreads but move together for big ones (FBS games
  2014-25: both hit 1.11-1.21x as often as independent legs for 15+ point favorites, in
  both halves of the history; about 1.0 below 14.5). So each game is drawn from real past
  games with a similar spread (`draws`): the favorite's margin and the total relative to
  the market, the total's spread rescaled to this game's total (14.6 points of SD at a
  45 total, 18.7 at 65+). Legs are priced at the sharp no-vig price at FanDuel's number
  (sgp.game_line_legs); the draws only say how they move together.
- **The ticket:** each game offers a "mini": one leg, or a side and the total that move
  together (a big favorite covering with the over, or the underdog with the under). The
  slice's ticket takes the best-value minis from 3-6 games inside the payout band
  (sgp_plus.ticket); fair chance is the product across games.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from betlab import config, ny_rules, sgp, sgp_plus
from betlab import odds_math as om
from betlab.sources import cfbd

ET = "America/New_York"
NEIGHBOURS = 4.0          # past games within this many points of spread
SD_TOTAL = (6.6, 0.175)   # SD of the total around the line: 6.6 + 0.175 x total (45 -> 14.5, 65 -> 18)


def residuals(games: pd.DataFrame, before_season: int) -> pd.DataFrame:
    """Past FBS-vs-FBS games with lines: |spread|, total line, favorite's margin minus the
    spread (m_res) and total minus the line (t_res)."""
    g = games[(games["season"] < before_season) & (games["home_div"] == "fbs") & (games["away_div"] == "fbs")]
    g = g.dropna(subset=["spread_line", "total_line", "home_pts", "away_pts"])
    fav_margin = np.where(g["spread_line"] >= 0, g["margin"], -g["margin"])
    return pd.DataFrame({"abs_sp": g["spread_line"].abs().to_numpy(), "total_line": g["total_line"].to_numpy(),
                         "m_res": fav_margin - g["spread_line"].abs().to_numpy(),
                         "t_res": (g["total"] - g["total_line"]).to_numpy()})


def draws(res: pd.DataFrame, spread_home: float, total: float, n: int = 4000, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """(home points, away points) for n versions of a game with the market's home margin
    spread_home and total, from past games with a similar spread."""
    s = abs(spread_home)
    near = res[(res["abs_sp"] - s).abs() <= NEIGHBOURS]
    if len(near) < 200:
        near = res.iloc[(res["abs_sp"] - s).abs().argsort()[:400]]
    rng = np.random.default_rng(seed)
    pick = near.iloc[rng.integers(0, len(near), n)]
    sd = lambda t: SD_TOTAL[0] + SD_TOTAL[1] * t
    fav_margin = s + pick["m_res"].to_numpy()
    tot = total + pick["t_res"].to_numpy() * sd(total) / sd(pick["total_line"].to_numpy())
    home_margin = fav_margin if spread_home >= 0 else -fav_margin
    return (tot + home_margin) / 2, (tot - home_margin) / 2


def _center(ev: pd.DataFrame, home_name: str) -> tuple[float, float] | None:
    """The market's home margin and total: median across books."""
    sp = ev[(ev["market"] == "spreads") & (ev["outcome"] == home_name)]["point"]
    tot = ev[(ev["market"] == "totals") & (ev["outcome"] == "Over")]["point"]
    if sp.empty or tot.empty:
        return None
    return -float(sp.median()), float(tot.median())


def _mini_doc(legs: list, p: float, event_id: str) -> dict:
    naive = float(np.prod([om.american_to_decimal(l.price) for l in legs]))
    key = event_id + "|" + "|".join(sorted(l.label for l in legs))
    return {"sgp_id": hashlib.sha1(key.encode()).hexdigest()[:12], "theme": "Blowout script" if len(legs) > 1 else "One leg",
            "legs": [sgp.leg_doc(l) for l in legs], "n_legs": len(legs), "p_fair": round(p, 4),
            "fair_price": sgp._american(p), "p_read": None, "naive_price": sgp._american(1 / naive),
            "leg_value": round(p * naive, 3), "read_value": round(p * naive, 3)}


def minis(legs: list, w: np.ndarray, cfg: dict, event_id: str) -> list[dict]:
    """A game's pieces for the day's ticket: single legs, and a side with the total when
    they move together (lift at least cfg["pair_lift"]); best leg value first."""
    lo, hi = cfg["leg_p"]
    ok = [l for l in legs if lo <= l.p <= hi and sgp.plausible(l) and (cfg.get("allow_unders") or l.side != "under")]
    out = [(_mini_doc([l], l.p, event_id), l.p * om.american_to_decimal(l.price)) for l in ok]
    sides = [l for l in ok if l.stat in ("moneyline", "spread")]
    totals = [l for l in ok if l.stat == "total"]
    for a in sides:
        for b in totals:
            joint = float((w * a.hit * b.hit).sum()) * (a.p / a.p_model) * (b.p / b.p_model)
            if joint / (a.p * b.p) >= cfg["pair_lift"]:
                out.append((_mini_doc([a, b], joint, event_id),
                            joint * om.american_to_decimal(a.price) * om.american_to_decimal(b.price)))
    out.sort(key=lambda x: -x[1])
    return [d for d, _ in out[: int(cfg["minis_per_game"])]]


def build(pick_snap: pd.DataFrame | None, asof: pd.Timestamp, cfg: dict) -> list[dict]:
    """The Fun tab's college slates: one lines-only SGP+ ticket per kickoff slice (sgp_plus.SLICES)."""
    if pick_snap is None or pick_snap.empty:
        return []
    snap = pick_snap[pd.to_datetime(pick_snap["commence_time"], utc=True, format="ISO8601") > asof]
    if snap.empty:
        return []
    sharp = config.settings()["odds_api"]["sharp_books"]
    games = cfbd.games()
    names = cfbd.team_names()
    season = int(pd.Timestamp(asof).tz_convert(ET).year)
    res = residuals(games, season)
    days: dict[str, list[dict]] = {}
    packs: dict[str, list[dict]] = {}                   # every game's builder pack, ticket or not
    for i, (event_id, ev) in enumerate(snap.groupby("event_id", sort=False)):
        first = ev.iloc[0]
        home_name, away_name = first["home_team"], first["away_team"]
        home, away = names.get(home_name), names.get(away_name)
        when = pd.Timestamp(first["commence_time"])
        day = when.tz_convert(ET).tz_localize(None).normalize()
        near = games[((games["date"] - day).abs() <= pd.Timedelta(days=1))]
        row = near[(near["home_team"] == home) & (near["away_team"] == away)]
        if row.empty:
            row = near[(near["home_team"] == away) & (near["away_team"] == home) & near["neutral"].fillna(False).astype(bool)]
        state = row["venue_state"].iloc[0] if len(row) and "venue_state" in row else None
        if home is None or away is None or row.empty or not isinstance(state, str) or not state:
            continue                                   # can't confirm who or where: never priced
        if not ny_rules.allowed("ncaaf", home, away, venue_state=state)[0]:
            continue
        center = _center(ev, home_name)
        if center is None:
            continue
        hp, ap = draws(res, center[0], center[1], seed=i)
        from types import SimpleNamespace
        sim = SimpleNamespace(points={home: hp, away: ap})
        w = np.full(len(hp), 1 / len(hp))
        legs = sgp.game_line_legs(ev, sim, w, home_name, away_name, home, away, sharp)
        key = "|".join(sgp_plus.slice_of(when, "ncaaf"))
        packs.setdefault(key, []).append({
            "event_id": str(event_id), "matchup": f"{away_name} @ {home_name}", "commence_time": str(first["commence_time"]),
            "game_ref": str(row["game_id"].iloc[0]), "sport": "ncaaf", **sgp.leg_pack(legs, w, seed=i)})
        pieces = minis(legs, w, cfg, str(event_id))
        if pieces:
            days.setdefault(key, []).append({
                "event_id": str(event_id), "game_ref": str(row["game_id"].iloc[0]),
                "matchup": f"{away_name} @ {home_name}", "commence_time": str(first["commence_time"]),
                "minis": pieces})
    out = []
    for d in sorted(set(days) | set(packs)):
        names = sgp_plus.slice_names("ncaaf", *d.split("|"), len(packs.get(d) or days[d]))
        sid, label = names["slate"], names["label"]
        if d not in days:                               # no ticket, but the builder still gets the slice's games
            out.append({**names, "sport": "ncaaf",
                        "lines_only": True, "kickoff": min(g["commence_time"] for g in packs[d]), "n_games": len(packs[d]),
                        "plus": None, "overs": [], "packs": packs[d], "sgps": sgp_plus.pack_own_slips(packs[d], "ncaaf")})
            continue
        games_d = sorted(days[d], key=lambda g: -max(m["leg_value"] for m in g["minis"]))[: int(cfg["pool_games"])]
        games_d.sort(key=lambda g: g["commence_time"])
        ticket = sgp_plus.ticket(games_d, sid, label, cfg)
        if ticket:
            ticket |= {"sport": "ncaaf", "why": ticket["why"].replace("priced from our simulation of that game (legs anchored to the market)",
                                                                   "priced at the sharp market, moving together as similar past college games did")}
        out.append({**names, "sport": "ncaaf", "lines_only": True,
                    "kickoff": min(g["commence_time"] for g in days[d]), "n_games": len(days[d]),
                    "plus": ticket, "overs": [], "packs": packs.get(d, []),
                    "sgps": sgp_plus.pack_own_slips(packs.get(d, []), "ncaaf")})      # shown for watched games (Nov 7)
    return out
