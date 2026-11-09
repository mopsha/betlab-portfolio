"""Walk-forward test of the soccer shots model (`betlab backtest soccer-props`, Oct 10).

Starters only (the props are priced after lineups). For each test season the trees train on every
earlier season, then predict shots and shots on target; P(over) at each line comes from a negative
binomial around the mean. Log loss at the line (lower is better) against two baselines:

- **recent:** the player's average shots per appearance over his last 10 (EWMA);
- **per 90 x minutes:** his long-run rate per 90 times his recent minutes per start.

And the question Mike asked: **one model for all leagues (league as a feature) or one per league?**
Both are fit and scored per league. A third model drops the market's expected goals, to measure
whether the team context helps (it did for NHL shots).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config
from betlab.models import props_soccer as PS
from betlab.models.props_nhl import p_over

HIST = config.DATA_DIR / "history" / "soccer_players"
LINES = {"shots": (0.5, 1.5, 2.5, 3.5), "sot": (0.5, 1.5), "goals": (0.5,), "assists": (0.5,), "ga": (0.5,)}
RATES = {"shots": ("shots90_l", "shots90_s"), "sot": ("sot90_l", "sot90_s"), "goals": ("goals90_l", "goals90_l"),
         "assists": ("assists90_l", "assists90_l"), "ga": ("ga90_l", "ga90_s")}


MODEL_PATH = config.DATA_DIR / "models" / "soccer_props.joblib"


def load_history() -> pd.DataFrame:
    from betlab.sources.espn_soccer import load_history as load

    return load()


def train_final(df: pd.DataFrame) -> PS.Fitted:
    """The live model: the pooled trees on every season (the backtest's winner), saved with joblib."""
    import joblib

    f = PS.fit(df)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(f, MODEL_PATH, compress=3)
    return f


def market_xg(pg: pd.DataFrame) -> pd.DataFrame:
    """[event_id, team, team_xg, opp_xg] from football-data.co.uk's close (1X2 + over/under 2.5), each
    ESPN match matched to its football-data row by club names and date."""
    from betlab.cards.fun_soccer import fit_goals
    from betlab.sources import soccer as FD

    out = []
    matches = pg.drop_duplicates(["event_id", "team"])[["event_id", "league", "season", "kickoff", "team", "home"]]
    for (league, season), m in matches.groupby(["league", "season"]):
        fd = FD.load(league, [int(season)])
        if fd.empty:
            continue
        clubs = sorted(set(fd["home"]) | set(fd["away"]))
        names = {t: max(clubs, key=lambda c: FD.similarity(t, c)) for t in m["team"].unique()}
        names = {t: c for t, c in names.items() if FD.similarity(t, c) >= 0.5}
        one = fd.assign(p=list(FD.closing_1x2(fd)))
        for eid, g in m.groupby("event_id"):
            h = g[g["home"]]
            a = g[~g["home"]]
            if h.empty or a.empty or h["team"].iloc[0] not in names or a["team"].iloc[0] not in names:
                continue
            day = pd.Timestamp(h["kickoff"].iloc[0]).tz_convert("Europe/London").tz_localize(None).normalize()
            row = one[(one["home"] == names[h["team"].iloc[0]]) & (one["away"] == names[a["team"].iloc[0]])
                      & ((one["date"] - day).abs() <= pd.Timedelta(days=1))]
            if row.empty:
                continue
            r = row.iloc[0]
            p = r["p"]
            o, u = r.get("pin_close_o25"), r.get("pin_close_u25")
            if not (np.isfinite(o) and np.isfinite(u)):
                o, u = r.get("avg_close_o25"), r.get("avg_close_u25")
            if not np.all(np.isfinite(p)):
                continue
            # MLS's file has no over/under: the 1X2 alone fixes both teams' expected goals
            overs = {2.5: (1 / o) / (1 / o + 1 / u)} if np.isfinite(o) and np.isfinite(u) and o > 1 and u > 1 else {}
            lh, la, err = fit_goals({"h": p[0], "d": p[1], "a": p[2], "overs": overs})
            if err > 0.05:
                continue
            out += [{"event_id": eid, "team": h["team"].iloc[0], "team_xg": lh, "opp_xg": la},
                    {"event_id": eid, "team": a["team"].iloc[0], "team_xg": la, "opp_xg": lh}]
    return pd.DataFrame(out)


def _ll(p, y) -> float:
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _score(mu, size, y, lines) -> dict:
    return {line: _ll(p_over(mu, line, size), (y > line).astype(float)) for line in lines}


def evaluate(df: pd.DataFrame, test_seasons: dict[str, tuple[int, ...]] | None = None) -> pd.DataFrame:
    """Log loss by league, test season, target and line for: recent, per90 x minutes, the pooled trees,
    the pooled trees without the market's xG, and per-league trees."""
    from betlab.models.props_nhl import nb_size

    test_seasons = test_seasons or {lg: ((2025, 2026) if lg == "mls" else (2025, 2026)) for lg in PS.LEAGUE_CODE}
    no_xg = [f for f in PS.PLAYER_FEATURES + PS.TEAM_FEATURES if f not in ("team_xg", "opp_xg")]
    rows = []
    seasons = sorted({s for v in test_seasons.values() for s in v})
    for season in seasons:
        train = df[df["season"] < season]
        test = df[(df["season"] == season) & df["starter"] & (df["apps_prior"] >= 3) & (df["minutes"] > 0)]
        if train.empty or test.empty:
            continue
        pooled = PS.fit(train)
        pooled_nx = PS.fit(train, no_xg)
        per = {lg: PS.fit(train[train["league"] == lg]) for lg in test["league"].unique()
               if (train["league"] == lg).sum() > 20000}
        tr = train[train["starter"] & (train["apps_prior"] >= 1)]
        for t in PS.TARGETS:
            rate, short = RATES[t]
            base_recent_tr = tr[short] * tr["start_min"].fillna(80) / 90
            base_rate_tr = tr[rate] * tr["start_min"].fillna(80) / 90
            size_recent = nb_size(tr[t].fillna(0).to_numpy(float), base_recent_tr.fillna(tr[t].mean()).clip(0.01).to_numpy())
            size_rate = nb_size(tr[t].fillna(0).to_numpy(float), base_rate_tr.fillna(tr[t].mean()).clip(0.01).to_numpy())
            for lg, g in test.groupby("league"):
                if season not in test_seasons.get(lg, ()):
                    continue
                y = g[t].fillna(0).to_numpy(float)
                cands = {
                    "recent": ((g[short] * g["start_min"].fillna(80) / 90).fillna(tr[t].mean()).clip(0.01), size_recent),
                    "per90 x minutes": ((g[rate] * g["start_min"].fillna(80) / 90).fillna(tr[t].mean()).clip(0.01), size_rate),
                    "trees, pooled": (PS.predict(pooled, g)[t], pooled.dispersion[t]),
                    "trees, pooled, no market xG": (PS.predict(pooled_nx, g)[t], pooled_nx.dispersion[t]),
                }
                if lg in per:
                    cands["trees, this league only"] = (PS.predict(per[lg], g)[t], per[lg].dispersion[t])
                for name, (mu, size) in cands.items():
                    for line, ll in _score(np.asarray(mu, float), size, y, LINES[t]).items():
                        rows.append({"league": lg, "season": season, "target": t, "line": line, "model": name,
                                     "n": len(g), "log_loss": round(ll, 4)})
    return pd.DataFrame(rows)


def prepare() -> pd.DataFrame:
    pg = load_history()
    if pg.empty:
        return pg
    return PS.features(pg, market_xg(pg))
