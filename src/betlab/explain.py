"""Football explanations for picks, leans and parlay legs, in plain English.

The why-notes in picks.why_note are the math (break-even, market, model, EV). These
add the game: a player's role (snaps, targets, carries, recent lines), the matchup
(how this defense has treated his position compared with the league), game script
(spread and implied points), and teammates who are out. For game lines: what our
ratings expect each team to score, rest, and how much weight the ratings carry.

Every sentence comes from data we have; nothing is invented. When our model has no
weight, the note says the pick comes from the price, not from these factors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab.models import roles_nfl as R

UNIT = {"receptions": "catches", "receiving_yards": "receiving yards", "rushing_yards": "rushing yards",
        "passing_yards": "passing yards"}
POS = {"WR": "wide receivers", "TE": "tight ends", "RB": "running backs", "QB": "quarterbacks"}
TEAM_NAME = {"LV": "Las Vegas Raiders", "LAC": "Los Angeles Chargers", "LA": "Los Angeles Rams"}


def nickname(abbr: str, names: dict[str, str]) -> str:
    """'GB' -> 'Packers' (names: full team name -> abbreviation)."""
    full = TEAM_NAME.get(abbr) or next((n for n, a in names.items() if a == abbr), abbr)
    return full.split()[-1]


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _unit(stat: str, n: float) -> str:
    """'1 catch' / '3 catches'."""
    return "catch" if stat == "receptions" and round(n) == 1 else UNIT[stat]


def _list(values) -> str:
    v = [f"{x:g}" for x in values]
    return v[0] if len(v) == 1 else ", ".join(v[:-1]) + " and " + v[-1]


def defense_table(hist: R.History, before, teams, rp: R.RoleParams | None = None) -> pd.DataFrame:
    """Every defense's matchup multipliers (1.10 = allows 10% more than average), one row
    per team, for ranking a single matchup against the league."""
    rp = rp or R.RoleParams()
    rows = []
    for t in teams:
        m = R.matchup(hist, t, before, rp)
        rows.append({"team": t, **{f"{g}_{k}": m[g][k] for g in ("WR", "TE", "RB") for k in ("ypt", "catch")},
                     "RB_ypc": m["RB"]["ypc"]})
    return pd.DataFrame(rows).set_index("team")


def _matchup_phrase(opp_name: str, value: float, col: pd.Series, what: str) -> tuple[str, int]:
    """('The Falcons have allowed 8% more yards per target to WRs than average (5th-most)', +1)"""
    pct = (value - 1) * 100
    rank = int((col > value).sum()) + 1
    if abs(pct) < 3:
        return f"the {opp_name} have been about league-average on {what}", 0
    more = pct > 0
    where = f"{_ordinal(rank)}-most" if more else f"{_ordinal(len(col) - rank + 1)}-fewest"
    return (f"the {opp_name} have allowed {abs(pct):.0f}% {'more' if more else 'fewer'} {what} than the "
            f"league average over their last 16 games ({where} in the NFL)", 1 if more else -1)


def prop_facts(prep: dict, hist: R.History, player_id: str, stat: str, draws: np.ndarray | None,
               defenses: pd.DataFrame, names: dict[str, str]) -> dict | None:
    """What we know about one player's prop, from the same inputs the simulator used."""
    for team, inp in prep["inputs"].items():
        pl = inp["players"]
        if len(pl) and (pl["player_id"] == player_id).any():
            break
    else:
        return None
    row = pl.set_index("player_id").loc[player_id]
    opp = prep["away"] if team == prep["home"] else prep["home"]
    spread_team = prep["spread_home"] if team == prep["home"] else -prep["spread_home"]
    recent = hist.player(player_id, prep["kickoff"]).tail(3)
    return {
        "name": row["name"], "position": row["position"], "team": nickname(team, names),
        "opp": nickname(opp, names), "opp_abbr": opp, "stat": stat,
        "snap": row["snap"], "recent": recent, "vol": inp["volume"],
        "exp_targets": row["t_share"] * inp["volume"]["targets"],
        "exp_carries": row["c_share"] * inp["volume"]["carries"],
        "matchup": prep["inputs"][team]["matchup"], "defenses": defenses,
        "spread": spread_team, "implied": (prep["total"] + spread_team) / 2, "total": prep["total"],
        "missing": inp.get("missing", []), "median": float(np.median(draws)) if draws is not None else None,
    }


def _factors(f: dict) -> list[tuple[str, int]]:
    """(sentence, direction for the over: +1 helps, -1 hurts, 0 neutral)."""
    out = []
    stat, pos, r = f["stat"], f["position"], f["recent"]
    receiving, rushing, passing = stat in ("receptions", "receiving_yards"), stat == "rushing_yards", stat == "passing_yards"
    # Role
    if len(r):
        snaps = r["offense_pct"].dropna()
        snap_txt = f"{snaps.mean():.0%} of snaps" if len(snaps) else "an unknown share of snaps"
        values = r[stat].tolist()
        if receiving:
            role = (f"{f['name']} has played {snap_txt} over his last {len(r)} games with "
                    f"{r['targets'].mean():.1f} targets a game ({UNIT[stat]}: {_list(values)})")
        elif rushing:
            role = (f"{f['name']} has played {snap_txt} over his last {len(r)} games with "
                    f"{r['carries'].mean():.1f} carries a game (rushing yards: {_list(values)})")
        else:
            role = (f"{f['name']} has thrown {r['attempts'].mean():.0f} passes a game over his last {len(r)} "
                    f"(passing yards: {_list(values)})")
        out.append((role, 0))
        if len(snaps) >= 2 and not passing:
            change = snaps.iloc[-1] - snaps.iloc[:-1].mean()
            if change >= 0.15:
                out.append((f"his snaps are climbing (to {snaps.iloc[-1]:.0%} last game)", 1))
            elif change <= -0.15:
                out.append((f"his snaps dropped to {snaps.iloc[-1]:.0%} last game", -1))
    else:
        out.append((f"{f['name']} has no NFL games in our data yet, so his role is a guess", 0))
    # Teammates out
    for m in f["missing"]:
        share = m["t_share"] if (receiving or passing) else m["c_share"]
        if share >= 0.05 and not (rushing and m["position"] not in ("RB", "QB")):
            kind = "carries" if rushing else "targets"
            out.append((f"with {m['name']} out, about {share:.0%} of the {f['team']}' {kind} are up for grabs",
                        1 if not passing else 0))
    # Matchup
    d = f["defenses"]
    if receiving:
        grp = pos if pos in ("WR", "TE", "RB") else "WR"
        key = f"{grp}_catch" if stat == "receptions" else f"{grp}_ypt"
        what = f"{'catch rate' if stat == 'receptions' else 'yards per target'} to {POS[grp]}"
        if f["opp_abbr"] in d.index:
            out.append(_matchup_phrase(f["opp"], d.loc[f["opp_abbr"], key], d[key], what))
    elif rushing:
        if f["opp_abbr"] in d.index:
            out.append(_matchup_phrase(f["opp"], d.loc[f["opp_abbr"], "RB_ypc"], d["RB_ypc"],
                                       "yards per carry to running backs"))
    elif f["opp_abbr"] in d.index:
        blend = d["WR_ypt"] * 0.6 + d["TE_ypt"] * 0.2 + d["RB_ypt"] * 0.2
        out.append(_matchup_phrase(f["opp"], blend.loc[f["opp_abbr"]], blend, "yards per pass target"))
    # Game script
    fav = f["spread"] > 0
    size = abs(f["spread"])
    who = (f"the {f['team']} are {size:g}-point {'favorites' if fav else 'underdogs'} with about "
           f"{f['implied']:.0f} implied points") if size >= 1 else f"the {f['team']} are in a pick'em game"
    if size >= 3:
        if rushing:
            out.append((who + (", and leading teams run more late" if fav else ", and trailing teams run less"),
                        1 if fav else -1))
        else:
            out.append((who + (", and leading teams lean on the run late" if fav else ", and trailing teams throw more"),
                        -1 if fav else 1))
    else:
        out.append((who, 0))
    if f["total"] >= 48:
        out.append((f"a {f['total']:g}-point total points to plenty of plays", 1))
    elif f["total"] <= 40:
        out.append((f"a low {f['total']:g}-point total points to a slow game", -1))
    return out


def prop_story(f: dict, side: str, point: float, w_model: float = 0.0, shifted: bool = True) -> str:
    """The football picture for one side of a prop, then which factors point each way."""
    facts = _factors(f)
    sign = 1 if side == "Over" else -1
    first = facts[0][0]
    pro = [t for t, d in facts[1:] if d * sign > 0]
    con = [t for t, d in facts[1:] if d * sign < 0]
    flat = [t for t, d in facts[1:] if d == 0]
    parts = [first[0].upper() + first[1:] + "."]
    if f["stat"] in ("receptions", "receiving_yards") and f["exp_targets"] > 0:
        parts.append(f"We project about {f['exp_targets']:.1f} targets"
                     + (f" and a median of {f['median']:.0f} {_unit(f['stat'], f['median'])}." if f["median"] is not None else "."))
    elif f["stat"] == "rushing_yards" and f["exp_carries"] > 0:
        parts.append(f"We project about {f['exp_carries']:.1f} carries"
                     + (f" and a median of {f['median']:.0f} rushing yards." if f["median"] is not None else "."))
    if pro:
        parts.append(f"For the {side.lower()}: " + "; ".join(pro) + ".")
    if con:
        parts.append(f"Against it: " + "; ".join(con) + ".")
    if flat:
        parts.append(flat[0][0].upper() + "; ".join(flat)[1:] + ".")
    if f["stat"] in ("receptions", "receiving_yards"):
        parts.append("And in 2025, overs on these props hit about 4 points less often than the market "
                     "priced them, which our fair price corrects for." if shifted else
                     "In 2025, overs on these props hit about 4 points less often than the market priced "
                     "them; 2026 hasn't shown that yet, so the price here is the market's, uncorrected.")
    if w_model == 0:
        parts.append("Our model has no weight yet, so this is the picture, not the reason: the pick comes "
                     "from FanDuel's price against the market.")
    return " ".join(parts)


def leg_note(f: dict) -> str:
    """One short line of football context for a parlay leg."""
    bits = []
    r = f["recent"]
    if len(r):
        snaps = r["offense_pct"].dropna()
        if len(snaps) and f["position"] != "QB":
            bits.append(f"{snaps.mean():.0%} of snaps")
        if f["stat"] in ("receptions", "receiving_yards"):
            bits.append(f"{r['targets'].mean():.1f} targets/game")
        elif f["stat"] == "rushing_yards":
            bits.append(f"{r['carries'].mean():.1f} carries/game")
        elif f["stat"] == "passing_yards":
            bits.append(f"{r['attempts'].mean():.0f} attempts/game")
        if f["stat"] in r:
            bits.append("last " + str(len(r)) + ": " + _list(r[f["stat"]].tolist()))
    for text, d in _factors(f)[1:]:
        if "allowed" in text:
            bits.append(text.replace("the " + f["opp"] + " have ", f"{f['opp']} have "))
            break
    return " · ".join(bits)


def game_line_story(g, market: str, home: str, away: str, center: float | None, w: float,
                    early: bool, names: dict[str, str] | None = None) -> str:
    """What our ratings say about a game, for a spread, total or moneyline."""
    # NFL teams read "the Packers ... have"; colleges read "Florida State ... has".
    if names:
        h, a = "the " + nickname(home, names), "the " + nickname(away, names)
        has = "have"
    else:
        h, a, has = home, away, "has"
    parts = []
    ph, pa = float(g["pts_home"]), float(g["pts_away"])
    margin = float(g["model_margin"])
    if market == "totals":
        parts.append(f"Our ratings, built from every team's recent scoring and what their defenses allow, "
                     f"expect about {ph:.0f} for {h} and {pa:.0f} for {a}: {float(g['model_total']):.0f} "
                     f"points" + (f", against a market total of {center:.1f}." if center is not None else "."))
    else:
        fav, dog = (h, a) if margin > 0 else (a, h)
        parts.append(f"Our ratings, built from every team's recent scoring and what their defenses allow, "
                     f"expect about {ph:.0f}-{pa:.0f} {h.removeprefix('the ')}: {fav} by {abs(margin):.1f}"
                     + (f", while the market has {h if center > 0 else a} by {abs(center):.1f}." if center is not None
                        and market == "spreads" else "."))
    rest = float(g.get("rest_diff", 0) or 0)
    if abs(rest) >= 3:
        team = h if rest > 0 else a
        parts.append(f"{team[0].upper() + team[1:]} {has} {abs(rest):.0f} more days of rest.")
    if early:
        parts.append("It's early in the season, so the ratings are still settling and get no weight: "
                     "the pick comes from FanDuel's price against the sharp market.")
    elif w < 0.1:
        parts.append(f"Backtests give our ratings only {w:.0%} weight against the sharp market, so this is "
                     "context: the pick comes from FanDuel's price lagging the market.")
    else:
        parts.append(f"Our ratings carry {w:.0%} of the final number here, earned in backtests.")
    return " ".join(parts)


THEME_STORY = {
    "QB + receiver stack": "A quarterback's passing yards are his receivers' yards, so when one has a big day "
                           "the other usually does too.",
    "Shootout": "Both passing games have to produce; a back-and-forth game lifts both quarterbacks.",
    "Scorer + yards": "Touchdowns come with yards: a player who scores usually had the ball a lot.",
    "Ground game": "A team that gets ahead leans on its running game, and its running backs pile up carries.",
    "Role shift": "The legs bet on where the ball goes: if one player gets it, the others don't.",
    "Low-scoring grind": "A slow, low-scoring game keeps everyone's numbers down together.",
    "Correlated overs": "These legs tend to rise and fall together in our simulations.",
    "Win it with them": "The team wins (or covers) when these players have big days: the legs ride one team's good game.",
}


def slip_story(doc: dict, prep: dict, names: dict[str, str]) -> str:
    """Why these legs belong together, in football terms, for one parlay slip."""
    home, away = nickname(prep["home"], names), nickname(prep["away"], names)
    spread = prep["spread_home"]
    fav, dog = (home, away) if spread > 0 else (away, home)
    parts = [THEME_STORY.get(doc["theme"], THEME_STORY["Correlated overs"])]
    parts.append(f"The {fav} are {abs(spread):g}-point favorites in a {prep['total']:g}-point game"
                 if abs(spread) >= 1 else f"It's a pick'em in a {prep['total']:g}-point game")
    parts[-1] += "."
    if doc.get("longshot"):
        parts.insert(0, f"The long shot: it hits about 1 in {1 / doc['p_fair']:.0f}, so treat it as a lottery ticket.")
    for l in doc["legs"]:
        if l["side"] == "under":
            parts.append(f"The one under, {l['label']}, is here as a near-lock ({l['p_fair']:.0%}).")
    return " ".join(parts)


def script_story(sc: dict | None, names: dict[str, str]) -> str:
    """The game a one-story slip needs, from sgp.script: who wins, how many points, who throws,
    in the simulated games where every leg hits compared with all of them. Only clear shifts
    (5+ points of win chance, 3+ total points, 20+ passing yards) are named."""
    if not sc:
        return ""
    home, away = nickname(sc["home"], names), nickname(sc["away"], names)
    parts = []
    d = sc["p_home_hit"] - sc["p_home"]
    if abs(d) >= 0.05:
        team, p, base = (home, sc["p_home_hit"], sc["p_home"]) if d > 0 else (away, 1 - sc["p_home_hit"], 1 - sc["p_home"])
        parts.append(f"the {team} winning ({p:.0%} of the games where it hits, {base:.0%} overall)")
    dt = sc["total_hit"] - sc["total"]
    if abs(dt) >= 3:
        parts.append(f"{'more' if dt > 0 else 'fewer'} points (about {sc['total_hit']:.0f} vs {sc['total']:.0f})")
    for side, team in (("home", home), ("away", away)):
        if f"pass_{side}" in sc:
            dp = sc[f"pass_{side}_hit"] - sc[f"pass_{side}"]
            if abs(dp) >= 20:
                parts.append(f"the {team} {'throwing more' if dp > 0 else 'throwing less'} "
                             f"({sc[f'pass_{side}_hit']:.0f} passing yards vs {sc[f'pass_{side}']:.0f})")
    if not parts:
        return "One story: the legs don't need a particular script, and none of them pulls against another."
    body = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"One story: this slip needs {body}. No two legs pull against each other."
