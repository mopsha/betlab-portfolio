"""How an NFL game should go: unit-vs-unit ratings from play-by-play, and a game projection.

1. **Team-game unit stats** (`team_games`), from every play:
   - passing (dropbacks, scrambles and sacks included) and rushing: EPA per play,
     success rate and explosive rate
   - pressure: sacks plus QB hits per dropback
   - neutral-situation pass rate and pass rate over expected (PROE)
   - pace: seconds per play in neutral situations, and total plays
   - red-zone touchdown rate, turnovers, points

   Each row is one offense against one defense.
2. **Unit ratings** (`fit_ratings`): for each stat, a weighted ridge regression
   stat = league + offense[team] + defense[opponent] + home edge, on games before the
   date, with older games weighted down (half-life in days). This separates "the
   Packers' pass offense is good" from "they played bad pass defenses".
3. **Game projection** (`project`): plays for each team, pass/run mix (with game
   script), EPA per play for each side of each matchup, points, margin, total, and
   win chance. Also the unit matchups with the biggest edges, ranked against the league.
4. **Who plays and where** (`qb_ratings`, `qb_adjust`, `weather_effects`): a team's
   pass rating reflects the QBs who took its recent snaps, so when a different QB
   starts, the pass offense moves by the gap between them. Kickoff weather (wind, rain
   or snow, freezing cold) moves passing efficiency and pass rate by amounts fit on
   2012-25 games.

Walk-forward only: nothing uses the game being projected or anything after it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PBP_COLUMNS = [
    "game_id", "season", "week", "season_type", "posteam", "defteam", "home_team", "away_team", "play_type",
    "pass", "rush", "epa", "success", "yards_gained", "sack", "qb_hit", "qb_scramble", "interception",
    "fumble_lost", "touchdown", "yardline_100", "down", "half_seconds_remaining", "game_seconds_remaining",
    "wp", "pass_oe", "drive", "qtr", "two_point_attempt", "passer_id", "passer",
    "receiver_player_id", "air_yards", "complete_pass",   # receiver matchups (models/matchups_nfl.py)
]
# The stats we rate. "higher" says which direction is good for the offense.
STATS = {
    "pass_epa": "higher", "rush_epa": "higher", "pass_success": "higher", "rush_success": "higher",
    "pressure": "lower", "explosive": "higher", "neutral_pass": None, "proe": None, "sec_per_play": None,
    "plays": None, "rz_td": "higher", "turnovers": "lower", "points": "higher",
}
RELOCATED = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


def team_games(pbp: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, offense): unit stats from its plays, plus date, opponent, home."""
    p = pbp[pbp["play_type"].isin(["pass", "run"]) & (pbp["two_point_attempt"].fillna(0) == 0)].copy()
    for c in ("posteam", "defteam", "home_team", "away_team"):
        p[c] = p[c].replace(RELOCATED)
    p["dropback"] = p["pass"].fillna(0).astype(bool)
    p["is_rush"] = ~p["dropback"] & (p["rush"].fillna(0) == 1)
    p["explosive_play"] = np.where(p["dropback"], p["yards_gained"] >= 20, p["yards_gained"] >= 10)
    p["neutral"] = p["wp"].between(0.2, 0.8) & (p["qtr"] <= 3) & (p["half_seconds_remaining"] > 120)
    p = p.sort_values(["game_id", "drive", "game_seconds_remaining"], ascending=[True, True, False])
    nxt = p.groupby(["game_id", "drive"])["game_seconds_remaining"].shift(-1)
    p["secs"] = (p["game_seconds_remaining"] - nxt).where(lambda s: s.between(1, 60))

    def agg(g: pd.DataFrame) -> pd.Series:
        db, ru = g[g["dropback"]], g[g["is_rush"]]
        neu = g[g["neutral"]]
        rz = g[g["yardline_100"] <= 20]
        rz_drives = rz["drive"].nunique()
        rz_tds = rz.groupby("drive")["touchdown"].max().sum() if rz_drives else 0
        return pd.Series({
            "plays": len(g), "dropbacks": len(db), "rushes": len(ru),
            "pass_epa": db["epa"].mean(), "rush_epa": ru["epa"].mean(),
            "pass_success": db["success"].mean(), "rush_success": ru["success"].mean(),
            "pressure": (db["sack"].fillna(0) + db["qb_hit"].fillna(0)).clip(upper=1).mean(),
            "explosive": g["explosive_play"].mean(),
            "neutral_pass": neu["dropback"].mean() if len(neu) >= 8 else np.nan,
            "proe": neu["pass_oe"].mean() / 100 if len(neu) >= 8 else np.nan,
            "sec_per_play": neu["secs"].mean() if neu["secs"].notna().sum() >= 8 else np.nan,
            "rz_trips": rz_drives, "rz_td": rz_tds / rz_drives if rz_drives else np.nan,
            "turnovers": g["interception"].fillna(0).sum() + g["fumble_lost"].fillna(0).sum(),
            "total_epa": g["epa"].sum(),
        })

    tg = p.groupby(["game_id", "posteam", "defteam"]).apply(agg, include_groups=False).reset_index()
    tg = tg.rename(columns={"posteam": "team", "defteam": "opp"})
    g = games[["game_id", "season", "week", "date", "home_team", "away_team", "home_pts", "away_pts",
               "spread_line", "total_line", "game_type"]]
    tg = tg.merge(g, on="game_id", how="inner")
    tg["home"] = np.where(tg["team"] == tg["home_team"], 1.0, np.where(tg["team"] == tg["away_team"], -1.0, 0.0))
    tg["points"] = np.where(tg["home"] > 0, tg["home_pts"], tg["away_pts"])
    tg["opp_points"] = np.where(tg["home"] > 0, tg["away_pts"], tg["home_pts"])
    return tg.sort_values(["date", "game_id"]).reset_index(drop=True)


@dataclass
class GameParams:
    half_life_days: float = 120.0     # older games count less; last season still informs early weeks
    ridge: float = 4.0                # shrinkage toward average, in (weighted) games
    script_pass: float = -0.0025      # change in pass rate per point of expected margin (fit on 2023-24)
    margin_sd: float = 13.5           # outcome spread around the projected margin
    points_sd: float = 9.5
    # QB ratings (walk-forward 2023-25, `betlab backtest game`): opponent-adjusted EPA per
    # dropback, shrunk toward a backup's level by qb_k dropbacks. Every setting tried beat
    # no QB term on games after a QB change; these sit mid-grid, not at the single best.
    qb_prior: float = -0.15           # a QB with no record: about a backup's EPA per dropback vs average
    qb_k: float = 300.0               # prior strength, in dropbacks
    qb_half_life: float = 730.0       # QB skill is steadier than a team's, so a longer memory
    qb_alpha: float = 0.8             # share of the QB gap that moves the team's pass rating


@dataclass
class Ratings:
    """Unit ratings as of a date: for each stat, league mean, home edge, offense and defense effects."""
    date: pd.Timestamp
    league: dict
    home: dict
    off: pd.DataFrame                 # index team, columns stats
    dfn: pd.DataFrame
    points_fit: tuple                 # (intercept, per-EPA slope, per-play slope)


def _ridge(y: np.ndarray, w: np.ndarray, team_idx: np.ndarray, opp_idx: np.ndarray, home: np.ndarray,
           n_teams: int, lam: float) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Solve stat = mu + home_edge*home + off[team] + def[opp] with a ridge penalty on off/def."""
    n = len(y)
    X = np.zeros((n, 2 + 2 * n_teams))
    X[:, 0] = 1.0
    X[:, 1] = home
    X[np.arange(n), 2 + team_idx] = 1.0
    X[np.arange(n), 2 + n_teams + opp_idx] = 1.0
    W = w[:, None]
    A = X.T @ (X * W)
    A[2:, 2:] += lam * np.eye(2 * n_teams)
    b = X.T @ (w * y)
    beta = np.linalg.solve(A + 1e-9 * np.eye(A.shape[0]), b)
    return beta[0], beta[1], beta[2:2 + n_teams], beta[2 + n_teams:]


def fit_ratings(tg: pd.DataFrame, date, gp: GameParams | None = None) -> Ratings:
    """Unit ratings from team-games strictly before `date`."""
    gp = gp or GameParams()
    date = pd.Timestamp(date)
    h = tg[(tg["date"] < date) & (tg["date"] >= date - pd.Timedelta(days=800))]
    teams = sorted(set(h["team"]) | set(h["opp"]))
    idx = {t: i for i, t in enumerate(teams)}
    age = (date - h["date"]).dt.days.to_numpy()
    w_time = 0.5 ** (age / gp.half_life_days)
    league, home, off, dfn = {}, {}, {}, {}
    for stat in STATS:
        y = h[stat].to_numpy(dtype=float)
        ok = np.isfinite(y)
        if ok.sum() < 20:
            continue
        # Weight a game by how much it says: dropbacks for pass stats, rushes for run stats.
        size = {"pass_epa": "dropbacks", "pass_success": "dropbacks", "pressure": "dropbacks",
                "rush_epa": "rushes", "rush_success": "rushes", "rz_td": "rz_trips"}.get(stat)
        w = w_time * (h[size].to_numpy(dtype=float) / h[size].mean() if size else 1.0)
        mu, he, o, d = _ridge(y[ok], w[ok], h["team"].map(idx).to_numpy()[ok], h["opp"].map(idx).to_numpy()[ok],
                              h["home"].to_numpy()[ok], len(teams), gp.ridge)
        league[stat], home[stat] = mu, he
        off[stat], dfn[stat] = o, d
    # Points from EPA and plays (fit on the same window): points ~ a + b*total EPA + c*plays
    X = np.column_stack([np.ones(len(h)), h["total_epa"], h["plays"]])
    ok = np.isfinite(X).all(axis=1) & h["points"].notna().to_numpy()
    coef = np.linalg.lstsq(X[ok] * np.sqrt(w_time[ok])[:, None], h["points"].to_numpy()[ok] * np.sqrt(w_time[ok]),
                           rcond=None)[0]
    return Ratings(date=date, league=league, home=home,
                   off=pd.DataFrame(off, index=teams), dfn=pd.DataFrame(dfn, index=teams),
                   points_fit=tuple(float(c) for c in coef))


def qb_games(pbp: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, offense, passer): dropbacks with EPA (sacks and scrambles
    included), total EPA, name, date, opponent, home. `starter` marks the passer with
    the most dropbacks in that team's game."""
    p = pbp[pbp["play_type"].isin(["pass", "run"]) & (pbp["two_point_attempt"].fillna(0) == 0)
            & (pbp["pass"].fillna(0) == 1) & pbp["passer_id"].notna()]
    p = p.assign(posteam=p["posteam"].replace(RELOCATED), defteam=p["defteam"].replace(RELOCATED))
    qg = (p.groupby(["game_id", "posteam", "defteam", "passer_id"])
          .agg(dropbacks=("epa", "count"), epa=("epa", "sum"), name=("passer", "first")).reset_index()
          .rename(columns={"posteam": "team", "defteam": "opp"}))
    qg = qg[qg["dropbacks"] > 0].merge(games[["game_id", "date", "home_team", "away_team"]], on="game_id")
    qg["home"] = np.where(qg["team"] == qg["home_team"], 1.0, np.where(qg["team"] == qg["away_team"], -1.0, 0.0))
    qg["starter"] = False
    qg.loc[qg.groupby(["game_id", "team"])["dropbacks"].idxmax(), "starter"] = True
    return qg.drop(columns=["home_team", "away_team"]).sort_values(["date", "game_id"]).reset_index(drop=True)


def qb_ratings(qg: pd.DataFrame, r: Ratings, date, gp: GameParams | None = None) -> pd.DataFrame:
    """Each QB's passing before `date`: EPA per dropback minus what the league, home field
    and that game's pass defense explain, weighted by dropbacks and recency, and shrunk
    toward a backup's level (qb_prior, by qb_k dropbacks). Index passer_id: est, w, name."""
    gp = gp or GameParams()
    date = pd.Timestamp(date)
    h = qg[qg["date"] < date]
    w = h["dropbacks"].to_numpy() * 0.5 ** ((date - h["date"]).dt.days.to_numpy() / gp.qb_half_life)
    expected = (r.league["pass_epa"] + r.home["pass_epa"] * h["home"]
                + h["opp"].map(r.dfn["pass_epa"]).fillna(0.0))
    resid = (h["epa"] / h["dropbacks"] - expected).to_numpy()
    by = (pd.DataFrame({"passer_id": h["passer_id"].to_numpy(), "wr": w * resid, "w": w, "name": h["name"].to_numpy()})
          .groupby("passer_id").agg(wr=("wr", "sum"), w=("w", "sum"), name=("name", "last")))
    by["est"] = (by["wr"] + gp.qb_k * gp.qb_prior) / (by["w"] + gp.qb_k)
    return by[["est", "w", "name"]]


def qb_adjust(qg: pd.DataFrame, qbr: pd.DataFrame, team: str, starter: str | None, date,
              gp: GameParams | None = None) -> dict:
    """How a starter moves a team's pass rating: qb_alpha x (his rating minus the QB mix
    behind the team's current rating, weighted like the ratings: dropbacks, 120-day
    half-life). Zero when he's the usual starter; negative for a backup; positive when
    the starter returns after a backup played. Also gives the QB with the most weight in
    that mix (usual_id) and the starter of the team's last game (last_id)."""
    gp = gp or GameParams()
    date = pd.Timestamp(date)
    th = qg[(qg["team"] == team) & (qg["date"] < date) & (qg["date"] >= date - pd.Timedelta(days=800))]
    w = th["dropbacks"] * 0.5 ** ((date - th["date"]).dt.days / gp.half_life_days)
    est = th["passer_id"].map(qbr["est"]).fillna(gp.qb_prior)
    usual = float((w * est).sum() / w.sum()) if w.sum() > 0 else gp.qb_prior
    lead = th.assign(w=w).groupby("passer_id")["w"].sum().idxmax() if len(th) else None
    last = th[th["starter"]].sort_values("date")["passer_id"].iloc[-1] if th["starter"].any() else None
    usual_last = th.loc[th["passer_id"] == lead, "date"].max() if lead is not None else None
    s = float(qbr["est"].get(starter, gp.qb_prior)) if starter else usual
    return {"adj": gp.qb_alpha * (s - usual), "starter_est": s, "usual_est": usual, "usual_id": lead,
            "usual_name": qbr["name"].get(lead) if lead is not None else None, "last_id": last,
            "usual_days_ago": int((date - usual_last).days) if usual_last is not None else None}


# Kickoff weather's effect on a team's unit stats, fit on 7,284 team-games 2012-25 as
# residuals from walk-forward ratings (`betlab backtest game`; game-bootstrap SEs in the
# comments). Effects under 2 SEs are left out (cold on efficiency, anything on the run game).
WEATHER = {
    "wind_pass_epa": -0.059,      # per 10 mph above 10, capped at 25 mph (SE 0.014)
    "wind_pass_rate": -0.013,     # neutral-situation pass rate, same wind scale (SE 0.006)
    "wind_explosive": -0.0087,    # explosive-play rate, same wind scale (SE 0.0020)
    "precip_pass_epa": -0.041,    # rain or snow at kickoff (SE 0.014)
    "precip_pass_rate": -0.020,   # (SE 0.006)
    "cold_pass_rate": -0.017,     # 32 F or colder (SE 0.005)
}


def weather_effects(wx: dict | None) -> dict:
    """Changes to both teams' unit stats for a kickoff forecast (sources/weather.forecast).
    Rain counts in proportion to its chance, so a 40% chance is 40% of the effect."""
    if not wx:
        return {}
    num = lambda k: float(wx[k]) if wx.get(k) is not None and np.isfinite(wx[k]) else None  # missing -> no effect
    wind = min(max((num("wind_mph") or 0.0) - 10, 0), 15) / 10
    rain = num("precip_prob") or 0.0
    cold = 1.0 if (num("temp_f") is not None and num("temp_f") <= 32) else 0.0
    return {"pass_epa": WEATHER["wind_pass_epa"] * wind + WEATHER["precip_pass_epa"] * rain,
            "explosive": WEATHER["wind_explosive"] * wind,
            "neutral_pass": (WEATHER["wind_pass_rate"] * wind + WEATHER["precip_pass_rate"] * rain
                             + WEATHER["cold_pass_rate"] * cold)}


def _unit(r: Ratings, stat: str, team: str, opp: str, home: float) -> float:
    return (r.league.get(stat, np.nan) + r.home.get(stat, 0.0) * home
            + (r.off[stat].get(team, 0.0) if stat in r.off else 0.0)
            + (r.dfn[stat].get(opp, 0.0) if stat in r.dfn else 0.0))


def project(r: Ratings, home: str, away: str, neutral: bool = False, gp: GameParams | None = None,
            market_margin_home: float | None = None, adjust: dict | None = None) -> dict:
    """How the game should go: per-team plays, pass/run mix, efficiency, points; margin, total.

    With market_margin_home, game script (leaders run, trailers throw) follows the
    market's expected margin, which predicts the score better than our ratings do.
    adjust: {team: {stat: change}} for who starts at QB and the weather
    (qb_adjust, weather_effects); the pass EPA change is kept as `pass_adj`."""
    gp = gp or GameParams()
    side = {}
    for team, opp, h in ((home, away, 0.0 if neutral else 1.0), (away, home, 0.0 if neutral else -1.0)):
        side[team] = {k: _unit(r, k, team, opp, h) for k in STATS}
        for stat, change in ((adjust or {}).get(team) or {}).items():
            side[team][stat] = side[team][stat] + change
        side[team]["pass_adj"] = ((adjust or {}).get(team) or {}).get("pass_epa", 0.0)
    # First pass: points from the neutral mix, to get an expected margin for the script.
    for it in range(2):
        for team, opp in ((home, away), (away, home)):
            s = side[team]
            if market_margin_home is not None:
                margin = market_margin_home if team == home else -market_margin_home
            else:
                margin = (side[team].get("proj_points", 22) - side[opp].get("proj_points", 22)) if it else 0.0
            pass_rate = float(np.clip(s["neutral_pass"] + gp.script_pass * margin, 0.3, 0.8))
            plays = s["plays"]
            epa = plays * (pass_rate * s["pass_epa"] + (1 - pass_rate) * s["rush_epa"])
            a, b, c = r.points_fit
            s.update(pass_rate=pass_rate, dropbacks=plays * pass_rate, rushes=plays * (1 - pass_rate),
                     proj_epa=epa, proj_points=max(3.0, a + b * epa + c * plays))
    hp, ap = side[home]["proj_points"], side[away]["proj_points"]
    margin = hp - ap
    from scipy.stats import norm
    return {"home": home, "away": away, "sides": side, "home_points": hp, "away_points": ap,
            "margin": margin, "total": hp + ap, "home_win": float(norm.cdf(margin / gp.margin_sd))}


def ranks(r: Ratings) -> pd.DataFrame:
    """Each team's rank (1 = best for that unit) on every rated offense and defense stat."""
    rows = {}
    for stat, good in STATS.items():
        if stat not in r.off or good is None:
            continue
        hi = good == "higher"
        rows[f"off_{stat}"] = r.off[stat].rank(ascending=not hi, method="min")
        rows[f"def_{stat}"] = r.dfn[stat].rank(ascending=hi, method="min")  # defense: allowing less is better
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- matchups and the script, in words

UNIT_LABEL = {"pass_epa": ("passing game", "pass defense", "EPA per dropback"),
              "rush_epa": ("running game", "run defense", "EPA per rush"),
              "pressure": ("pass protection", "pass rush", "pressure rate (sacks + QB hits per dropback)"),
              "rz_td": ("red-zone offense", "red-zone defense", "touchdown rate on red-zone trips"),
              "explosive": ("big-play offense", "big-play defense", "explosive-play rate")}


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def matchups(r: Ratings, home: str, away: str, name) -> list[dict]:
    """The unit-vs-unit matchups with the biggest edges, strongest first. Each offense meets
    the other team's defense; an edge is the offense's rating plus the defense's (in the
    stat's own units), scaled by how much teams differ on that stat."""
    rk = ranks(r)
    out = []
    for team, opp in ((home, away), (away, home)):
        for stat, (o_lbl, d_lbl, what) in UNIT_LABEL.items():
            if stat not in r.off:
                continue
            spread = pd.concat([r.off[stat], r.dfn[stat]]).std()
            effect = r.off[stat].get(team, 0.0) + r.dfn[stat].get(opp, 0.0)
            sign = -1 if STATS[stat] == "lower" else 1
            size = sign * effect / spread if spread else 0.0
            o_rank, d_rank = int(rk.loc[team, f"off_{stat}"]), int(rk.loc[opp, f"def_{stat}"])
            fav = name(team) if size > 0 else name(opp)
            if stat == "pressure":
                text = (f"{name(opp)} {d_lbl} ({_ord(d_rank)}) vs {name(team)} {o_lbl} ({_ord(o_rank)}): "
                        f"edge {fav}")
            else:
                text = (f"{name(team)} {o_lbl} ({_ord(o_rank)}) vs {name(opp)} {d_lbl} ({_ord(d_rank)}): "
                        f"edge {fav}")
            out.append({"offense": team, "defense": opp, "stat": stat, "what": what, "size": round(float(size), 2),
                        "edge": team if size > 0 else opp, "off_rank": o_rank, "def_rank": d_rank, "text": text})
    return sorted(out, key=lambda m: -abs(m["size"]))


def script_features(r: Ratings, tg: pd.DataFrame, pr: dict, team: str, opp: str, before) -> dict:
    """What the game script says about one offense, in the units the prop script lean
    uses (props_market.script_lean): the pass and run matchup edges in league standard
    deviations (the offense's rating plus the defense's, as in matchups()), and projected
    dropbacks and rushes as log ratios to the team's last 8 games."""
    out = {}
    for stat in ("pass_epa", "rush_epa"):
        spread = pd.concat([r.off[stat], r.dfn[stat]]).std()
        effect = r.off[stat].get(team, 0.0) + r.dfn[stat].get(opp, 0.0)
        if stat == "pass_epa":  # who starts at QB, and the weather
            effect += pr["sides"][team].get("pass_adj", 0.0)
        out[stat] = float(effect / spread) if spread else 0.0
    past = tg[(tg["team"] == team) & (tg["date"] < before)].tail(8)
    s = pr["sides"][team]
    out["dropbacks"] = float(np.log(s["dropbacks"] / past["dropbacks"].mean())) if len(past) else 0.0
    out["rushes"] = float(np.log(s["rushes"] / past["rushes"].mean())) if len(past) else 0.0
    return out


def script_text(pr: dict, market: dict | None, name) -> str:
    """The game in a few sentences: the market's score, our read, pace, run/pass, and the biggest edge."""
    h, a = pr["home"], pr["away"]
    sh, sa = pr["sides"][h], pr["sides"][a]
    parts = []
    if market:
        fav = h if market["spread_home"] > 0 else a
        parts.append(f"The market has the {name(fav)} by {abs(market['spread_home']):g} in a {market['total']:g}-point "
                     f"game (about {market['home_points']:.0f}-{market['away_points']:.0f}).")
    ofav = h if pr["margin"] > 0 else a
    parts.append(f"Our unit ratings see the {name(ofav)} by {abs(pr['margin']):.1f} with {pr['total']:.0f} points "
                 "(the market has been the better guide to the score; we use it for the how).")
    pace = []
    for t, s in ((h, sh), (a, sa)):
        pace.append(f"the {name(t)} about {s['plays']:.0f} plays ({s['dropbacks']:.0f} dropbacks, {s['rushes']:.0f} runs)")
    parts.append("Expect " + " and ".join(pace) + ".")
    slow = [name(t) for t, s in ((h, sh), (a, sa)) if s["sec_per_play"] >= 34]
    fast = [name(t) for t, s in ((h, sh), (a, sa)) if s["sec_per_play"] <= 31.5]
    if slow:
        parts.append(f"The {' and '.join(slow)} play slow, which trims the number of plays.")
    if fast:
        parts.append(f"The {' and '.join(fast)} play fast, which adds plays.")
    runners = [name(t) for t, s in ((h, sh), (a, sa)) if s["pass_rate"] < 0.55]
    if runners:
        parts.append(f"The {' and '.join(runners)} lean on the run.")
    return " ".join(parts)
