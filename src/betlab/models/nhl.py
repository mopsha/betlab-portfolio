"""NHL game model: team shot and scoring ratings, the starting goalie, and a score grid.

1. **Team ratings** (`fit`): the football engine's weighted ridge (stat = league + home
   edge + offense[team] + defense[opponent]) on games before the date, for
   - `shots`: shots on goal,
   - `goals`: goals that weren't into an empty net (the shootout goal is removed),
   - `ff`: unblocked shot attempts at 5-on-5 (who controls play; kept for the notes).
   Recency half-life and ridge are in `Params`.
2. **Goalies** (`fit`): each goalie's save percentage over recent seasons, shrunk toward
   the league by `goalie_k` shots (a goalie with few shots is near league average, and a
   goalie with none starts a little below it: backups and call-ups usually are).
3. **Expected goals** (`project`): two views blended by `w_goals`:
   - shots view: projected shots × (1 − the opposing starter's save %) × the team's
     finishing (goals per shot above the league's, shrunk);
   - goals view: the goals ridge, adjusted by how the opposing starter compares with the
     goalies that team usually plays.
   A team on the second night of a back-to-back scores `b2b` (log) less.
4. **Score grid** (`grid`): independent Poisson regulation goals with a small extra
   weight on ties (`tie_boost`, the NHL has more 60-minute ties than Poisson says);
   overtime or a shootout goes to the stronger side by `ot_edge`; the leading team adds
   empty-net goals at the rates seen when a game is within one or two goals. Books count
   the shootout winner as one goal for totals, and so does the grid.

Walk-forward only. Backtest: `backtest_nhl` (`betlab backtest nhl`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import gamma, poisson

from betlab.models.game_nfl import _ridge

STATS = ("shots", "goals", "ff")
MAX_GOALS = 14
DISP_NODES = 9


@dataclass
class Params:
    half_life_days: float = 60.0
    ridge: float = 8.0
    window_days: int = 500
    goalie_half_life_days: float = 365.0
    goalie_k: float = 1500.0        # shots of league-average play added to every goalie
    new_goalie_sv_gap: float = 0.004  # a goalie with no history starts this far below league
    finish_k: float = 1500.0        # shots of league-average finishing added to every team
    w_goals: float = 0.5            # weight of the goals view (the rest is the shots view)
    b2b: float = -0.04              # log expected goals on the second night of a back-to-back
    tie_boost: float = 1.12         # extra weight on 60-minute ties
    ot_edge: float = 1.0            # overtime: P(home) = logistic(ot_edge * log(home xG / away xG))
    en_rate_1: float = 0.45         # empty-net goals added when the lead is one goal
    en_rate_2: float = 0.25         # ... two goals
    disp: float = 0.0               # a shared scoring factor per game ~ Gamma(shape 1/disp, mean 1); 0 = off.
                                    # Some nights both teams score more (a hot goalie pair, a loose game):
                                    # it widens totals without moving who's favored
    goal_scale: float = 1.0         # every expected-goal rate times this (fit so totals average right)


@dataclass
class Ratings:
    date: pd.Timestamp
    league: dict
    home: dict
    off: pd.DataFrame
    dfn: pd.DataFrame
    goalie_sv: dict                 # goalie name -> shrunk save %
    team_sv: dict                   # team -> save % of the goalies it has played lately
    league_sv: float
    finish: dict                    # team -> goals per shot relative to the league
    params: Params = field(default_factory=Params)


def team_games(tg: pd.DataFrame) -> pd.DataFrame:
    """Model inputs per (game, team) from `sources.nhl.load_team_games`, plus rest."""
    t = tg.copy()
    opp_en = t[["game_id", "team", "en_goals"]].rename(columns={"team": "opp", "en_goals": "opp_en"})
    t = t.merge(opp_en, on=["game_id", "opp"], how="left")
    t["shots"] = t["sf"]
    t["goals"] = (t["gf_play"] - t["en_goals"]).clip(lower=0)
    t["goals_against"] = (t["ga_play"] - t["opp_en"].fillna(0)).clip(lower=0)
    t = t.sort_values(["team", "date"])
    t["rest"] = t.groupby("team")["date"].diff().dt.days
    t["b2b"] = (t["rest"] == 1).astype(float)
    return t.sort_values(["date", "game_id", "home"]).reset_index(drop=True)


def fit(tg: pd.DataFrame, gg: pd.DataFrame, date, p: Params | None = None) -> Ratings:
    """Team ratings and goalie save % from games strictly before `date`."""
    p = p or Params()
    date = pd.Timestamp(date)
    h = tg[(tg["date"] < date) & (tg["date"] >= date - pd.Timedelta(days=p.window_days))]
    teams = sorted(set(h["team"]) | set(h["opp"]))
    idx = {t: i for i, t in enumerate(teams)}
    w = 0.5 ** ((date - h["date"]).dt.days.to_numpy() / p.half_life_days)
    home = np.where(h["home"].to_numpy() == 1, 1.0, -1.0)
    league, he, off, dfn = {}, {}, {}, {}
    for stat in STATS:
        y = h[stat].to_numpy(float)
        ok = np.isfinite(y)
        mu, e, o, d = _ridge(y[ok], w[ok], h["team"].map(idx).to_numpy()[ok], h["opp"].map(idx).to_numpy()[ok],
                             home[ok], len(teams), p.ridge)
        league[stat], he[stat], off[stat], dfn[stat] = mu, e, o, d

    # Finishing: goals per shot, shrunk toward the league.
    lg_sh = float((h["goals"] * w).sum() / max((h["shots"] * w).sum(), 1))
    by = pd.DataFrame({"team": h["team"], "g": h["goals"] * w, "s": h["shots"] * w}).groupby("team").sum()
    finish = ((by["g"] + p.finish_k * lg_sh) / (by["s"] + p.finish_k) / lg_sh).to_dict()

    # Goalies: save % with recency weights, shrunk toward the league.
    g = gg[(gg["date"] < date) & (gg["date"] >= date - pd.Timedelta(days=3 * 365))]
    wg = 0.5 ** ((date - g["date"]).dt.days.to_numpy() / p.goalie_half_life_days)
    league_sv = float((g["saves"] * wg).sum() / max((g["shots_against"] * wg).sum(), 1)) if len(g) else 0.900
    gs = pd.DataFrame({"goalie": g["goalie"], "sv": g["saves"] * wg, "sh": g["shots_against"] * wg}).groupby("goalie").sum()
    goalie_sv = ((gs["sv"] + p.goalie_k * league_sv) / (gs["sh"] + p.goalie_k)).to_dict()
    # The goalies a team has played lately (what its goals-allowed rating already includes).
    recent = g[g["date"] >= date - pd.Timedelta(days=120)]
    wr = 0.5 ** ((date - recent["date"]).dt.days.to_numpy() / p.half_life_days)
    ts = pd.DataFrame({"team": recent["team"], "goalie": recent["goalie"], "sh": recent["shots_against"] * wr})
    team_sv = {}
    for team, grp in ts.groupby("team"):
        tot = grp["sh"].sum()
        team_sv[team] = float(sum(goalie_sv.get(gl, league_sv) * s for gl, s in zip(grp["goalie"], grp["sh"])) / tot) if tot else league_sv
    return Ratings(date, league, he, pd.DataFrame(off, index=teams), pd.DataFrame(dfn, index=teams),
                   goalie_sv, team_sv, league_sv, finish, p)


def goalie_sv(r: Ratings, name: str | None) -> float:
    if not name or name not in r.goalie_sv:
        return r.league_sv - r.params.new_goalie_sv_gap
    return float(r.goalie_sv[name])


def _stat(r: Ratings, stat: str, team: str, opp: str, hh: float) -> float:
    return (r.league[stat] + r.home[stat] * hh + float(r.off[stat].get(team, 0.0)) + float(r.dfn[stat].get(opp, 0.0)))


def expected_goals(r: Ratings, team: str, opp: str, hh: float, opp_goalie: str | None, b2b: bool = False) -> dict:
    """A team's expected non-empty-net goals against this opposing starter."""
    p = r.params
    shots = max(_stat(r, "shots", team, opp, hh), 15.0)
    sv = goalie_sv(r, opp_goalie)
    shots_view = shots * (1 - sv) * r.finish.get(team, 1.0)
    base_sv = r.team_sv.get(opp, r.league_sv)
    goals_view = max(_stat(r, "goals", team, opp, hh), 0.5) * (1 - sv) / max(1 - base_sv, 1e-3)
    lam = p.w_goals * goals_view + (1 - p.w_goals) * shots_view
    if b2b:
        lam *= np.exp(p.b2b)
    return {"lambda": float(lam), "shots": float(shots), "goalie_sv": float(sv)}


def grid(lh: float, la: float, p: Params) -> dict:
    """Win, total and puck-line probabilities from the two expected-goal rates."""
    k = np.arange(MAX_GOALS + 1)
    if p.disp > 0:
        shape = 1 / p.disp
        z = gamma.ppf((np.arange(DISP_NODES) + 0.5) / DISP_NODES, a=shape, scale=1 / shape)
        z = z / z.mean()
        m = sum(np.outer(poisson.pmf(k, lh * zi), poisson.pmf(k, la * zi)) for zi in z) / len(z)
    else:
        m = np.outer(poisson.pmf(k, lh), poisson.pmf(k, la))
    m = m.copy()
    m[np.diag_indices_from(m)] *= p.tie_boost
    m /= m.sum()
    diff = k[:, None] - k[None, :]
    reg_tot = k[:, None] + k[None, :]
    p_tie = float(m[diff == 0].sum())
    ot_home = 1 / (1 + np.exp(-p.ot_edge * np.log(max(lh, 1e-6) / max(la, 1e-6))))
    p_home = float(m[diff > 0].sum()) + p_tie * ot_home
    # Final totals and margins: regulation, then empty-net goals for a leader by 1 or 2,
    # then one goal for overtime or a shootout.
    totals, margins = {}, {}
    final = np.zeros((MAX_GOALS + 5, MAX_GOALS + 5))     # final score (home, away), as books settle it

    def add(d, key, v):
        d[key] = d.get(key, 0.0) + v

    for (i, j), pr in np.ndenumerate(m):
        if pr < 1e-12:
            continue
        dm = i - j
        if dm == 0:
            add(totals, i + j + 1, pr)
            add(margins, 1, pr * ot_home)
            add(margins, -1, pr * (1 - ot_home))
            final[i + 1, j] += pr * ot_home
            final[i, j + 1] += pr * (1 - ot_home)
            continue
        rate = p.en_rate_1 if abs(dm) == 1 else p.en_rate_2 if abs(dm) == 2 else 0.0
        if rate:
            for e in range(4):
                pe = poisson.pmf(e, rate) if e < 3 else 1 - poisson.cdf(2, rate)
                add(totals, i + j + e, pr * pe)
                add(margins, dm + (e if dm > 0 else -e), pr * pe)
                final[(i + e, j) if dm > 0 else (i, j + e)] += pr * pe
        else:
            add(totals, i + j, pr)
            add(margins, dm, pr)
            final[i, j] += pr
    return {"p_home": p_home, "p_tie_reg": p_tie, "totals": totals, "margins": margins, "final": final,
            "exp_total": float(sum(t * v for t, v in totals.items()))}


def p_over(g: dict, line: float) -> tuple[float, float]:
    """(P(over), P(push)) at a total line."""
    over = sum(v for t, v in g["totals"].items() if t > line)
    push = sum(v for t, v in g["totals"].items() if t == line)
    return float(over), float(push)


def p_cover(g: dict, home_line: float) -> float:
    """P(home covers the puck line), e.g. home_line = -1.5 means home wins by 2+."""
    return float(sum(v for mg, v in g["margins"].items() if mg + home_line > 0))


def project(r: Ratings, home: str, away: str, home_goalie: str | None = None, away_goalie: str | None = None,
            home_b2b: bool = False, away_b2b: bool = False) -> dict:
    """Both teams' expected goals and the game's probabilities."""
    eh = expected_goals(r, home, away, 1.0, away_goalie, home_b2b)
    ea = expected_goals(r, away, home, -1.0, home_goalie, away_b2b)
    g = grid(eh["lambda"] * r.params.goal_scale, ea["lambda"] * r.params.goal_scale, r.params)
    return {"home": home, "away": away, "home_xg": eh["lambda"], "away_xg": ea["lambda"],
            "home_shots": eh["shots"], "away_shots": ea["shots"],
            "home_goalie_sv": ea["goalie_sv"], "away_goalie_sv": eh["goalie_sv"], **g}


def ranks(r: Ratings) -> pd.DataFrame:
    """1 = best: most shots and goals created, fewest allowed, most 5-on-5 control."""
    return pd.DataFrame({
        "off_shots": r.off["shots"].rank(ascending=False, method="min"),
        "def_shots": r.dfn["shots"].rank(ascending=True, method="min"),
        "off_goals": r.off["goals"].rank(ascending=False, method="min"),
        "def_goals": r.dfn["goals"].rank(ascending=True, method="min"),
        "control": (r.off["ff"] - r.dfn["ff"]).rank(ascending=False, method="min"),
    })


# ---------------------------------------------------------------- special teams (analysis)
SPECIAL_K_OPP = 80.0      # power-play chances of league-average play added to every team's rate
SPECIAL_K_GAMES = 20.0    # games of league-average penalties added


def special_ratings(tg: pd.DataFrame, special: pd.DataFrame, date, half_life_days: float = 150.0) -> pd.DataFrame:
    """Each team's power play (goals per chance), penalty kill (share of chances killed),
    penalties drawn and taken per game, shrunk toward the league, from games before `date`,
    with ranks (1 = best)."""
    date = pd.Timestamp(date)
    sp = special.merge(tg[["game_id", "opp", "team", "date"]], on=["game_id", "opp"], how="inner")
    sp = sp[(sp["date"] < date) & (sp["date"] >= date - pd.Timedelta(days=500))]
    if sp.empty:
        return pd.DataFrame()
    w = 0.5 ** ((date - sp["date"]).dt.days.to_numpy() / half_life_days)
    agg = pd.DataFrame({"team": sp["team"], "pp_goals": sp["pp_goals"] * w, "pp_opp": sp["pp_opp"] * w,
                        "pk_ga": sp["pp_goals_against"] * w, "times_sh": sp["times_sh"] * w, "games": w}).groupby("team").sum()
    lg_pp = agg["pp_goals"].sum() / max(agg["pp_opp"].sum(), 1)
    lg_pk = agg["pk_ga"].sum() / max(agg["times_sh"].sum(), 1)
    lg_drawn = agg["pp_opp"].sum() / max(agg["games"].sum(), 1)
    out = pd.DataFrame({
        "pp_pct": (agg["pp_goals"] + SPECIAL_K_OPP * lg_pp) / (agg["pp_opp"] + SPECIAL_K_OPP),
        "pk_pct": 1 - (agg["pk_ga"] + SPECIAL_K_OPP * lg_pk) / (agg["times_sh"] + SPECIAL_K_OPP),
        "drawn_pg": (agg["pp_opp"] + SPECIAL_K_GAMES * lg_drawn) / (agg["games"] + SPECIAL_K_GAMES),
        "taken_pg": (agg["times_sh"] + SPECIAL_K_GAMES * lg_drawn) / (agg["games"] + SPECIAL_K_GAMES),
    })
    out["pp_rank"] = out["pp_pct"].rank(ascending=False, method="min").astype(int)
    out["pk_rank"] = out["pk_pct"].rank(ascending=False, method="min").astype(int)
    out["drawn_rank"] = out["drawn_pg"].rank(ascending=False, method="min").astype(int)
    out["disc_rank"] = out["taken_pg"].rank(ascending=True, method="min").astype(int)
    out.attrs["league"] = {"pp_pct": lg_pp, "pk_pct": 1 - lg_pk, "chances_pg": lg_drawn}
    return out


def expected_pp_goals(sr: pd.DataFrame, team: str, opp: str) -> dict:
    """A team's expected power-play chances and goals against this opponent (log5-style:
    its own drawing and conversion against the opponent's discipline and kill)."""
    lg = sr.attrs["league"]
    a, d = sr.loc[team], sr.loc[opp]
    chances = a["drawn_pg"] * d["taken_pg"] / lg["chances_pg"]
    conv = a["pp_pct"] * (1 - d["pk_pct"]) / max(1 - lg["pk_pct"], 1e-6)
    return {"chances": float(chances), "conversion": float(conv), "pp_goals": float(chances * conv)}
