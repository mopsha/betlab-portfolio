"""NFL player roles and matchups (props model v0.2): the inputs the game simulator draws from.

v0.1 (props_nfl.player_profile) estimated each player's share of team targets from
his own past shares, shrunk toward a starter-level prior. Two problems showed up on
the first live game (Falcons @ Packers, 2026-09-24):
- Backups with thin histories were pulled up toward starter shares, so a team's
  shares summed to about 130% and the simulator squeezed the real starters.
- Roles lagged: a rookie who became a starter two games ago still looked like a backup.

v0.2 builds a role from snap share:
- **Snap share:** how much he's on the field, from his last few games (half-life
  `snap_half_life` games; games for another team count `other_team_weight`).
- **Per-snap rates:** targets per team target while on the field, and carries per
  team carry while on the field, over a longer window, shrunk toward the position.
- **Shares:** snap share × per-snap rate, so a backup on 10% of snaps gets a backup's
  share. The team's shares are then normalized to leave a small "other" bucket.
- **Matchup:** the opponent's recent yards per target allowed (by position group),
  catch rate allowed, and yards per carry allowed, relative to the league, shrunk
  toward average, multiply the player's efficiency.
- **Absences:** regulars who aren't playing (injury report, or not active) leave their
  target and carry shares to teammates.

Every number uses only games before the one being priced.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from betlab.models import props_nfl as P

GROUP = {"WR": "WR", "TE": "TE", "RB": "RB", "QB": "QB"}
# Per-snap priors: targets per team target while on the field, carries per team carry.
TPS_PRIOR = {"WR": 0.21, "TE": 0.16, "RB": 0.13, "QB": 0.0}
CPS_PRIOR = {"WR": 0.015, "TE": 0.003, "RB": 0.62, "QB": 0.12}
SNAP_PRIOR = {"WR": 0.35, "TE": 0.35, "RB": 0.30, "QB": 0.9}


@dataclass
class RoleParams:
    """Defaults are v0.2 as backtested on 2023-2025 (docs/MODEL_CHANGELOG.md). Each was
    kept only because it lowered the backtest's error; the rejected tries are logged there."""
    snap_half_life: float = 2.0       # games; snap share reflects the current role (1.5 was worse)
    rate_half_life: float = 8.0       # games; per-snap rates are steadier
    other_team_weight: float = 0.3    # a game for a previous team counts this much
    snap_prior_games: float = 0.1     # shrinkage of snap share, in games (0.5 dragged regulars down)
    rate_prior: float = 12.0          # shrinkage of per-snap rates, in on-field team targets/carries
    rb_cps_prior: float = 0.62        # carries per team carry for an RB on the field (0.78 was worse)
    use_snaps: bool = True            # False = v0.1 shares (for comparison)
    use_matchup: bool = True
    matchup_prior: float = 250.0      # shrinkage of defense rates, in targets (carries use 1.5x)
    defense_games: int = 16
    share_total: float = 0.96         # listed players' shares are normalized to this (sim keeps 4% for others)
    fill_shares: bool = True          # scale the players who play up to share_total too (not only down)
    robust_volume: bool = True        # leave out games where the offense barely threw (starters rested, QB hurt)
    opp_volume: bool = False          # adjust targets for how many the opponent's defense allows (worse: off)
    opp_volume_prior: float = 8.0     # shrinkage of that adjustment, in games


class History:
    """Player-games indexed for fast 'everything before this date' lookups."""

    def __init__(self, df: pd.DataFrame):
        self.df = df.sort_values(["date", "game_id"]).reset_index(drop=True)
        self.by_player = {pid: g for pid, g in self.df.groupby("player_id", sort=False)}
        team_cols = ["game_id", "date", "team", "team_targets", "team_carries", "team_attempts",
                     "exp_margin", "total_line"]
        tds = self.df.groupby(["game_id", "team"])[["passing_tds", "rushing_tds"]].sum()
        tds.columns = ["team_pass_tds", "team_rush_tds"]
        tg = self.df.drop_duplicates(["game_id", "team"])[team_cols].join(tds, on=["game_id", "team"])
        self.by_team = {t: g for t, g in tg.groupby("team", sort=False)}
        # What each defense allowed, by position group of the pass catcher / runner.
        d = self.df.assign(group=self.df["position"].map(GROUP))
        agg = d.groupby(["opp", "game_id", "date", "group"], sort=False)[
            ["targets", "receptions", "receiving_yards", "carries", "rushing_yards"]].sum().reset_index()
        self.by_defense = {o: g.sort_values("date") for o, g in agg.groupby("opp", sort=False)}
        self.league = agg.sort_values("date").reset_index(drop=True)
        self._league_cum = {grp: g.assign(**{c: g[c].cumsum() for c in
                                              ["targets", "receptions", "receiving_yards", "carries",
                                               "rushing_yards"]})
                            for grp, g in self.league.groupby("group", sort=False)}

    def player(self, pid: str, before) -> pd.DataFrame:
        g = self.by_player.get(pid)
        return self.df.iloc[0:0] if g is None else g[g["date"] < before]

    def team(self, team: str, before) -> pd.DataFrame:
        g = self.by_team.get(team)
        return self.df.iloc[0:0] if g is None else g[g["date"] < before]

    def league_rates(self, group: str, before, days: int = 365) -> dict:
        """League yards per target, catch rate and yards per carry for a position group,
        over the `days` before `before`."""
        g = self._league_cum.get(group)
        if g is None or g.empty:
            return {}
        dates = g["date"].to_numpy()
        hi = np.searchsorted(dates, np.datetime64(before), side="left") - 1
        lo = np.searchsorted(dates, np.datetime64(before) - np.timedelta64(days, "D"), side="left") - 1
        if hi < 0:
            return {}
        top = g.iloc[hi]
        bot = g.iloc[lo] if lo >= 0 else None
        tot = {c: top[c] - (bot[c] if bot is not None else 0) for c in
               ["targets", "receptions", "receiving_yards", "carries", "rushing_yards"]}
        return {"ypt": tot["receiving_yards"] / max(tot["targets"], 1),
                "catch": tot["receptions"] / max(tot["targets"], 1),
                "ypc": tot["rushing_yards"] / max(tot["carries"], 1)}


def prepare(ps: pd.DataFrame, games: pd.DataFrame, snaps: pd.DataFrame | None) -> pd.DataFrame:
    """Player-games for the skill positions, with snap share, opponent, game script and
    team totals. Players who played (snaps) but have no stats row are added with zeros:
    nflverse's player stats leave them out, which inflated past "actuals"."""
    stat_cols = ["attempts", "completions", "passing_yards", "passing_tds", "carries", "rushing_yards",
                 "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds"]
    ps = ps[["player_id", "player_display_name", "position", "game_id", "team"] + stat_cols].copy()
    if snaps is not None:
        sn = snaps[["player_id", "game_id", "team", "position", "player", "offense_snaps", "offense_pct"]]
        ps = ps.merge(sn, on=["player_id", "game_id"], how="outer", suffixes=("", "_snap"))
        ps["team"] = ps["team"].fillna(ps["team_snap"])
        ps["position"] = ps["position"].fillna(ps["position_snap"])
        ps["player_display_name"] = ps["player_display_name"].fillna(ps["player"])
        ps = ps.drop(columns=["team_snap", "position_snap", "player"])
    else:
        ps["offense_snaps"], ps["offense_pct"] = np.nan, np.nan
    ps = ps[ps["position"].isin(P.SKILL)].copy()
    ps[stat_cols] = ps[stat_cols].fillna(0)
    g = games[["game_id", "season", "week", "date", "home_team", "away_team", "spread_line", "total_line",
               "home_pts", "away_pts"]]
    ps = ps.merge(g, on="game_id", how="inner")
    home = ps["team"] == ps["home_team"]
    ps["opp"] = np.where(home, ps["away_team"], ps["home_team"])
    ps["exp_margin"] = np.where(home, ps["spread_line"], -ps["spread_line"])
    team = ps.groupby(["game_id", "team"])[["targets", "carries", "attempts"]].sum().add_prefix("team_")
    ps = ps.join(team, on=["game_id", "team"])
    return ps.sort_values(["date", "game_id"]).reset_index(drop=True)


def _w(n: int, half_life: float) -> np.ndarray:
    return 0.5 ** (np.arange(n)[::-1] / half_life)


def player_role(hp: pd.DataFrame, team: str, position: str, rp: RoleParams, p: P.PropParams) -> dict:
    """A player's role and efficiency from his games before this one (hp).

    Returns snap, t_share, c_share, catch, ypt, ypc, ypa, a_share, games.
    """
    h = hp.tail(24)
    base = P.player_profile(h, h["player_id"].iloc[0], position, p) if len(h) else \
        P.player_profile(h, "", position, p)
    if not rp.use_snaps:
        return {**base, "snap": np.nan}
    if h.empty:
        snap = SNAP_PRIOR.get(position, 0.3) * 0.5  # no history: a part-time role until shown otherwise
        return {**base, "snap": snap, "t_share": snap * TPS_PRIOR[position], "c_share": snap * CPS_PRIOR[position],
                "a_share": 0.95 if position == "QB" else 0.0}
    same = np.where(h["team"].to_numpy() == team, 1.0, rp.other_team_weight)
    has = h["offense_pct"].notna().to_numpy()
    pct = h["offense_pct"].fillna(0).to_numpy()
    if has.any():
        ws = _w(len(h), rp.snap_half_life) * same * has
        k = rp.snap_prior_games
        snap = (np.dot(ws, pct) + k * SNAP_PRIOR[position]) / (ws.sum() + k)
    else:  # no snap data: infer from target and carry shares
        snap = SNAP_PRIOR[position]
    wr = _w(len(h), rp.rate_half_life) * same
    on_field = np.where(has, pct, snap)
    t_exp = np.dot(wr, h["team_targets"].to_numpy() * on_field)
    c_exp = np.dot(wr, h["team_carries"].to_numpy() * on_field)
    k = rp.rate_prior
    tps = (np.dot(wr, h["targets"]) + k * TPS_PRIOR[position]) / (t_exp + k)
    cps_prior = rp.rb_cps_prior if position == "RB" else CPS_PRIOR[position]
    cps = (np.dot(wr, h["carries"]) + k * cps_prior) / (c_exp + k)
    a_share = base["a_share"]
    if position == "QB":
        a_share = float(np.clip(snap * 1.02, 0, 1))
    return {**base, "snap": float(snap), "t_share": float(snap * tps), "c_share": float(snap * cps),
            "a_share": a_share}


def matchup(hist: History, opp: str, before, rp: RoleParams) -> dict:
    """Multipliers on catch rate, yards per target (by position group) and yards per carry
    for players facing this defense, from its last `defense_games` games, shrunk toward 1."""
    out = {grp: {"catch": 1.0, "ypt": 1.0, "ypc": 1.0} for grp in ("WR", "TE", "RB", "QB")}
    if not rp.use_matchup:
        return out
    d = hist.by_defense.get(opp)
    if d is None:
        return out
    d = d[d["date"] < before]
    games = d["game_id"].drop_duplicates().tail(rp.defense_games)
    d = d[d["game_id"].isin(games)]
    for grp in ("WR", "TE", "RB"):
        lg = hist.league_rates(grp, before)
        x = d[d["group"] == grp]
        if not lg or x.empty:
            continue
        k, kc = rp.matchup_prior, rp.matchup_prior * 1.5
        tg, rec, yds = x["targets"].sum(), x["receptions"].sum(), x["receiving_yards"].sum()
        car, ry = x["carries"].sum(), x["rushing_yards"].sum()
        ypt = (yds + k * lg["ypt"]) / (tg + k) / lg["ypt"]
        catch = (rec + k * lg["catch"]) / (tg + k) / lg["catch"]
        ypc = (ry + kc * lg["ypc"]) / (car + kc) / lg["ypc"] if lg["ypc"] > 0 else 1.0
        out[grp] = {"catch": float(catch), "ypt": float(ypt), "ypc": float(ypc)}
    out["QB"] = {"catch": 1.0, "ypt": 1.0, "ypc": out["RB"]["ypc"]}
    return out


def opponent_volume(hist: History, opp: str, before, rp: RoleParams) -> float:
    """Targets the opponent's defense allows per game relative to the league, shrunk
    toward 1 with opp_volume_prior games of league-average evidence."""
    d = hist.by_defense.get(opp)
    if d is None:
        return 1.0
    d = d[d["date"] < before]
    per_game = d.groupby("game_id")["targets"].sum().tail(rp.defense_games)
    lg = hist.league[(hist.league["date"] < before)
                     & (hist.league["date"] >= np.datetime64(before) - np.timedelta64(365, "D"))]
    league = lg.groupby(["opp", "game_id"])["targets"].sum().mean() if len(lg) else np.nan
    if per_game.empty or not np.isfinite(league) or league <= 0:
        return 1.0
    k = rp.opp_volume_prior
    return float((per_game.sum() + k * league) / (len(per_game) + k) / league)


def team_inputs(hist: History, team: str, opp: str, before, roster: pd.DataFrame, exp_margin: float,
                total: float, rp: RoleParams, p: P.PropParams, out_ids: frozenset = frozenset(),
                sp=None, starter: str | None = None) -> dict:
    """Everything the game simulator needs for one team.

    roster: players who will play (player_id, name, position). out_ids: regulars ruled
    out; their shares go to the players who play. starter: the QB the market lists
    (the one with a passing-yards line), when there is one: he starts over whoever has
    the most recent snaps. Returns {"players": DataFrame, "volume": dict,
    "pass_td_share": float}.
    """
    from betlab.models import game_sim_nfl as G

    sp = sp or G.SimParams(props=p)
    th = hist.team(team, before)
    if rp.robust_volume and len(th) >= 4:
        # A game with under 60% of the team's usual pass attempts is almost always resting
        # starters or a QB injury; it says nothing about this week's volume.
        usual = th.tail(16)["team_attempts"].median()
        th = th[th["team_attempts"] >= 0.6 * usual]
    vol = P.team_volume(th.assign(team=team), team, exp_margin, total, p) if len(th) else \
        {"targets": 33.0, "carries": 26.0, "attempts": 34.0}
    if rp.opp_volume:
        vol = {**vol, "targets": vol["targets"] * opponent_volume(hist, opp, before, rp)}
    m = matchup(hist, opp, before, rp)
    rows = []
    for r in roster.itertuples():
        hp = hist.player(r.player_id, before)
        role = player_role(hp, team, r.position, rp, p)
        mm = m.get(GROUP.get(r.position, "WR"), m["WR"])
        rec_td, rush_td = G.td_rates(hp, r.player_id, r.position, sp) if len(hp) else \
            (G.TD_PRIOR[r.position]["rec"], G.TD_PRIOR[r.position]["rush"])
        rows.append({"player_id": r.player_id, "name": r.name, "position": r.position, **role,
                     "catch": float(np.clip(role["catch"] * mm["catch"], 0.3, 0.95)),
                     "ypt": role["ypt"] * mm["ypt"], "ypc": role["ypc"] * mm["ypc"],
                     "rec_td": rec_td, "rush_td": rush_td})
    pl = pd.DataFrame(rows)
    if pl.empty:
        return {"players": pl, "volume": vol, "pass_td_share": sp.pass_td_prior, "matchup": m, "missing": []}
    # The starting QB: the market's QB, else the QB with the biggest recent snap/attempt share.
    # (Sep 27: snaps picked Shedeur Sanders over Deshaun Watson and Carson Wentz over Kyler
    # Murray; the real starters got no carries and the market's rushing and TD prices for
    # them couldn't be matched, so both games lost their parlays.)
    qbs = pl[pl["position"] == "QB"]
    if starter is None or starter not in set(qbs["player_id"]):
        starter = qbs.sort_values(["snap", "games"], ascending=False)["player_id"].iloc[0] if len(qbs) else None
    else:
        i = pl.index[pl["player_id"] == starter][0]
        if pl.loc[i, "c_share"] < 0.01:  # no rushing history: a full-time starter's prior
            pl.loc[i, "c_share"] = SNAP_PRIOR["QB"] * CPS_PRIOR["QB"]
    pl["is_qb"] = pl["player_id"] == starter
    pl.loc[(pl["position"] == "QB") & ~pl["is_qb"], ["t_share", "c_share"]] = 0.0
    pl.loc[pl["position"] == "QB", "t_share"] = 0.0
    # Regulars ruled out leave their shares to the players who play.
    vacated = {"t_share": 0.0, "c_share": 0.0}
    missing = []
    for pid in out_ids:
        hp = hist.player(pid, before)
        if len(hp) and hp["team"].iloc[-1] == team:
            pos = hp["position"].iloc[-1]
            role = player_role(hp, team, pos, rp, p)
            vacated["t_share"] += role["t_share"] if pos != "QB" else 0.0
            vacated["c_share"] += role["c_share"]
            missing.append({"name": hp["player_display_name"].iloc[-1], "position": pos,
                            "t_share": role["t_share"], "c_share": role["c_share"]})
    for col in ("t_share", "c_share"):
        tot = pl[col].sum()
        if tot > 0:
            if not rp.use_snaps:
                target = tot + vacated[col]
            elif rp.fill_shares:
                target = rp.share_total
            else:
                target = min(rp.share_total, tot + vacated[col])
            pl[col] *= target / tot
    return {"players": pl, "volume": vol, "pass_td_share": _pass_td_share(th, sp), "matchup": m, "missing": missing}


def _pass_td_share(th: pd.DataFrame, sp) -> float:
    """Share of the team's offensive TDs thrown, over its last 16 games (shrunk)."""
    t = th.tail(16)
    passing, rushing = t["team_pass_tds"].sum(), t["team_rush_tds"].sum()
    return float((passing + 8 * sp.pass_td_prior) / (passing + rushing + 8))
