"""The Notebook on an NFL game page (Mike, Nov 6: "our analysis should work a lot like" @conchpicks' TikTok notebooks).

His notes run one way: the story of the game (who will have to throw, who will run), what changed (a new QB, who is
out), the opponent's recent pattern in plain counts ("4 for 34, 2 for 25, 11 for 71 to backs"), then one bet or
"nothing here". This writes the first three from what the preview already knows; the apps add the bet from the game's
own picks and leans (our prices decide it, as everywhere else), or say there is nothing worth betting.

The words explain; they set no price. The scheme angles behind his notes (blitz, shells, personnel) didn't beat the
market on 2024-25 lines (docs/DECISIONS.md 2026-11-06), and neither did the opponent patterns' ancestors (target
funnels, Sep 25): a pattern here is context, never a reason a bet qualifies.
"""

from __future__ import annotations

import pandas as pd

# who the pattern is about: the position group, what it caught or ran, and the words for it
GROUPS = (("RB", "receiving", "running backs' catches"), ("WR", "receiving", "wide receivers' catches"),
          ("TE", "receiving", "tight ends' catches"), ("RB", "rushing", "running backs' carries"))
GAMES = 3


def allowed(stats: pd.DataFrame, defense: str, before: pd.Timestamp, n: int = GAMES) -> dict:
    """What a defense gave up to each group in its last `n` games before `before`, game by game (oldest first), and the
    league's per-game average this season for the same group. stats: weekly player rows with date, opponent_team,
    position, receptions, receiving_yards, carries, rushing_yards."""
    s = stats[stats["date"] < before]
    if s.empty:
        return {}
    vs = s[s["opponent_team"] == defense]
    games = vs.drop_duplicates("game_id").sort_values("date")["game_id"].tail(n).tolist()
    out = {}
    for pos, kind, _ in GROUPS:
        a, b = ("receptions", "receiving_yards") if kind == "receiving" else ("carries", "rushing_yards")
        g = s[s["position"] == pos]
        per_game = g.groupby(["game_id", "team"])[[a, b]].sum()
        league = per_game.mean() if len(per_game) else pd.Series({a: 0.0, b: 0.0})
        mine = vs[(vs["position"] == pos) & vs["game_id"].isin(games)].groupby("game_id")[[a, b]].sum().reindex(games).fillna(0)
        out[(pos, kind)] = {"games": [(int(r[a]), int(r[b])) for _, r in mine.iterrows()],
                            "league": (float(league[a]), float(league[b]))}
    return out


def pattern(defense_name: str, offense_name: str, a: dict) -> dict | None:
    """The group this defense has given up the most to lately, against the league (yards, as a share above the
    average), in his form: "Jaguars' defense, last 3 games, running backs' catches: 4 for 34, 2 for 25, 11 for 71
    (league 5.1 for 38 a game)". None when no group runs 20%+ over the league or there are fewer than 2 games. A
    trend, not one blowout: at least 2 of the games must be over the league's average on their own ("1 for -1, 6 for 45,
    9 for 143" was one big game, Nov 6)."""
    best, best_key = 0.2, None
    for key, v in a.items():
        if len(v["games"]) < 2 or v["league"][1] <= 0 or sum(y > v["league"][1] for _, y in v["games"]) < 2:
            continue
        over = sum(y for _, y in v["games"]) / len(v["games"]) / v["league"][1] - 1
        if over > best:
            best, best_key = over, key
    if best_key is None:
        return None
    v, words = a[best_key], next(w for p, k, w in GROUPS if (p, k) == best_key)
    counts = ", ".join(f"{c} for {y}" for c, y in v["games"])
    lc, ly = v["league"]
    return {"defense": defense_name, "group": best_key[0], "kind": best_key[1], "over": round(best, 2),
            "games": [list(x) for x in v["games"]],
            "text": f"{defense_name} defense, last {len(v['games'])} games, {words}: {counts} "
                    f"(league {lc:.1f} for {ly:.0f} a game). Something for the {offense_name} to look at."}


def story(entry: dict, name) -> str:
    """The game in two sentences: the market's score, and who the script says will throw more or less than usual."""
    m, parts = entry.get("market"), []
    if m:
        fav, by = (entry["home"], m["spread_home"]) if m["spread_home"] >= 0 else (entry["away"], -m["spread_home"])
        parts.append(f"The market has the {name(fav)} by {by:g} in a {m['total']:g}-point game." if by >= 0.5
                     else f"The market has it even in a {m['total']:g}-point game.")
    for t in (entry["away"], entry["home"]):
        r = (entry.get("script_read") or {}).get(t) or {}
        d = r.get("dropbacks_vs_usual")
        if d is None:
            continue
        if d >= 0.05:
            parts.append(f"The {name(t)} should throw more than usual, about {round(100 * d)}% more dropbacks.")
        elif d <= -0.05:
            parts.append(f"The {name(t)} should throw less than usual, about {round(-100 * d)}% fewer dropbacks.")
    return " ".join(parts)


def changes(entry: dict) -> list[str]:
    """What's different this week: a new QB, and who is out with what it does (the preview's own sentences)."""
    out = [q["text"] for q in (entry.get("qbs") or {}).values() if q.get("change") and q.get("text")]
    out += [t for t in (entry.get("injury_effects") or {}).values() if t]
    return out


def build(entry: dict, stats: pd.DataFrame | None, before: pd.Timestamp, name) -> dict:
    """The notebook for one preview entry: story, changes, and each defense's pattern (none without stats)."""
    pats = []
    if stats is not None and len(stats):
        for defense, offense in ((entry["home"], entry["away"]), (entry["away"], entry["home"])):
            p = pattern(f"{name(defense)}'", name(offense), allowed(stats, defense, before))
            if p:
                pats.append(p)
    return {"story": story(entry, name), "changes": changes(entry), "patterns": pats}
