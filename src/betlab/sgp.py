"""Fun same-game parlays: correlated FanDuel legs, priced from the anchored game simulation.

For one game we have n simulated versions of it (models/game_sim_nfl), reweighted
so every player's main line matches the market's no-vig price (props_market). Any
combination of legs is priced by counting the weighted draws where all of them hit.

Which parlays we suggest:
- Legs are FanDuel's own: main over/unders, alt ladders ("60+ yards") and anytime TD,
  only for players and stats the market anchored, minus legs where we beat
  FanDuel's price by more than 8 points, or 4 for rungs only our model prices
  (plausible()).
- Chances come from the weighted draws, which match the market on every main line
  and Pinnacle TD price. Where other books quote the same alt rung, their no-vig
  chance is a ceiling: the leg (and every parlay with it) is scaled down to it,
  never up, so a parlay can only look worse than the draws say, not better.
- Unders only as near-locks (75-92%), at most one per slip (fun.under_min_p,
  max_unders): a slip of unders is no fun, Mike's rule.
- One leg per player (fun.one_leg_per_player): books cut same-player stacks hard.
- 4-5 legs, each 55-80% likely on its own (settings: fun.min_leg_p/max_leg_p), at most
  one per player and stat, at least one pair that tends to hit together, and fair
  odds inside the payout band (settings: fun.band, +150 to +1,000). Mike asked for
  likely legs after the first slips each leaned on a +400 to +640 rung.
- Ranked by the product of each leg's value (our fair chance x FanDuel's payout).
  FanDuel prices the correlation between legs itself, so correlation alone isn't
  an edge: if its correlation estimate matches ours, a parlay of well-priced legs is
  the best we can do. The real test is FanDuel's quoted SGP price, which Mike types
  into the page: the bet is worth it only above our fair odds.

Parlays are for the fun bucket only ($10 a month), never the main record.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from betlab import odds_math as om
from betlab import props_market as PM


@dataclass
class Leg:
    key: tuple            # (player, stat): at most one leg per key in a parlay
    label: str            # "Drake London 80+ receiving yds"
    player: str
    team: str
    stat: str
    side: str             # over / under / yes
    point: float
    price: int            # FanDuel's American price for the leg alone
    hit: np.ndarray       # bool per draw
    p: float = 0.0        # fair chance: p_model, capped by other books' same rung
    p_model: float = 0.0  # chance in the anchored simulation
    source: str = ""      # what anchors it: a book, "consensus of N books", or "model shape"
    p_raw: float | None = None   # our model's own chance, before market anchoring (for display)
    note: str = ""               # football context for the leg (explain.leg_note)
    injury: str | None = None    # set when the player is Questionable
    p_read: float | None = None  # chance with our game read (the Games tab's script lean); None = no read
    read: str = ""               # the read's one-line story, when it favors this leg

    @property
    def value(self) -> float:
        """Fair chance x FanDuel's decimal payout: above 1 means the leg is priced generously."""
        return self.p * om.american_to_decimal(self.price)

    @property
    def read_value(self) -> float:
        """value, with our game read's chance where there is one (used to rank slips)."""
        return (self.p if self.p_read is None else self.p_read) * om.american_to_decimal(self.price)


def _label(player: str, stat: str, side: str, point: float, alt: bool) -> str:
    name = PM.STAT_LABEL[stat]
    if stat == "tds":
        return f"{player} anytime TD"
    if alt:
        return f"{player} {int(point + 0.5)}+ {name}"
    return f"{player} {'over' if side == 'over' else 'under'} {point:g} {name}"


def build_legs(snap: pd.DataFrame, sim, ids: dict[str, str], w: np.ndarray, fair: pd.DataFrame,
               target: str = "fanduel") -> list[Leg]:
    """Every FanDuel leg we can price: only players and stats the market anchored (fair)."""
    team_of = dict(zip(sim.players["player_id"], sim.players["team"]))
    main = fair[fair["kind"] == "main"]
    anchored = set(zip(main["player"], main["stat"]))
    source = {(r.player, r.stat, r.point): r.source for r in main.itertuples()}
    rung = {(r.player, r.stat, r.point): r for r in fair[fair["kind"] == "rung"].itertuples()}
    fd = snap[(snap["bookmaker"] == target) & snap["market"].isin(list(PM.STAT_OF))]
    legs = []
    for r in fd.itertuples():
        stat = PM.STAT_OF[r.market]
        pid = ids.get(r.player)
        d = sim.get(pid, stat) if pid else None
        if d is None or (r.player, stat) not in anchored:
            continue
        alt = r.market in PM.ALT
        if stat == "tds":
            if r.outcome != "Yes":
                continue
            side, point, hit = "yes", 0.5, d > 0.5
        elif r.outcome == "Over":
            side, point, hit = "over", float(r.point), d > r.point
        elif r.outcome == "Under":
            side, point, hit = "under", float(r.point), d < r.point
        else:
            continue
        leg = Leg(key=(r.player, stat), label=_label(r.player, stat, side, point, alt), player=r.player,
                  team=team_of.get(pid, ""), stat=stat, side=side, point=point, price=int(r.price), hit=hit,
                  source=source.get((r.player, stat, point), "model shape"))
        leg.p = leg.p_model = float(w[hit].sum())
        other = rung.get((r.player, stat, point)) if alt else None
        if other is not None:  # other books' same rung is a ceiling: never look better than them
            leg.p, leg.source = min(leg.p_model, other.p_over), other.source
        legs.append(leg)
    # A rung no other book quotes gets the tightest cap of the player's quoted rungs,
    # so 30+ can't stay at the model's chance when the books cut 25+ down.
    caps: dict[tuple, float] = {}
    for leg in legs:
        # (a rung the simulation never reaches has no ratio: it crashed a whole game's build on Sep 26)
        if leg.source not in ("", "model shape") and leg.side == "over" and leg.stat != "tds" and leg.p_model > 0:
            caps[leg.key] = min(caps.get(leg.key, 1.0), leg.p / leg.p_model)
    for leg in legs:
        if leg.source == "model shape" and leg.key in caps:
            leg.p = leg.p_model * caps[leg.key]
    return legs


GAME_STATS = {"moneyline": "moneyline", "spread": "spread", "total": "total points"}
NBA_STATS = {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes": "threes",
             "pra": "pts + reb + ast", "pr": "pts + reb", "pa": "pts + ast", "ra": "reb + ast"}
STAT_NAME = {**PM.STAT_LABEL, **GAME_STATS, **NBA_STATS}


def _line_leg(label: str, key: str, team: str, stat: str, side: str, point: float, price, hit: np.ndarray,
              w: np.ndarray, p_market: float | None, source: str) -> Leg:
    """A game-line leg: the simulation gives how it moves with the players' legs; the sharp
    no-vig price at FanDuel's number gives its chance (the search scales the joint by the
    ratio), else the simulation, which is centred on the market's spread and total."""
    leg = Leg(key=("game", key), label=label, player=f"game {key}", team=team, stat=stat, side=side,
              point=float(point), price=int(price), hit=hit, source=source if p_market is not None else "simulation")
    leg.p_model = float(w[hit].sum())
    leg.p = float(p_market) if p_market is not None else leg.p_model
    return leg


def game_line_legs(pick_ev: pd.DataFrame, sim, w: np.ndarray, home_name: str, away_name: str, home: str,
                   away: str, sharp_books, target: str = "fanduel") -> list[Leg]:
    """FanDuel's moneyline, spread and total for the game as parlay legs (Mike, 2026-09-26),
    joint with the player legs through the simulated points. Labels grade in fun_ledger:
    "Buffalo Bills ML", "Buffalo Bills -3.5", "Over 47.5 total points"."""
    from betlab.market import reference_books, two_way

    if pick_ev is None or pick_ev.empty or home not in sim.points or away not in sim.points:
        return []
    margin = sim.points[home] - sim.points[away]
    total = sim.points[home] + sim.points[away]
    legs = []

    def fair_two_way(market, a, b, point_a=None):
        books, source = reference_books(pick_ev, market, list(sharp_books), target)
        ps = []
        for bk in books:
            tw = two_way(pick_ev, market, bk, a, b)
            if tw and (point_a is None or float(tw[0][0]) == float(point_a)):
                ps.append(om.devig([tw[0][1], tw[1][1]])[0])
        return (float(np.median(ps)), source) if ps else (None, source)

    fd = two_way(pick_ev, "h2h", target, home_name, away_name)
    if fd:
        p_home, source = fair_two_way("h2h", home_name, away_name)
        for name, abbr, price, hit, pk in ((home_name, home, fd[0][1], margin > 0, p_home),
                                           (away_name, away, fd[1][1], margin < 0, None if p_home is None else 1 - p_home)):
            legs.append(_line_leg(f"{name} ML", "side", abbr, "moneyline", "yes", 0.0, price, hit, w, pk, source))
    fd = two_way(pick_ev, "spreads", target, home_name, away_name)
    if fd:
        (pt_h, pr_h), (pt_a, pr_a) = fd
        p_home, source = fair_two_way("spreads", home_name, away_name, pt_h)
        for name, abbr, pt, price, hit, pk in ((home_name, home, pt_h, pr_h, margin + pt_h > 0, p_home),
                                               (away_name, away, pt_a, pr_a, -margin + pt_a > 0,
                                                None if p_home is None else 1 - p_home)):
            legs.append(_line_leg(f"{name} {float(pt):+g}", "side", abbr, "spread", "yes", pt, price, hit, w, pk, source))
    fd = two_way(pick_ev, "totals", target, "Over", "Under")
    if fd:
        (pt, pr_o), (_, pr_u) = fd
        p_over, source = fair_two_way("totals", "Over", "Under", pt)
        legs.append(_line_leg(f"Over {float(pt):g} total points", "total", "", "total", "over", pt, pr_o,
                              total > pt, w, p_over, source))
        legs.append(_line_leg(f"Under {float(pt):g} total points", "total", "", "total", "under", pt, pr_u,
                              total < pt, w, None if p_over is None else 1 - p_over, source))
    return legs


def _american(p: float) -> int:
    return int(round(om.prob_to_american(p)))


def theme(legs: list[Leg], qb_teams: dict[str, str]) -> str:
    """A short name for the story the legs tell."""
    stats = {(l.stat, l.side, l.team) for l in legs}
    qbs_over = [l for l in legs if l.stat == "passing_yards" and l.side == "over"]
    side = next((l for l in legs if l.stat in ("moneyline", "spread")), None)
    if side and any(l.team == side.team and l.stat in PM.STAT_LABEL and l.side in ("over", "yes") for l in legs):
        return "Win it with them"
    if any(l.stat == "total" and l.side == "over" for l in legs) and len({l.team for l in legs if l.team}) >= 2:
        return "Shootout"
    if len({l.team for l in qbs_over}) == 2:
        return "Shootout"
    for q in qbs_over:
        if any(l.team == q.team and l.stat in ("receiving_yards", "receptions") and l.side == "over" for l in legs):
            return "QB + receiver stack"
    by_player = {}
    for l in legs:
        by_player.setdefault(l.player, set()).add(l.stat)
    if any("tds" in s and len(s) > 1 for s in by_player.values()):
        return "Scorer + yards"
    if any(s[0] == "rushing_yards" and s[1] == "over" for s in stats):
        return "Ground game"
    if all(l.side == "under" for l in legs):
        return "Low-scoring grind"
    if any(l.side == "under" for l in legs):
        return "Role shift"
    return "Correlated overs"


def why(legs: list[Leg], p_joint: float, pair: tuple[Leg, Leg, float], p_read: float | None = None) -> str:
    a, b, lift = pair
    fair = _american(p_joint)
    naive = _american(1 / np.prod([om.american_to_decimal(l.price) for l in legs]))
    name = lambda l: l.label if l.stat in GAME_STATS else f"{l.player} ({STAT_NAME[l.stat]})"
    who = (f"{a.player}'s {STAT_NAME[a.stat]} and {STAT_NAME[b.stat]}" if a.player == b.player
           else f"{name(a)} and {name(b)}")
    text = (f"{who} tend to hit together: in our simulations both land "
            f"{lift:.1f}x as often as if they were unrelated. Fair odds {fair:+d}; FanDuel's legs "
            f"multiply to {naive:+d}, but FanDuel prices the correlation too, so expect its SGP "
            f"price to be lower. Worth it only if FanDuel pays more than {fair:+d}.")
    fits = [l for l in legs if l.read]
    if p_read is not None and fits:
        text += (f" {len(fits)} of the legs fit how we read the game ({fits[0].read.rstrip('.')}); "
                 f"with that read the slip is {_american(p_read):+d}. The read held on 2025 prop lines but "
                 f"isn't confirmed on a second season, so the verdict uses the fair odds.")
    return text


MAX_GAP = 0.08        # fair chance minus FanDuel's implied chance, for market-anchored legs
MAX_GAP_MODEL = 0.04  # for alt rungs only our simulation's shape prices


def plausible(leg: Leg) -> bool:
    """Drop legs where we beat FanDuel's own price by more than 8 points of probability
    (4 when no other book quotes the rung).

    Big disagreements on props are far more often our mistake (a thin roster read, a
    tail we got wrong) than FanDuel's, the same lesson as long moneylines.
    """
    gap = MAX_GAP_MODEL if leg.source == "model shape" else MAX_GAP
    return leg.p - om.implied_prob(leg.price) <= gap


def search(legs: list[Leg], w: np.ndarray, band=(150, 1000), min_legs: int = 4, max_legs: int = 5,
           min_leg_p: float = 0.55, max_leg_p: float = 0.80, under_min_p: float = 0.75,
           under_max_p: float = 0.92, max_unders: int = 1, one_per_player: bool = True, pool: int = 80,
           beam: int = 300, min_pair_lift: float = 1.10) -> list[dict]:
    """Candidate parlays inside the band, best leg value first.

    Every leg must be likely on its own (fair chance at least min_leg_p, 55% by default,
    about -122): Mike wants 4-5 legs that each tend to hit, not one +600 rung carrying
    the price. Legs are also capped at max_leg_p (80%, about -400): a -1800 leg adds
    almost nothing to the payout but still carries FanDuel's margin. Legs must be
    plausible with value at least 0.8. Unders are only welcome as near-locks (fair chance
    under_min_p to under_max_p, 75-92%), at most max_unders per slip: Mike finds a
    slip of unders no fun. With one_per_player, a slip never has two legs on the same
    player: books price those as nearly one bet and cut the payout hard (a Penix +
    London catches + London yards slip was quoted +104 against +230 for its legs).
    Pairs are scored with one weighted matrix product, then
    grown by beam search up to max_legs; only parlays with at least min_legs legs are kept.
    Each candidate records its weakest pair's lift (min_lift): under 1, two legs pull against
    each other (one_story).
    """
    lo_p, hi_p = 1 / (1 + band[1] / 100), 1 / (1 + band[0] / 100)
    def eligible(l: Leg) -> bool:
        if l.side == "under":
            return under_min_p <= l.p <= under_max_p
        return min_leg_p <= l.p <= max_leg_p

    pool_legs = [l for l in legs if eligible(l) and 0.8 <= l.value and plausible(l)]
    pool_legs = sorted(pool_legs, key=lambda l: -l.read_value)[:pool]
    if len(pool_legs) < 2:
        return []
    hits = np.array([l.hit for l in pool_legs], dtype=float)           # (L, n)
    p = np.array([l.p for l in pool_legs])
    shrink = p / np.array([l.p_model for l in pool_legs])     # <= 1 where another book caps a leg
    joint2 = (hits * w) @ hits.T * np.outer(shrink, shrink)             # (L, L)
    np.fill_diagonal(joint2, p)
    lift2 = joint2 / np.outer(p, p)
    keys = [(l.player,) if one_per_player else l.key for l in pool_legs]
    vals = np.array([l.value for l in pool_legs])
    rvals = np.array([l.read_value for l in pool_legs])      # ranking: with our game read where we have one
    ratio = np.array([(l.p if l.p_read is None else l.p_read) / l.p for l in pool_legs])
    under = np.array([l.side == "under" for l in pool_legs])

    def ok(combo) -> bool:
        return len({keys[i] for i in combo}) == len(combo) and under[list(combo)].sum() <= max_unders

    found = []

    def consider(combo, pj):
        if len(combo) < min_legs:
            return
        lift = pj / np.prod(p[list(combo)])
        pair_lifts = [(lift2[i, j], i, j) for i, j in itertools.combinations(combo, 2)]
        best, worst = max(pair_lifts), min(pair_lifts)
        if lo_p <= pj <= hi_p and lift >= 1.0 and best[0] >= min_pair_lift:
            found.append({"combo": combo, "p": float(pj), "lift": float(lift), "min_lift": float(worst[0]),
                          "value": float(np.prod(vals[list(combo)])), "read_value": float(np.prod(rvals[list(combo)])),
                          "p_read": float(min(pj * np.prod(ratio[list(combo)]), 0.999)), "pair": best})

    frontier = []
    for i, j in itertools.combinations(range(len(pool_legs)), 2):
        if keys[i] != keys[j] and ok((i, j)):
            consider((i, j), joint2[i, j])
            if lift2[i, j] >= 1.0:
                frontier.append(((i, j), joint2[i, j]))
    for size in range(3, max_legs + 1):
        frontier = sorted(frontier, key=lambda c: -np.prod(rvals[list(c[0])]))[:beam]
        grown = []
        for combo, _ in frontier:
            both = hits[list(combo)].prod(axis=0) * w
            pj_all = (hits @ both) * np.prod(shrink[list(combo)]) * shrink
            for k in range(combo[-1] + 1, len(pool_legs)):
                c = combo + (k,)
                if ok(c) and pj_all[k] >= lo_p * 0.5:
                    consider(c, pj_all[k])
                    grown.append((c, pj_all[k]))
        frontier = grown
    for f in found:
        f["legs"] = [pool_legs[i] for i in f["combo"]]
        f["pair"] = (pool_legs[f["pair"][1]], pool_legs[f["pair"][2]], float(f["pair"][0]))
    return sorted(found, key=lambda f: (-f["read_value"], -f["lift"]))


STORY_MIN_PAIR_LIFT = 0.97   # sim noise: pairs this close to independent don't pull against each other


def one_story(c: dict, floor: float = STORY_MIN_PAIR_LIFT) -> bool:
    """A slip that tells one game story (Mike, Oct 11: no Huntley 250+ passing yards with the
    Falcons' moneyline): every pair of legs hits together at least about as often as if they
    were unrelated, so no leg needs the game to go the other way."""
    return c.get("min_lift", 0.0) >= floor


def slip_id(legs: list[Leg], event_id: str) -> str:
    return hashlib.sha1((event_id + "|" + "|".join(sorted(l.label for l in legs))).encode()).hexdigest()[:12]


def script(legs: list[Leg], w: np.ndarray, sim, home: str, away: str) -> dict | None:
    """The game a slip needs: in the simulated games where every leg hits (weighted draws) vs all of
    them, how often the home team wins, the total points and each team's passing yards."""
    if home not in getattr(sim, "points", {}) or away not in sim.points:
        return None
    hit = np.prod([l.hit for l in legs], axis=0).astype(float) * w
    if hit.sum() <= 0:
        return None
    avg = lambda x, wt: float((x * wt).sum() / wt.sum())
    margin, total = sim.points[home] - sim.points[away], sim.points[home] + sim.points[away]
    out = {"home": home, "away": away, "p_home": avg(margin > 0, w), "p_home_hit": avg(margin > 0, hit),
           "total": avg(total, w), "total_hit": avg(total, hit)}
    for side, team in (("home", home), ("away", away)):
        py = (getattr(sim, "team", {}).get(team) or {}).get("pass_yds")
        if py is not None:
            out[f"pass_{side}"], out[f"pass_{side}_hit"] = avg(py, w), avg(py, hit)
    return out


def paused_themes() -> set[str]:
    """Slip themes taken off the Fun tab (settings fun.paused_themes); the builder still allows them."""
    from betlab import config

    return set((config.settings().get("fun") or {}).get("paused_themes") or [])


def pick(candidates: list[dict], k: int = 5, max_overlap: int = 2, max_per_player: int = 3,
         max_leg_repeat: int = 2, paused: set[str] | None = None) -> list[dict]:
    """The top k, skipping paused themes and near-duplicates of ones already chosen: sharing more than
    `max_overlap` player-stats, a player-stat already in `max_leg_repeat` slips, or a player in `max_per_player`.
    Legs compare by player and stat (Leg.key), not the exact rung: on Oct 19 four of MNF's five slips were the
    same Purdy / McCaffrey / Kittle / Daniels props with the yardage nudged (225+ vs 200+), each a "new" leg."""
    paused = paused_themes() if paused is None else paused
    chosen, per_player, per_leg = [], {}, {}
    for c in candidates:
        if paused and theme(c["legs"], {}) in paused:
            continue
        ids = {l.key for l in c["legs"]}
        if any(len(ids & {l.key for l in o["legs"]}) > max_overlap for o in chosen):
            continue
        if any(per_player.get(l.player, 0) >= max_per_player for l in c["legs"]):
            continue
        if any(per_leg.get(key, 0) >= max_leg_repeat for key in ids):
            continue
        chosen.append(c)
        for key in ids:
            per_leg[key] = per_leg.get(key, 0) + 1
        for l in c["legs"]:
            per_player[l.player] = per_player.get(l.player, 0) + 1
        if len(chosen) == k:
            break
    return chosen


def pick_story(chosen: list[dict], pool: list[dict], k: int, max_overlap: int = 2,
               paused: set[str] | None = None) -> list[dict]:
    """The k one-story slips beside the value slips: none shares more than `max_overlap` player-stats with a value
    slip, and `pick`'s player and leg limits count among the story slips only. Picking them as more of the same list
    (Oct 19 to Nov 9) let the five value slips use up those limits, and no story slip was made after Oct 18."""
    taken = [{l.key for l in o["legs"]} for o in chosen]
    fresh = [c for c in pool if all(len({l.key for l in c["legs"]} & t) <= max_overlap for t in taken)]
    return pick(fresh, k=k, max_overlap=max_overlap, paused=paused)


def leg_pack(legs: list[Leg], w: np.ndarray, n: int = 3000, seed: int = 0) -> dict:
    """Every leg of a game for the page's parlay builder (Mike, 2026-09-28: grade the parlays he
    builds): n draws resampled from the weighted simulation (so each counts equally), and per
    leg a bitset of the draws where it hits (base64). The page ANDs bitsets for a joint chance,
    scaled by each leg's shrink (its fair chance over its chance in these draws), as search does.
    Legs under 2% or over 98% are left out."""
    import base64

    rng = np.random.default_rng(seed)
    idx = rng.choice(len(w), size=n, p=w / w.sum())
    out, seen, packed = [], set(), {}
    for l in legs:
        if not (0.02 <= l.p <= 0.98) or l.label in seen:
            continue
        seen.add(l.label)
        h = l.hit[idx]
        p_pack = float(h.mean())
        if p_pack <= 0:
            continue
        doc = {"label": l.label, "player": l.player if l.stat not in GAME_STATS else "", "team": l.team,
               "stat": l.stat, "side": l.side, "point": l.point, "price": l.price, "p": round(l.p, 4),
               "p_pack": round(p_pack, 4), "source": l.source}
        bits = np.packbits(h.astype(np.uint8)).tobytes()
        flip = np.packbits((~h).astype(np.uint8)).tobytes()
        if flip in packed:        # an under at a half-point line is its over's complement: point to it
            doc["not"] = packed[flip]
        else:
            doc["bits"] = base64.b64encode(bits).decode("ascii")
            packed[bits] = l.label
        out.append(doc)
    return {"draws": int(n), "legs": out}


def pack_hits(pack: dict) -> tuple[list[dict], np.ndarray]:
    """A builder pack's legs and their hits per draw (legs x draws, bool), the bitsets unpacked; a leg kept as `not`
    (an under at a half point) is its over's complement."""
    import base64

    n = int(pack.get("draws") or 0)
    legs = [l for l in pack.get("legs") or [] if l.get("bits") or l.get("not")]
    by, rows = {}, []
    for l in legs:
        if l.get("bits"):
            by[l["label"]] = np.unpackbits(np.frombuffer(base64.b64decode(l["bits"]), dtype=np.uint8))[:n].astype(bool)
    keep = []
    for l in legs:
        h = by.get(l["label"]) if l.get("bits") else (~by[l["not"]] if l.get("not") in by else None)
        if h is not None and len(h) == n:
            keep.append(l)
            rows.append(h)
    return keep, (np.vstack(rows) if rows else np.zeros((0, n), bool))


SIDE_STATS = {"moneyline", "spread", "puck line", "double chance", "draw", "h2h"}   # who wins: one leg a slip
TOTAL_STATS = {"total", "goals"}


def _market(l: dict) -> tuple:
    """One leg per market in a slip: a player (any stat); who wins (a moneyline, spread, puck line, double chance or
    draw: a team's moneyline with its own spread is nearly one bet); the total, a team's total; BTTS."""
    if l.get("player"):
        return ("player", l["player"])
    s = l.get("stat") or ""
    if s in SIDE_STATS:
        return ("side",)
    if s in TOTAL_STATS:
        return ("total", l.get("team") or "")
    return (s, l.get("team") or "")


def lines_only(legs: list[dict]) -> bool:
    """A pack with only who-wins and the game total (college lines, a UFC fight): no props, no BTTS, no team totals."""
    return all(not l.get("player") and _market(l) in (("side",), ("total", "")) for l in legs)


def best_single(legs: list[dict], game: dict) -> dict | None:
    """A lines-only game's one bet (Nov 7, Mike: "if something like cfb where you can't really make a parlay out of it
    just give a pick"): the side or total with the best price at FanDuel against the sharp no-vig chance, with its EV
    said plainly, even when there's no edge. Not a pick: the card's picks keep their own bar. Legs with no FanDuel
    price (a stand-in) are left out."""
    priced = [l for l in legs if l.get("price") is not None and not str(l.get("source") or "").startswith("fair price")
              and 0.05 <= float(l["p"]) <= 0.95]
    if not priced:
        return None
    ev = lambda l: float(l["p"]) * om.american_to_decimal(float(l["price"])) - 1
    l = max(priced, key=ev)
    e, p = ev(l), float(l["p"])
    return {"sgp_id": hashlib.sha1((str(game["event_id"]) + "|single|" + l["label"]).encode()).hexdigest()[:12],
            "theme": "", "legs": [{"label": l["label"], "player": "", "team": l.get("team") or "", "stat": l.get("stat"),
                                   "side": l.get("side"), "point": l.get("point"), "price": l["price"],
                                   "p_fair": round(p, 4), "fair_price": _american(p), "source": l.get("source")}],
            "p_fair": round(p, 4), "n_legs": 1, "fair_price": _american(p), "naive_price": int(l["price"]),
            "price": int(l["price"]), "ev": round(e, 4), "style": "single",
            "why": (f"{game['matchup']} has only its winner and total to bet, which make no real parlay, so its best "
                    f"single: {l['label']} {int(l['price']):+d} at FanDuel against the sharp no-vig chance {p:.1%} "
                    f"(fair {_american(p):+d}), EV {e:+.1%}."
                    + ("" if e > 0 else " No edge: the fairest price on the game, not a pick."))}


def pack_slips(pack: dict, game: dict, sport: str, k: int = 3, band=(150, 1000), long_band=(1500, 6000),
               legs=(2, 4), leg_p=(0.35, 0.85), long_leg_p=0.12, beam: int = 150, under_p=(0.75, 0.92),
               max_unders: int = 1) -> list[dict]:
    """A game's own same-game slips from its builder pack (Nov 7, Mike: "if a game is watched that means i want single
    game slips for it"): the sports whose builders make no full slips (college, soccer, the NHL, UFC). The joint chance
    is what Build shows (lib/builder.ts): the share of draws where every leg hits, times each leg's shrink (its fair
    chance over its chance in the draws), capped at the likeliest leg. One leg per market and per player. Ranked by how
    much the legs move together (the joint over the product of the legs); `k` slips in the fun band, no two sharing more
    than one leg, then one long shot in `long_band` from longer legs, sharing at most one leg with them."""
    lg, hits = pack_hits(pack)
    n = hits.shape[1]
    if n == 0 or not lg:
        return []
    if lines_only(lg):            # a winner and a total make no real parlay (Mike, Nov 7: "just give a pick")
        s = best_single(lg, game)
        return [s] if s else []
    if len(lg) < 2:
        return []
    p = np.array([float(l["p"]) for l in lg])
    shrink = p / np.maximum(np.array([float(l.get("p_pack") or l["p"]) for l in lg]), 1e-6)
    lo_n, hi_n = legs
    # the fun rules on player props (settings fun): an under only as a near-lock, at most one a slip; a game's under
    # (fewer goals, BTTS no) is a story of its own and isn't capped
    under = [bool(l.get("player")) and str(l.get("side") or "").lower() == "under" for l in lg]
    ok_leg = [not u or under_p[0] <= p[i] <= under_p[1] for i, u in enumerate(under)]

    def search(pmin: float, pmax: float, odds) -> list[tuple[float, float, tuple]]:
        ok = [i for i in range(len(lg)) if ok_leg[i] and (pmin <= p[i] <= pmax or under[i])]
        lo_p, hi_p = 1 / (1 + odds[1] / 100), 1 / (1 + odds[0] / 100)
        frontier = [((i,), hits[i]) for i in ok]
        out = []
        for size in range(2, hi_n + 1):
            grown = {}
            for combo, h in frontier:
                taken = {_market(lg[i]) for i in combo}
                for j in ok:
                    if j <= combo[-1] or _market(lg[j]) in taken or (under[j] and sum(under[i] for i in combo) >= max_unders):
                        continue
                    c = combo + (j,)
                    hj = h & hits[j]
                    joint = min(float(hj.mean()) * float(np.prod(shrink[list(c)])), float(p[list(c)].min()))
                    if joint <= 0:
                        continue
                    lift = joint / float(np.prod(p[list(c)]))
                    grown[c] = (lift, joint, hj)
            ranked = sorted(grown.items(), key=lambda kv: -kv[1][0])
            for c, (lift, joint, _) in ranked:
                if size >= lo_n and lo_p <= joint <= hi_p and lift >= 1.0:
                    out.append((lift, joint, c))
            frontier = [(c, v[2]) for c, v in ranked[:beam]]
        return sorted(out, key=lambda x: (-x[0], -x[1]))

    chosen: list[tuple[float, float, tuple, str]] = []
    for lift, joint, c in search(*leg_p, band):
        if len(chosen) == k:
            break
        if all(len(set(c) & set(x[2])) <= 1 for x in chosen):
            chosen.append((lift, joint, c, "value"))
    for lift, joint, c in search(long_leg_p, leg_p[1], long_band):
        if all(len(set(c) & set(x[2])) <= 1 for x in chosen):
            chosen.append((lift, joint, c, "longshot"))
            break
    out = []
    for lift, joint, c, style in chosen:
        ls = [lg[i] for i in c]
        labels = [l["label"] for l in ls]
        naive = float(np.prod([om.american_to_decimal(l["price"]) for l in ls if l.get("price") is not None])) \
            if all(l.get("price") is not None for l in ls) else None
        doc = {"sgp_id": hashlib.sha1((str(game["event_id"]) + "|" + "|".join(sorted(labels))).encode()).hexdigest()[:12],
               "theme": "", "legs": [{"label": l["label"], "player": l.get("player") or "", "team": l.get("team") or "",
                                      "stat": l.get("stat"), "side": l.get("side"), "point": l.get("point"),
                                      "price": l.get("price"), "p_fair": round(float(l["p"]), 4),
                                      "fair_price": _american(float(l["p"])), "source": l.get("source")} for l in ls],
               "p_fair": round(joint, 4), "n_legs": len(ls), "fair_price": _american(joint),
               "naive_price": _american(1 / naive) if naive else None, "lift": round(lift, 2),
               "style": style, **({"longshot": True} if style == "longshot" else {}),
               "why": (f"{len(ls)} legs of {game['matchup']}, priced together from the same simulated games the "
                       f"Build tab uses: {joint:.1%}, fair {_american(joint):+d}"
                       + (f"; they hit together {lift:.2f}x as often as unrelated legs would." if lift >= 1.02 else ".")
                       + " Type the book's quote to see the EV.")}
        out.append(doc)
    return out


def leg_doc(l: Leg) -> dict:
    """One leg as the page shows it."""
    return {"label": l.label, "player": l.player, "team": l.team, "stat": l.stat, "side": l.side,
            "point": l.point, "price": l.price, "p_fair": round(l.p, 4),
            "fair_price": _american(l.p), "source": l.source,
            "p_model_raw": None if l.p_raw is None else round(l.p_raw, 4),
            "p_read": None if l.p_read is None else round(l.p_read, 4), "read": l.read,
            "questionable": l.injury, "note": l.note}


def to_doc(c: dict, event_id: str) -> dict:
    """One parlay as the page shows it."""
    legs = sorted(c["legs"], key=lambda l: (l.team, l.player))
    sgp_id = slip_id(legs, event_id)
    naive_dec = float(np.prod([om.american_to_decimal(l.price) for l in legs]))
    return {
        "sgp_id": sgp_id,
        "theme": theme(legs, {}),
        "legs": [leg_doc(l) for l in legs],
        "p_fair": round(c["p"], 4),
        "n_legs": len(legs),
        "fair_price": _american(c["p"]),
        "fits_read": sum(bool(l.read) for l in legs),
        "p_read": None if all(l.p_read is None for l in legs) else round(c.get("p_read", c["p"]), 4),
        "read_price": None if all(l.p_read is None for l in legs) else _american(c.get("p_read", c["p"])),
        "naive_price": _american(1 / naive_dec),
        "lift": round(c["lift"], 2),
        "min_pair_lift": None if c.get("min_lift") is None else round(c["min_lift"], 3),
        "one_story": None if c.get("min_lift") is None else one_story(c),
        "leg_value": round(c["value"], 3),
        "read_value": round(c.get("read_value", c["value"]), 3),
        "why": why(legs, c["p"], c["pair"], None if all(l.p_read is None for l in legs) else c.get("p_read")),
    }


def grid_pack(final: np.ndarray, legs: list[dict], n: int = 3000, seed: int = 0) -> dict:
    """A builder pack (as `leg_pack`) for a sport priced from a final-score grid (hockey,
    soccer): n final scores drawn from the grid; each leg is either a mask over the grid
    (`mask`, a boolean array shaped like it) or independent of the score with chance `p`
    (`indep`: player props we have no joint model for, labeled as such in `source`).
    Leg dicts: label, team, player, stat, side, point, price (None = not in FanDuel's feed),
    p (the fair chance), source."""
    from types import SimpleNamespace

    rng = np.random.default_rng(seed)
    flat = final.ravel() / final.sum()
    idx = rng.choice(flat.size, size=n, p=flat)
    out = []
    for leg in legs:
        hit = leg["mask"].ravel()[idx] if "mask" in leg else (rng.random(n) < leg["p"])
        out.append(SimpleNamespace(label=leg["label"], player=leg.get("player") or "", team=leg.get("team") or "",
                                   stat=leg["stat"], side=leg["side"], point=leg.get("point"), p=float(leg["p"]),
                                   hit=hit, source=leg.get("source", ""),
                                   price=leg["price"] if leg.get("price") is not None else _american(leg["p"])))
    return leg_pack(out, np.ones(n), n=n, seed=seed)


def draws_pack(legs: list[dict], seed: int = 0) -> dict:
    """A builder pack (as `leg_pack`) from legs that already carry their hit per simulated game
    (`hit`, a boolean array; all the same length): the joint NHL model's legs."""
    from types import SimpleNamespace

    n = len(legs[0]["hit"]) if legs else 0
    out = [SimpleNamespace(label=l["label"], player=l.get("player") or "", team=l.get("team") or "", stat=l["stat"],
                           side=l["side"], point=l.get("point"), p=float(l["p"]), hit=np.asarray(l["hit"], bool),
                           source=l.get("source", ""), price=l["price"] if l.get("price") is not None else _american(l["p"]))
           for l in legs]
    return leg_pack(out, np.ones(n), n=n, seed=seed)
