"""College basketball in the fun bucket: one lines-only SGP+ ticket per tip slice (to-do c-sgp-ncaab, Oct 12),
the college football ticket's rules (cards/fun_ncaaf.py) with basketball's numbers.

New York bans college player props, so the legs are each game's moneyline, spread and total, never a game
involving a New York school or played in New York (a game whose venue we can't confirm is skipped too).

- **Prices:** before `leagues.ncaab.paid_odds_from` (Oct 26 since Oct 15, so never in a game week; was Mar 1) the lines are ESPN's free
  DraftKings numbers, so the legs are DraftKings' prices and their fair chance is DraftKings' own no-vig price
  (there's no sharp book in that feed): type FanDuel's quote for the real EV. From Mar 1, FanDuel's prices
  against the sharp books, as everywhere else.
- **How lines move together** (checked Oct 12 on 27,364 D-I games with closing lines, 2022-26): the favorite
  covering and the over are close to independent, even slightly against each other, under a 15-point spread
  (lift 0.92-0.99 in both halves of the history), and move together only for 20+ point favorites (1.08 and
  1.10). So each game is drawn from real past games with a similar spread (`draws`): the favorite's margin
  and the total relative to the market, the total's spread rescaled to this game's total (15 points of SD at
  a 125 total, 18 at 165). A side and the total go in together only when they move together (pair_lift).
- **The ticket:** each game's best minis, then the slice's ticket from 3-4 games inside the payout band
  (sgp_plus.ticket). Slices: afternoon, evening, late (sgp_plus.SLICES).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from betlab import config, ny_rules, sgp, sgp_plus
from betlab.cards import fun_ncaaf as F
from betlab.sources import cbbd

NEIGHBOURS = 3.0          # past games within this many points of spread
SD_TOTAL = (5.7, 0.075)   # SD of the total around the line: 5.7 + 0.075 x total (125 -> 15.1, 165 -> 18.1)


def residuals(games: pd.DataFrame, before_season: int) -> pd.DataFrame:
    """Past D-I games with closing lines: |spread|, total line, the favorite's margin minus the spread and
    the total minus the line (spread_line is the home team's expected margin)."""
    g = games[(games["season"] < before_season)].dropna(subset=["spread_line", "total_line", "home_pts", "away_pts"])
    g = g[g["spread_line"].abs() > 0]
    fav_margin = np.where(g["spread_line"] > 0, g["margin"], -g["margin"])
    return pd.DataFrame({"abs_sp": g["spread_line"].abs().to_numpy(), "total_line": g["total_line"].to_numpy(),
                         "m_res": fav_margin - g["spread_line"].abs().to_numpy(),
                         "t_res": (g["total"] - g["total_line"]).to_numpy()})


def draws(res: pd.DataFrame, spread_home: float, total: float, n: int = 4000, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """(home points, away points) for n versions of a game with the market's home margin and total."""
    s = abs(spread_home)
    near = res[(res["abs_sp"] - s).abs() <= NEIGHBOURS]
    if len(near) < 300:
        near = res.iloc[(res["abs_sp"] - s).abs().argsort()[:600]]
    rng = np.random.default_rng(seed)
    pick = near.iloc[rng.integers(0, len(near), n)]
    sd = lambda t: SD_TOTAL[0] + SD_TOTAL[1] * t
    fav_margin = s + pick["m_res"].to_numpy()
    tot = total + pick["t_res"].to_numpy() * sd(total) / sd(pick["total_line"].to_numpy())
    home_margin = fav_margin if spread_home >= 0 else -fav_margin
    return (tot + home_margin) / 2, (tot - home_margin) / 2


def build(pick_snap: pd.DataFrame | None, asof: pd.Timestamp, cfg: dict, data=None) -> list[dict]:
    """The Fun tab's college basketball slates: one lines-only SGP+ ticket per tip slice. data: (finished
    games, schedule, feed name -> CBBD name) for tests; read from the saved history otherwise."""
    from betlab.cards.ncaab import _game_row

    if pick_snap is None or pick_snap.empty:
        return []
    snap = pick_snap[pd.to_datetime(pick_snap["commence_time"], utc=True, format="ISO8601") > asof]
    if snap.empty:
        return []
    book = "fanduel" if (snap["bookmaker"] == "fanduel").any() else "draftkings"
    sharp = config.settings()["odds_api"]["sharp_books"] if book == "fanduel" else ["draftkings"]
    if data is None:
        feed = sorted(set(snap["home_team"]) | set(snap["away_team"]))
        data = (cbbd.games(), cbbd.schedule(), cbbd.team_names(feed_names=feed))
    games, sched, names = data
    res = residuals(games, cbbd.current_season(pd.Timestamp(asof).tz_convert("America/New_York")))
    days: dict[str, list[dict]] = {}
    packs: dict[str, list[dict]] = {}
    for i, (event_id, ev) in enumerate(snap.groupby("event_id", sort=False)):
        first = ev.iloc[0]
        home_name, away_name = first["home_team"], first["away_team"]
        home, away = names.get(home_name), names.get(away_name)
        if home is None or away is None:
            continue
        row = _game_row(sched, home, away, first["commence_time"])
        state = row.get("state") if row is not None else None
        if row is None or not isinstance(state, str) or not state:
            continue                                   # can't confirm where: never priced
        if not ny_rules.allowed("ncaab", home, away, venue_state=state)[0]:
            continue
        center = F._center(ev, home_name)
        if center is None:
            continue
        hp, ap = draws(res, center[0], center[1], seed=i)
        sim = SimpleNamespace(points={home: hp, away: ap})
        w = np.full(len(hp), 1 / len(hp))
        legs = sgp.game_line_legs(ev, sim, w, home_name, away_name, home, away, sharp, target=book)
        when = pd.Timestamp(first["commence_time"])
        key = "|".join(sgp_plus.slice_of(when, "ncaab"))
        base = {"event_id": str(event_id), "matchup": f"{away_name} @ {home_name}",
                "commence_time": str(first["commence_time"]), "game_ref": str(row["game_id"])}
        packs.setdefault(key, []).append({**base, "sport": "ncaab", **sgp.leg_pack(legs, w, seed=i)})
        pieces = F.minis(legs, w, cfg, str(event_id))
        if pieces:
            days.setdefault(key, []).append({**base, "minis": pieces})
    note = ("DraftKings' prices from ESPN's free lines until Mar 1: type FanDuel's quote for the real EV."
            if book == "draftkings" else "")
    out = []
    for d in sorted(set(days) | set(packs)):
        names_d = sgp_plus.slice_names("ncaab", *d.split("|"), len(packs.get(d) or days[d]))
        base = {**names_d, "sport": "ncaab", "lines_only": True, "book": book, "overs": [], "packs": packs.get(d, [])}
        if d not in days:
            out.append(base | {"kickoff": min(g["commence_time"] for g in packs[d]), "n_games": len(packs[d]), "plus": None,
                               "sgps": sgp_plus.pack_own_slips(packs[d], "ncaab")})
            continue
        games_d = sorted(days[d], key=lambda g: -max(m["leg_value"] for m in g["minis"]))[: int(cfg["pool_games"])]
        games_d.sort(key=lambda g: g["commence_time"])
        ticket = sgp_plus.ticket(games_d, names_d["slate"], names_d["label"], cfg)
        if ticket:
            why = ticket["why"].replace("priced from our simulation of that game (legs anchored to the market)",
                                        "priced at the market, moving together as similar past college games did")
            ticket |= {"sport": "ncaab", "why": (why + " " + note).strip()}
        out.append(base | {"kickoff": min(g["commence_time"] for g in days[d]), "n_games": len(days[d]), "plus": ticket,
                           "sgps": sgp_plus.pack_own_slips(packs.get(d, []), "ncaab")})      # shown for watched games (Nov 7)
    return out
