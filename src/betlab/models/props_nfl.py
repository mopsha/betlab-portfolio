"""NFL player props: volume x share x efficiency, simulated.

For each player in an upcoming game, using only earlier games:
1. Team volume: the team's recent targets and carries (exponentially weighted),
   adjusted for game script. A team expected to trail throws more.
2. Player share: the player's weighted share of that volume, shrunk toward a
   typical share for the position when the sample is small.
3. Efficiency: catch rate, yards per target, yards per carry, yards per
   attempt, shrunk toward position norms.
4. Simulation: team volume and the player's role are uncertain, and yards
   per catch are heavily skewed, so we draw 4,000 games and read P(over) for
   any line straight off the draws. Props void when a player doesn't play, so
   everything here assumes he plays.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Position priors (league-typical values) used to shrink small samples.
PRIOR = {
    "WR": {"t_share": 0.14, "c_share": 0.01, "catch": 0.63, "ypt": 8.3, "ypc": 6.0},
    "TE": {"t_share": 0.11, "c_share": 0.00, "catch": 0.70, "ypt": 7.3, "ypc": 4.0},
    "RB": {"t_share": 0.08, "c_share": 0.30, "catch": 0.78, "ypt": 6.0, "ypc": 4.3},
    "QB": {"t_share": 0.00, "c_share": 0.12, "catch": 0.60, "ypt": 6.0, "ypc": 5.0, "ypa": 6.9},
}
SKILL = ("WR", "TE", "RB", "QB")


@dataclass
class PropParams:
    share_half_life: float = 4.0      # games; roles change fast
    eff_half_life: float = 12.0       # games; efficiency is noisy, so look longer
    team_half_life: float = 6.0
    prior_games: float = 2.0          # shrinkage strength, in games of evidence
    script_coef_targets: float = -0.35  # extra team targets per point of expected deficit
    script_coef_carries: float = 0.30   # extra team carries per point of expected lead
    total_coef: float = 0.25            # extra plays per point of game total above 44
    team_sd: float = 6.0              # game-to-game SD of team targets/carries/attempts
    share_kappa: float = 40.0         # target-share uncertainty (Beta concentration)
    carry_kappa: float = 20.0         # carry shares move more (committees, game script)
    exit_prob: float = 0.05           # chance he leaves early (injury, benching, blowout)
    yds_shape: float = 1.3            # skew of yards per catch (Gamma shape)
    rush_sd_per_carry: float = 5.8
    pass_sd_per_att: float = 7.4


def prepare(ps: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Player-games with team totals, shares, date and game script."""
    ps = ps[ps["position"].isin(SKILL)].copy()
    g = games[["game_id", "date", "home_team", "away_team", "spread_line", "total_line"]]
    ps = ps.merge(g, on="game_id", how="inner")
    home = ps["team"] == ps["home_team"]
    ps["exp_margin"] = np.where(home, ps["spread_line"], -ps["spread_line"])  # team's expected margin
    team = ps.groupby(["game_id", "team"])[["targets", "carries", "attempts"]].sum().add_prefix("team_")
    ps = ps.join(team, on=["game_id", "team"])
    for c in ("targets", "carries", "attempts", "receptions", "receiving_yards", "rushing_yards", "passing_yards"):
        ps[c] = ps[c].fillna(0)
    return ps.sort_values(["date", "game_id"]).reset_index(drop=True)


def _weights(n: int, half_life: float) -> np.ndarray:
    """Most recent game last; weight 1 for it, halving every `half_life` games back."""
    return 0.5 ** (np.arange(n)[::-1] / half_life)


def team_volume(hist: pd.DataFrame, team: str, exp_margin: float, total: float, p: PropParams) -> dict:
    """Projected team targets, pass attempts and carries: weighted recent average plus game script."""
    t = hist[hist["team"] == team].drop_duplicates("game_id").tail(16)
    if t.empty:
        return {"targets": 33.0, "carries": 26.0, "attempts": 34.0}
    w = _weights(len(t), p.team_half_life)
    base = {k: float(np.average(t[f"team_{k}"], weights=w)) for k in ("targets", "carries", "attempts")}
    margin = 0.0 if np.isnan(exp_margin) else exp_margin
    extra = 0.0 if np.isnan(total) else (total - 44) * p.total_coef
    return {
        "targets": max(15.0, base["targets"] + p.script_coef_targets * margin + extra / 2),
        "attempts": max(15.0, base["attempts"] + p.script_coef_targets * margin + extra / 2),
        "carries": max(10.0, base["carries"] + p.script_coef_carries * margin + extra / 2),
    }


def player_profile(hist: pd.DataFrame, player_id: str, position: str, p: PropParams) -> dict:
    """Shrunk share and efficiency estimates from a player's earlier games."""
    h = hist[hist["player_id"] == player_id].tail(20)
    prior = PRIOR[position]
    k = p.prior_games
    if h.empty:
        return {"t_share": prior["t_share"], "c_share": prior["c_share"], "catch": prior["catch"],
                "ypt": prior["ypt"], "ypc": prior["ypc"], "ypa": prior.get("ypa", 0.0),
                "a_share": 0.95 if position == "QB" else 0.0, "games": 0}
    ws, we = _weights(len(h), p.share_half_life), _weights(len(h), p.eff_half_life)
    avg_team_t, avg_team_c = h["team_targets"].mean(), h["team_carries"].mean()
    t_share = (np.dot(ws, h["targets"]) + k * prior["t_share"] * avg_team_t) / (np.dot(ws, h["team_targets"]) + k * avg_team_t)
    c_share = (np.dot(ws, h["carries"]) + k * prior["c_share"] * avg_team_c) / (np.dot(ws, h["team_carries"]) + k * avg_team_c)
    tg, cr = np.dot(we, h["targets"]), np.dot(we, h["carries"])
    catch = (np.dot(we, h["receptions"]) + 10 * prior["catch"]) / (tg + 10)
    ypt = (np.dot(we, h["receiving_yards"]) + 10 * prior["ypt"]) / (tg + 10)
    ypc = (np.dot(we, h["rushing_yards"]) + 15 * prior["ypc"]) / (cr + 15)
    att = np.dot(we, h["attempts"])
    ypa = (np.dot(we, h["passing_yards"]) + 30 * prior.get("ypa", 6.9)) / (att + 30) if position == "QB" else 0.0
    if position == "QB":  # his share of team pass attempts (backups throw some in blowouts)
        team_att = h["team_attempts"].mean()
        a_share = (np.dot(ws, h["attempts"]) + k * 0.95 * team_att) / (np.dot(ws, h["team_attempts"]) + k * team_att)
    else:
        a_share = 0.0
    return {"t_share": float(t_share), "c_share": float(c_share), "catch": float(np.clip(catch, 0.3, 0.95)),
            "ypt": float(ypt), "ypc": float(ypc), "ypa": float(ypa), "a_share": float(np.clip(a_share, 0, 1)),
            "games": int(len(h))}


def simulate(vol: dict, prof: dict, position: str, p: PropParams, n: int = 4000, seed: int = 0) -> dict[str, np.ndarray]:
    """n simulated games for one player: targets, receptions, receiving/rushing (and QB passing) yards."""
    rng = np.random.default_rng(seed)
    out = {}

    def share_draws(mean: float, kappa: float) -> np.ndarray:
        mean = float(np.clip(mean, 1e-3, 0.97))
        return rng.beta(mean * kappa, (1 - mean) * kappa, n)

    # Early exits: in a few games he plays only part of the game.
    played = np.where(rng.random(n) < p.exit_prob, rng.uniform(0.1, 0.7, n), 1.0)

    team_t = np.maximum(5, rng.normal(vol["targets"], p.team_sd, n) * played).round().astype(int)
    targets = rng.binomial(team_t, share_draws(prof["t_share"], p.share_kappa))
    rec = rng.binomial(targets, prof["catch"])
    ypr = prof["ypt"] / max(prof["catch"], 0.3)
    yards = np.where(rec > 0, rng.gamma(np.maximum(rec, 1) * p.yds_shape, ypr / p.yds_shape), 0.0)
    out |= {"targets": targets, "receptions": rec, "receiving_yards": yards}

    team_c = np.maximum(3, rng.normal(vol["carries"], p.team_sd, n) * played).round().astype(int)
    carries = rng.binomial(team_c, share_draws(prof["c_share"], p.carry_kappa))
    out |= {"carries": carries,
            "rushing_yards": rng.normal(prof["ypc"] * carries, p.rush_sd_per_carry * np.sqrt(np.maximum(carries, 1)))}
    if position == "QB":
        att = np.maximum(3, rng.normal(vol["attempts"], p.team_sd, n) * prof["a_share"] * played)
        out["passing_yards"] = rng.normal(prof["ypa"] * att, p.pass_sd_per_att * np.sqrt(att))
    return out


def prob_over(draws: np.ndarray, line: float) -> tuple[float, float]:
    """(P over | no push, P push) for a prop line."""
    over, push = float(np.mean(draws > line)), float(np.mean(draws == line))
    return over / max(1 - push, 1e-9), push
