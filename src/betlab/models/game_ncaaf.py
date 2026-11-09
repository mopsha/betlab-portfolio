"""How a college football game should go, and what the early-week market misses.

1. **Team-game stats** (`team_games`): CFBD's advanced game stats (`cfbd.advanced`) for
   every offense: plays, EPA (CFBD's PPA) and success rate, split by pass and run,
   explosiveness, line yards, stuff rate, pass rate, points.
2. **Unit ratings** (`fit_ratings`): the NFL engine's weighted ridge (stat = league + home
   edge + offense[team] + defense[opponent]) on games before the date, half-life 150
   days, ridge 3 (college has bigger talent gaps). `ranks` ranks FBS units only.
3. **Projection and words** (`project`, `matchups`): plays, pass/run, efficiency; the
   unit-vs-unit edges with ranks.
4. **The early read** (`early_features`, `early_read`): home-minus-away net ratings
   (success rate, EPA, stuff rate, line yards, and "points luck", points beyond what
   efficiency supports) and both offenses' combined EPA, plays and success. On 2022-25
   games (`betlab backtest cfb`), strong reads beat the **opening** total 55.3% of the
   time out of sample and moved the line their way by the close; against the closing
   line they're break-even. The market catches up during the week, so the read is only
   worth anything early. Tracked, not priced (rule 3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from betlab import config
from betlab.models.game_nfl import _ord, _ridge

STATS = {  # "higher" = good for the offense
    "epa": "higher", "success": "higher", "explosiveness": "higher", "pass_epa": "higher", "rush_epa": "higher",
    "pass_success": "higher", "rush_success": "higher", "line_yards": "higher", "stuff_rate": "lower",
    "points": "higher", "plays": None, "pass_rate": None,
}
EARLY_PATH = config.DATA_DIR / "models" / "ncaaf_early.json"
SIDE_FEATURES = ["net_success", "net_epa", "luck", "net_stuff_rate", "net_line_yards"]
TOTAL_FEATURES = ["sum_epa", "sum_plays", "sum_success"]


@dataclass
class Params:
    half_life_days: float = 150.0
    ridge: float = 3.0


@dataclass
class Ratings:
    date: pd.Timestamp
    league: dict
    home: dict
    off: pd.DataFrame
    dfn: pd.DataFrame
    fbs: set


def team_games(adv: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, offense): the advanced stats plus date, opponent, home (1 / -1 / 0
    at a neutral site) and points."""
    g = games[["game_id", "date", "home_team", "away_team", "home_pts", "away_pts", "neutral", "home_div", "away_div"]]
    t = adv.merge(g, on="game_id", how="inner")
    t["home"] = np.where(t["neutral"], 0.0, np.where(t["team"] == t["home_team"], 1.0, -1.0))
    t["points"] = np.where(t["team"] == t["home_team"], t["home_pts"], t["away_pts"])
    t["pass_rate"] = t["dropbacks"] / (t["dropbacks"] + t["rushes"])
    t["fbs"] = np.where(t["team"] == t["home_team"], t["home_div"], t["away_div"]) == "fbs"
    return t.sort_values(["date", "game_id"]).reset_index(drop=True)


def fit_ratings(tg: pd.DataFrame, date, p: Params | None = None) -> Ratings:
    """Unit ratings from team-games strictly before `date` (last 800 days)."""
    p = p or Params()
    date = pd.Timestamp(date)
    h = tg[(tg["date"] < date) & (tg["date"] >= date - pd.Timedelta(days=800))]
    teams = sorted(set(h["team"]) | set(h["opp"]))
    idx = {t: i for i, t in enumerate(teams)}
    w = 0.5 ** ((date - h["date"]).dt.days.to_numpy() / p.half_life_days)
    league, home, off, dfn = {}, {}, {}, {}
    for stat in STATS:
        y = h[stat].to_numpy(dtype=float)
        ok = np.isfinite(y)
        if ok.sum() < 50:
            continue
        mu, he, o, d = _ridge(y[ok], w[ok], h["team"].map(idx).to_numpy()[ok], h["opp"].map(idx).to_numpy()[ok],
                              h["home"].to_numpy()[ok], len(teams), p.ridge)
        league[stat], home[stat], off[stat], dfn[stat] = mu, he, o, d
    fbs = set(h.loc[h["fbs"], "team"])
    return Ratings(date, league, home, pd.DataFrame(off, index=teams), pd.DataFrame(dfn, index=teams), fbs)


def _u(r: Ratings, stat: str, team: str, opp: str, home: float) -> float:
    return (r.league.get(stat, np.nan) + r.home.get(stat, 0.0) * home
            + float(r.off[stat].get(team, 0.0)) + float(r.dfn[stat].get(opp, 0.0)))


def project(r: Ratings, home: str, away: str, neutral: bool = False) -> dict:
    """Each offense's expected plays, pass rate, efficiency and points against this defense."""
    sides = {}
    for team, opp, h in ((home, away, 0.0 if neutral else 1.0), (away, home, 0.0 if neutral else -1.0)):
        s = {k: _u(r, k, team, opp, h) for k in STATS if k in r.off}
        s["dropbacks"] = s["plays"] * s["pass_rate"]
        s["rushes"] = s["plays"] - s["dropbacks"]
        sides[team] = s
    return {"home": home, "away": away, "sides": sides,
            "home_points": sides[home]["points"], "away_points": sides[away]["points"],
            "margin": sides[home]["points"] - sides[away]["points"],
            "total": sides[home]["points"] + sides[away]["points"]}


def ranks(r: Ratings) -> pd.DataFrame:
    """FBS-only ranks (1 = best) for every rated offense and defense stat."""
    rows = {}
    fbs = [t for t in r.off.index if t in r.fbs]
    for stat, good in STATS.items():
        if stat not in r.off or good is None:
            continue
        hi = good == "higher"
        rows[f"off_{stat}"] = r.off.loc[fbs, stat].rank(ascending=not hi, method="min")
        rows[f"def_{stat}"] = r.dfn.loc[fbs, stat].rank(ascending=hi, method="min")
    return pd.DataFrame(rows)


UNIT_LABEL = {"pass_epa": ("passing game", "pass defense"), "rush_epa": ("running game", "run defense"),
              "success": ("offense (success rate)", "defense (success rate)"),
              "line_yards": ("offensive line (line yards)", "defensive front"),
              "explosiveness": ("big-play offense", "big-play defense")}


def matchups(r: Ratings, home: str, away: str, name=lambda t: t, n: int = 4) -> list[dict]:
    """The unit-vs-unit edges, biggest first (FBS ranks out of about 136)."""
    rk = ranks(r)
    out = []
    for team, opp in ((home, away), (away, home)):
        for stat, (ol, dl) in UNIT_LABEL.items():
            if stat not in r.off:
                continue
            spread = pd.concat([r.off[stat], r.dfn[stat]]).std()
            size = (float(r.off[stat].get(team, 0)) + float(r.dfn[stat].get(opp, 0))) / spread if spread else 0.0
            orank = int(rk[f"off_{stat}"].get(team, 0)) or None
            drank = int(rk[f"def_{stat}"].get(opp, 0)) or None
            txt = (f"{name(team)} {ol}" + (f" ({_ord(orank)})" if orank else "") + f" vs {name(opp)} {dl}"
                   + (f" ({_ord(drank)})" if drank else "") + f": edge {name(team) if size > 0 else name(opp)}")
            out.append({"offense": team, "defense": opp, "stat": stat, "size": round(size, 2), "text": txt})
    return sorted(out, key=lambda m: -abs(m["size"]))[:n]


def early_features(r: Ratings, home: str, away: str) -> dict:
    """Net (home minus away) and summed ratings the early read uses. Net = offense rating
    minus defense rating (defense ratings are 'allowed'); stuff rate flipped so higher is better."""
    f = {}
    for s in ("epa", "success", "stuff_rate", "line_yards", "points", "plays"):
        if s not in r.off:
            continue
        o, d = r.off[s], r.dfn[s]
        oh, oa, dh, da = (float(o.get(home, 0)), float(o.get(away, 0)), float(d.get(home, 0)), float(d.get(away, 0)))
        f[f"net_{s}"] = (oh - dh) - (oa - da)
        f[f"sum_{s}"] = (oh + da) + (oa + dh)
    f["net_stuff_rate"] = -f.get("net_stuff_rate", 0.0)
    return f


def add_luck(f: dict, luck_coef: float) -> dict:
    """Points beyond what efficiency supports (luck_coef from the fit: points per unit of net EPA)."""
    return {**f, "luck": f.get("net_points", 0.0) - luck_coef * f.get("net_epa", 0.0)}


def load_early() -> dict | None:
    return json.loads(EARLY_PATH.read_text(encoding="utf-8")) if EARLY_PATH.exists() else None


DRIVER = {"net_success": "success rate", "net_epa": "EPA per play", "luck": "points luck (scoring beyond efficiency)",
          "net_stuff_rate": "run stuffs", "net_line_yards": "line play (line yards)", "open": "the size of the spread",
          "sum_epa": "both offenses' efficiency against these defenses", "sum_plays": "pace",
          "sum_success": "success rates", "topen": "the total itself (extreme totals drift back)"}


def early_read(f: dict, line_spread: float | None, line_total: float | None, fit: dict) -> dict:
    """The early read at the current lines: predicted (margin - spread) and (points - total),
    how strong each is in SDs of the fitted prediction, and the two biggest drivers pushing
    that way (in words)."""
    out = {}
    f = add_luck(f, fit["luck_coef"])
    for kind, feats, line in (("spread", SIDE_FEATURES, line_spread), ("total", TOTAL_FEATURES, line_total)):
        m = fit.get(kind)
        if m is None or line is None or not np.isfinite(line):
            continue
        x = [f.get(k, 0.0) for k in feats] + [line]
        names = feats + (["open"] if kind == "spread" else ["topen"])
        pred = m["coef"][0] + float(np.dot(m["coef"][1:], x))
        if kind == "total":  # centre the line's pull on an average total so "the total itself" reads as a driver
            contrib = {n: c * (v - 55.0 if n == "topen" else v) for n, c, v in zip(names, m["coef"][1:], x)}
        else:
            contrib = {n: c * v for n, c, v in zip(names, m["coef"][1:], x)}
        push = sorted((c for c in contrib.items() if np.sign(c[1]) == np.sign(pred)), key=lambda c: -abs(c[1]))
        out[kind] = {"edge_pts": round(pred, 2), "strength": round(pred / m["pred_sd"], 2),
                     "drivers": [DRIVER[n] for n, _ in push[:2]]}
    return out
