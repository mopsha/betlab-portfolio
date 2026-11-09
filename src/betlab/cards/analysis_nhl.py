"""NHL game analysis for the Games tab, NFL-style: how the game should go and where it's decided.

For one game, from the team ratings (models/nhl.fit), the special-teams ratings
(models/nhl.special_ratings), tonight's goalies and the injury report:
- `matchups`: "where it's decided", each a sentence and a size in standard deviations
  (positive favors the attacking side): each team's shot volume against the other's shot
  suppression, each power play against the other's penalty kill, the goalie gap, and
  finishing.
- `script`: a short story of the game: who should control play, the special-teams edge, the
  goaltending, back-to-backs and who's missing.
- `hurt`: each team's injured players with their recent ice time and share of the team's
  shots, so a missing top-line shooter stands out.
These are reads, not prices: none of them has been tested against the market yet (the
props model below tests which ones help: models/props_nhl.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab.models import nhl as M

GOALIE_SD = 0.008          # spread of starters' shrunk save % (about one standard deviation)


def _ord(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def matchups(r: M.Ratings, sr: pd.DataFrame, home: str, away: str, home_goalie: str | None,
             away_goalie: str | None) -> list[dict]:
    """Where it's decided, biggest first."""
    out = []
    sd_shots = float(np.std(r.off["shots"] + 0)) * np.sqrt(2) or 1.0
    for att, dfd in ((home, away), (away, home)):
        z = (float(r.off["shots"].get(att, 0)) + float(r.dfn["shots"].get(dfd, 0))) / sd_shots
        out.append({"text": f"{att}'s shot volume ({_ord(int((-r.off['shots']).rank(method='min').get(att, 16)))}) vs "
                            f"{dfd}'s shot suppression ({_ord(int(r.dfn['shots'].rank(method='min').get(dfd, 16)))})",
                    "size": round(z, 2), "kind": "shots", "team": att})
    if len(sr) and home in sr.index and away in sr.index:
        sd_pp = float(np.std(sr["pp_pct"])) * np.sqrt(2) or 0.02
        for att, dfd in ((home, away), (away, home)):
            e = M.expected_pp_goals(sr, att, dfd)
            z = (e["conversion"] - sr.attrs["league"]["pp_pct"]) / sd_pp
            out.append({"text": f"{att}'s power play ({_ord(int(sr.loc[att, 'pp_rank']))}) vs {dfd}'s penalty kill "
                                f"({_ord(int(sr.loc[dfd, 'pk_rank']))}): {e['chances']:.1f} chances, "
                                f"{e['pp_goals']:.2f} goals expected",
                        "size": round(z, 2), "kind": "special", "team": att})
    gh, ga = M.goalie_sv(r, home_goalie), M.goalie_sv(r, away_goalie)
    if home_goalie and away_goalie:
        better, worse, gap = (home_goalie, away_goalie, gh - ga) if gh >= ga else (away_goalie, home_goalie, ga - gh)
        out.append({"text": f"In net: {better} ({gh if better == home_goalie else ga:.3f}) over {worse} "
                            f"({ga if better == home_goalie else gh:.3f})",
                    "size": round(gap / GOALIE_SD, 2), "kind": "goalie", "team": home if better == home_goalie else away})
    out.sort(key=lambda m: -abs(m["size"]))
    return out


def hurt(injuries: pd.DataFrame, skaters: pd.DataFrame, team: str, asof_date) -> list[dict]:
    """A team's injured players with recent ice time and shot share (last 10 team games)."""
    inj = injuries[injuries["team"] == team] if len(injuries) else injuries
    if inj is None or inj.empty:
        return []
    from betlab.sources.nhl import _plain

    sk = skaters[(skaters["team"] == team) & (skaters["date"] < pd.Timestamp(asof_date))]
    last = sorted(sk["game_id"].unique())[-10:]
    recent = sk[sk["game_id"].isin(last)]
    team_shots = recent["shots"].sum() or 1.0
    by = recent.assign(plain=recent["player"].map(_plain)).groupby("plain").agg(
        toi=("toi", "mean"), shots=("shots", "sum"), games=("game_id", "nunique"))
    rows = []
    for i in inj.itertuples():
        info = by.loc[i.plain] if i.plain in by.index else None
        rows.append({"player": i.player, "pos": i.pos, "status": i.status, "injury": i.detail,
                     "toi_min": round(float(info["toi"]) / 60, 1) if info is not None else None,
                     "shot_share": round(float(info["shots"]) / team_shots, 3) if info is not None else None,
                     "recent_games": int(info["games"]) if info is not None else 0})
    rows.sort(key=lambda x: -(x["toi_min"] or 0))
    return rows


def script(home: str, away: str, pr: dict, sr: pd.DataFrame, goalies: dict, b2b: dict, hurt_rows: dict,
           r: M.Ratings) -> str:
    """The game in a few sentences, from the projection and the reads."""
    hs, as_ = pr["home_shots"], pr["away_shots"]
    share = hs / (hs + as_)
    lead, trail = (home, away) if share >= 0.5 else (away, home)
    s = [f"{lead} should drive play: about {max(hs, as_):.0f} shots to {min(hs, as_):.0f} "
         f"({max(share, 1 - share):.0%} of the shots)." if abs(share - 0.5) >= 0.02 else
         f"An even game on the shot clock: about {hs:.0f} shots each way."]
    if len(sr) and home in sr.index and away in sr.index:
        eh, ea = M.expected_pp_goals(sr, home, away), M.expected_pp_goals(sr, away, home)
        if abs(eh["pp_goals"] - ea["pp_goals"]) >= 0.12:
            best, other, e_best = (home, away, eh) if eh["pp_goals"] > ea["pp_goals"] else (away, home, ea)
            s.append(f"Special teams lean {best}: its power play ({_ord(int(sr.loc[best, 'pp_rank']))}) against "
                     f"{other}'s penalty kill ({_ord(int(sr.loc[other, 'pk_rank']))}) is worth about "
                     f"{e_best['pp_goals']:.2f} goals.")
    gh, ga = M.goalie_sv(r, goalies["home"][0]), M.goalie_sv(r, goalies["away"][0])
    if goalies["home"][0] and goalies["away"][0]:
        if abs(gh - ga) >= GOALIE_SD:
            g_best = (goalies["home"][0], home) if gh > ga else (goalies["away"][0], away)
            s.append(f"The goaltending favors {g_best[1]}: {g_best[0]} ({max(gh, ga):.3f}) vs {min(gh, ga):.3f}.")
        else:
            s.append(f"Goaltending is close: {goalies['away'][0]} ({ga:.3f}) and {goalies['home'][0]} ({gh:.3f}).")
    tired = [t for t in (home, away) if b2b.get(t)]
    if tired:
        s.append(f"{' and '.join(tired)} played last night.")
    for t in (home, away):
        big = [h for h in hurt_rows.get(t, []) if (h["shot_share"] or 0) >= 0.08 and h["status"] != "Day-To-Day"]
        if big:
            s.append(f"{t} is without {', '.join(h['player'] for h in big[:2])} "
                     f"({sum(h['shot_share'] for h in big[:2]):.0%} of its recent shots).")
    s.append(f"About {pr['exp_total']:.1f} goals in all, counting empty nets and overtime.")
    return " ".join(s)
