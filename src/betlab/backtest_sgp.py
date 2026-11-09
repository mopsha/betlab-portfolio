"""Does the fun-parlay simulator get the joint right? (`betlab backtest sgp`)

The Fun tab prices a same-game parlay in two parts: the market sets each leg's chance,
and the game simulator (models/game_sim_nfl.py) decides how the legs move together.
This backtest checks the second part, walk-forward, on games the simulator never saw
(inputs from earlier games only, as `betlab backtest props` builds them):

1. **Pairs by role, 2023-25.** For a pair of legs in the same game (a QB and his top
   target, the two QBs, a running back and the other team's QB...), how strongly do they
   move together in the simulator, and in real games? "Together" is measured on each
   stat's rank within its own simulated distribution (its PIT), so the test doesn't
   depend on the simulator's averages being right. Then the payoff number: when both
   legs are 70% legs, how much more often do both hit than if they were independent
   (the "lift"), simulated vs real, and the tail lift for two 25% legs. The game's
   lines are legs too (role "GAME": the total, and a team's margin for moneyline and
   spread legs), graded on the final score.
2. **Four-leg slips, 2023-25.** Typical stacks with 70% legs: the simulator's chance
   that all four hit, against how often they did.
3. **Anytime TDs, 2023-25.** The simulator's chance of 1+ TD for every prop-worthy
   player, against what happened, by chance bucket and position; team TD totals.
4. **Against real lines, 2025.** For every pair of FanDuel main lines in a game
   (different players), with the market's no-vig chances as each leg's chance: does the
   simulator's joint predict the four outcomes (both over, over-under, ...) better than
   treating the legs as independent? Log loss, with game-bootstrap standard errors.
"""

from __future__ import annotations

import time
import zlib
from itertools import combinations

import numpy as np
import pandas as pd

from betlab import backtest_props as BP
from betlab.models import game_sim_nfl as G
from betlab.models import props_nfl as P
from betlab.models import roles_nfl as R

Q = 0.3  # a leg over the simulator's 30th percentile: a 70% leg (the builder uses 55-80%)

# (key, label, (role, stat), (role, stat), "same" team or "opp"osite teams)
PAIRS = [
    ("qb_t1", "QB passing yds + his top target's yds", ("QB", "passing_yards"), ("T1", "receiving_yards"), "same"),
    ("qb_t2", "QB passing yds + his No. 2 target's yds", ("QB", "passing_yards"), ("T2", "receiving_yards"), "same"),
    ("qb_t1rec", "QB passing yds + his top target's catches", ("QB", "passing_yards"), ("T1", "receptions"), "same"),
    ("t1_t2", "Top two targets' yds, same team", ("T1", "receiving_yards"), ("T2", "receiving_yards"), "same"),
    ("qb_rb", "QB passing yds + his RB's rushing yds", ("QB", "passing_yards"), ("RB1", "rushing_yards"), "same"),
    ("rb_t1", "RB rushing yds + top target's yds, same team", ("RB1", "rushing_yards"), ("T1", "receiving_yards"), "same"),
    ("qb_qb", "Both QBs' passing yds (shootout)", ("QB", "passing_yards"), ("QB", "passing_yards"), "opp"),
    ("t1_t1", "Both teams' top targets' yds", ("T1", "receiving_yards"), ("T1", "receiving_yards"), "opp"),
    ("rb_oqb", "RB rushing yds + the other QB's passing yds", ("RB1", "rushing_yards"), ("QB", "passing_yards"), "opp"),
    ("rb_orb", "Both teams' RB rushing yds", ("RB1", "rushing_yards"), ("RB1", "rushing_yards"), "opp"),
    ("t1td_qb", "Top target scores + his QB's passing yds", ("T1", "tds"), ("QB", "passing_yards"), "same"),
    ("rbtd_t1td", "RB scores + top target scores, same team", ("RB1", "tds"), ("T1", "tds"), "same"),
    ("rbtd_qb", "RB scores + his QB's passing yds", ("RB1", "tds"), ("QB", "passing_yards"), "same"),
    # Game lines as legs (added Sep 26, tested Sep 28): the "GAME" role's stats are the game's
    # total points and the team's margin (moneyline and spread legs hit on it).
    ("tot_qb", "Game total + a QB's passing yds", ("GAME", "total"), ("QB", "passing_yards"), "same"),
    ("tot_t1", "Game total + a top target's yds", ("GAME", "total"), ("T1", "receiving_yards"), "same"),
    ("tot_rb", "Game total + an RB's rushing yds", ("GAME", "total"), ("RB1", "rushing_yards"), "same"),
    ("tot_t1td", "Game total + a top target scores", ("GAME", "total"), ("T1", "tds"), "same"),
    ("tot_rbtd", "Game total + an RB scores", ("GAME", "total"), ("RB1", "tds"), "same"),
    ("win_qb", "Team wins big + its QB's passing yds", ("GAME", "margin"), ("QB", "passing_yards"), "same"),
    ("win_t1", "Team wins big + its top target's yds", ("GAME", "margin"), ("T1", "receiving_yards"), "same"),
    ("win_rb", "Team wins big + its RB's rushing yds", ("GAME", "margin"), ("RB1", "rushing_yards"), "same"),
    ("win_rbtd", "Team wins big + its RB scores", ("GAME", "margin"), ("RB1", "tds"), "same"),
    ("win_oqb", "Team wins big + the other QB's passing yds", ("GAME", "margin"), ("QB", "passing_yards"), "opp"),
]
Q_TAIL = 0.75  # both legs over the 75th percentile: a 25% rung, like the long-shot slips
# Four-leg slips: (label, [(side, role, stat)]) where side is "a" (each team in turn) or "b" (its opponent)
SLIPS = [
    ("Shootout: both QBs + both top targets", [("a", "QB", "passing_yards"), ("a", "T1", "receiving_yards"),
                                                ("b", "QB", "passing_yards"), ("b", "T1", "receiving_yards")]),
    ("One team: QB + top two targets + RB", [("a", "QB", "passing_yards"), ("a", "T1", "receiving_yards"),
                                            ("a", "T2", "receiving_yards"), ("a", "RB1", "rushing_yards")]),
    ("Spread out: both top targets + both RBs", [("a", "T1", "receiving_yards"), ("b", "T1", "receiving_yards"),
                                                 ("a", "RB1", "rushing_yards"), ("b", "RB1", "rushing_yards")]),
]


def pit_draws(d: np.ndarray, rng) -> np.ndarray:
    """Each draw's rank in its own distribution, spread uniformly over ties (so a stat
    with many zeros, like TDs, still gives uniform ranks)."""
    s = np.sort(d)
    lo = np.searchsorted(s, d, "left") / len(d)
    hi = np.searchsorted(s, d, "right") / len(d)
    return lo + rng.random(len(d)) * (hi - lo)


def pit_value(d: np.ndarray, y: float, v: float) -> float:
    """Where the real result fell in the simulated distribution (ties spread by v in [0, 1))."""
    return float(np.mean(d < y) + v * np.mean(d == y))


def roles(sim: G.GameSim, team: str) -> dict:
    """The team's QB (the simulated starter), top two targets and lead RB, by pregame shares."""
    pl = sim.players[sim.players["team"] == team]
    out = {}
    qb = pl[pl["is_qb"]]
    out["QB"] = qb["player_id"].iloc[0] if len(qb) else None
    rec = pl[pl["position"] != "QB"].sort_values("t_share", ascending=False)
    out["T1"] = rec["player_id"].iloc[0] if len(rec) > 0 else None
    out["T2"] = rec["player_id"].iloc[1] if len(rec) > 1 else None
    rb = pl[pl["position"] == "RB"].sort_values("c_share", ascending=False)
    out["RB1"] = rb["player_id"].iloc[0] if len(rb) else None
    return out


def _actual(row, stat: str) -> float:
    return float(row["receiving_tds"] + row["rushing_tds"]) if stat == "tds" else float(row[stat])


def run(test_seasons=(2023, 2024, 2025), n: int = 2000, max_games: int | None = None,
        hist: R.History | None = None, rp: R.RoleParams | None = None,
        sp: G.SimParams | None = None) -> dict[str, pd.DataFrame]:
    """Simulate every regular-season game walk-forward; returns {"pairs", "slips", "tds", "teams"}.
    sp: simulator settings to test (default: the live ones)."""
    rp = rp or R.RoleParams()
    hist = hist or BP.load(min(test_seasons) - 2, max(test_seasons))
    games = hist.df[hist.df["season"].isin(test_seasons)].drop_duplicates("game_id")
    games = games[games["game_id"].str.contains(r"_\d\d_") & (games["week"] <= 18)].sort_values("date")
    if max_games:
        games = games.head(max_games)
    p = sp.props if sp else P.PropParams()
    sp = sp or G.SimParams(props=p)
    pairs, slips, tds, teams = [], [], [], []
    t0 = time.time()
    for gi, gm in enumerate(games.itertuples()):
        if pd.isna(gm.spread_line) or pd.isna(gm.total_line):
            continue
        g = hist.by_game[gm.game_id]
        home, away, before = gm.home_team, gm.away_team, gm.date
        inputs, worthy = {}, {}
        for team, opp in ((home, away), (away, home)):
            played = g[(g["team"] == team) & ((g["offense_pct"].fillna(0) > 0) | (g["targets"] + g["carries"]
                                                                                 + g["attempts"] > 0))]
            roster = played.rename(columns={"player_display_name": "name"})[["player_id", "name", "position"]]
            out = BP._regulars_out(hist, team, before, set(played["player_id"]))
            exp_margin = gm.spread_line if team == home else -gm.spread_line
            inputs[team] = R.team_inputs(hist, team, opp, before, roster, exp_margin, gm.total_line, rp, p, out, sp)
            for pid in played["player_id"]:
                worthy[pid] = BP._worthy(hist.player(pid, before))
        sim = G.simulate_teams(inputs, home, away, gm.spread_line, gm.total_line, sp, n=n, seed=gi)
        if sim.players.empty:
            continue
        rng = np.random.default_rng(100_000 + gi)
        actual = g.drop_duplicates("player_id").set_index("player_id")
        cache: dict = {}

        def leg(pid, stat):
            if pid is None:
                return None
            if (pid, stat) not in cache:
                if pid.startswith("game:"):
                    return None  # no final score for this game
                d = sim.get(pid, stat)
                cache[(pid, stat)] = None if d is None or pid not in actual.index else \
                    (pit_draws(d, rng), pit_value(d, _actual(actual.loc[pid], stat), rng.random()))
            return cache[(pid, stat)]

        role = {t: {**roles(sim, t), "GAME": f"game:{t}"} for t in (home, away)}
        other = {home: away, away: home}
        real_pts = {home: getattr(gm, "home_pts", np.nan), away: getattr(gm, "away_pts", np.nan)}
        for t in (home, away):  # the game's lines as legs: total points, and this team's margin
            o = other[t]
            if pd.isna(real_pts[t]) or pd.isna(real_pts[o]):
                continue
            for stat, d, y in (("total", sim.points[t] + sim.points[o], real_pts[t] + real_pts[o]),
                               ("margin", sim.points[t] - sim.points[o], real_pts[t] - real_pts[o])):
                cache[(f"game:{t}", stat)] = (pit_draws(d, rng), pit_value(d, float(y), rng.random()))
        base = {"game_id": gm.game_id, "season": gm.season, "week": gm.week}
        for key, _, (ra, sa), (rb, sb), side in PAIRS:
            symmetric = side == "opp" and (ra, sa) == (rb, sb)
            for ta in ((home,) if symmetric else (home, away)):
                tb = ta if side == "same" else other[ta]
                A, B = leg(role[ta].get(ra), sa), leg(role[tb].get(rb), sb)
                if A is None or B is None or role[ta].get(ra) == role[tb].get(rb):
                    continue
                (da, ua), (db, ub) = A, B
                pairs.append({**base, "pair": key, "sim_rho": float(np.corrcoef(da, db)[0, 1]),
                              "sim_joint": float(np.mean((da > Q) & (db > Q))),
                              "sim_joint_tail": float(np.mean((da > Q_TAIL) & (db > Q_TAIL))), "ua": ua, "ub": ub})
        for label, legs in SLIPS:
            for ta in (home, away):
                got = [leg(role[ta if s == "a" else other[ta]].get(r), st) for s, r, st in legs]
                ids = [role[ta if s == "a" else other[ta]].get(r) for s, r, _ in legs]
                if any(x is None for x in got) or len(set(ids)) < len(ids):
                    continue
                sim_all = np.all(np.vstack([x[0] for x in got]) > Q, axis=0).mean()
                slips.append({**base, "slip": label, "sim_all": float(sim_all),
                              "hit": float(all(x[1] > Q for x in got)), "legs_hit": sum(x[1] > Q for x in got),
                              **{f"leg{i}": float(x[1] > Q) for i, x in enumerate(got)}})
        for pid, stats in worthy.items():
            d = sim.get(pid, "tds")
            if "tds" not in stats or d is None or pid not in actual.index:
                continue
            a = actual.loc[pid]
            tds.append({**base, "player_id": pid, "position": a["position"], "team": a["team"],
                        "p_td": float(np.mean(d >= 1)), "td": float(_actual(a, "tds") >= 1)})
        for team in (home, away):
            t = g[g["team"] == team]
            teams.append({**base, "team": team, "sim_points": float(sim.points[team].mean()),
                          "sim_tds": float(sp.td_per_point * sim.points[team].mean()),
                          "tds": float(t["passing_tds"].sum() if "passing_tds" in t else 0) + float(t["rushing_tds"].sum()),
                          "points": float(getattr(gm, "home_pts" if team == home else "away_pts", np.nan))})
        if gi % 100 == 99:
            print(f"  {gi + 1} games, {time.time() - t0:.0f}s")
    return {"pairs": pd.DataFrame(pairs), "slips": pd.DataFrame(slips), "tds": pd.DataFrame(tds),
            "teams": pd.DataFrame(teams)}


def _boot(df: pd.DataFrame, stat, reps: int = 300, seed: int = 0) -> float:
    """Game-bootstrap standard error of stat(df)."""
    rng = np.random.default_rng(seed)
    ids = df["game_id"].unique()
    by = {g: x for g, x in df.groupby("game_id")}
    vals = []
    for _ in range(reps):
        pick = rng.choice(ids, len(ids))
        vals.append(stat(pd.concat([by[g] for g in pick])))
    return float(np.std(vals))


def _lift(x: pd.DataFrame, q: float = Q) -> float:
    a, b = x["ua"] > q, x["ub"] > q
    return float((a & b).mean() / (a.mean() * b.mean()))


def _tail_lift(x: pd.DataFrame) -> float:
    return _lift(x, Q_TAIL)


def report(res: dict[str, pd.DataFrame], boot: int = 200) -> dict[str, pd.DataFrame]:
    """Tables: pairs (simulated vs real co-movement and lift), slips, TD calibration."""
    pr = res["pairs"]
    labels = {k: lbl for k, lbl, *_ in PAIRS}
    rows = []
    for key, x in pr.groupby("pair", sort=False):
        rho = lambda d: float(np.corrcoef(d["ua"], d["ub"])[0, 1])
        rows.append({"pair": labels[key], "n": len(x), "sim_together": round(x["sim_rho"].mean(), 3),
                     "real_together": round(rho(x), 3), "se": round(_boot(x, rho, boot), 3),
                     "sim_lift": round(x["sim_joint"].mean() / (1 - Q) ** 2, 3),
                     "real_lift": round(_lift(x), 3), "lift_se": round(_boot(x, _lift, boot), 3),
                     **({"sim_tail_lift": round(x["sim_joint_tail"].mean() / (1 - Q_TAIL) ** 2, 3),
                         "real_tail_lift": round(_tail_lift(x), 3), "tail_se": round(_boot(x, _tail_lift, boot), 3)}
                        if "sim_joint_tail" in x else {}),
                     "leg_hit_rate": round(float(((x["ua"] > Q).mean() + (x["ub"] > Q).mean()) / 2), 3)})
    pairs = pd.DataFrame(rows)
    sl = res["slips"]
    # lift: how much more often all four hit than independent legs would, each against its own legs
    slip_lift = lambda x: float(x["hit"].mean() / np.prod([x[f"leg{i}"].mean() for i in range(4)]))
    slips = pd.DataFrame([{"slip": k, "n": len(x), "sim_all_4": round(x["sim_all"].mean(), 3),
                           "if_independent": round((1 - Q) ** 4, 3), "real_all_4": round(x["hit"].mean(), 3),
                           "real_leg_rate": round(x["legs_hit"].mean() / 4, 3),
                           "sim_lift": round(x["sim_all"].mean() / (1 - Q) ** 4, 2),
                           "real_lift": round(slip_lift(x), 2), "lift_se": round(_boot(x, slip_lift, boot), 2)}
                          for k, x in sl.groupby("slip", sort=False)])
    td = res["tds"]
    bins = pd.cut(td["p_td"], [0, .1, .2, .3, .4, .5, .6, 1])
    td_bins = td.groupby(bins, observed=True).agg(n=("td", "size"), sim=("p_td", "mean"), real=("td", "mean")).round(3)
    td_pos = td.groupby("position").agg(n=("td", "size"), sim=("p_td", "mean"), real=("td", "mean")).round(3)
    tm = res["teams"]
    teams = {"team_games": len(tm), "sim_tds": round(tm["sim_tds"].mean(), 2), "real_offensive_tds": round(tm["tds"].mean(), 2)}
    return {"pairs": pairs, "slips": slips, "td_bins": td_bins, "td_pos": td_pos, "teams": teams}


# ---------------------------------------------------------------- against real 2025 lines
def _kind(a: dict, b: dict) -> str:
    rec = {"receiving_yards", "receptions"}
    s = {a["stat"], b["stat"]}
    if a["team"] == b["team"]:
        if "passing_yards" in s and s & rec:
            return "QB + his receiver"
        if s <= rec:
            return "two receivers, same team"
        if "rushing_yards" in s:
            return "rusher + a teammate"
        return "other, same team"
    if s == {"passing_yards"}:
        return "both QBs"
    if s <= rec:
        return "receivers on opposite teams"
    if "rushing_yards" in s:
        return "rusher + the other team"
    return "passer + the other team's receiver"


def market_pairs(lines: pd.DataFrame, hist: R.History | None = None, n: int = 4000,
                 sp: G.SimParams | None = None) -> pd.DataFrame:
    """Every pair of FanDuel main lines in a 2025 game (different players), with the
    market's chances (no-vig, corrected for the over lean) as the legs' chances: the four
    outcome probabilities under independence and under the simulator's joint, and what
    happened. One row per pair."""
    from betlab import props_market as PM

    rows = []
    for gid, _, _, game_rows in BP.market_games(lines, hist, n=n, sp=sp):
        rng = np.random.default_rng(zlib.crc32(str(gid).encode()))
        legs = [{**r, "u": pit_draws(r["draws"], rng), "p": float(np.clip(PM.over_shift(r["p_market"], r["stat"]), .02, .98))}
                for r in game_rows]
        for a, b in combinations(legs, 2):
            if a["player_id"] == b["player_id"]:
                continue
            both = float(np.mean((a["u"] > 1 - a["p"]) & (b["u"] > 1 - b["p"])))
            both = float(np.clip(both, max(0.0, a["p"] + b["p"] - 1) + 1e-4, min(a["p"], b["p"]) - 1e-4))
            sim = {"oo": both, "ou": a["p"] - both, "uo": b["p"] - both, "uu": 1 - a["p"] - b["p"] + both}
            ind = {"oo": a["p"] * b["p"], "ou": a["p"] * (1 - b["p"]), "uo": (1 - a["p"]) * b["p"],
                   "uu": (1 - a["p"]) * (1 - b["p"])}
            cell = ("o" if a["over"] else "u") + ("o" if b["over"] else "u")
            rows.append({"game_id": gid, "kind": _kind(a, b), "cell": cell, "p_both_sim": sim["oo"],
                         "p_both_ind": ind["oo"], "both": float(cell == "oo"),
                         "ll_sim": -np.log(max(sim[cell], 1e-6)), "ll_ind": -np.log(max(ind[cell], 1e-6))})
    return pd.DataFrame(rows)


def market_report(mp: pd.DataFrame, boot: int = 200) -> pd.DataFrame:
    """Per kind of pair: log loss of the four outcomes, simulator's joint vs independent
    legs (positive gain = the simulator's joint is better), with a game-bootstrap SE, and
    how often both went over vs each prediction."""
    rows = []
    for kind, x in list(mp.groupby("kind")) + [("all pairs", mp)]:
        gain = lambda d: float((d["ll_ind"] - d["ll_sim"]).mean())
        rows.append({"pairs": kind, "n": len(x), "games": x["game_id"].nunique(),
                     "gain_per_pair": round(gain(x), 4), "se": round(_boot(x, gain, boot), 4),
                     "both_over_real": round(x["both"].mean(), 3), "both_over_sim": round(x["p_both_sim"].mean(), 3),
                     "both_over_if_independent": round(x["p_both_ind"].mean(), 3)})
    return pd.DataFrame(rows)
