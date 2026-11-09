"""Who is missing, in numbers: non-QB absences for the game-flow engine (Games tab).

The QB test (backtest_game.qb_eval) showed who starts at QB moves a passing game. This
module does the same for the rest of the roster, from snap counts and player stats:

- **Regulars** are defined from a team's earlier games this season (`find_regulars`):
  - offensive line: linemen (T, G, C) with 80%+ of the snaps in 2 of the team's last 3 games
  - top target: the receiver (WR, TE or RB) with the most targets over the last 4 games, if
    he drew 20%+ of the team's targets
  - lead back: the RB with 40%+ of the team's carries over the last 4 games
  - top pass rusher: the front-seven defender with the most sacks + half QB hits this
    season (2+), over up to 16 games
  - front and back starters: defensive linemen/linebackers and defensive backs with 80%+ of
    the defensive snaps in 2 of the last 3 games
- Windows stay inside the current season (a player who left in the offseason isn't
  "missing"). The backtest counts from a team's 4th game (5th for the top target and pass
  rusher). Live it needs 2 earlier games with snap counts (then "2 of the last 3" is "both"),
  because nflverse's snap counts can lag a week behind early in the season.
- Names are matched within a team on first initial + last name, so "Matt Judon" (snap
  counts) and "Matthew Judon" (player stats) are one player.
- **Missing** means he took no snap in the game (backtest). Live, it is what's known
  before kickoff: Out or Doubtful on the injury report, or off the active roster
  (reserve/IR, cut, traded; those drop off the injury report).

`absences(...)` returns one row per (game, team) with the counts for the backtest
(`backtest_game.injury_eval`); `live(...)` does the same for this week from the injury
report. `EFFECTS` holds the fitted numbers; `adjustments(...)` turns counts into the
game_nfl.project adjustments and a sentence per team.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab.players import normalize

OL = {"T", "G", "C", "OT", "OG", "OL"}
FRONT = {"DE", "DT", "NT", "LB", "OLB", "ILB", "MLB", "DL", "EDGE"}
BACK = {"CB", "FS", "SS", "S", "DB", "SAF"}
RECEIVERS = {"WR", "TE", "RB"}

# What each missing regular does, per player, beyond the walk-forward ratings and the QB
# adjustment (`betlab backtest game`, 3,987 team-games 2016-25, game-bootstrap SEs). Kept
# only where the effect is 2+ SEs from zero with the same sign in 2016-20 and 2021-25, and
# held out of sample (fit 2016-20, error down on 2021-25).
#   own:  the team's offense moves when its own regular is missing
#   opp:  the team's offense moves when the OPPONENT's defensive regular is missing
EFFECTS = {
    "own": {"ol_out": {"pass_epa": -0.023},             # SE 0.008 (2016-20 -0.019, 2021-25 -0.027)
            "top_target_out": {"pass_epa": -0.043}},    # SE 0.017 (-0.073, -0.020)
    "opp": {"rusher_out": {"pressure": -0.016},         # SE 0.004 (-0.015, -0.017)
            "back_out": {"pass_epa": 0.029,             # SE 0.008 (0.020, 0.035)
                         "pressure": -0.0045}},         # SE 0.002 (-0.004, -0.005)
}
# Tested and left out: the lead back (rush EPA -0.029 in 2016-25, but -0.047 then -0.005:
# didn't hold out of sample), linemen on rushing and pressure, front-seven starters.


def key(name: str) -> str:
    """'Matthew Judon' -> 'm judon': first initial + last name, for matching within a team."""
    words = normalize(name).split()
    return f"{words[0][0]} {words[-1]}" if len(words) >= 2 else " ".join(words)


def find_regulars(prev3: list[pd.DataFrame], prev4_stats: pd.DataFrame | None,
                  season_stats: pd.DataFrame | None) -> dict:
    """A team's regulars from its earlier games this season.

    prev3: snap-count frames of its last 3 games (player = key, position, offense_pct,
    defense_pct). prev4_stats: player stats of its last 4 games (name = key, position,
    targets, carries). season_stats: player stats of up to its last 16 games this season
    (def_sacks, def_qb_hits). Returns {"ol", "front", "back": sets of keys; "top_target",
    "lead_back", "rusher": a key or None}."""
    def starters(positions, pct):
        counts = {}
        for g in prev3:
            for name in g.loc[g["position"].isin(positions) & (g[pct] >= 0.8), "player"]:
                counts[name] = counts.get(name, 0) + 1
        return {n for n, c in counts.items() if c >= 2}

    out = {"ol": starters(OL, "offense_pct"), "front": starters(FRONT, "defense_pct"),
           "back": starters(BACK, "defense_pct"), "top_target": None, "lead_back": None, "rusher": None}
    if prev4_stats is not None and len(prev4_stats):
        rec = prev4_stats[prev4_stats["position"].isin(RECEIVERS)].groupby("name")["targets"].sum()
        if rec.sum() > 0 and rec.max() / rec.sum() >= 0.20:
            out["top_target"] = rec.idxmax()
        rb = prev4_stats[prev4_stats["position"] == "RB"].groupby("name")["carries"].sum()
        if len(rb) and prev4_stats["carries"].sum() > 0 and rb.max() / prev4_stats["carries"].sum() >= 0.40:
            out["lead_back"] = rb.idxmax()
    if season_stats is not None and len(season_stats):
        d = season_stats[season_stats["position"].isin(FRONT)]
        score = (d["def_sacks"].fillna(0) + 0.5 * d["def_qb_hits"].fillna(0)).groupby(d["name"]).sum()
        if len(score) and score.max() >= 2:
            out["rusher"] = score.idxmax()
    return out


def count_missing(regs: dict, missing: set[str]) -> dict:
    """Counts of the regulars in `missing` (keys), and who they are."""
    return {"ol_out": len(regs["ol"] & missing), "front_out": len(regs["front"] & missing),
            "back_out": len(regs["back"] & missing),
            "top_target_out": float(regs["top_target"] in missing) if regs["top_target"] else 0.0,
            "lead_back_out": float(regs["lead_back"] in missing) if regs["lead_back"] else 0.0,
            "rusher_out": float(regs["rusher"] in missing) if regs["rusher"] else 0.0}


def _prep(snaps: pd.DataFrame, stats: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    from betlab.models.game_nfl import RELOCATED

    snaps = snaps.copy()
    snaps["team"] = snaps["team"].replace(RELOCATED)
    snaps["player"] = snaps["player"].map(key)
    stats = stats.copy()
    stats["team"] = stats["team"].replace(RELOCATED)
    stats["name"] = stats["player_display_name"].map(key)
    return snaps, stats


def absences(snaps: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id, team): ol_out, top_target_out, lead_back_out (the team's own
    regulars who didn't play) and rusher_out, front_out, back_out (its defense's).

    snaps: raw nflverse snap counts (game_id, season, week, player, position, team,
    offense_pct, defense_pct). stats: raw nflverse player stats (player_display_name, team,
    game_id, position, targets, carries, def_sacks, def_qb_hits)."""
    snaps, stats = _prep(snaps[snaps["game_id"].isin(stats["game_id"])], stats)
    by_game = {k: g for k, g in snaps.groupby(["team", "game_id"])}
    st_by = {k: g for k, g in stats.groupby(["team", "game_id"])}
    order = snaps.drop_duplicates(["team", "game_id"]).sort_values(["team", "season", "week"])
    rows = []
    for (team, _), g in order.groupby(["team", "season"]):
        ids = g["game_id"].tolist()
        for i, gid in enumerate(ids):
            prev = ids[:i]
            now = set(by_game[(team, gid)]["player"])
            row = {"game_id": gid, "team": team}
            if len(prev) < 3:
                rows.append(row | dict.fromkeys(["ol_out", "front_out", "back_out", "top_target_out",
                                                 "lead_back_out", "rusher_out"], np.nan))
                continue
            stats_of = lambda games: pd.concat([st_by[(team, p)] for p in games if (team, p) in st_by]) \
                if any((team, p) in st_by for p in games) else None
            regs = find_regulars([by_game[(team, p)] for p in prev[-3:]], stats_of(prev[-4:]), stats_of(prev[-16:]))
            missing = {n for n in regs["ol"] | regs["front"] | regs["back"]
                       | {regs["top_target"], regs["lead_back"], regs["rusher"]} if n and n not in now}
            c = count_missing(regs, missing)
            if len(prev) < 4:  # the backtest's rule: the top target, lead back and pass rusher from game 5
                c.update(top_target_out=np.nan, lead_back_out=np.nan, rusher_out=np.nan)
            rows.append(row | c)
    return pd.DataFrame(rows)


OFF_ROSTER = {"RES", "CUT", "RET", "TRD", "TRC", "EXE"}   # weekly roster statuses that mean gone


def live(snaps: pd.DataFrame, stats: pd.DataFrame, team: str, before, out_names,
         roster: pd.DataFrame | None = None) -> dict:
    """This week's missing regulars for one team. out_names: the injury report's Out and
    Doubtful players (full names). roster: the team's latest weekly roster (full_name,
    status); a regular listed as reserve/cut/traded, or not listed at all, is missing too.
    snaps/stats: this season's raw nflverse frames with a `date` column. Returns
    count_missing's counts plus "who": {kind: [names]}, or {} with under 2 earlier games."""
    snaps, stats = _prep(snaps[(snaps["team"] == team) & (snaps["date"] < before)],
                         stats[(stats["team"] == team) & (stats["date"] < before)])
    games = snaps.drop_duplicates("game_id").sort_values("date")["game_id"].tolist()
    if len(games) < 2:
        return {}
    by_game = {gid: g for gid, g in snaps.groupby("game_id")}
    pick = lambda ids: stats[stats["game_id"].isin(ids)]
    regs = find_regulars([by_game[g] for g in games[-3:]], pick(games[-4:]), pick(games[-16:]))
    names = {key(n): n for n in out_names}
    if roster is not None and len(roster):
        listed = {key(n): n for n in roster["full_name"].dropna()}
        gone = {key(n): n for n in roster.loc[roster["status"].isin(OFF_ROSTER), "full_name"].dropna()}
        everyone = regs["ol"] | regs["front"] | regs["back"] | {regs["top_target"], regs["lead_back"], regs["rusher"]}
        names |= {k: gone[k] for k in gone if k in everyone}
        names |= {k: k.title() for k in everyone if k and k not in listed}      # no longer on the roster
    c = count_missing(regs, set(names))
    who = {"ol": sorted(names[k] for k in regs["ol"] & set(names)),
           "back": sorted(names[k] for k in regs["back"] & set(names)),
           "top_target": [names[regs["top_target"]]] if regs["top_target"] in names else [],
           "rusher": [names[regs["rusher"]]] if regs["rusher"] in names else []}
    return c | {"who": who}


def adjustments(counts: dict[str, dict], team: str, opp: str) -> dict[str, float]:
    """The game_nfl.project changes for `team`'s offense from its own and the opponent's
    missing regulars: {stat: change}."""
    out: dict[str, float] = {}
    for side, t in (("own", team), ("opp", opp)):
        for feat, effects in EFFECTS[side].items():
            n = float(counts.get(t, {}).get(feat, 0.0) or 0.0)
            for stat, per in effects.items():
                out[stat] = out.get(stat, 0.0) + n * per
    return {k: v for k, v in out.items() if v}


def sentence(counts: dict[str, dict], team: str, opp: str, name) -> str:
    """'Without Drake London (their top target) and 1 line starter, the Falcons' passing
    projects -0.07 EPA per dropback; ...' for the Games tab, or ''."""
    own, oth = counts.get(team, {}).get("who", {}), counts.get(opp, {}).get("who", {})
    adj = adjustments(counts, team, opp)
    parts = []
    missing = [f"{n} (top target)" for n in own.get("top_target", [])] + \
              [f"{n} (line starter)" for n in own.get("ol", [])]
    if missing and adj.get("pass_epa", 0) < 0:
        own_pass = sum(float(counts[team].get(f, 0) or 0) * EFFECTS["own"][f].get("pass_epa", 0)
                       for f in EFFECTS["own"])
        parts.append(f"Without {', '.join(missing)}, {name(team)}' passing loses about {abs(own_pass):.2f} EPA per dropback")
    helped = [f"{n} (top pass rusher)" for n in oth.get("rusher", [])] + [f"{n} (DB)" for n in oth.get("back", [])]
    if helped:
        parts.append(f"{name(opp)} are missing {', '.join(helped)}, which helps {name(team)}' passing game")
    return "; ".join(parts) + ("." if parts else "")
