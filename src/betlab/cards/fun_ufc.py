"""UFC in the fun bucket (Oct 23): one parlay ticket per card segment, from fighters' FanDuel moneylines.

Fights on a card don't affect each other, so a ticket is a plain cross-fight parlay: its fair chance is the product
of each fighter's sharp no-vig chance (cards/ufc._fair), with no simulation and no model. Each fight offers its
fighters whose chance is inside `leg_p`; the segment's ticket takes the best-value fighters from `min_games` to
`max_games` fights inside the payout band (sgp_plus.ticket). Segments are sgp_plus.SLICES["ufc"]: a card's early
prelims, prelims and main card each lock about 15 minutes before they start.

The Build tab gets each fight's two moneylines (a pack: draws where one fighter or the other wins). Total rounds
stay out of the packs: a fighter and the under move together (favorites finish fights), which plain draws can't say.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config, sgp, sgp_plus
from betlab import odds_math as om
from betlab.cards import ufc
from betlab.market import two_way
from betlab.sources import espn_ufc as src

DRAWS = 2000


def _legs(ev: pd.DataFrame, a: str, b: str, rng) -> tuple[list[sgp.Leg], np.ndarray] | None:
    """The fight's two FanDuel moneyline legs, at the sharp no-vig chance, with draws where each one wins."""
    tw = two_way(ev, "h2h", "fanduel", a, b)
    p_a, source = ufc._fair(ev, "h2h", a, b, "fanduel")
    if not tw or p_a is None:
        return None
    (_, pr_a), (_, pr_b) = tw
    w = np.full(DRAWS, 1 / DRAWS)
    a_wins = rng.random(DRAWS) < p_a
    legs = []
    for name, pr, hit, p in ((a, pr_a, a_wins, p_a), (b, pr_b, ~a_wins, 1 - p_a)):
        leg = sgp._line_leg(f"{name} ML", "side", name, "moneyline", "yes", 0.0, pr, hit, w, p, source)
        legs.append(leg)
    return legs, w


def _mini(leg: sgp.Leg, event_id: str) -> dict:
    import hashlib

    naive = om.american_to_decimal(leg.price)
    return {"sgp_id": hashlib.sha1(f"{event_id}|{leg.label}".encode()).hexdigest()[:12], "theme": "One leg",
            "legs": [sgp.leg_doc(leg)], "n_legs": 1, "p_fair": round(leg.p, 4), "fair_price": sgp._american(leg.p),
            "p_read": None, "naive_price": sgp._american(1 / naive),
            "leg_value": round(leg.p * naive, 3), "read_value": round(leg.p * naive, 3)}


def build(pick_snap: pd.DataFrame | None, asof: pd.Timestamp, cfg: dict, fights: pd.DataFrame | None = None) -> list[dict]:
    """The Fun tab's UFC slates: per card segment, a parlay ticket and the Build tab's packs."""
    if pick_snap is None or pick_snap.empty:
        return []
    fights = ufc.card_fights(asof) if fights is None else fights
    lo, hi = cfg["leg_p"]
    rng = np.random.default_rng(0)
    segs: dict[str, list[dict]] = {}
    packs: dict[str, list[dict]] = {}
    for event_id, ev in pick_snap.groupby("event_id", sort=False):
        x, y = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        f = src.find(fights, x, y)
        if f is None or pd.Timestamp(f["start"]) <= asof:
            continue
        a, b = (x, y) if src._last(f["a_name"]) == src._last(x) else (y, x)
        got = _legs(ev, a, b, rng)
        if got is None:
            continue
        legs, w = got
        start = pd.Timestamp(f["start"]).strftime("%Y-%m-%dT%H:%M:%SZ")
        ref = f"ufc:{f.get('espn_event')}:{f['fight_id']}"
        key = "|".join(sgp_plus.slice_of(start, "ufc"))
        game = {"event_id": str(event_id), "game_ref": ref, "matchup": f"{a} vs {b}", "commence_time": start}
        packs.setdefault(key, []).append(game | {"sport": "ufc", **sgp.leg_pack(legs, w)})
        pieces = sorted((_mini(l, str(event_id)) for l in legs if lo <= l.p <= hi), key=lambda m: -m["leg_value"])
        if pieces:
            segs.setdefault(key, []).append(game | {"minis": pieces[: int(cfg["minis_per_game"])]})
    out = []
    for k in sorted(set(segs) | set(packs)):
        day, name = k.split("|")
        games = packs.get(k) or segs[k]
        names = sgp_plus.slice_names("ufc", day, name, len(games))
        playable = sorted(segs.get(k, []), key=lambda g: g["commence_time"])
        ticket = sgp_plus.ticket(playable, names["slate"], names["label"], cfg) if len(playable) >= int(cfg["min_games"]) else None
        if ticket:
            p = ticket["p_fair"]
            ticket |= {"sport": "ufc", "matchup": ticket["matchup"].replace("SGP+ ", "Parlay ", 1),
                       "why": f"{ticket['n_games']} fights, one fighter each, priced at the sharp no-vig moneyline. "
                              f"Fights don't affect each other, so the ticket's chance is the product: {p:.1%}, "
                              f"fair {sgp._american(p):+d}. A plain parlay: FanDuel pays the legs' prices multiplied, "
                              f"{ticket['naive_price']:+d}."}
        out.append({**names, "sport": "ufc", "lines_only": True, "kickoff": min(g["commence_time"] for g in games),
                    "n_games": len(games), "plus": ticket, "overs": [], "packs": packs.get(k, []),
                    "sgps": sgp_plus.pack_own_slips(packs.get(k, []), "ufc")})      # shown for watched fights (Nov 7)
    return out
