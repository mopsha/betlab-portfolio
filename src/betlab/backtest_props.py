"""Walk-forward backtest of the NFL props models (`betlab backtest props`).

For every regular-season game in the test seasons, using only earlier games:
- **Who plays:** the skill players who took an offensive snap. That matches what's
  known before kickoff once inactives are out.
- **Who's missing:** regulars (50%+ of snaps in either of the team's last two games)
  who didn't play. Their targets and carries go to teammates, as the injury report
  does live.
- **The game:** both teams simulated together (2,000 draws) around nflverse's closing
  spread and total.
- **Scoring:** each prop-worthy player's receptions, receiving yards, rushing yards,
  passing yards and anytime TD against what happened. A player who played but
  recorded nothing counts as zero; that sample bias skewed the old backtest.

Prop-worthy is decided without either model, from the player's last 4 games:
2.5+ targets a game (receiving), 5+ carries (rushing), 15+ pass attempts (passing).

Scores, for each stat and model version:
- **CRPS:** the whole-distribution error in the stat's own units; lower is better. It
  judges the tails too, which matters for alt ladders.
- **Bias:** mean projection minus mean actual.
- **Log loss at a naive line:** the player's median over his last 6 games, + 0.5. Real
  prop lines come with the 2025 backfill.
- **Calibration at alt-ladder rungs** (e.g. 60+ receiving yards) and **PIT deciles**
  (10% each when the whole distribution is right).
"""

from __future__ import annotations

import time
from dataclasses import replace

import numpy as np
import pandas as pd

from betlab.models import game_sim_nfl as G
from betlab.models import props_nfl as P
from betlab.models import roles_nfl as R
from betlab.sources import nflverse

RUNGS = {
    "receptions": [2.5, 3.5, 4.5, 5.5, 6.5],
    "receiving_yards": [29.5, 49.5, 69.5, 89.5, 109.5],
    "rushing_yards": [29.5, 49.5, 69.5, 89.5, 109.5],
    "passing_yards": [174.5, 199.5, 224.5, 249.5, 274.5, 299.5],
    "tds": [0.5],
}
VERSIONS = {
    "v0.1": R.RoleParams(use_snaps=False, use_matchup=False, robust_volume=False),
    "v0.2": R.RoleParams(),
}


def load(first_season: int, last_season: int) -> R.History:
    """Player-games (with snaps and zero-stat games) for the seasons, as a History."""
    seasons = range(first_season, last_season + 1)
    ps = nflverse.load_player_stats(seasons)
    snaps = nflverse.load_snap_counts(seasons)
    games = nflverse.load_games()
    df = R.prepare(ps, games[games["season"].between(first_season, last_season)], snaps)
    hist = R.History(df)
    hist.by_game = {g: x for g, x in df.groupby("game_id", sort=False)}
    return hist


def crps(x: np.ndarray, y: float) -> float:
    """Continuous ranked probability score from draws: E|X - y| - E|X - X'| / 2."""
    x = np.sort(x)
    n = len(x)
    spread = 2.0 / (n * n) * np.dot(2 * np.arange(1, n + 1) - n - 1, x)
    return float(np.mean(np.abs(x - y)) - 0.5 * spread)


def _worthy(h: pd.DataFrame) -> set[str]:
    last = h.tail(4)
    out = set()
    if len(last) and last["targets"].mean() >= 2.5:
        out |= {"receptions", "receiving_yards"}
    if len(last) and last["carries"].mean() >= 5:
        out.add("rushing_yards")
    if len(last) and last["attempts"].mean() >= 15:
        out.add("passing_yards")
    if out:
        out.add("tds")
    return out


def _regulars_out(hist: R.History, team: str, before, playing: set[str]) -> frozenset:
    th = hist.team(team, before).tail(2)
    ids = set()
    for gid in th["game_id"]:
        g = hist.by_game.get(gid)
        if g is not None:
            ids |= set(g.loc[(g["team"] == team) & (g["offense_pct"] >= 0.5), "player_id"])
    return frozenset(ids - playing)


def run(test_seasons=(2023, 2024, 2025), versions=None, n: int = 2000, max_games: int | None = None,
        hist: R.History | None = None) -> pd.DataFrame:
    """One row per (game, player, stat, version) with the scores' inputs."""
    versions = versions or VERSIONS
    hist = hist or load(min(test_seasons) - 2, max(test_seasons))
    games = hist.df[hist.df["season"].isin(test_seasons)].drop_duplicates("game_id")
    games = games[games["game_id"].str.contains(r"_\d\d_") & (games["week"] <= 18)].sort_values("date")
    if max_games:
        games = games.head(max_games)
    rows, t0 = [], time.time()
    for gi, gm in enumerate(games.itertuples()):
        g = hist.by_game[gm.game_id]
        home, away, before = gm.home_team, gm.away_team, gm.date
        if pd.isna(gm.spread_line) or pd.isna(gm.total_line):
            continue
        rosters, outs, worthy = {}, {}, {}
        for team in (home, away):
            played = g[(g["team"] == team) & ((g["offense_pct"].fillna(0) > 0) | (g["targets"] + g["carries"]
                                                                                 + g["attempts"] > 0))]
            rosters[team] = played.rename(columns={"player_display_name": "name"})[["player_id", "name", "position"]]
            outs[team] = _regulars_out(hist, team, before, set(played["player_id"]))
            for pid in played["player_id"]:
                worthy[pid] = _worthy(hist.player(pid, before))
        if not any(worthy.values()):
            continue
        actual = g.set_index("player_id")
        for vname, spec in versions.items():
            # A version is RoleParams, or (RoleParams, PropParams overrides, SimParams overrides).
            rp, p_over, sp_over = spec if isinstance(spec, tuple) else (spec, {}, {})
            p = replace(P.PropParams(), **p_over)
            sp = replace(G.SimParams(props=p), **sp_over)
            inputs = {}
            for team, opp in ((home, away), (away, home)):
                exp_margin = gm.spread_line if team == home else -gm.spread_line
                inputs[team] = R.team_inputs(hist, team, opp, before, rosters[team], exp_margin, gm.total_line,
                                             rp, p, outs[team], sp)
            sim = G.simulate_teams(inputs, home, away, gm.spread_line, gm.total_line, sp, n=n, seed=gi)
            for pid, stats in worthy.items():
                a = actual.loc[pid]
                a = a.iloc[0] if isinstance(a, pd.DataFrame) else a
                recent = hist.player(pid, before).tail(6)
                for stat in stats:
                    d = sim.get(pid, stat)
                    if d is None:
                        continue
                    y = float(a["receiving_tds"] + a["rushing_tds"]) if stat == "tds" else float(a[stat])
                    col = "receiving_tds" if stat == "tds" else stat
                    base = (recent["receiving_tds"] + recent["rushing_tds"]) if stat == "tds" else recent[col]
                    line = 0.5 if stat == "tds" else float(np.floor(base.median()) + 0.5)
                    row = {"version": vname, "season": gm.season, "week": gm.week, "game_id": gm.game_id,
                           "player_id": pid, "position": a["position"], "stat": stat, "mean": float(d.mean()),
                           "actual": y, "crps": crps(d, y), "line": line,
                           "p_over": float(np.mean(d > line)), "y_over": float(y > line),
                           "pit": float(np.mean(d < y) + np.random.default_rng(gi).random() * np.mean(d == y))}
                    for rung in RUNGS[stat]:
                        row[f"p{rung}"] = float(np.mean(d > rung))
                        row[f"y{rung}"] = float(y > rung)
                    rows.append(row)
        if gi % 100 == 99:
            print(f"  {gi + 1} games, {time.time() - t0:.0f}s")
    return pd.DataFrame(rows)


def _logloss(p, y):
    p = np.clip(p, 0.01, 0.99)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def report(res: pd.DataFrame) -> dict:
    """Summary tables: scores by stat and version, rung calibration, PIT tails."""
    summary = res.groupby(["stat", "version"]).apply(lambda g: pd.Series({
        "n": len(g), "bias": g["mean"].mean() - g["actual"].mean(), "crps": g["crps"].mean(),
        "logloss_line": _logloss(g["p_over"], g["y_over"]),
        "pit_low10": float(np.mean(g["pit"] < 0.1)), "pit_high10": float(np.mean(g["pit"] > 0.9)),
    }), include_groups=False).round(4)
    rungs = []
    for (stat, version), g in res.groupby(["stat", "version"]):
        for rung in RUNGS[stat]:
            if f"p{rung}" in g:
                rungs.append({"stat": stat, "version": version, "rung": rung + 0.5,
                              "predicted": g[f"p{rung}"].mean(), "actual": g[f"y{rung}"].mean(),
                              "logloss": _logloss(g[f"p{rung}"], g[f"y{rung}"])})
    return {"summary": summary, "rungs": pd.DataFrame(rungs).round(4)}


# ---------------------------------------------------------------- against the market

def market_eval(lines: pd.DataFrame, hist: R.History | None = None, rp: R.RoleParams | None = None,
                n: int = 4000, sharp_books=("pinnacle", "lowvig", "betonlineag")) -> pd.DataFrame:
    """Our model vs the market on real prop lines (backfill_props snapshots).

    For every FanDuel two-way main line: the market's no-vig chance of the over
    (Pinnacle, else the median of the other books, moved to FanDuel's line with our
    simulator's shape), our model's chance from the same pregame simulation the
    backtest uses, FanDuel's prices, and what happened. One row per line.
    """
    rows = []
    for *_, game_rows in market_games(lines, hist, rp, n, sharp_books):
        rows += [{k: v for k, v in r.items() if k != "draws"} for r in game_rows]
    return pd.DataFrame(rows)


def market_games(lines: pd.DataFrame, hist: R.History | None = None, rp: R.RoleParams | None = None,
                 n: int = 4000, sharp_books=("pinnacle", "lowvig", "betonlineag"), sp: G.SimParams | None = None):
    """market_eval one game at a time: yields (game_id, game row, sim, rows), where rows
    are market_eval's rows for that game plus "draws" (the simulated stat), so the
    parlay backtest (backtest_sgp) can test how lines move together."""
    from betlab import players
    from betlab import props_market as PM

    rp = rp or R.RoleParams()
    seasons = sorted(lines["game_id"].str[:4].astype(int).unique())
    hist = hist or load(min(seasons) - 2, max(seasons))
    p = sp.props if sp else P.PropParams()
    sp = sp or G.SimParams(props=p)
    for gi, (gid, ev) in enumerate(lines.groupby("game_id", sort=False)):
        rows = []
        g = hist.by_game.get(gid)
        if g is None:
            continue
        gm = g.iloc[0]
        home, away, before = gm["home_team"], gm["away_team"], gm["date"]
        inputs, played_all = {}, []
        for team, opp in ((home, away), (away, home)):
            played = g[(g["team"] == team) & ((g["offense_pct"].fillna(0) > 0) | (g["targets"] + g["carries"]
                                                                                 + g["attempts"] > 0))]
            played_all.append(played)
            roster = played.rename(columns={"player_display_name": "name"})[["player_id", "name", "position"]]
            out = _regulars_out(hist, team, before, set(played["player_id"]))
            exp_margin = gm["spread_line"] if team == home else -gm["spread_line"]
            inputs[team] = R.team_inputs(hist, team, opp, before, roster, exp_margin, gm["total_line"], rp, p, out, sp)
        sim = G.simulate_teams(inputs, home, away, gm["spread_line"], gm["total_line"], sp, n=n, seed=gi)
        played = pd.concat(played_all)
        roster = pd.DataFrame({"gsis_id": played["player_id"], "full_name": played["player_display_name"],
                               "football_name": None})
        ids, _ = players.match(ev["player"].dropna().unique(), roster)
        ref = PM.reference_quotes(ev, list(sharp_books))
        fd = PM.fanduel_main(ev)
        actual = played.drop_duplicates("player_id").set_index("player_id")
        for r in fd.itertuples():
            pid = ids.get(r.player)
            d = sim.get(pid, r.stat) if pid else None
            q = ref[(ref["player"] == r.player) & (ref["stat"] == r.stat)]
            if d is None or q.empty or pid not in actual.index:
                continue
            p_market = float(np.median([PM.translate(x.p_over, x.point, r.point, d) for x in q.itertuples()]))
            y = float(actual.loc[pid, r.stat])
            if y == r.point:
                continue  # a push
            rows.append({"game_id": gid, "week": int(gm["week"]), "team": actual.loc[pid, "team"],
                         "player": r.player, "player_id": pid, "stat": r.stat,
                         "line": r.point, "fd_over": r.over, "fd_under": r.under, "source": q["source"].iloc[0],
                         "p_market": p_market, "p_model": float(np.mean(d > r.point)), "over": float(y > r.point),
                         "draws": d})
        yield gid, gm, sim, rows


def market_report(m: pd.DataFrame, min_ev: float = 0.05) -> dict:
    """Does the model add anything to the market? Log loss by stat for the market, the
    model and the best blend (with its fitted weight), and what betting FanDuel would
    have returned when the market alone, or the blend, showed min_ev or more."""
    from betlab import edge
    from betlab import odds_math as om

    out = []
    for stat, g in list(m.groupby("stat")) + [("all", m)]:
        w = edge.fit_blend_weight(g["p_model"], g["p_market"], g["over"])
        blend = edge.blend_prob(g["p_model"], g["p_market"], w)
        out.append({"stat": stat, "n": len(g), "market": edge.log_loss(g["p_market"], g["over"]),
                    "model": edge.log_loss(g["p_model"], g["over"]), "blend": edge.log_loss(blend, g["over"]),
                    "w_model": w, "gap": float(np.mean(np.abs(g["p_model"] - g["p_market"])))})
    bets = []
    for name, p in (("market only", m["p_market"]),
                    ("blend w=0.2", edge.blend_prob(m["p_model"], m["p_market"], 0.2)),
                    ("model only", m["p_model"])):
        for side, price_col, win in (("over", "fd_over", m["over"] == 1), ("under", "fd_under", m["over"] == 0)):
            pw = p if side == "over" else 1 - p
            ev = np.array([om.expected_value(a, b) for a, b in zip(pw, m[price_col])])
            take = ev >= min_ev
            dec = m[price_col].map(om.american_to_decimal)
            profit = np.where(win, dec - 1, -1.0)[take]
            bets.append({"probability": name, "side": side, "bets": int(take.sum()),
                         "units": round(float(profit.sum()), 1),
                         "roi": round(float(profit.mean()), 3) if take.any() else None})
    return {"logloss": pd.DataFrame(out).round(4), "bets": pd.DataFrame(bets)}


PASS_GAME = ("receptions", "receiving_yards", "passing_yards")


def _logit_offset(y: np.ndarray, X: np.ndarray, offset: np.ndarray, iters: int = 25) -> np.ndarray:
    """Logistic regression with a fixed offset (the market's log-odds), by Newton steps."""
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        mu = 1 / (1 + np.exp(-(offset + X @ b)))
        H = X.T @ (X * (mu * (1 - mu))[:, None])
        b = b + np.linalg.solve(H, X.T @ (y - mu))
    return b


def script_eval(m: pd.DataFrame, tg: pd.DataFrame | None = None, qg: pd.DataFrame | None = None,
                who_and_weather: bool = True, boot: int = 400, seed: int = 0) -> dict:
    """Does the game script (models/game_nfl.py) add anything to the prop market?

    For every line from market_eval: the offense's pass/run matchup edge and projected
    dropbacks/rushes vs. its last 8 games (game_nfl.script_features, walk-forward
    ratings, the game script from nflverse's closing spread). Fits
    logit P(over) = logit(market, over-lean corrected) + a + b_matchup*edge + b_volume*volume
    per stat, with game-bootstrap standard errors for the pass-game fit, the fit in each
    half of the season, and how often the side the matchup favors hit.

    who_and_weather: the pass matchup includes who started at QB (`game_nfl.qb_adjust`)
    and the kickoff weather (`game_nfl.weather_effects`, from nflverse's recorded
    weather), as the Games tab does live.
    """
    from betlab import props_market as PM
    from betlab.models import game_nfl as GN

    games = nflverse.load_games().set_index("game_id")
    seasons = sorted(m["game_id"].str[:4].astype(int).unique())
    if tg is None or qg is None:
        pbp = nflverse.load_pbp(range(min(seasons) - 2, max(seasons) + 1))
        tg, qg = GN.team_games(pbp, games.reset_index()), GN.qb_games(pbp, games.reset_index())
    wx = nflverse.load_weather(seasons).set_index("game_id") if who_and_weather else None
    rows, ratings = [], {}
    for gid, g in m.groupby("game_id"):
        gm = games.loc[gid]
        if gm["date"] not in ratings:
            ratings[gm["date"]] = GN.fit_ratings(tg, gm["date"])
        r = ratings[gm["date"]]
        adjust = None
        if who_and_weather:
            qbr = GN.qb_ratings(qg, r, gm["date"])
            starters = qg[(qg["game_id"] == gid) & qg["starter"]].set_index("team")["passer_id"]
            w = wx.loc[gid] if gid in wx.index else None
            eff = GN.weather_effects(None if w is None else {
                "wind_mph": w["wind"], "precip_prob": float(bool(w["precip"])), "temp_f": w["temp"]})
            adjust = {t: {"pass_epa": GN.qb_adjust(qg, qbr, t, starters.get(t), gm["date"])["adj"]
                          + eff.get("pass_epa", 0.0), "neutral_pass": eff.get("neutral_pass", 0.0)}
                      for t in (gm["home_team"], gm["away_team"])}
        pr = GN.project(r, gm["home_team"], gm["away_team"], neutral=bool(gm["neutral"]),
                        market_margin_home=float(gm["spread_line"]), adjust=adjust)
        feats = {t: GN.script_features(r, tg, pr, t, o, gm["date"])
                 for t, o in ((gm["home_team"], gm["away_team"]), (gm["away_team"], gm["home_team"]))}
        for x in g.itertuples():
            f = feats.get(x.team)
            if f is None:
                continue
            rush = x.stat == "rushing_yards"
            rows.append({"game_id": gid, "week": x.week, "stat": x.stat, "over": x.over,
                         "player_id": x.player_id, "team": x.team, "line": x.line,
                         "p_mkt": PM.over_shift(x.p_market, x.stat), "fd_over": x.fd_over, "fd_under": x.fd_under,
                         "matchup": f["rush_epa" if rush else "pass_epa"],
                         "volume": f["rushes" if rush else "dropbacks"]})
    d = pd.DataFrame(rows)
    off = lambda g: np.log(g["p_mkt"].clip(0.02, 0.98) / (1 - g["p_mkt"].clip(0.02, 0.98))).to_numpy()
    X = lambda g: np.column_stack([np.ones(len(g)), g["matchup"], g["volume"]])
    fits = []
    for stat, g in list(d.groupby("stat")) + [("pass game", d[d["stat"].isin(PASS_GAME)])]:
        b = _logit_offset(g["over"].to_numpy(), X(g), off(g))
        fits.append({"stat": stat, "n": len(g), "const": b[0], "matchup": b[1], "volume": b[2]})
    p = d[d["stat"].isin(PASS_GAME)].set_index("game_id")
    ids = p.index.unique()
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(boot):
        s = p.loc[rng.choice(ids, len(ids))]
        bs.append(_logit_offset(s["over"].to_numpy(), X(s), off(s)))
    bs = np.array(bs)
    halves = []
    for lo, hi in ((1, 10), (11, 22)):
        s = p[p["week"].between(lo, hi)]
        b = _logit_offset(s["over"].to_numpy(), X(s), off(s))
        halves.append({"weeks": f"{lo}-{hi}", "n": len(s), "matchup": b[1], "volume": b[2]})
    k = p["matchup"].abs() >= 1
    over_side = p["matchup"] > 0
    hit = np.where(over_side, p["over"], 1 - p["over"])[k]
    mkt = np.where(over_side, p["p_mkt"], 1 - p["p_mkt"])[k]
    return {"fits": pd.DataFrame(fits).round(3),
            "bootstrap": {"matchup_se": float(bs[:, 1].std()), "volume_se": float(bs[:, 2].std()),
                          "matchup_positive": float((bs[:, 1] > 0).mean()),
                          "volume_positive": float((bs[:, 2] > 0).mean())},
            "halves": pd.DataFrame(halves).round(3),
            "strong_matchups": {"n": int(k.sum()), "hit": float(hit.mean()), "market": float(mkt.mean())},
            "lines": d}
