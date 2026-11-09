"""The market's fair prices for player props, and anchoring the game simulator to them.

BetLab's rule: the market sets each player's center and, where other books publish
alt ladders, his tails; our model supplies how players move together. The market's
no-vig over prices run high for receptions and receiving yards (overs hit 44-46% in
2025 when priced ~49-50%), so those are shifted toward the under (over_shift). Steps:

1. fair quotes: no-vig probabilities from two-way lines (over/under, TD yes/no).
   Pinnacle, LowVig or BetOnline if they have the player; otherwise every other
   book's no-vig price, and we take the median.
2. calibrate: nudge the simulator's usage (target and carry shares) toward the
   market, then rescale each player's yards so P(over FanDuel's line) matches the
   market exactly (ranks are kept, so correlations survive).
3. tails: bend each player's yards (keeping the main line fixed) so our alt ladder
   matches the books' alt ladders (median fit across books). Our own tails were too fat for low-usage
   players (Jonnu Smith 30+ yards: model 24%, books about 10%).
4. rake: reweight the draws so receptions and TD probabilities match exactly too.
   Joint probabilities are then read from the weighted draws.

One-sided prices (alt ladders, FanDuel's anytime TD) have no clean no-vig price;
their fair value is read from the anchored draws, with the books' ladders
(each shrunk by that book's margin) as the tail target.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import odds_math as om
from betlab.models import game_sim_nfl as G

MAIN = {"player_receptions": "receptions", "player_reception_yds": "receiving_yards",
        "player_rush_yds": "rushing_yards", "player_pass_yds": "passing_yards"}
ALT = {f"{k}_alternate": v for k, v in MAIN.items()}
TD = {"player_anytime_td": "tds"}
STAT_OF = MAIN | ALT | TD
STAT_LABEL = {"receptions": "receptions", "receiving_yards": "receiving yds", "rushing_yards": "rushing yds",
              "passing_yards": "passing yds", "tds": "anytime TD"}


MAX_PRICE = 10_000   # beyond +/-10000 is no real market: Novig's props carry -99900 placeholders (Oct 23)


def _two_way(rows: pd.DataFrame, yes: str, no: str) -> list[tuple[str, float, float]]:
    """[(book, point, no-vig P(yes side))] for every book quoting both sides at the same point. A placeholder price
    (beyond MAX_PRICE) or a pair the de-vig can't solve is skipped: on Oct 23 one Novig -99900 quote raised in the
    de-vig and took down the whole NBA props card and its fun tickets."""
    out = []
    for (book, point), g in rows.groupby(["bookmaker", rows["point"].fillna(-1)], sort=False):
        a, b = g[g["outcome"] == yes], g[g["outcome"] == no]
        if len(a) and len(b):
            pa, pb = float(a["price"].iloc[0]), float(b["price"].iloc[0])
            if not (abs(pa) < MAX_PRICE and abs(pb) < MAX_PRICE):
                continue
            try:
                p_yes, _ = om.no_vig_two_way(pa, pb)
            except ValueError:
                continue
            out.append((book, float(point), p_yes))
    return out


NBA_MAIN = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists",
            "player_threes": "threes", "player_points_rebounds_assists": "pra", "player_points_rebounds": "pr",
            "player_points_assists": "pa", "player_rebounds_assists": "ra"}


def mine(target: str = "fanduel") -> set[str]:
    """Mike's books (odds_api.target_books) plus the target: never part of a consensus fair price, so neither
    of his books is the other's market (docs/DRAFTKINGS_PLAN.md rule 7, as market.reference_books)."""
    from betlab import config
    return set(config.settings()["odds_api"].get("target_books") or []) | {target}


def reference_quotes(snap: pd.DataFrame, sharp_books, target: str = "fanduel", main: dict | None = None) -> pd.DataFrame:
    """No-vig reference quotes per (player, stat): the first sharp book that has the player,
    else every other book but Mike's (mine). Columns: player, stat, book, point, p_over, source.
    main: the league's over/under markets ({market key: stat}; the NFL's by default)."""
    main = MAIN if main is None else main
    stat_of = STAT_OF if main is MAIN else main
    rows = []
    two_way = snap[snap["market"].isin(list(main) + (list(TD) if main is MAIN else []))]
    for (player, market), g in two_way.groupby(["player", "market"]):
        yes, no = ("Yes", "No") if market in TD else ("Over", "Under")
        quotes = _two_way(g, yes, no)
        sharp = [q for b in sharp_books for q in quotes if q[0] == b]
        if sharp:
            chosen, source = sharp[:1], sharp[0][0]
        else:
            chosen = [q for q in quotes if q[0] not in mine(target)]
            source = f"consensus of {len(chosen)} books"
        for book, point, p in chosen:
            rows.append({"player": player, "stat": stat_of[market], "book": book,
                         "point": None if market in TD else point, "p_over": p, "source": source})
    return pd.DataFrame(rows, columns=["player", "stat", "book", "point", "p_over", "source"])


def book_main(snap: pd.DataFrame, target: str = "fanduel", main: dict | None = None) -> pd.DataFrame:
    """A book's two-way main lines (FanDuel's by default): player, stat, point, over, under (main: the league's
    markets). A book that hangs two numbers for one player keeps the first."""
    main = MAIN if main is None else main
    fd = snap[(snap["bookmaker"] == target) & snap["market"].isin(list(main))]
    over = fd[fd["outcome"] == "Over"].drop_duplicates(["player", "market"]).set_index(["player", "market"])[["point", "price"]]
    under = fd[fd["outcome"] == "Under"]
    under = under.merge(over["point"].reset_index(), on=["player", "market", "point"])     # at the over's number
    under = under.drop_duplicates(["player", "market"]).set_index(["player", "market"])["price"]
    out = over.join(under.rename("under"), how="inner").rename(columns={"price": "over"}).reset_index()
    out["stat"] = out["market"].map(main)
    return out[["player", "stat", "point", "over", "under"]]


fanduel_main = book_main                  # the name before DraftKings (Oct 12)


def translate(p_over: float, from_point: float, to_point: float, draws: np.ndarray) -> float:
    """Move a no-vig P(over from_point) to to_point using the simulator's shape between the two."""
    if from_point == to_point:
        return p_over
    between = np.mean(draws <= to_point) - np.mean(draws <= from_point)
    return float(np.clip(p_over - between, 0.01, 0.99))


def poisson_mean_for(p_over: float, line: float) -> float:
    """The Poisson mean whose P(X > line) equals p_over (bisection)."""
    k = int(np.floor(line))

    def p_gt(lam: float) -> float:
        term, cdf = np.exp(-lam), 0.0
        for i in range(k + 1):
            cdf += term
            term *= lam / (i + 1)
        return 1 - cdf

    lo, hi = 0.01, 30.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if p_gt(mid) < p_over else (lo, mid)
    return (lo + hi) / 2


YARDS = ("receiving_yards", "rushing_yards", "passing_yards")


def calibrate(simulate, fair: pd.DataFrame, ids: dict[str, str], iters: int = 5, damp: float = 0.9):
    """Adjust usage toward the market before the exact steps (scale_yards, rake).

    simulate(adjust) -> GameSim. fair: rows of player, stat, point, p_over (fair_main).
    Receptions lines set each team's pass volume (the total the market expects its
    listed receivers to catch) and, relative to that, each receiver's target share.
    A receiver without a receptions line uses his yards line; a rushing line sets a
    carry share. Returns (sim, adjust).
    """
    adjust: dict = {}
    has_rec = set(fair.loc[fair["stat"] == "receptions", "player"])
    sim = simulate(adjust)
    for _ in range(iters):
        team_of = dict(zip(sim.players["player_id"], sim.players["team"]))
        want, got, t_ratio = {}, {}, {}
        for r in fair.itertuples():
            pid = ids.get(r.player)
            d = sim.get(pid, r.stat) if pid else None
            if d is None:
                continue
            if r.stat == "receptions":
                lam, mean = poisson_mean_for(r.p_over, r.point), max(float(np.mean(d)), 0.1)
                team = team_of[pid]
                want[team], got[team] = want.get(team, 0) + lam, got.get(team, 0) + mean
                t_ratio[pid] = lam / mean
            elif r.stat == "receiving_yards" and r.player not in has_rec:
                t_ratio[pid] = max(r.point, 1.0) / max(float(np.quantile(d, 1 - r.p_over)), 1.0)
            elif r.stat == "rushing_yards":
                key = ("c", pid)
                ratio = max(r.point, 1.0) / max(float(np.quantile(d, 1 - r.p_over)), 1.0)
                adjust[key] = float(np.clip(adjust.get(key, 1.0) * ratio ** damp, 0.2, 10.0))
        team_ratio = {t: want[t] / got[t] for t in want}
        for t, ratio in team_ratio.items():
            adjust[("vol", t)] = float(np.clip(adjust.get(("vol", t), 1.0) * ratio ** damp, 0.6, 1.6))
        for pid, ratio in t_ratio.items():
            rel = ratio / team_ratio.get(team_of[pid], 1.0)
            adjust[("t", pid)] = float(np.clip(adjust.get(("t", pid), 1.0) * rel ** damp, 0.2, 10.0))
        sim = simulate(adjust)
    return sim, adjust


def scale_yards(sim: G.GameSim, fair: pd.DataFrame, ids: dict[str, str]) -> None:
    """Rescale each player's yards so P(over FanDuel's line) equals the market's exactly.

    A multiplicative rescale keeps every draw's rank, so the correlations between
    players survive; the market sets the level, the simulator the shape.
    """
    for r in fair[fair["stat"].isin(YARDS)].itertuples():
        pid = ids.get(r.player)
        d = sim.get(pid, r.stat) if pid else None
        if d is None:
            continue
        q = float(np.quantile(d, 1 - r.p_over))
        if q > 0.5:
            sim.draws[(pid, r.stat)] = d * float(np.clip(r.point / q, 0.25, 4.0))


def over_shift(p_over: float, stat: str, shifts: dict | None = None) -> float:
    """Correct the market's lean toward overs (settings props.market_shift, log-odds)."""
    if shifts is None:
        from betlab import config
        shifts = (config.settings().get("props") or {}).get("market_shift") or {}
    b = shifts.get(stat, 0.0)
    if not b:
        return p_over
    p = float(np.clip(p_over, 1e-4, 1 - 1e-4))
    return float(1 / (1 + np.exp(-(np.log(p / (1 - p)) + b))))


def script_lean(p_over: float, stat: str, feats: dict, coef: dict | None = None) -> float:
    """The market's P(over) moved by the game script (settings preview.script_lean).

    Only pass-game props move: the offense's pass matchup edge and projected dropbacks
    (game_nfl.script_features) added to the market's log-odds. Fit on 2025 lines
    (`betlab backtest script`); rushing props showed no effect."""
    if coef is None:
        from betlab import config
        coef = (config.settings().get("preview") or {}).get("script_lean") or {}
    if stat not in coef.get("stats", []):
        return p_over
    p = float(np.clip(p_over, 1e-4, 1 - 1e-4))
    z = coef.get("matchup", 0.0) * feats["pass_epa"] + coef.get("volume", 0.0) * feats["dropbacks"]
    return float(1 / (1 + np.exp(-(np.log(p / (1 - p)) + z))))


def fair_main(sim: G.GameSim, snap: pd.DataFrame, ids: dict[str, str], sharp_books,
              shift: bool = True, target: str = "fanduel") -> pd.DataFrame:
    """The market's no-vig P(over) at a book's main lines (FanDuel's by default; and TD yes), translated to
    that book's point with the simulator's shape, and (with shift) corrected for the
    market's lean toward overs (over_shift). Columns: player, stat, point, p_over, source, moved (no reference
    quote at the book's exact number: the chance was moved along the simulator's shape, so the offer is a lean at
    most: docs/DRAFTKINGS_PLAN.md rule 1, both books, Mike, Oct 12)."""
    ref = reference_quotes(snap, sharp_books, target)
    rows = []
    for r in book_main(snap, target).itertuples():
        pid = ids.get(r.player)
        d = sim.get(pid, r.stat) if pid else None
        q = ref[(ref["player"] == r.player) & (ref["stat"] == r.stat)]
        if d is None or q.empty:
            continue
        p_fair = float(np.median([translate(x.p_over, x.point, r.point, d) for x in q.itertuples()]))
        rows.append({"player": r.player, "stat": r.stat, "point": r.point,
                     "p_over": over_shift(p_fair, r.stat) if shift else p_fair,
                     "source": q["source"].iloc[0], "moved": not bool((q["point"] == r.point).any())})
    for q in ref[ref["stat"] == "tds"].itertuples():
        pid = ids.get(q.player)
        if pid and sim.get(pid, "tds") is not None:
            rows.append({"player": q.player, "stat": "tds", "point": 0.5, "p_over": q.p_over, "source": q.source,
                         "moved": False})
    return pd.DataFrame(rows, columns=["player", "stat", "point", "p_over", "source", "moved"])


def rake(indicators: list[np.ndarray], targets: list[float], n: int, iters: int = 200, tol: float = 5e-4):
    """Weights over n draws (summing to 1) that hit each P(indicator) = target.

    Iterative proportional fitting on binary margins: the smallest reweighting (in
    the KL sense) that matches every market price. Returns (weights, max error).
    """
    w = np.full(n, 1.0 / n)
    err = 1.0
    for _ in range(iters):
        err = 0.0
        for ind, t in zip(indicators, targets):
            p = float(w[ind].sum())
            if 0 < p < 1:
                w[ind] *= t / p
                w[~ind] *= (1 - t) / (1 - p)
            err = max(err, abs(p - t))
        w /= w.sum()
        if err < tol:
            break
    return w, err


def effective_draws(w: np.ndarray) -> float:
    """How many equally weighted draws the weights are worth (1/sum w^2)."""
    return float(1.0 / np.sum(w ** 2))


# BetOnline's alt ladders run far fatter than every other book's (Jonnu Smith 28+
# yards at 31% vs DraftKings' 25+ at 20% on 2026-09-24), so they are left out.
LADDER_SKIP = ("betonlineag",)


def ladder_quotes(snap: pd.DataFrame, default_margin: float = 0.07) -> pd.DataFrame:
    """Every book's alt ladders (FanDuel's too) as approximate fair probabilities.

    Alt rungs are one-sided ("60+ yards" has no "under"), so each price is shrunk by
    that book's own margin on the player's main line (or 7% without one). Rungs at a
    book's price floor (the same price as the rung before, e.g. BetMGM's 100+ and 125+)
    and rungs outside 4-96% are dropped, and so are LADDER_SKIP books.
    Columns: player, stat, point, p_over, book.
    """
    rows = []
    margins = {}
    for (book, player, market), g in snap[snap["market"].isin(list(MAIN))].groupby(["bookmaker", "player", "market"]):
        o, u = g[g["outcome"] == "Over"], g[g["outcome"] == "Under"]
        if len(o) and len(u):
            margins[(book, player, MAIN[market])] = om.overround([o["price"].iloc[0], u["price"].iloc[0]])
    alt = snap[snap["market"].isin(list(ALT)) & (snap["outcome"] == "Over")
               & ~snap["bookmaker"].isin(LADDER_SKIP)]
    for (book, player, market), g in alt.groupby(["bookmaker", "player", "market"]):
        stat = ALT[market]
        m = margins.get((book, player, stat), default_margin)
        g = g.sort_values("point")
        floor = g["price"].eq(g["price"].shift())
        for r in g[~floor].itertuples():
            p = om.implied_prob(r.price) / (1 + m)
            if 0.04 <= p <= 0.96:
                rows.append({"player": player, "stat": stat, "point": float(r.point), "p_over": p, "book": book})
    return pd.DataFrame(rows, columns=["player", "stat", "point", "p_over", "book"])


def fit_tails(sim: G.GameSim, fair: pd.DataFrame, ladders: pd.DataFrame, ids: dict[str, str]) -> dict:
    """Bend each player's yards so our alt ladder matches the books' ladders.

    X -> line * (X / line) ** gamma keeps every draw's rank and keeps P(over the main
    line) exactly where the market put it; gamma > 1 fattens the tail, < 1 thins it.
    gamma is fitted to each book's ladder separately (logit error on a grid) and the
    median is used, so one book with odd ladders can't drag the fit. Returns
    {(player, stat): gamma} for the players it changed.
    """
    grid = np.round(np.arange(0.3, 2.01, 0.02), 2)
    fitted = {}
    for r in fair[fair["stat"].isin(YARDS)].itertuples():
        pid = ids.get(r.player)
        d = sim.get(pid, r.stat) if pid else None
        q = ladders[(ladders["player"] == r.player) & (ladders["stat"] == r.stat)]
        if d is None or q.empty or r.point <= 0:
            continue
        base = np.maximum(d, 0) / r.point
        curves = {g: r.point * base ** g for g in grid}
        gammas = []
        for _, b in q.groupby("book"):
            rungs, target = b["point"].to_numpy(), b["p_over"].to_numpy()
            best, best_err = 1.0, np.inf
            for g, x in curves.items():
                p = np.clip((x[None, :] > rungs[:, None]).mean(axis=1), 0.002, 0.998)
                err = float(np.sum((np.log(p / (1 - p)) - np.log(target / (1 - target))) ** 2))
                if err < best_err:
                    best, best_err = float(g), err
            gammas.append(best)
        gamma = float(np.median(gammas))
        sim.draws[(pid, r.stat)] = np.where(d > 0, r.point * base ** gamma, d)
        fitted[(r.player, r.stat)] = gamma
    return fitted


def rung_targets(snap: pd.DataFrame, ladders: pd.DataFrame, target: str = "fanduel",
                 min_books: int = 1) -> pd.DataFrame:
    """FanDuel's alt rungs that other books also quote at the same point, with their
    median fair chance. Columns: player, stat, point, p_over, source."""
    fd = snap[(snap["bookmaker"] == target) & snap["market"].isin(list(ALT)) & (snap["outcome"] == "Over")]
    others = ladders[ladders["book"] != target]
    rows = []
    for r in fd.itertuples():
        stat = ALT[r.market]
        same = others[(others["player"] == r.player) & (others["stat"] == stat) & (others["point"] == r.point)]
        if len(same) >= min_books:
            rows.append({"player": r.player, "stat": stat, "point": float(r.point),
                         "p_over": float(same["p_over"].median()), "source": ", ".join(sorted(same["book"]))})
    return pd.DataFrame(rows, columns=["player", "stat", "point", "p_over", "source"])


def anchor(simulate, snap: pd.DataFrame, ids: dict[str, str], sharp_books):
    """Anchor the simulator to the market: calibrate usage, rescale yards to the main
    lines, bend the tails to the books' alt ladders, then rake so every main line and
    Pinnacle TD price matches the market exactly.

    Returns (sim, weights, fair, rake error). fair has one row per anchored main line
    and TD (kind "main"), plus FanDuel rungs other books also quote (kind "rung"). The
    rungs are not raked: each book's one-sided margin is a guess, and forcing them
    alongside the main lines stopped the raking from converging. sgp uses them as a
    ceiling on a leg's chance instead.
    """
    sim = simulate({})
    fair = fair_main(sim, snap, ids, sharp_books)
    sim, _ = calibrate(simulate, fair, ids)
    fair = fair_main(sim, snap, ids, sharp_books)
    scale_yards(sim, fair, ids)
    ladders = ladder_quotes(snap)
    fit_tails(sim, fair, ladders, ids)
    indicators = [sim.get(ids[r.player], r.stat) > r.point for r in fair.itertuples()]
    w, err = rake(indicators, fair["p_over"].tolist(), sim.n)
    rungs = rung_targets(snap, ladders)
    keep = [ids.get(r.player) is not None and sim.get(ids[r.player], r.stat) is not None
            for r in rungs.itertuples()]
    fair = pd.concat([fair.assign(kind="main"), rungs[keep].assign(kind="rung")], ignore_index=True)
    return sim, w, fair, err
