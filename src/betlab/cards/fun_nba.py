"""NBA in the fun bucket (Mike, 2026-09-26: "same as the NFL"): SGP+ tickets per slice (afternoon,
early, late; Oct 21), a regular one and a likelier one, every game's own slips (shown for watched games, Nov 7),
and straight overs to root for in national-TV games.

The worker pulls every game of a slice 15-45 minutes before the slice's first tip (pregame). For each game:
1. Every priced player's lines come from the market: each base stat's negative binomial mean
   is set so the market's no-vig chance at FanDuel's line is reproduced (the dispersion is
   player model v3's). Stats without a FanDuel line aren't simulated.
2. models/game_sim_nba draws the game jointly (copula correlations measured on 2024-25, checked
   on 2025-26), with the game's total and margin around the market's.
3. Combos (PRA and the pairs) are the sums of their parts; the draws are then reweighted
   (props_market.rake) so each combo's FanDuel line also matches the market.
4. The same slip rules as the NFL (sgp.search via sgp_plus.minis): legs 55-80% likely, one
   leg per player, unders only as near-locks, no unders in a ticket. The copula matches real
   games for 70% legs; it overstates some long-shot pairs, which is why legs stay likely.
Overs to root for are listed only for national-TV games (Mike's "national-TV singles").
Fun bucket only; FanDuel's quoted SGP+ price, typed on the page, is the real test.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from betlab import config
from betlab import odds_math as om
from betlab import props_market as PM
from betlab import sgp, sgp_plus
from betlab.cards import props_nba as PN
from betlab.models import game_sim_nba as G

ET = "America/New_York"


def _center(pick_snap: pd.DataFrame | None, home_name: str, away_name: str) -> tuple[float, float] | None:
    """(home expected margin, total): median across books in the game-line snapshot."""
    if pick_snap is None or pick_snap.empty:
        return None
    ev = pick_snap[(pick_snap["home_team"] == home_name) & (pick_snap["away_team"] == away_name)]
    sp = ev[(ev["market"] == "spreads") & (ev["outcome"] == home_name)]["point"]
    tot = ev[(ev["market"] == "totals") & (ev["outcome"] == "Over")]["point"]
    if sp.empty or tot.empty:
        return None
    return -float(sp.median()), float(tot.median())


def game_inputs(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (player, team, base stat) with the market-set mean: player, team, stat, mu, r."""
    base = rows[rows["stat"].isin(G.BASE)]
    out = [{"player": r.player, "team": r.team, "stat": r.stat, "r": float(r.disp),
            "mu": PN.mu_for_quote(float(r.p_market), float(r.line), float(r.disp))} for r in base.itertuples()]
    return pd.DataFrame(out, columns=["player", "team", "stat", "mu", "r"]).drop_duplicates(["player", "stat"])


def legs_for(rows: pd.DataFrame, sim: G.GameSim, w: np.ndarray) -> list:
    """FanDuel's main lines as parlay legs (both sides), with chances from the weighted draws."""
    out = []
    for r in rows.itertuples():
        d = sim.get(r.player, r.stat)
        if d is None:
            continue
        for side, price, hit in (("over", r.fd_over, d > r.line), ("under", r.fd_under, d < r.line)):
            label = f"{r.player} {side} {r.line:g} {PN.LABEL[r.stat]}"
            leg = sgp.Leg(key=(r.player, r.stat), label=label, player=r.player, team=r.team, stat=r.stat,
                          side=side, point=float(r.line), price=int(price), hit=hit,
                          source=f"{r.market_source} (market)")
            leg.p = leg.p_model = float(w[hit].sum())
            if r.questionable:
                leg.injury = "day-to-day"
            out.append(leg)
    return out


ALT = {"player_points_alternate": "points", "player_rebounds_alternate": "rebounds",
       "player_assists_alternate": "assists", "player_threes_alternate": "threes"}
MAIN_OF = {v: k for k, v in PM.NBA_MAIN.items()}


def alt_legs(ev: pd.DataFrame, sim: G.GameSim, w: np.ndarray, rows: pd.DataFrame) -> list:
    """FanDuel's alt rungs ("25+ points") as over legs. The chance is the simulation's (market-set
    center, model shape), capped by other books' same rung (each shrunk by that book's margin
    on the player's main line, 7% without one): a rung can look worse than the books, never
    better. A rung no other book quotes gets the player's tightest cap ratio, as in the NFL."""
    if ev is None or ev.empty:
        return []
    team = dict(zip(rows["player"], rows["team"]))
    dtd = set(rows.loc[rows["questionable"].astype(bool), "player"])
    margins = {}
    for (book, player, market), g in ev[ev["market"].isin(list(MAIN_OF.values()))].groupby(["bookmaker", "player", "market"]):
        o, u = g[g["outcome"] == "Over"], g[g["outcome"] == "Under"]
        if len(o) and len(u):
            margins[(book, player, PM.NBA_MAIN[market])] = om.overround([o["price"].iloc[0], u["price"].iloc[0]])
    alt = ev[ev["market"].isin(list(ALT)) & (ev["outcome"] == "Over") & ~ev["bookmaker"].isin(PM.LADDER_SKIP)]
    ceilings = {}
    for r in alt[alt["bookmaker"] != "fanduel"].itertuples():
        stat = ALT[r.market]
        p = om.implied_prob(r.price) / (1 + margins.get((r.bookmaker, r.player, stat), 0.07))
        if 0.04 <= p <= 0.96:
            ceilings.setdefault((r.player, stat, float(r.point)), []).append((p, r.bookmaker))
    out = []
    for r in alt[alt["bookmaker"] == "fanduel"].itertuples():
        stat = ALT[r.market]
        d = sim.get(r.player, stat)
        if d is None:
            continue
        hit = d > r.point
        leg = sgp.Leg(key=(r.player, stat), label=f"{r.player} {int(r.point + 0.5)}+ {PN.LABEL[stat]}", player=r.player,
                      team=team.get(r.player, ""), stat=stat, side="over", point=float(r.point), price=int(r.price),
                      hit=hit, source="model shape")
        leg.p = leg.p_model = float(w[hit].sum())
        cap = ceilings.get((r.player, stat, float(r.point)))
        if cap:
            leg.p = min(leg.p_model, float(np.median([c[0] for c in cap])))
            leg.source = ", ".join(sorted({c[1] for c in cap}))
        if r.player in dtd:
            leg.injury = "day-to-day"
        out.append(leg)
    ratio: dict = {}
    for leg in out:
        if leg.source != "model shape" and leg.p_model > 0:
            ratio[leg.key] = min(ratio.get(leg.key, 1.0), leg.p / leg.p_model)
    for leg in out:
        if leg.source == "model shape" and leg.key in ratio:
            leg.p = leg.p_model * ratio[leg.key]
    return out


def build_game(rows: pd.DataFrame, pick_snap: pd.DataFrame | None, fun: dict, national: dict, seed: int = 0,
               ev: pd.DataFrame | None = None) -> dict | None:
    """One game's pieces: minis for the window's SGP+ ticket and (national TV) overs to root for."""
    first = rows.iloc[0]
    center = _center(pick_snap, first["home_name"], first["away_name"])
    if center is None:
        return None
    inputs = game_inputs(rows)
    if len(inputs) < 4:
        return None
    sim = G.simulate(inputs, first["home"], first["away"], center[0], center[1], n=int(fun.get("sims", 20000)), seed=seed)
    combos = rows[rows["stat"].isin(list(G.COMBOS))]
    ind, targets = [], []
    for r in combos.itertuples():
        d = sim.get(r.player, r.stat)
        if d is not None:
            ind.append(d > r.line)
            targets.append(float(r.p_market))
    w, err = PM.rake(ind, targets, sim.n) if ind else (np.full(sim.n, 1 / sim.n), 0.0)
    if PM.effective_draws(w) < 1000 or err > 0.02:
        w = np.full(sim.n, 1 / sim.n)                  # combos off the market: drop them rather than trust thin draws
        rows = rows[~rows["stat"].isin(list(G.COMBOS))]
    legs = legs_for(rows, sim, w) + alt_legs(ev, sim, w, rows) + sgp.game_line_legs(
        pick_snap[(pick_snap["home_team"] == first["home_name"]) & (pick_snap["away_team"] == first["away_name"])],
        sim, w, first["home_name"], first["away_name"], first["home"], first["away"],
        config.settings()["odds_api"]["sharp_books"])
    plus = fun["nba"]
    doc = {"event_id": str(first["event_id"]), "game_ref": game_ref(first["home"], first["away"], first["tipoff"]),
           "matchup": first["matchup"],
           "commence_time": str(first["tipoff"]), "spread_home": center[0], "total": center[1],
           "national_tv": national.get((first["home"], first["away"]), []),
           "minis": [sgp.to_doc(c, str(first["event_id"])) for c in sgp_plus.minis(legs, w, plus, fun)]}
    doc["sgps"] = game_slips(legs, w, fun, doc)        # on the slate, shown for the games an account watches (Nov 7)
    doc["overs"] = sgp_plus.rooting_overs(legs, plus) if doc["national_tv"] else []
    doc["pack"] = sgp.leg_pack(legs, w, seed=seed)     # the page's parlay builder
    return doc


def game_slips(legs: list, w: np.ndarray, fun: dict, game: dict) -> list[dict]:
    """A game's own same-game slips, by the NFL's rules (fun band, 4-5 legs each 55-80% likely, sgp.pick's
    no-repeats, one long shot): what a window with one game shows instead of an SGP+ ticket, as the NFL does
    for a prime-time game (Mike, Oct 19: "count them like primetime games"). Each carries its game so the fun
    ledger grades its legs from the box score (game_ref). Pairs need the NBA's lift (fun.nba.min_pair_lift), not
    search's NFL default of 1.10: NBA pairs across players rarely reach it, so opening night's 3 PM game got no
    value slip, only its long shot (Oct 20: 0 candidates at 1.10, 3,253 at 1.03)."""
    common = dict(max_leg_p=float(fun["max_leg_p"]), under_min_p=float(fun.get("under_min_p", 0.75)),
                  under_max_p=float(fun.get("under_max_p", 0.92)), max_unders=int(fun.get("max_unders", 1)),
                  one_per_player=bool(fun.get("one_leg_per_player", True)),
                  min_pair_lift=float(fun["nba"].get("min_pair_lift", 1.10)))
    cands = sgp.search(legs, w, band=tuple(fun["band"]), min_legs=int(fun["min_legs"]), max_legs=int(fun["max_legs"]),
                       min_leg_p=float(fun["min_leg_p"]), **common)
    chosen = sgp.pick(cands, k=int(fun["per_game"]))
    picked = [(c, "value") for c in chosen]
    ls = fun.get("longshot")
    if ls:   # bigger payout, longer legs, never a stretched copy of a value slip (at most 2 player-stats shared)
        long_cands = sgp.search(legs, w, band=tuple(ls["band"]), min_legs=int(ls["min_legs"]), max_legs=int(ls["max_legs"]),
                                min_leg_p=float(ls["min_leg_p"]), **common)
        taken = [{l.key for l in c["legs"]} for c in chosen]
        best = next((c for c in long_cands if all(len({l.key for l in c["legs"]} & t) <= 2 for t in taken)), None)
        if best:
            picked.append((best, "longshot"))
    out = []
    for c, style in picked:
        d = sgp.to_doc(c, game["event_id"]) | {"style": style, "sport": "nba", "matchup": game["matchup"],
                                                "event_id": game["event_id"], "commence_time": game["commence_time"]}
        d["games"] = [{"event_id": game["event_id"], "game_ref": game["game_ref"], "matchup": game["matchup"],
                       "commence_time": game["commence_time"], "legs": [l["label"] for l in d["legs"]]}]
        out.append(d | ({"longshot": True} if style == "longshot" else {}))
    return out


def game_ref(home: str, away: str, tipoff) -> str:
    """How an NBA leg finds its box score later (fun_ledger): nba|HOME|AWAY|tipoff."""
    return f"nba|{home}|{away}|{pd.Timestamp(tipoff).isoformat()}"


# NBA slices: afternoon, early and late (sgp_plus.SLICES["nba"]; Mike, Oct 21: "early and late slices"). Until Oct 21
# they were 30-minute tip windows (Oct 10), which on Oct 21 made six slices of 1-3 games, locked minutes after their
# last game was priced. A fixed slice locks before its later games' own windows, so pregame pulls every game of a
# slice before its first tip (pregame.due_by_slice).
def slice_key(tip) -> tuple[str, str]:
    """(ET day, slice name) of a tip."""
    return sgp_plus.slice_of(tip, "nba")


def build(rows: list[dict], pick_snap: pd.DataFrame | None, fun: dict, national: dict,
          props_snap: pd.DataFrame | None = None, day_tips=None) -> list[dict]:
    """The Fun tab's NBA slates for one run: the games priced this run, one slate per slice (afternoon,
    early, late), each with SGP+ tickets across its games (2+) and overs to root for from its national-TV
    games. props_snap: the run's props snapshot (FanDuel's alt ladders and the other books' rungs).
    day_tips: unused since fixed slices replaced tip windows (Oct 21); kept for the caller."""
    df = pd.DataFrame(rows)
    if df.empty or "home" not in df:
        return []
    games = []
    for i, (eid, g) in enumerate(df.groupby("event_id", sort=False)):
        ev = props_snap[props_snap["event_id"] == eid] if props_snap is not None else None
        doc = build_game(g, pick_snap, fun, national, seed=i, ev=ev)
        if doc:
            games.append(doc)
    return slates_from(games, fun)


def slates_from(games: list[dict], fun: dict, day_tips=None) -> list[dict]:
    """Game docs -> one slate per slice (afternoon, early, late)."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for g in games:
        groups.setdefault(slice_key(g["commence_time"]), []).append(g)
    return sorted((_slate(gs, fun) for gs in groups.values()), key=lambda s: pd.Timestamp(s["kickoff"]))


def short_ticket(games: list[dict], main: dict | None, sid: str, label: str, cfg: dict) -> dict | None:
    """A likelier SGP+ next to the regular one (Mike, Oct 21: NBA tickets ran longer than the other markets'; "just
    want a mix"): the `short` band, from the games the regular ticket left out when enough are left, else from all."""
    short = cfg.get("short")
    if not short:
        return None
    sub = cfg | short
    used = {g["event_id"] for g in (main or {}).get("games") or []}
    rest = [g for g in games if g["event_id"] not in used]
    pools = ([rest] if len(rest) >= int(sub["min_games"]) else []) + [games]
    for pool in pools:
        t = sgp_plus.ticket(pool, sid, label + " (likelier)", sub)
        if t and t["sgp_id"] != (main or {}).get("sgp_id"):
            return t | {"style": "likelier"}
    return None


def _slate(games: list[dict], fun: dict, packs: list[dict] | None = None) -> dict:
    """One slice's slate from its games' docs: the SGP+ tickets across them, national-TV overs, every game's own slips
    (the apps show a watched game's, Nov 7), builder packs (`packs` plus those of games that carry one), and the games themselves
    without packs, so a later re-pull of one game rebuilds the tickets with all of them (merge)."""
    games = sorted(games, key=lambda g: g["commence_time"])
    names = sgp_plus.slice_names("nba", *slice_key(games[0]["commence_time"]), len(games))
    sid, label = names["slate"], names["label"]
    plus_cfg = fun["nba"]
    overs = [o | {"kind": "over", "matchup": g["matchup"], "event_id": g["event_id"], "commence_time": g["commence_time"],
                  "sgp_id": "over-" + hashlib.sha1((g["event_id"] + "|" + o["label"]).encode()).hexdigest()[:10]}
             for g in games for o in g["overs"]]
    overs.sort(key=lambda o: -(o["p_fair"] * om.american_to_decimal(o["price"])))
    many = len(games) >= int(plus_cfg["min_games"])
    ticket = sgp_plus.ticket(games, sid, label, plus_cfg) if many else None
    short = short_ticket(games, ticket, sid, label, plus_cfg) if many else None
    # every game's own slips ride on the slate; the apps show the games an account watches (Mike, Nov 7: no more
    # Knicks rule or lone-game rule; until then a lone game's and a Knicks game's showed, Oct 19 and 21)
    solo = sgp_plus.own_slips(games, "nba", "sgps")
    packs = (packs or []) + [{"event_id": g["event_id"], "matchup": g["matchup"], "commence_time": g["commence_time"],
                              "game_ref": g["game_ref"], "sport": "nba", **g["pack"]} for g in games if g.get("pack")]
    return {"slate": sid, "label": label, "title": names["title"], "sport": "nba",
            "kickoff": games[0]["commence_time"], "n_games": len(games),
            "plus": (ticket | {"sport": "nba"}) if ticket else None,
            "plus_short": (short | {"sport": "nba"}) if short else None,
            "sgps": solo,
            "overs": overs[: int(plus_cfg["overs_per_slate"])],
            "packs": packs,
            "games": [{k: v for k, v in g.items() if k != "pack"} for g in games],
            "side_note": {"title": "National TV", "text": (
                "Straight overs to root for, only in national-TV games: fun bets, never picks. Each price is "
                "against the market's no-vig chance; FanDuel's margin means most cost a few cents a dollar.")}}


def merge(new: list[dict], old: list[dict], fun: dict) -> list[dict]:
    """A run prices only the games in its window, and a news re-pull prices one game again: a new slate
    sharing a game with an earlier one is rebuilt with that slate's other games and keeps its id, so a
    re-pull never shrinks or drops the tip time's ticket (Oct 10)."""
    out = []
    for s in new:
        ids = {g["event_id"] for g in s.get("games") or []}
        prev = next((o for o in old or [] if o["slate"] == s["slate"]
                     or ids & {g["event_id"] for g in o.get("games") or []}), None)
        others = [g for g in (prev or {}).get("games") or [] if g["event_id"] not in ids]
        if not others:
            out.append(s if prev is None else s | {"slate": prev["slate"], "label": prev["label"],
                                                    "title": prev.get("title", s["title"])})
            continue
        packs = [p for p in prev.get("packs") or [] if p.get("event_id") not in ids] + (s.get("packs") or [])
        merged = _slate(others + s["games"], fun, packs)
        out.append(merged | {"slate": prev["slate"], "label": prev["label"], "title": prev.get("title", merged["title"]),
                             "kickoff": min(prev["kickoff"], merged["kickoff"])})
    return out
