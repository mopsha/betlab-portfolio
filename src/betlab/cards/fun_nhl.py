"""NHL in the fun bucket: one SGP+ ticket per night, plus shots-on-goal overs to root for.

- **Where the chances come from:** the market, not our ratings (they lost to the close;
  docs/MODELS.md, "NHL"). For each game the two teams' expected goals are fit so our score
  grid (models/nhl.grid: 60-minute ties, overtime, empty-net goals, the shared scoring
  factor) reproduces the sharp book's no-vig moneyline and total. Every leg is read off that
  one grid of final scores, so how legs move together inside a game is consistent: a
  favorite winning by two goes with goals.
- **Legs:** a team to win, the favorite -1.5, the underdog +1.5, over FanDuel's total (it posts one number, no alternates).
  No unders: every leg is something to cheer for. FanDuel's price is shown where the feed
  has that exact bet.
- **The ticket:** each game offers "minis" (one leg, or two legs that move together), and
  the night's ticket takes 2-4 games whose product lands in the payout band
  (sgp_plus.ticket). Never mixed with other sports.
- **Overs to root for:** FanDuel's shots-on-goal overs against the other books' no-vig
  price at the same number (from the props pull, 1 credit a game), best value first.
  Straight fun-bucket bets, never picks.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
from scipy import optimize

from betlab import config, sgp, sgp_plus
from betlab import odds_math as om
from betlab.cards import nhl as card
from betlab.cards.preview_nhl import load_params
from betlab.market import two_way
from betlab.models import nhl as M
from betlab.sources import nhl as src

ET = "America/New_York"
SOG = "player_shots_on_goal"
SHOTS_SIZE = 21.0       # shots' negative binomial size (models/props_nhl, 2020-26): moves other books' numbers to FanDuel's
CHEER = {("moneyline", False): 1.10, ("goals", True): 1.05, ("puck line", False): 1.05, ("puck line", True): 0.90}
SIDE_NOTE = {"title": "Shots to root for",
             "text": ("Shots-on-goal overs from the fun bucket, never picks. EV is FanDuel's price against the other books' "
                      "no-vig chance at the same number. Every shot on net is something to cheer for.")}


def fit_goals(p_home: float, p_over: float, line: float, p: M.Params) -> tuple[float, float, float]:
    """(home xG, away xG, max error) whose grid gives the market's win and over chances."""
    logit = lambda q: np.log(np.clip(q, 1e-4, 1 - 1e-4) / (1 - np.clip(q, 1e-4, 1 - 1e-4)))

    def chances(x):
        g = M.grid(np.exp(x[0]), np.exp(x[1]), p)
        over, push = M.p_over(g, line)
        return g["p_home"], over / max(1 - push, 1e-6)

    def loss(x):
        h, o = chances(x)
        return (logit(h) - logit(p_home)) ** 2 + (logit(o) - logit(p_over)) ** 2

    res = optimize.minimize(loss, np.log([3.1, 2.9]), method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-10})
    h, o = chances(res.x)
    return float(np.exp(res.x[0])), float(np.exp(res.x[1])), float(max(abs(h - p_home), abs(o - p_over)))


def legs(final: np.ndarray, home: str, away: str, fd: dict) -> list[dict]:
    """Every leg for one game: label, stat, cells of the final-score grid where it hits, p,
    and FanDuel's price when the feed has that bet."""
    i, j = np.indices(final.shape)
    fav, dog = (home, away) if final[i > j].sum() >= 0.5 else (away, home)
    fav_home = fav == home
    out = [{"label": f"{home} to win", "team": home, "stat": "moneyline", "side": "yes", "point": 0.0, "cells": i > j,
            "price": fd.get(("ml", home))},
           {"label": f"{away} to win", "team": away, "stat": "moneyline", "side": "yes", "point": 0.0, "cells": i < j,
            "price": fd.get(("ml", away))},
           {"label": f"{fav} -1.5", "team": fav, "stat": "puck line", "side": "yes", "point": -1.5,
            "cells": (i - j >= 2) if fav_home else (j - i >= 2), "price": fd.get(("pl", fav, -1.5))},
           {"label": f"{dog} +1.5", "team": dog, "stat": "puck line", "side": "yes", "point": 1.5,
            "cells": (j - i <= 1) if fav_home else (i - j <= 1), "price": fd.get(("pl", dog, 1.5))}]
    # FanDuel posts one NHL total per game and no alternates (Mike, Sep 30): only its number
    out += [{"label": f"Over {line:g} goals", "team": None, "stat": "goals", "side": "over", "point": line,
             "cells": i + j > line, "price": fd[("total", line)]} for line in fanduel_totals(fd)]
    for leg in out:
        leg["p"] = float(final[leg["cells"]].sum())
    return out


def _leg_doc(leg: dict) -> dict:
    return {"label": leg["label"], "player": None, "team": leg["team"] or "", "stat": leg["stat"], "side": leg["side"],
            "point": leg["point"], "price": leg["price"], "p_fair": round(leg["p"], 4),
            "fair_price": sgp._american(leg["p"]),
            "source": "FanDuel price in the feed" if leg["price"] is not None else "no FanDuel price for this number",
            "p_model_raw": None, "p_read": None, "read": "", "questionable": None, "note": ""}


def minis(game_legs: list[dict], final: np.ndarray, cfg: dict, event_id: str) -> list[dict]:
    """A game's pieces: single legs in the leg band, and pairs that move together (joint over
    product at least pair_lift); a winner with goals first, then pairs, then single legs."""
    lo, hi = cfg["leg_p"]
    ok = [leg for leg in game_legs if lo <= leg["p"] <= hi]
    pieces = [([leg], leg["p"], 1.0) for leg in ok]
    for a_i, a in enumerate(ok):
        for b in ok[a_i + 1:]:
            if a["stat"] == b["stat"] or {a["stat"], b["stat"]} <= {"moneyline", "puck line"}:
                continue          # two totals, or a winner with a puck line: nearly one bet
            joint = float(final[a["cells"] & b["cells"]].sum())
            lift = joint / (a["p"] * b["p"])
            if lift >= cfg["pair_lift"] and joint >= cfg.get("pair_min_p", 0.3):
                pieces.append(([a, b], joint, lift))
    has_win = lambda ls: any(leg["stat"] == "moneyline" for leg in ls)
    pieces.sort(key=lambda x: (-(has_win(x[0]) and len(x[0]) > 1), -(len(x[0]) > 1), -x[2], -x[1]))
    # a leg in at most 2 of the game's pieces, so the ticket picks from real alternatives (sgp.pick's rule, Oct 19);
    # FanDuel's one total and +-1.5 puck lines mean no nudged rungs here, only the same leg reused
    kept, uses = [], {}
    for piece in pieces:
        if any(uses.get(leg["label"], 0) >= 2 for leg in piece[0]):
            continue
        kept.append(piece)
        for leg in piece[0]:
            uses[leg["label"]] = uses.get(leg["label"], 0) + 1
        if len(kept) == int(cfg["minis_per_game"]):
            break
    out = []
    for ls, p, lift in kept:
        key = event_id + "|" + "|".join(sorted(leg["label"] for leg in ls))
        docs = [_leg_doc(leg) for leg in ls]
        for d in docs:          # the ticket builder multiplies prices: missing ones stand in at fair
            d["_price"] = d["price"] if d["price"] is not None else d["fair_price"]
        # Something to cheer for (Mike): winners and goals over a +1.5 cushion, a winner with goals most.
        cheer = float(np.prod([CHEER.get((leg["stat"], leg["point"] > 0), 1.0) for leg in ls]))
        value = round(lift * cheer * (1.2 if has_win(ls) and len(ls) > 1 else 1.0), 3)
        out.append({"sgp_id": hashlib.sha1(key.encode()).hexdigest()[:12],
                    "theme": "Goals and a winner" if len(ls) > 1 else "One leg", "legs": docs, "n_legs": len(docs),
                    "p_fair": round(p, 4), "fair_price": sgp._american(p), "p_read": None, "naive_price": None,
                    "lift": round(lift, 3), "leg_value": value, "read_value": value})
    return out


def builder_pack(final: np.ndarray, home: str, away: str, fd: dict, props_ev: pd.DataFrame | None, seed: int = 0,
                 view: dict | None = None) -> dict:
    """Everything for the page's parlay builder in one game, from one joint simulation
    (models/joint_nhl.py): both moneylines, every puck line, FanDuel's total both ways (it posts no alternates), and
    FanDuel's shots and saves lines both ways, all moving together the way real games do (a
    goalie's saves with his team's win, a shooter's night with the game's goals, score effects).
    Fair chances stay the market's: the grid is fit to the sharp moneyline and total, props to
    the other books' no-vig; the simulation only says how legs move together. view: the NHL
    view's game (projected shots, the props model's expected shots) when it's built."""
    from betlab.cards.props_nhl import MARKETS, _consensus, _mean_for
    from betlab.models import joint_nhl as J
    from betlab.sources.nhl import _plain

    k = np.arange(final.shape[0])
    goals_mean = (float((final.sum(axis=1) * k).sum()), float((final.sum(axis=0) * k).sum()))
    teams = {t["team"]: t for t in (view or {}).get("teams", [])}
    shots_proj = (float(teams.get(home, {}).get("shots") or 30.0), float(teams.get(away, {}).get("shots") or 30.0))
    model_mean = {(_plain(x["player"]), x["stat"]): x for x in (view or {}).get("props", [])}
    props = []
    if props_ev is not None and len(props_ev):
        for (market, player), g in props_ev[props_ev["market"].isin(MARKETS)].groupby(["market", "player"]):
            fdp = g[g["bookmaker"] == "fanduel"]
            o, u = fdp[fdp["outcome"] == "Over"], fdp[fdp["outcome"] == "Under"]
            if o.empty:
                continue
            stat, point = MARKETS[market], float(o["point"].iloc[0])
            size = 29.0 if stat == "saves" else SHOTS_SIZE
            p_over, _ = _consensus(g, point, size)
            if p_over is None:
                continue
            mm = model_mean.get((_plain(player), stat))
            team = (mm or {}).get("team")
            props.append({"player": player, "stat": stat, "point": point, "p_over": p_over, "team": team,
                          "over": float(o["price"].iloc[0]), "under": float(u["price"].iloc[0]) if len(u) else None,
                          "mean": (mm or {}).get("model_mean") or _mean_for(p_over, point, size)})
    shooters = [{"key": f"{x['player']}|{x['stat']}", "side": "home" if x["team"] == home else "away", "mean": x["mean"]}
                for x in props if x["stat"] == "shots" and x["team"] in (home, away)]
    sim = J.simulate(final, shots_proj, goals_mean, shooters, n=3000, seed=seed)
    gh, ga = sim["home_goals"], sim["away_goals"]
    legs = []
    for t, me, them in ((home, gh, ga), (away, ga, gh)):
        legs.append({"label": f"{t} to win", "team": t, "stat": "moneyline", "side": "yes", "point": 0.0,
                     "hit": me > them, "price": fd.get(("ml", t))})
        for pt in (-1.5, 1.5):
            legs.append({"label": f"{t} {pt:+g}", "team": t, "stat": "puck line", "side": "yes", "point": pt,
                         "hit": (me - them + pt) > 0, "price": fd.get(("pl", t, pt))})
    for line in fanduel_totals(fd):        # FanDuel's one total: it posts no NHL alternates
        legs.append({"label": f"Over {line:g} goals", "stat": "goals", "side": "over", "point": line,
                     "hit": gh + ga > line, "price": fd.get(("total", line))})
        legs.append({"label": f"Under {line:g} goals", "stat": "goals", "side": "under", "point": line,
                     "hit": gh + ga < line, "price": fd.get(("total_u", line))})
    i, j = np.indices(final.shape)          # the market's chance (the grid), not the draws' sampling noise
    exact = {}
    for t, me, them in ((home, i, j), (away, j, i)):
        exact[f"{t} to win"] = final[me > them].sum()
        for pt in (-1.5, 1.5):
            exact[f"{t} {pt:+g}"] = final[(me - them + pt) > 0].sum()
    for line in fanduel_totals(fd):
        exact[f"Over {line:g} goals"], exact[f"Under {line:g} goals"] = final[i + j > line].sum(), final[i + j < line].sum()
    for leg in legs:
        leg["p"] = float(exact[leg["label"]])
    for leg in legs:
        leg["source"] = "FanDuel price in the feed" if leg["price"] is not None else "fair price (FanDuel's isn't in the feed)"
    for x in props:
        if x["stat"] == "shots":
            draws = sim["players"].get(f"{x['player']}|{x['stat']}")
            joint = draws is not None
        else:                                   # saves: the starter's side from the model, else by name
            side = "home" if x["team"] == home else "away" if x["team"] == away else None
            draws = sim[f"{side}_saves"] if side else None
            joint = draws is not None
        if draws is None:                       # no team known: independent of the score, labeled
            draws = np.random.default_rng(seed + 7).random(len(gh))
            over_hit = draws < x["p_over"]
        else:
            over_hit = draws > x["point"]
        src = "other books' no-vig; moves with the game (joint model)" if joint else \
            "other books' no-vig; drawn independently of the score"
        for side, pr, pv, hit in (("over", x["over"], x["p_over"], over_hit), ("under", x["under"], 1 - x["p_over"], ~over_hit)):
            legs.append({"label": f"{x['player']} {side} {x['point']:g} {x['stat']}", "player": x["player"], "stat": x["stat"],
                         "side": side, "point": x["point"], "price": pr, "p": pv, "hit": hit, "source": src})
    return sgp.draws_pack(legs, seed=seed)


def fanduel_totals(fd: dict) -> list[float]:
    """The total(s) FanDuel posts for a game: one main number, no alternates in the app or the feed."""
    return sorted({k[1] for k in fd if k[0] == "total"})


def _views() -> dict:
    """The NHL view's games by matchup (exports/nhl.json, built earlier in the run): projected
    shots and the props model's expected shots and saves for the joint simulation."""
    import json

    path = config.EXPORTS_DIR / "nhl.json"
    if not path.exists():
        return {}
    try:
        return {g["matchup"]: g for g in json.loads(path.read_text(encoding="utf-8")).get("games", [])}
    except (ValueError, KeyError):
        return {}


def _fanduel(ev: pd.DataFrame, home_name: str, away_name: str, home: str, away: str) -> dict:
    """FanDuel's prices keyed like the legs: ("ml", team), ("pl", team, point), ("total", line)."""
    out = {}
    tw = two_way(ev, "h2h", "fanduel", home_name, away_name)
    if tw:
        out[("ml", home)], out[("ml", away)] = float(tw[0][1]), float(tw[1][1])
    tw = two_way(ev, "spreads", "fanduel", home_name, away_name)
    if tw:
        (pt_h, pr_h), (pt_a, pr_a) = tw
        out[("pl", home, float(pt_h))], out[("pl", away, float(pt_a))] = float(pr_h), float(pr_a)
    rows = ev[(ev["market"] == "totals") & (ev["bookmaker"] == "fanduel")]
    for r in rows.itertuples():
        out[("total" if r.outcome == "Over" else "total_u", float(r.point))] = float(r.price)
    return out


def sog_overs(props: pd.DataFrame | None, games: dict, cfg: dict) -> list[dict]:
    """FanDuel's shots-on-goal overs with a fair price from the other books at the same
    number (median no-vig), best EV first. games: {event_id: game info}."""
    if props is None or props.empty:
        return []
    lo, hi = cfg.get("over_p", [0.30, 0.80])
    sog = props[props["market"] == SOG]
    rows = []
    for (eid, player), g in sog.groupby(["event_id", "player"]):
        if eid not in games:
            continue
        fd = g[(g["bookmaker"] == "fanduel") & (g["outcome"] == "Over")]
        if fd.empty:
            continue
        point, price = float(fd["point"].iloc[0]), float(fd["price"].iloc[0])
        from betlab.cards.props_nhl import _consensus
        p, n_books = _consensus(g, point, SHOTS_SIZE)
        if p is None:
            continue
        fairs = [None] * n_books
        if not lo <= p <= hi:
            continue
        info = games[eid]
        label = f"{player} over {point:g} shots"
        rows.append({"sgp_id": "nhl-sog-" + hashlib.sha1(f"{eid}|{label}".encode()).hexdigest()[:10],
                     "kind": "over", "sport": "nhl", "label": label, "price": price, "p_fair": round(p, 4),
                     "fair_price": sgp._american(p), "ev": round(p * om.american_to_decimal(price) - 1, 4),
                     "ev_read": None, "matchup": info["matchup"], "event_id": str(eid),
                     "commence_time": info["commence_time"], "note": f"{len(fairs)} other book(s) at {point:g}",
                     "games": [{"matchup": info["matchup"], "event_id": str(eid), "game_ref": info["game_ref"],
                                "legs": [label]}]})
    rows.sort(key=lambda r: -r["ev"])
    return rows[: int(cfg.get("overs", 8))]


def build(snap: pd.DataFrame | None, props: pd.DataFrame | None, asof: pd.Timestamp, cfg: dict) -> list[dict]:
    """The Fun tab's NHL slates: one SGP+ ticket per kickoff slice (afternoon, evening, late:
    sgp_plus.SLICES, locked 15 minutes before the slice starts), plus shots overs."""
    if snap is None or snap.empty:
        return []
    horizon = pd.Timedelta(hours=float(cfg.get("horizon_hours", 36)))
    kick = pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601")
    snap = snap[(kick > asof) & (kick <= asof + horizon)]
    if snap.empty:
        return []
    p = load_params()
    codes = src.team_codes()
    sched = card._game_ids(asof)
    nights: dict[str, list[dict]] = {}
    packs: dict[str, list[dict]] = {}
    views = _views()
    infos: dict[str, dict] = {}
    for event_id, ev in snap.groupby("event_id", sort=False):
        home_name, away_name = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        home, away = src.code_for(home_name, codes) or home_name, src.code_for(away_name, codes) or away_name
        start = ev["commence_time"].iloc[0]
        info = {"matchup": f"{away} @ {home}", "commence_time": str(start),
                "game_ref": card._game_ref(sched, home, away, start)}
        infos[str(event_id)] = info
        p_home, _ = card._fair(ev, "h2h", home_name, away_name)
        # the sharp total nearest a hockey number, and its no-vig over
        tot = None
        for line in (6.5, 5.5, 6.0, 5.0, 7.0):
            po, _ = card._fair(ev, "totals", "Over", "Under", point_a=line)
            if po is not None:
                tot = (line, po)
                break
        if p_home is None or tot is None:
            continue
        lh, la, err = fit_goals(p_home, tot[1], tot[0], p)
        if err > cfg.get("max_fit_error", 0.03):
            continue
        final = M.grid(lh, la, p)["final"]
        fd = _fanduel(ev, home_name, away_name, home, away)
        night = "|".join(sgp_plus.slice_of(start, "nhl"))
        props_ev = props[props["event_id"] == event_id] if props is not None and len(props) else None
        packs.setdefault(night, []).append({"event_id": str(event_id), "matchup": info["matchup"],
                                            "commence_time": info["commence_time"], "game_ref": info["game_ref"],
                                            "sport": "nhl", **builder_pack(final, home, away, fd, props_ev, seed=len(infos),
                                                                           view=views.get(info["matchup"]))})
        pieces = minis(legs(final, home, away, fd), final, cfg, str(event_id))
        if not pieces:
            continue
        nights.setdefault(night, []).append({"event_id": str(event_id), "league": "nhl", **info,
                                             "xg": [round(lh, 2), round(la, 2)], "minis": pieces})
    overs = sog_overs(props, infos, cfg)
    out = []
    slice_key = lambda o: "|".join(sgp_plus.slice_of(o["commence_time"], "nhl"))
    for d in sorted(set(nights) | set(packs) | {slice_key(o) for o in overs}):
        pool = sorted(nights.get(d, []), key=lambda g: -max(m["lift"] for m in g["minis"]))[: int(cfg["pool_games"])]
        pool.sort(key=lambda g: g["commence_time"])
        night_overs = [o for o in overs if slice_key(o) == d]
        n_games = len({g["event_id"] for g in nights.get(d, []) + packs.get(d, [])} | {o["event_id"] for o in night_overs})
        names = sgp_plus.slice_names("nhl", *d.split("|"), n_games)
        sid, label = names["slate"], names["label"]
        # two games reach a lower top than four: their own floor, as soccer's (Mike, Nov 7: the afternoon slice locked
        # with no ticket when FanDuel's only total moved and the pair's best was +265)
        tcfg = cfg | {"band": cfg["band_two_games"]} if len(pool) == 2 and cfg.get("band_two_games") else cfg
        ticket = _ticket(pool, sid, label, tcfg) if len(pool) >= int(cfg["min_games"]) else None
        if ticket is None and not night_overs and not packs.get(d):
            continue
        kicks = [g["commence_time"] for g in nights.get(d, []) + packs.get(d, [])] + [o["commence_time"] for o in night_overs]
        out.append({**names, "sport": "nhl", "kickoff": min(kicks), "n_games": n_games,
                    "plus": ticket, "overs": night_overs, "side_note": SIDE_NOTE, "packs": packs.get(d, []),
                    "sgps": sgp_plus.pack_own_slips(packs.get(d, []), "nhl")})      # shown for watched games (Nov 7)
    return out


def _ticket(pool: list[dict], sid: str, label: str, cfg: dict) -> dict | None:
    """sgp_plus.ticket with stand-in prices for legs FanDuel's feed lacks, then the page's view."""
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
    ticket |= {"sport": "nhl", "why": (
        f"{ticket['n_games']} games, {ticket['n_legs']} legs. Each game's chances come from our score grid fit to the "
        f"sharp book's no-vig moneyline and total (ties, overtime and empty-net goals included), so a winner and "
        f"goals move together; games don't affect each other, so the ticket's chance is their product: "
        f"{ticket['p_fair']:.1%}, fair {ticket['fair_price']:+d}. Type FanDuel's SGP+ quote to see the EV.")}
    return ticket
