"""Soccer in the fun bucket: one SGP+ ticket per day across leagues (Mike, 2026-09-26: "one per
day, leagues mixed, never with other sports"). Since Oct 10, one per kickoff slice (morning, midday,
evening: sgp_plus.SLICES), locked 15 minutes before the slice starts (sgp_plus.keep_tickets), so a new parlay no longer
replaces it every time a match kicks off.

- **Where the chances come from:** no ratings (ours lost to the market in every league). For
  each match, the two teams' expected goals are fit so a Dixon-Coles score grid reproduces
  the sharp market: Pinnacle's no-vig home / draw / away and its over/under ladder at the
  half-goal lines (LowVig or BetOnline if Pinnacle is missing). Every leg is read off that
  one grid, so how legs move together within a match is exact: a favorite winning goes with
  goals, both teams scoring goes with the over.
- **Legs:** a team to win, over 1.5 / 2.5 / 3.5 goals, both teams to score. No unders and no
  draw: every leg is something to cheer for. FanDuel posts only the 3-way result in the bulk odds
  feed, so goals legs have no FanDuel price here: the ticket shows our fair odds, and the
  real test is FanDuel's SGP+ quote, typed on the Fun tab. Since Oct 10 the ticket's matches
  also get one event pull for FanDuel's goals ladder and both teams to score (GOALS_MARKETS),
  only for the legs' betslip links: Open in FanDuel puts the whole ticket in the betslip.
- **The ticket:** each match offers "minis" (one leg, or two legs that move together, lift
  at least pair_lift), and the day's ticket takes 3-5 matches from different kickoffs whose
  product lands in the payout band (sgp_plus.ticket), preferring correlated pairs.
"""

from __future__ import annotations

import hashlib
import itertools

import numpy as np
import pandas as pd
from scipy import optimize

from betlab import config, sgp, sgp_plus
from betlab import odds_math as om
from betlab.cards import soccer as card
from betlab.market import reference_books
from betlab.models import soccer as S

ET = "America/New_York"
LINES = (1.5, 2.5, 3.5)
SIDE_NOTE = {"title": "How it's priced",
             "text": ("One ticket per kickoff slice (morning, midday, evening) across the leagues. Each match's chances come from a score grid fit to "
                      "Pinnacle's result and goals prices, so a favorite winning and goals move together the way the "
                      "market implies. FanDuel only sends its match-result prices to our feed, so goals legs show no "
                      "FanDuel price: type the SGP+ price FanDuel quotes to see if it pays more than fair.")}
SHARP_TOTALS = ("pinnacle", "lowvig", "betonlineag")
FAR_LINE = 4.5     # a high-scoring game's only sharp line (Nov 4): anchors the grid when nothing nearer does, never a leg
# FanDuel's goals ladder (1.5 / 2.5 / 3.5 and the rest) and both teams to score, from the event endpoint
# for the ticket's matches only: the legs' betslip links (cli._soccer_goals_lines, links.py)
GOALS_MARKETS = ("alternate_totals", "btts")


def targets(ev: pd.DataFrame, home: str, away: str) -> dict | None:
    """The sharp market for one match: {"h", "d", "a", "source", "overs": {line: P(over)},
    "fd": [home, draw, away] FanDuel prices or None}."""
    s = config.settings()
    h2h = ev[ev["market"] == "h2h"]
    books, source = reference_books(h2h, "h2h", s["odds_api"]["sharp_books"], "fanduel")
    fairs = [om.devig(tw, s["picks"].get("devig_three_way", "shin")) for b in books
             if (tw := card.three_way(h2h, b, home, away))]
    if not fairs:
        return None
    ph, pdraw, pa = np.median(np.array(fairs), axis=0)
    overs = {}
    tot = ev[ev["market"] == "totals"]
    # x.5 lines, and whole-number lines (2.0, 3.0) read with their push (Oct 12: the cups' Pinnacle main is
    # often 3.0, and 7 of tomorrow's 9 Champions League matches had no x.5 line); quarter lines are skipped.
    # Nov 4: only when none of those is there, 4.5 (Barcelona, Bayern and Real Madrid games lost their packs and legs).
    for usable in (lambda x: x in LINES or x.is_integer(), lambda x: x == FAR_LINE):
        for book in SHARP_TOTALS:
            rows = tot[tot["bookmaker"] == book]
            for point, g in rows.groupby("point"):
                if usable(float(point)) and float(point) not in overs:
                    o, u = g[g["outcome"] == "Over"], g[g["outcome"] == "Under"]
                    if len(o) and len(u):
                        overs[float(point)] = om.no_vig_two_way(float(o["price"].iloc[0]), float(u["price"].iloc[0]))[0]
        if overs:
            break
    return {"h": float(ph), "d": float(pdraw), "a": float(pa), "source": source, "overs": overs,
            "fd": card.three_way(h2h, "fanduel", home, away)}


def _over(sm: np.ndarray, goals: np.ndarray, line: float) -> float:
    """P(over line); for a whole-number line, given no push."""
    over = sm[goals > line].sum()
    return over if not float(line).is_integer() else over / max(over + sm[goals < line].sum(), 1e-12)


def fit_goals(t: dict, rho: float = -0.05) -> tuple[float, float, float]:
    """(home xG, away xG, max error) whose Dixon-Coles grid reproduces the market's result
    chances and over/under ladder (least squares in log-odds). A whole-number line's no-vig chance is the over's
    chance once a push (exactly that many goals) is set aside, as the books price it."""
    want = [("h", t["h"]), ("a", t["a"])] + [(line, p) for line, p in t["overs"].items()]
    logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))

    def chances(x):
        sm = S.score_matrix(np.exp(x[0]), np.exp(x[1]), rho)
        i, j = np.indices(sm.shape)
        return {"h": sm[i > j].sum(), "a": sm[i < j].sum(), **{line: _over(sm, i + j, line) for line in t["overs"]}}

    def loss(x):
        c = chances(x)
        return sum((logit(c[k]) - logit(p)) ** 2 for k, p in want)

    res = optimize.minimize(loss, np.log([1.4, 1.1]), method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-9})
    c = chances(res.x)
    return float(np.exp(res.x[0])), float(np.exp(res.x[1])), float(max(abs(c[k] - p) for k, p in want))


def legs(sm: np.ndarray, home: str, away: str, fd: list | None) -> list[dict]:
    """Every leg for one match: label, stat, cells (the grid cells where it hits), p, and
    FanDuel's price when the feed has it (the result only)."""
    i, j = np.indices(sm.shape)
    out = [{"label": f"{home} to win", "team": home, "stat": "moneyline", "side": "yes", "point": 0.0, "cells": i > j,
            "price": fd[0] if fd else None},
           {"label": f"{away} to win", "team": away, "stat": "moneyline", "side": "yes", "point": 0.0, "cells": i < j,
            "price": fd[2] if fd else None},
           {"label": "Both teams to score", "team": None, "stat": "btts", "side": "yes", "point": 0.0,
            "cells": (i > 0) & (j > 0), "price": None}]
    out += [{"label": f"Over {line:g} goals", "team": None, "stat": "goals", "side": "over", "point": line,
             "cells": i + j > line, "price": None} for line in LINES]
    for leg in out:
        leg["p"] = float(sm[leg["cells"]].sum())
    return out


# Neither FanDuel's nor DraftKings' feed has the Conference League's goals or shots (Oct 25: 0 of 36 games; Nov 5: 0 of
# 18), so those legs get no link: the Nov 5 12:45 ticket had 7 of its 8 legs there and opened as one pick. Its winners
# are in the feed, so its matches join a ticket on those alone.
NO_GOALS_FEED = {"uecl"}
OWN_TICKET, CUP = {"uecl"}, "Conference League"


def builder_pack(sm: np.ndarray, home: str, away: str, fd: list | None, seed: int = 0) -> dict:
    """Everything for the page's parlay builder in one match, from its score grid: the 3-way
    result (FanDuel's prices), double chance, both teams to score yes and no, and totals
    0.5-4.5 both ways (fair prices: FanDuel's aren't in the feed)."""
    i, j = np.indices(sm.shape)
    legs = [{"label": f"{home} to win", "team": home, "stat": "moneyline", "side": "yes", "mask": i > j, "price": fd[0] if fd else None},
            {"label": "Draw", "stat": "draw", "side": "yes", "mask": i == j, "price": fd[1] if fd else None},
            {"label": f"{away} to win", "team": away, "stat": "moneyline", "side": "yes", "mask": i < j, "price": fd[2] if fd else None},
            {"label": f"{home} or draw", "team": home, "stat": "double chance", "side": "yes", "mask": i >= j, "price": None},
            {"label": f"{away} or draw", "team": away, "stat": "double chance", "side": "yes", "mask": i <= j, "price": None},
            {"label": "Both teams to score", "stat": "btts", "side": "yes", "mask": (i > 0) & (j > 0), "price": None},
            {"label": "Both teams to score: no", "stat": "btts", "side": "no", "mask": (i == 0) | (j == 0), "price": None}]
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        legs += [{"label": f"Over {line:g} goals", "stat": "goals", "side": "over", "point": line, "mask": i + j > line, "price": None},
                 {"label": f"Under {line:g} goals", "stat": "goals", "side": "under", "point": line, "mask": i + j < line, "price": None}]
    for leg in legs:
        leg["p"] = float(sm[leg["mask"]].sum())
        leg["source"] = "FanDuel price in the feed" if leg["price"] is not None else "fair price (FanDuel's isn't in the feed)"
    return sgp.grid_pack(sm, legs, seed=seed)


def _leg_doc(leg: dict) -> dict:
    return {"label": leg["label"], "player": None, "team": leg["team"] or "", "stat": leg["stat"], "side": leg["side"],
            "point": leg["point"], "price": leg["price"], "p_fair": round(leg["p"], 4),
            "fair_price": sgp._american(leg["p"]),
            "source": "FanDuel price in the feed" if leg["price"] is not None else "no FanDuel price in the feed",
            "p_model_raw": None, "p_read": None, "read": "", "questionable": None, "note": ""}


def minis(match_legs: list[dict], sm: np.ndarray, cfg: dict, event_id: str) -> list[dict]:
    """A match's pieces for the day's ticket: single legs in the leg band, and pairs that move
    together (joint over product at least pair_lift); correlated, likelier pieces first."""
    lo, hi = cfg["leg_p"]
    ok = [leg for leg in match_legs if lo <= leg["p"] <= hi]
    pieces = [([leg], leg["p"], 1.0) for leg in ok]
    for a_i, a in enumerate(ok):
        for b in ok[a_i + 1:]:
            if a["stat"] == b["stat"] or {a["stat"], b["stat"]} == {"moneyline"}:
                continue          # two goals lines or both teams' wins: one bet, or impossible
            joint = float(sm[a["cells"] & b["cells"]].sum())
            lift = joint / (a["p"] * b["p"])
            if lift >= cfg["pair_lift"] and joint >= cfg.get("pair_min_p", 0.3):
                pieces.append(([a, b], joint, lift))
    # A winner with goals first (something to cheer for from both), then goals pairs, then single
    # legs: otherwise every match offers the same both-teams-score + over pair, whose correlation
    # FanDuel prices too.
    has_win = lambda legs_: any(leg["stat"] == "moneyline" for leg in legs_)
    pieces.sort(key=lambda x: (-(has_win(x[0]) and len(x[0]) > 1), -(len(x[0]) > 1), -x[2], -x[1]))
    out = []
    for legs_, p, lift in pieces[: int(cfg["minis_per_game"])]:
        key = event_id + "|" + "|".join(sorted(leg["label"] for leg in legs_))
        docs = [_leg_doc(leg) for leg in legs_]
        # the ticket builder multiplies leg prices: goals legs stand in at their fair price, blanked after
        for d in docs:
            d["_price"] = d["price"] if d["price"] is not None else d["fair_price"]
        out.append({"sgp_id": hashlib.sha1(key.encode()).hexdigest()[:12],
                    "theme": "Goals and a winner" if len(legs_) > 1 else "One leg",
                    "legs": docs, "n_legs": len(docs), "p_fair": round(p, 4), "fair_price": sgp._american(p),
                    "p_read": None, "naive_price": None, "lift": round(lift, 3),
                    # the ticket prefers winners with goals, then correlated pairs
                    "leg_value": round(lift * (1.2 if has_win(legs_) and len(legs_) > 1 else 1.0), 3),
                    "read_value": round(lift * (1.2 if has_win(legs_) and len(legs_) > 1 else 1.0), 3)})
    return out


def prime_minis(match_legs: list[dict], sm: np.ndarray, cfg: dict, event_id: str, n: int = 3) -> list[dict]:
    """A prime-time match's own parlays (Mike, Oct 25: El Clásico "as a primetime game"): 2-3 of its legs (a winner,
    both teams to score, goals lines) priced together on its one score grid, so the chance is exact, not a product.
    No shot legs: a player's shots move with the goals in a way the grid doesn't know. Winners with goals first, then
    the legs that move together most; fair odds in fun.soccer.band_primetime."""
    lo_odds, hi_odds = cfg.get("band_primetime", [150, 1500])
    lo_p, hi_p = 1 / (1 + hi_odds / 100), 1 / (1 + lo_odds / 100)
    found = []
    for k in (3, 2):
        for combo in itertools.combinations(match_legs, k):
            stats = [leg["stat"] for leg in combo]
            if stats.count("goals") > 1 or stats.count("moneyline") > 1:
                continue                  # two goals lines or both teams' wins: one bet, or impossible
            cells = np.logical_and.reduce([leg["cells"] for leg in combo])
            p = float(sm[cells].sum())
            if not lo_p <= p <= hi_p:
                continue
            lift = p / float(np.prod([leg["p"] for leg in combo]))
            found.append((combo, p, lift))
    has_win = lambda legs_: any(leg["stat"] == "moneyline" for leg in legs_)
    found.sort(key=lambda x: (-has_win(x[0]), -x[2], -len(x[0])))
    out = []
    for legs_, p, lift in found[:n]:
        key = event_id + "|prime|" + "|".join(sorted(leg["label"] for leg in legs_))
        docs = [_leg_doc(leg) for leg in legs_]
        for d in docs:
            d["_price"] = d["price"] if d["price"] is not None else d["fair_price"]
        out.append({"sgp_id": hashlib.sha1(key.encode()).hexdigest()[:12], "theme": "The big match",
                    "legs": docs, "n_legs": len(docs), "p_fair": round(p, 4), "fair_price": sgp._american(p),
                    "p_read": None, "naive_price": None, "lift": round(lift, 3), "leg_value": round(lift, 3),
                    "read_value": round(lift, 3)})
    return out


# ---------------------------------------------------------------- shot overs (Oct 10, Mike: "shot overs in the
# soccer tickets"). From the props tracker's FanDuel rungs (tracking_soccer_props): a starter's "2+ shots" or
# "1+ shots on target" at FanDuel's price. The fair chance is the market's (BetRivers' ladder, else FanDuel's own
# with its margin off); the shots model has no weight, so a rung goes in only when the model agrees (its chance
# at least the fair one): never a fake over. A shot leg is a match's whole piece of the ticket (one piece per
# match), so it never sits next to a team leg it moves with.
SHOT_WORDS = {"shots": "shots", "sot": "shots on target"}


def shot_rungs(lines: pd.DataFrame | None, event_id: str, band: tuple[float, float]) -> list[dict]:
    """Eligible FanDuel shot rungs for one match, the model's biggest agreement first."""
    if lines is None or lines.empty:
        return []
    g = lines[(lines["event_id"].astype(str) == str(event_id)) & lines["stat"].isin(list(SHOT_WORDS))
              & (lines["starter"].astype(str) == "True") & lines["p_model"].notna()]
    out = []
    for r in g.itertuples():
        fair = r.p_market if pd.notna(r.p_market) else r.p_fd_fair
        price = r.last_fd_price if pd.notna(r.last_fd_price) else r.fd_price
        if pd.isna(fair) or pd.isna(price) or not band[0] <= fair <= band[1] or r.p_model < fair:
            continue
        label = f"{r.player} {int(float(r.line) + 0.5)}+ {SHOT_WORDS[r.stat]}"
        out.append({"label": label, "player": r.player, "team": r.team or "", "stat": r.stat, "side": "over",
                    "point": float(r.line), "price": float(price), "p": float(fair), "p_model": float(r.p_model),
                    "source": "BetRivers' ladder" if pd.notna(r.p_market) else "FanDuel's ladder, margin off"})
    out.sort(key=lambda x: -(x["p_model"] - x["p"]))
    seen, best = set(), []
    for x in out:                       # one rung per player
        if x["player"] not in seen:
            seen.add(x["player"])
            best.append(x)
    return best


def _shot_doc(leg: dict) -> dict:
    return {"label": leg["label"], "player": leg["player"], "team": leg["team"], "stat": leg["stat"], "side": "over",
            "point": leg["point"], "price": leg["price"], "p_fair": round(leg["p"], 4), "fair_price": sgp._american(leg["p"]),
            "source": leg["source"], "p_model_raw": round(leg["p_model"], 4), "p_read": None,
            "read": f"our shots model {leg['p_model']:.0%} (no weight)", "questionable": None, "note": ""}


def shot_minis(rungs: list[dict], event_id: str, n: int = 2) -> list[dict]:
    """Single shot legs as a match's pieces for the ticket (preferred a little over a lone team leg)."""
    out = []
    for leg in rungs[:n]:
        d = _shot_doc(leg) | {"_price": leg["price"]}
        out.append({"sgp_id": hashlib.sha1(f"{event_id}|{leg['label']}".encode()).hexdigest()[:12], "theme": "A shot to cheer",
                    "legs": [d], "n_legs": 1, "p_fair": round(leg["p"], 4), "fair_price": sgp._american(leg["p"]),
                    "p_read": None, "naive_price": None, "lift": 1.0, "leg_value": 1.1, "read_value": 1.1})
    return out


def shot_overs(rungs_by_match: list[tuple[dict, list[dict]]], band: tuple[float, float], n: int) -> list[dict]:
    """Straight shot overs to root for in one slice, the model's biggest agreement first."""
    rows = []
    for g, rungs in rungs_by_match:
        for leg in rungs:
            if not band[0] <= leg["p"] <= band[1]:
                continue
            rows.append({"sgp_id": "soc-shot-" + hashlib.sha1(f"{g['event_id']}|{leg['label']}".encode()).hexdigest()[:10],
                         "kind": "over", "sport": "soccer", "label": leg["label"], "player": leg["player"],
                         "stat": leg["stat"], "side": "over", "point": leg["point"], "price": leg["price"],
                         "p_fair": round(leg["p"], 4), "fair_price": sgp._american(leg["p"]),
                         "ev": round(leg["p"] * om.american_to_decimal(leg["price"]) - 1, 4),
                         "ev_read": round(leg["p_model"] * om.american_to_decimal(leg["price"]) - 1, 4),
                         "p_model": round(leg["p_model"], 4), "matchup": g["matchup"], "event_id": g["event_id"],
                         "commence_time": g["commence_time"],
                         "note": f"fair from {leg['source']}; our shots model {leg['p_model']:.0%} (no weight)",
                         "games": [{"matchup": g["matchup"], "event_id": g["event_id"], "game_ref": g["game_ref"],
                                    "legs": [leg["label"]]}],
                         "_edge": leg["p_model"] - leg["p"]})
    rows.sort(key=lambda r: -r["_edge"])
    return [{k: v for k, v in r.items() if k != "_edge"} for r in rows[:n]]


def game_ref(league: str, home: str, away: str, kickoff) -> str:
    """How a soccer leg finds its final score later (fun_ledger): league|home|away|kickoff."""
    return f"{league}|{home}|{away}|{pd.Timestamp(kickoff).isoformat()}"


def build(snaps: dict[str, pd.DataFrame], asof: pd.Timestamp, cfg: dict, lines: pd.DataFrame | None = None) -> list[dict]:
    """The Fun tab's soccer slates: one SGP+ ticket per kickoff slice (sgp_plus.SLICES) across the leagues.
    snaps: {league: latest pick snapshot}; lines: the props tracker's rows (shot legs and overs)."""
    shots_by_slice: dict[str, list] = {}
    days: dict[str, list[dict]] = {}
    packs: dict[str, list[dict]] = {}
    max_age = pd.Timedelta(hours=float(cfg.get("max_snapshot_age_hours", 24)))
    horizon = pd.Timedelta(hours=float(cfg.get("horizon_hours", 36)))
    for league, snap in snaps.items():
        if snap is None or snap.empty:
            continue
        if asof - pd.to_datetime(snap["snapshot_ts"], utc=True).max() > max_age:
            continue                 # a stale pull (Sep 28: a Sep 25 snapshot priced Oct 10 matches)
        kick = pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601")
        snap = snap[(kick > asof) & (kick <= asof + horizon)]
        for event_id, ev in snap.groupby("event_id", sort=False):
            home, away = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
            t = targets(ev, home, away)
            if t is None or not t["overs"]:
                continue                          # no sharp goals line: can't anchor the goals legs
            lh, la, err = fit_goals(t)
            if err > cfg.get("max_fit_error", 0.03):
                continue                          # the market's prices don't fit one score grid: skip
            sm = S.score_matrix(lh, la)
            when = pd.Timestamp(ev["commence_time"].iloc[0])
            day = "|".join(sgp_plus.slice_of(when, "soccer", home, away))
            packs.setdefault(day, []).append({"event_id": str(event_id), "matchup": f"{away} @ {home}",
                                              "commence_time": str(ev["commence_time"].iloc[0]),
                                              "game_ref": game_ref(league, home, away, when), "sport": "soccer",
                                              **builder_pack(sm, home, away, t["fd"], seed=len(packs))})
            match_legs = legs(sm, home, away, t["fd"])
            listed = league not in NO_GOALS_FEED
            if not listed:
                match_legs = [leg for leg in match_legs if leg["stat"] == "moneyline"]
            pieces = minis(match_legs, sm, cfg, str(event_id))
            if listed:
                pieces += shot_minis(shot_rungs(lines, str(event_id), tuple(cfg["leg_p"])), str(event_id))
            info = {"event_id": str(event_id), "game_ref": game_ref(league, home, away, when), "league": league,
                    "matchup": f"{away} @ {home}", "commence_time": str(ev["commence_time"].iloc[0])}
            feature = sgp_plus.primetime("soccer", home, away)
            if feature:                           # its own parlays, priced on its grid (prime_minis)
                info |= {"feature": feature, "prime_minis": prime_minis(match_legs, sm, cfg, str(event_id))}
            over_rungs = shot_rungs(lines, str(event_id), tuple(cfg.get("over_p", [0.35, 0.8])))
            if over_rungs:
                shots_by_slice.setdefault(day, []).append((info, over_rungs))
            if not pieces:
                continue
            days.setdefault(day, []).append(info | {"xg": [round(lh, 2), round(la, 2)], "minis": pieces})
    out = []
    for d in sorted(set(days) | set(shots_by_slice) | set(packs)):
        games_d = days.get(d, [])
        kicks0 = ([g["commence_time"] for g in games_d] + [i["commence_time"] for i, _ in shots_by_slice.get(d, [])]
                  + [pk["commence_time"] for pk in packs.get(d, [])])
        feature = next((g["feature"] for g in games_d if g.get("feature")), None)
        names = sgp_plus.slice_names("soccer", *d.split("|"), max(len(games_d), 1), min(kicks0) if kicks0 else None,
                                     feature=feature)
        if feature:                  # a prime-time match's own slice: its own parlay, one match (prime_minis)
            pool = [g | {"minis": g.get("prime_minis") or []} for g in games_d if g.get("feature")]
            tcfg = cfg | {"band": cfg.get("band_primetime", [150, 1500]), "min_games": 1, "max_games": 1}
            tickets = [_ticket(pool, names["slate"], names["label"], tcfg)] if pool else []
        else:                        # the Conference League gets its own ticket, never mixed in (Mike, Nov 5)
            tickets = [_slice_ticket([g for g in games_d if g["league"] not in OWN_TICKET], names, cfg),
                       _slice_ticket([g for g in games_d if g["league"] in OWN_TICKET], names, cfg, CUP)]
        tickets = [t for t in tickets if t]
        ticket, second = (tickets + [None, None])[:2]
        overs = shot_overs(shots_by_slice.get(d, []), tuple(cfg.get("over_p", [0.35, 0.8])), int(cfg.get("overs", 6)))
        if ticket is None and not overs and not packs.get(d):
            continue                 # a slice with nothing to show shows nothing, not an empty slate
        kicks = ([g["commence_time"] for g in games_d] + [o["commence_time"] for o in overs]
                 + [pk["commence_time"] for pk in packs.get(d, [])])
        out.append({**names, "sport": "soccer", "lines_only": not overs, "kickoff": min(kicks),
                    "n_games": len(games_d), "plus": ticket, "plus_short": second, "overs": overs, "side_note": SIDE_NOTE,
                    "packs": packs.get(d, []),
                    "sgps": sgp_plus.pack_own_slips(packs.get(d, []), "soccer")})      # shown for watched games (Nov 7)
    return out


def _slice_ticket(games: list[dict], names: dict, cfg: dict, cup: str | None = None) -> dict | None:
    """One slice's ticket from these matches, the likeliest-to-move ones first."""
    pool = sorted(games, key=lambda g: -max(m["lift"] for m in g["minis"]))[: int(cfg["pool_games"])]
    pool.sort(key=lambda g: g["commence_time"])
    # two matches (the cups' 12:45 slot) reach about +340 at best: their own floor (Mike, Oct 14)
    tcfg = cfg | {"band": cfg["band_two_games"]} if len(pool) == 2 and cfg.get("band_two_games") else cfg
    label = f"{names['label']} ({cup})" if cup else names["label"]
    ticket = _ticket(pool, names["slate"], label, tcfg) if pool else None
    return ticket | {"cup": cup} if ticket and cup else ticket


def _ticket(pool: list[dict], sid: str, label: str, cfg: dict) -> dict | None:
    """sgp_plus.ticket with the goals legs' stand-in prices, then the page's view: FanDuel's
    price only where the feed has one, no 'legs multiply to', and a soccer 'why'."""
    work = [g | {"minis": [m | {"legs": [l | {"price": l["_price"]} for l in m["legs"]]} for m in g["minis"]]}
            for g in pool]
    ticket = sgp_plus.ticket(work, sid, label, cfg)
    if not ticket:
        return None
    real = {(m["sgp_id"], l["label"]): l["price"] for g in pool for m in g["minis"] for l in m["legs"]}
    for g in ticket["games"]:
        g["legs"] = [{k: v for k, v in l.items() if k != "_price"} | {"price": real[(g["sgp_id"], l["label"])]}
                     for l in g["legs"]]
    ticket["legs"] = [l for g in ticket["games"] for l in g["legs"]]
    ticket["naive_price"] = None
    leagues = sorted({g["league"] for g in pool if g["event_id"] in {x["event_id"] for x in ticket["games"]}})
    n_shots = sum(1 for l in ticket["legs"] if l.get("stat") in SHOT_WORDS)
    if ticket["n_games"] == 1:               # a prime-time match's own parlay (prime_minis)
        ticket |= {"sport": "soccer", "why": (
            f"{ticket['games'][0]['matchup']}, {ticket['n_legs']} legs, priced together on one score grid fit to "
            f"Pinnacle's no-vig result and goals prices, so the legs move together as the market implies: "
            f"{ticket['p_fair']:.1%}, fair {ticket['fair_price']:+d}. FanDuel's goals prices aren't in the odds feed, "
            f"so type its quote to see the EV.")}
        return ticket
    ticket |= {"sport": "soccer", "why": (
        f"{ticket['n_games']} matches ({', '.join(leagues)}), {ticket['n_legs']} legs. Each match's chances come from "
        f"one score grid fit to Pinnacle's no-vig result and goals prices, so a winner and goals move together as the "
        f"market implies; matches don't affect each other, so the ticket's chance is their product: "
        f"{ticket['p_fair']:.1%}, fair {ticket['fair_price']:+d}. "
        + (f"{n_shots} shot leg{'s' * (n_shots != 1)} at the market's fair chance (BetRivers' shot ladder, else "
           f"FanDuel's with its margin off), each where our shots model agrees; a shot leg is its match's only leg. "
           if n_shots else "")
        + "FanDuel's goals prices aren't in the odds feed, so type its SGP+ quote to see the EV.")}
    return ticket
