"""NFL same-game simulator: every player in one game, drawn together.

props_nfl.simulate draws one player at a time, which is fine for a single prop but
not for a parlay: when the Falcons throw 45 times, Penix and London both tend to
go over. Each draw here is one version of the whole game:

1. Points: each team's points around the market's implied team total
   (total/2 +- spread/2), SD 9.5, independently for the two teams (real scoring
   surprises correlate 0.035). The same points shock moves that offense's
   efficiency (yards per target +13%, per carry +5% per SD), so a good day is good
   for every player on that side.
2. Volume: team targets and carries from props_nfl.team_volume, moved by how the
   score goes (a team that falls behind throws more; one that gets ahead runs more),
   with the rest of a team's targets and carries trading off (more dropbacks leave
   fewer runs). A game that goes over its total gives both offenses more targets
   (Sep 28: without it, a QB's yards moved with the total 0.24 vs 0.34 in real games).
   Passing yards also bend with the final margin: most when trailing by about a TD,
   less in wins by 7+ and in blowout losses (margin_bend).
3. Shares: one Dirichlet draw per team splits targets (and another splits carries)
   among its players plus an "other" bucket, so teammates compete for the same
   volume. Each player's share has the same Beta spread as in props_nfl.
4. Stats: receptions and yards as in props_nfl. The QB's passing yards are the
   sum of his receivers' yards: they are the same yards.
5. Touchdowns: team TDs ~ Poisson(0.105 x points drawn), split pass/rush by the
   team's history. A draw with a big passing day gets more TDs and a bigger passing
   share of them (matched to 2021-24: passing yards move with passing TDs, not rushing
   TDs). Then TDs are handed to the simulated players in proportion to their
   targets or carries in that draw times their own TD rate per opportunity. The
   "other" bucket (unlisted players) gets volume but no TDs.

v1 (2026-09-25): backtested (`betlab backtest sgp`, docs/MODELS.md). Volume and
efficiency settings fit on 2021-24 team-games; on 2025 they moved every pass/run
pair toward reality without changing single-player accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from betlab.models import props_nfl as P

STATS = ("receptions", "receiving_yards", "rushing_yards", "passing_yards", "tds")

# TDs per opportunity (league-typical), used to shrink small samples.
TD_PRIOR = {
    "WR": {"rec": 0.045, "rush": 0.02},
    "TE": {"rec": 0.055, "rush": 0.01},
    "RB": {"rec": 0.025, "rush": 0.033},
    "QB": {"rec": 0.0, "rush": 0.045},
}
OTHER = {"catch": 0.65, "ypt": 7.3, "ypc": 4.2, "rec_td": 0.04, "rush_td": 0.03}


@dataclass
class SimParams:
    props: P.PropParams = field(default_factory=P.PropParams)
    points_sd: float = 9.5          # SD of one team's points around its implied total
    eff_beta: float = 0.13          # log yards per target per SD of the points shock (fit 2021-24: 0.13)
    eff_beta_rush: float = 0.053    # log yards per carry per SD of the points shock (0.053)
    # How the score as it unfolds moves volume, per point of margin surprise, and how the
    # rest of a team's targets and carries trade off. Fit on 2021-24 team-games; 2025 agreed
    # (-0.126, +0.279, -0.32). v0 used half the pregame script coefficients and no trade-off.
    surprise_targets: float = -0.158
    surprise_carries: float = 0.291
    vol_corr: float = -0.32
    # A game that goes over its total brings both offenses more targets (per point of total
    # surprise; fit on 2021-24 team-games with the margin terms: +0.084 targets, SE 0.011, and
    # +0.018 carries, SE 0.010; 2025 agreed at +0.070 and +0.016). Without it the simulator tied
    # a QB's yards to the game total 0.24 vs 0.34 in real games (Sep 28 parlay backtest).
    surprise_total_targets: float = 0.084
    surprise_total_carries: float = 0.018
    # The bend in a team's passing yards by the final margin, left over by the linear terms
    # above: log-slope changes at margins of -21, -7, +7 and +21 (a linear spline, flat below
    # -21). Passing peaks when a team trails by about a touchdown (+6%), and drops about 6% in
    # wins by 7+ and 11% in blowout losses (starters sit, the clock runs). Fit on 2021-24
    # team-games; on 2025 it cut the leftover error and matched both ends (-9.4% vs -8.6% in
    # 21+ losses, -4.2% vs -4.3% in 21+ wins). Each draw's multiplier is normalized so a
    # team's average yards don't move.
    margin_knots: tuple = (-21.0, -7.0, 7.0, 21.0)
    margin_bend: tuple = (0.0122, -0.0203, 0.008, -0.0021)
    td_per_point: float = 0.105     # offensive TDs per point scored (22.5 points -> 2.4 TDs)
    pass_td_prior: float = 0.60     # league share of offensive TDs that are passing TDs
    other_min: float = 0.04         # at least this share of targets/carries goes to unlisted players
    depth_share: float = 0.02       # share for a rostered player with no history
    td_prior_rec: float = 40.0      # shrinkage in targets for receiving-TD rates
    td_prior_rush: float = 60.0     # shrinkage in carries for rushing-TD rates
    # A big passing day brings more TDs, and more of them through the air. The two settings are
    # matched to 2021-24 team-games: passing-yards surprise correlates 0.42 with passing TDs and
    # 0.02 with rushing TDs (simulated with these: 0.42 and 0.03; with neither, 0.10 and 0.09).
    pass_share_beta: float = 0.45   # log-odds of the pass-TD share per SD of the draw's passing yards
    td_yds_gamma: float = 0.20      # log TD count per SD of the draw's passing yards (mean kept)
    other_td: float = 0.0           # the unlisted bucket's TD rate scale (it keeps its yards); in the
                                    # backtest every TD went to a simulated player


@dataclass
class GameSim:
    """n joint draws of one game. draws[(player_id, stat)] is an array of length n."""

    n: int
    players: pd.DataFrame           # player_id, name, team, position, t_share, c_share
    draws: dict = field(default_factory=dict)
    points: dict = field(default_factory=dict)   # team -> points drawn
    team: dict = field(default_factory=dict)     # team -> {"pass_yds", "pass_tds", "rush_tds"} per draw

    def get(self, player_id: str, stat: str) -> np.ndarray | None:
        return self.draws.get((player_id, stat))


def td_rates(hist: pd.DataFrame, player_id: str, position: str, sp: SimParams) -> tuple[float, float]:
    """(receiving TDs per target, rushing TDs per carry), shrunk toward the position norm."""
    h = hist[hist["player_id"] == player_id].tail(32)
    prior = TD_PRIOR.get(position, TD_PRIOR["WR"])
    rec = (h["receiving_tds"].sum() + sp.td_prior_rec * prior["rec"]) / (h["targets"].sum() + sp.td_prior_rec)
    rush = (h["rushing_tds"].sum() + sp.td_prior_rush * prior["rush"]) / (h["carries"].sum() + sp.td_prior_rush)
    return float(rec), float(rush)


def pass_td_share(hist: pd.DataFrame, team: str, sp: SimParams) -> float:
    """Share of the team's offensive TDs that came through the air (last 16 games, shrunk)."""
    t = hist[hist["team"] == team]
    games = t["game_id"].drop_duplicates().tail(16)
    t = t[t["game_id"].isin(games)]
    passing, rushing = t["passing_tds"].sum(), t["rushing_tds"].sum()
    return float((passing + 8 * sp.pass_td_prior) / (passing + rushing + 8))


def team_players(hist: pd.DataFrame, roster: pd.DataFrame, featured: set[str], sp: SimParams,
                 out: frozenset = frozenset()) -> pd.DataFrame:
    """The players we simulate for one team, with their shares and rates.

    roster: this week's active players for the team (gsis_id, full_name, position).
    featured: player ids that have props; they are always included. The starting QB
    is the featured QB, else the QB with the most recent pass attempts.
    out: player ids ruled Out or Doubtful. Their target and carry shares go to the
    teammates who remain, in proportion to each teammate's own share.
    """
    rows = []
    skill = roster[roster["position"].isin(P.SKILL)]
    vacated = {"t_share": 0.0, "c_share": 0.0}
    for pid in skill.loc[skill["gsis_id"].isin(out) & (skill["position"] != "QB"), "gsis_id"]:
        if hist[hist["player_id"] == pid].empty:
            continue
        pos = skill.loc[skill["gsis_id"] == pid, "position"].iloc[0]
        prof = P.player_profile(hist, pid, pos, sp.props)
        vacated["t_share"] += prof["t_share"]
        vacated["c_share"] += prof["c_share"]
    skill = skill[~skill["gsis_id"].isin(out)]
    qbs = skill[skill["position"] == "QB"]
    starter = next((q for q in qbs["gsis_id"] if q in featured), None)
    if starter is None and len(qbs):
        recent = hist[hist["player_id"].isin(qbs["gsis_id"])].groupby("player_id")["attempts"].apply(
            lambda s: s.tail(3).sum())
        starter = recent.idxmax() if len(recent) else qbs["gsis_id"].iloc[0]
    for r in skill.itertuples():
        if r.position == "QB" and r.gsis_id != starter:
            continue  # backups are folded into "other" and the QB's early-exit chance
        h = hist[hist["player_id"] == r.gsis_id]
        prof = P.player_profile(hist, r.gsis_id, r.position, sp.props)
        if h.empty and r.gsis_id not in featured:
            prof["t_share"] = sp.depth_share if r.position != "QB" else 0.0
            prof["c_share"] = sp.depth_share / 2 if r.position == "RB" else 0.0
        if r.position == "QB":
            prof["t_share"] = 0.0
        if prof["t_share"] < 0.01 and prof["c_share"] < 0.01 and r.gsis_id not in featured:
            continue
        rec_td, rush_td = td_rates(hist, r.gsis_id, r.position, sp)
        rows.append({"player_id": r.gsis_id, "name": r.full_name, "position": r.position, **prof,
                     "rec_td": rec_td, "rush_td": rush_td, "is_qb": r.gsis_id == starter})
    df = pd.DataFrame(rows)
    for col in ("t_share", "c_share"):
        if len(df) and vacated[col] > 0 and df[col].sum() > 0:
            df[col] *= 1 + vacated[col] / df[col].sum()
    return df


def fit_shares(means: np.ndarray, fixed: np.ndarray, other_min: float) -> np.ndarray:
    """Make shares sum to at most 1 - other_min. Players with fixed=True (their share was
    set from the market) keep theirs; the others shrink first."""
    means = np.clip(np.asarray(means, float), 1e-3, None)
    room = 1 - other_min
    if means.sum() <= room:
        return means
    held = means[fixed].sum()
    if held < room - 0.02:
        free = ~fixed
        means[free] *= (room - held) / means[free].sum()
        return means
    return means * room / means.sum()


def _shares(means: np.ndarray, kappa: float, other_min: float, n: int, rng) -> np.ndarray:
    """(n, k+1) Dirichlet shares for k players plus the 'other' bucket (last column)."""
    alpha = kappa * np.append(means, max(1 - means.sum(), other_min / 2))
    return rng.dirichlet(alpha, size=n)


def margin_bend(margin: np.ndarray, sp: SimParams) -> np.ndarray:
    """Multiplier on a team's passing yards per draw from its final margin (settings
    margin_knots and margin_bend; 1 at every margin when the bend is all zeros)."""
    m = np.asarray(margin, float)
    z = sum(b * (np.maximum(0.0, m - k) - max(0.0, -k)) for k, b in zip(sp.margin_knots, sp.margin_bend))
    return np.exp(z) if np.ndim(z) else np.full(m.shape, np.exp(z))


def _allocate(n_tds: np.ndarray, weights: np.ndarray, rng) -> np.ndarray:
    """Hand each draw's TDs to players in proportion to weights (n, k) -> counts (n, k)."""
    w = weights.astype(float)
    s = w.sum(axis=1, keepdims=True)
    w = np.where(s > 0, w / np.where(s > 0, s, 1), 1.0 / w.shape[1])
    return rng.multinomial(n_tds, w)


def simulate_game(hist: pd.DataFrame, home: str, away: str, spread_home: float, total: float,
                  rosters: dict[str, pd.DataFrame], featured: set[str], sp: SimParams | None = None,
                  n: int = 20000, seed: int = 0, adjust: dict | None = None,
                  out: frozenset = frozenset()) -> GameSim:
    """Draw one game n times with v0.1 inputs (props_nfl profiles). spread_home is the
    home team's expected margin (+ = favored). See simulate_teams for `adjust`.

    out: players ruled Out/Doubtful (their volume goes to teammates; see team_players).
    """
    sp = sp or SimParams()
    mean_pts = {home: (total + spread_home) / 2, away: (total - spread_home) / 2}
    inputs = {}
    for team, opp in ((home, away), (away, home)):
        inputs[team] = {"players": team_players(hist, rosters[team], featured, sp, out),
                        "volume": P.team_volume(hist, team, mean_pts[team] - mean_pts[opp], total, sp.props),
                        "pass_td_share": pass_td_share(hist, team, sp)}
    return simulate_teams(inputs, home, away, spread_home, total, sp, n, seed, adjust)


def simulate_teams(inputs: dict, home: str, away: str, spread_home: float, total: float,
                   sp: SimParams | None = None, n: int = 20000, seed: int = 0,
                   adjust: dict | None = None) -> GameSim:
    """Draw one game n times from per-team inputs: {team: {"players": DataFrame of
    player_id, name, position, t_share, c_share, catch, ypt, ypc, rec_td, rush_td, is_qb;
    "volume": {"targets", "carries", "attempts"}; "pass_td_share": float}}.

    adjust scales the inputs toward the market (props_market.calibrate):
    {("t", player_id): x} multiplies a target share, ("c", player_id) a carry share,
    ("y", player_id) yards per target, ("vol", team) the team's targets. Adjusted shares
    are held when shares are rescaled.
    """
    adjust = adjust or {}
    sp = sp or SimParams()
    p = sp.props
    rng = np.random.default_rng(seed)
    mean_pts = {home: (total + spread_home) / 2, away: (total - spread_home) / 2}
    shock = {t: rng.standard_normal(n) for t in (home, away)}
    pts = {t: np.maximum(0.0, mean_pts[t] + sp.points_sd * shock[t]) for t in (home, away)}
    sim = GameSim(n=n, players=pd.DataFrame(), points=pts)
    frames = []
    for team, opp in ((home, away), (away, home)):
        exp_margin = mean_pts[team] - mean_pts[opp]
        pl = inputs[team]["players"].copy()
        if pl.empty:
            continue
        pl["team"] = team
        k = len(pl)
        vol = inputs[team]["volume"]
        surprise = (pts[team] - pts[opp]) - exp_margin
        total_surprise = pts[team] + pts[opp] - total
        eff = np.exp(sp.eff_beta * shock[team])
        eff_rush = np.exp(sp.eff_beta_rush * shock[team])

        # More dropbacks leave fewer runs: the two noises are correlated (vol_corr).
        z_t, z_o = rng.standard_normal(n), rng.standard_normal(n)
        z_c = sp.vol_corr * z_t + np.sqrt(1 - sp.vol_corr ** 2) * z_o
        vol_t = vol["targets"] * adjust.get(("vol", team), 1.0)
        team_t = np.maximum(5, vol_t + sp.surprise_targets * surprise + sp.surprise_total_targets * total_surprise
                            + p.team_sd * z_t).round()
        team_c = np.maximum(3, vol["carries"] + sp.surprise_carries * surprise
                            + sp.surprise_total_carries * total_surprise + p.team_sd * z_c).round()
        ids = pl["player_id"].tolist()
        t_mult = np.array([adjust.get(("t", i), 1.0) for i in ids])
        c_mult = np.array([adjust.get(("c", i), 1.0) for i in ids])
        pl["t_share"] = fit_shares(pl["t_share"].to_numpy() * t_mult, t_mult != 1.0, sp.other_min)
        pl["c_share"] = fit_shares(pl["c_share"].to_numpy() * c_mult, c_mult != 1.0, sp.other_min)
        frames.append(pl)
        t_sh = _shares(pl["t_share"].to_numpy(), p.share_kappa, sp.other_min, n, rng)
        c_sh = _shares(pl["c_share"].to_numpy(), p.carry_kappa, sp.other_min, n, rng)
        targets = rng.multinomial(team_t.astype(int), t_sh)          # (n, k+1)
        carries = rng.multinomial(team_c.astype(int), c_sh)

        # Early exits: a player occasionally plays only part of the game.
        frac = np.where(rng.random((n, k)) < p.exit_prob, rng.uniform(0.1, 0.7, (n, k)), 1.0)
        targets[:, :k] = rng.binomial(targets[:, :k], frac)
        carries[:, :k] = rng.binomial(carries[:, :k], frac)

        catch = np.append(pl["catch"].to_numpy(), OTHER["catch"])
        y_mult = np.array([adjust.get(("y", i), 1.0) for i in ids])
        ypt = np.append(pl["ypt"].to_numpy() * y_mult, OTHER["ypt"])
        ypc = np.append(pl["ypc"].to_numpy(), OTHER["ypc"])
        rec = rng.binomial(targets, catch)
        ypr = ypt / np.maximum(catch, 0.3)
        scale = (ypr[None, :] * eff[:, None]) / p.yds_shape
        rec_yds = np.where(rec > 0, rng.gamma(np.maximum(rec, 1) * p.yds_shape, scale), 0.0)
        bend = margin_bend(pts[team] - pts[opp], sp)
        rec_yds = rec_yds * (bend / bend.mean())[:, None]
        rush_mean = ypc[None, :] * eff_rush[:, None] * carries
        rush_yds = np.where(carries > 0,
                            rng.normal(rush_mean, p.rush_sd_per_carry * np.sqrt(np.maximum(carries, 1))), 0.0)

        # Touchdowns from the drawn points, split pass/rush by the team's share, tilted toward the
        # air when the passing game is having a big day (and toward the ground when it isn't).
        team_pass_yds = rec_yds.sum(axis=1)
        ly = np.log(np.maximum(team_pass_yds, 30.0))
        z = (ly - ly.mean()) / max(float(ly.std()), 1e-6)
        tilt = np.exp(sp.td_yds_gamma * z)
        tds = rng.poisson(sp.td_per_point * pts[team] * tilt / tilt.mean())
        base = float(np.clip(inputs[team]["pass_td_share"], 0.05, 0.95))
        share = 1 / (1 + np.exp(-(np.log(base / (1 - base)) + sp.pass_share_beta * z)))
        pass_tds = rng.binomial(tds, share)
        rush_tds = tds - pass_tds
        sim.team[team] = {"pass_yds": team_pass_yds, "pass_tds": pass_tds, "rush_tds": rush_tds}
        rec_w = targets * np.append(pl["rec_td"].to_numpy(), OTHER["rec_td"] * sp.other_td)
        rush_w = carries * np.append(pl["rush_td"].to_numpy(), OTHER["rush_td"] * sp.other_td)
        td_count = _allocate(pass_tds, rec_w, rng) + _allocate(rush_tds, rush_w, rng)

        for j, r in enumerate(pl.itertuples()):
            if r.is_qb:
                sim.draws[(r.player_id, "passing_yards")] = team_pass_yds * frac[:, j]
            sim.draws[(r.player_id, "receptions")] = rec[:, j]
            sim.draws[(r.player_id, "receiving_yards")] = rec_yds[:, j]
            sim.draws[(r.player_id, "rushing_yards")] = rush_yds[:, j]
            sim.draws[(r.player_id, "tds")] = td_count[:, j]
    sim.players = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return sim
