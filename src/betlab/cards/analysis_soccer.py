"""The soccer game page's analysis (Mike, 2026-10-10: "keep going with the soccer analysis").

For every soccer match in the next day and a half (exports/soccer_analysis.json, merged into the
app's soccer games by export-page):

- **The market's expected goals** for each team (the sharp 1X2 and goals line fit to a score
  grid, cards/fun_soccer).
- **Projected shots and shots on target** per team: the shots model's means for the starters
  (cards/props_soccer.means), divided by the share of a team's shots its starters take (history).
- **Shot form:** each team's shots for and against over its last 10 league matches, ranked in its
  league this season.
- **Rotation:** with the lineup out (about an hour before kickoff), changes from the team's last
  XI and the regulars (4+ starts in the last 5) not starting. Before that, each team's last XI
  stands in, labeled "expected".
- **Rest:** days since each team's last league match.
- **Likeliest shooters:** the top starters by expected shots, with FanDuel's rungs and the
  model's chance at each (tracking_soccer_props; the model has no weight).
- **Moneyline read** (Mike, 2026-10-15): the 3-way in one place. The sharp no-vig chances now
  and at our first look (the move), the best price per side at FanDuel or DraftKings with its EV,
  European games within 4 days either side (from the line tracker: our history has no cup matches),
  and the lineup's 1X2 (its expected goals on a score grid) with its live record against the market
  (soccer_goal_reads). Built for every tracked match in the horizon, analysis or not.

These are reads, not prices. They show what the model sees so Mike can judge the props himself.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from betlab import config
from betlab.models import props_soccer as PS

OUT = config.EXPORTS_DIR / "soccer_analysis.json"
HORIZON = pd.Timedelta(hours=36)
SHOOTERS = 3                                   # per team
MIN_KNOWN_STARTERS = 9                         # of a team's 11 starters with player history before its lineup totals show


def starter_share(history: pd.DataFrame) -> dict[str, float]:
    """The share of a team's shots and shots on target its starters take (the rest: substitutes)."""
    h = history[history["minutes"] > 0]
    h = h.assign(ga=h["goals"] + h["assists"]) if "ga" not in h and {"goals", "assists"} <= set(h) else h
    out = {}
    for t in PS.TARGETS:
        if t not in h:
            continue
        tot = h[t].sum()
        out[t] = float(h.loc[h["starter"].astype(bool), t].sum() / tot) if tot else 0.85
    return out


def team_form(history: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Per team: shots for and against over its last n league matches, its latest league and
    kickoff, and its league rank this season (1 = most shots for / fewest against)."""
    tm = history.groupby(["event_id", "team"], as_index=False).agg(
        league=("league", "first"), season=("season", "first"), kickoff=("kickoff", "first"),
        opponent=("opponent", "first"), shots=("shots", "sum"))
    opp = tm[["event_id", "team", "shots"]].rename(columns={"team": "opponent", "shots": "against"})
    tm = tm.merge(opp, on=["event_id", "opponent"], how="left")
    tm["kickoff"] = pd.to_datetime(tm["kickoff"], utc=True, format="ISO8601")
    tm = tm.sort_values("kickoff")
    last = tm.groupby("team").tail(n).groupby("team").agg(shots_for=("shots", "mean"), shots_against=("against", "mean"),
                                                          league=("league", "last"), season=("season", "last"),
                                                          last_match=("kickoff", "last"))
    cur = tm[tm["season"] == tm.groupby("league")["season"].transform("max")]
    season_avg = cur.groupby(["league", "team"]).agg(sf=("shots", "mean"), sa=("against", "mean")).reset_index()
    season_avg["rank_for"] = season_avg.groupby("league")["sf"].rank(ascending=False, method="min")
    season_avg["rank_against"] = season_avg.groupby("league")["sa"].rank(ascending=True, method="min")
    season_avg["n_teams"] = season_avg.groupby("league")["team"].transform("count")
    return last.join(season_avg.set_index("team")[["rank_for", "rank_against", "n_teams"]], how="left")


def last_xi(history: pd.DataFrame, team: str) -> pd.DataFrame:
    """The team's starters in its most recent match."""
    t = history[history["team"] == team]
    if t.empty:
        return t
    eid = t.sort_values("kickoff")["event_id"].iloc[-1]
    return t[(t["event_id"] == eid) & t["starter"].astype(bool)]


def regulars(history: pd.DataFrame, team: str, n: int = 5, starts: int = 4) -> pd.DataFrame:
    """Players with `starts`+ starts in the team's last n matches: who's missing if they don't start."""
    t = history[history["team"] == team]
    ids = t.sort_values("kickoff")["event_id"].drop_duplicates().iloc[-n:]
    r = t[t["event_id"].isin(ids) & t["starter"].astype(bool)].groupby(["player_id", "player"]).size()
    return r[r >= starts].reset_index()[["player_id", "player"]]


def expected_squad(history: pd.DataFrame, espn_id: str, home: str, away: str, kickoff) -> pd.DataFrame:
    """Both teams' last XIs as tonight's squad (before the lineups are out)."""
    rows = []
    for team, opp, is_home in ((home, away, True), (away, home, False)):
        xi = last_xi(history, team)
        for r in xi.itertuples():
            rows.append({"event_id": str(espn_id), "kickoff": pd.Timestamp(kickoff), "team": team, "opponent": opp,
                         "home": is_home, "player_id": str(r.player_id), "player": r.player, "position": r.position,
                         "formation_place": r.formation_place, "starter": True, "came_on": False})
    return pd.DataFrame(rows)


def rotation(history: pd.DataFrame, squad: pd.DataFrame, team: str) -> dict:
    """Changes from the team's last XI and regulars not starting (a confirmed lineup only)."""
    xi = set(squad.loc[(squad["team"] == team) & squad["starter"].astype(bool), "player_id"].astype(str))
    before = last_xi(history, team)
    prev = set(before["player_id"].astype(str))
    reg = regulars(history, team)
    missing = reg[~reg["player_id"].astype(str).isin(xi)]["player"].tolist()
    return {"changes": len(prev - xi) if prev else None, "missing": missing}


def _rungs(lines: pd.DataFrame, event_id: str, player: str, stat: str) -> list[dict]:
    g = lines[(lines["event_id"].astype(str) == str(event_id)) & (lines["player"] == player) & (lines["stat"] == stat)]
    return [{"line": float(r.line), "fd_price": float(r.fd_price),
             "link": r.fd_link if "fd_link" in g and isinstance(r.fd_link, str) else None,
             "p_model": None if pd.isna(r.p_model) else round(float(r.p_model), 4),
             "p_fd_fair": None if pd.isna(r.p_fd_fair) else round(float(r.p_fd_fair), 4)}
            for r in g.sort_values("line").itertuples()]


def _pin(lines: pd.DataFrame, event_id: str, player: str) -> float | None:
    """Pinnacle's no-vig scorer chance on the props tracker's row, when it posted one."""
    g = lines[(lines["event_id"].astype(str) == str(event_id)) & (lines["player"] == player) & (lines["stat"] == "scorer")]
    return None if g.empty or pd.isna(g["p_market"].iloc[0]) else round(float(g["p_market"].iloc[0]), 4)


EUROPE = pd.Timedelta(days=4)                  # a cup match this close either side is congestion
MOVE = 0.02                                    # a sharp move worth a sentence (2 points)
LINEUP_GAP = 0.08                              # a lineup read this far from the market gets a sentence


def one_x_two(xg_home: float, xg_away: float) -> tuple[float, float, float]:
    """(home, draw, away) chances from two teams' expected goals on the Dixon-Coles score grid."""
    import numpy as np
    from betlab.models.soccer import score_matrix

    m = score_matrix(xg_home, xg_away)
    m = m / m.sum()
    i, j = np.indices(m.shape)
    return float(m[i > j].sum()), float(m[i == j].sum()), float(m[i < j].sum())


def lineup_record(reads: pd.DataFrame | None = None) -> dict | None:
    """The lineup 1X2 read's graded record against the market's (1X2 log loss; lower is better)."""
    import numpy as np
    from betlab import soccer_goal_reads

    d = soccer_goal_reads.load() if reads is None else reads
    if d.empty:
        return None
    d = d[pd.to_numeric(d["home_goals"], errors="coerce").notna()]
    d = d.dropna(subset=["xg_home", "xg_away", "xg_home_mkt", "xg_away_mkt"])
    if d.empty:
        return None
    mine, mkt = [], []
    for r in d.itertuples():
        hg, ag = float(r.home_goals), float(r.away_goals)
        o = 0 if hg > ag else 1 if hg == ag else 2
        mine.append(-np.log(max(one_x_two(float(r.xg_home), float(r.xg_away))[o], 1e-6)))
        mkt.append(-np.log(max(one_x_two(float(r.xg_home_mkt), float(r.xg_away_mkt))[o], 1e-6)))
    return {"n": len(mine), "log_loss": round(float(np.mean(mine)), 4), "log_loss_mkt": round(float(np.mean(mkt)), 4)}


def cup_games(tracked: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per European cup match in the line tracker: league, event_id, home, away, t (kickoff)."""
    from betlab import tracking_soccer
    from betlab.cards.soccer import CUPS

    df = tracking_soccer.load() if tracked is None else tracked
    cols = ["league", "event_id", "home", "away", "t"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    c = df[df["league"].isin(CUPS)].drop_duplicates("event_id")
    return c.assign(t=pd.to_datetime(c["commence_time"], utc=True, format="ISO8601"))[cols]


def europe(cups: pd.DataFrame | None, team: str, kickoff, event_id) -> dict | None:
    """The team's nearest European cup match within EUROPE of this kickoff (negative days: before it)."""
    from betlab.cards.soccer import NAMES

    if cups is None or cups.empty:
        return None
    k = pd.Timestamp(kickoff)
    c = cups[((cups["home"] == team) | (cups["away"] == team)) & (cups["event_id"].astype(str) != str(event_id))]
    c = c.assign(gap=(c["t"] - k).dt.total_seconds() / 86400)
    c = c[c["gap"].abs() <= EUROPE.total_seconds() / 86400]
    if c.empty:
        return None
    r = c.loc[c["gap"].abs().idxmin()]
    return {"competition": NAMES.get(r["league"], r["league"]),
            "opponent": r["away"] if r["home"] == team else r["home"], "days": round(float(r["gap"]), 1)}


def _when(days: float) -> str:
    d = round(abs(days))
    if d == 0:
        return "today"
    n = "1 day" if d == 1 else f"{d} days"
    return f"{n} ago" if days < 0 else f"in {n}"


def _am(price) -> str:
    return f"{int(round(float(price))):+d}"


def moneyline(g: dict, teams: list[dict] | None = None, cups: pd.DataFrame | None = None,
              record: dict | None = None, confirmed: bool = False) -> dict | None:
    """The match's 3-way read: the market now vs our first look, the best price per side, European games
    nearby, and the lineup's 1X2 (no weight) with its record. g: a tracking_soccer.view game; teams: the
    analysis's teams (for the lineup's expected goals and rest)."""
    lines = [o for o in g.get("lines") or [] if o.get("p_market") is not None]
    if len(lines) != 3:
        return None
    home, away = g["home"], g["away"]
    by_team = {t["team"]: t for t in teams or []}
    gm = [by_team.get(home, {}).get("goals_model"), by_team.get(away, {}).get("goals_model")]
    lineup = one_x_two(*gm) if None not in gm else None
    sides = []
    for i, o in enumerate(lines):
        books = [("fanduel", o.get("price"), o.get("ev")), ("draftkings", o.get("dk_price"), o.get("dk_ev"))]
        books = [b for b in books if b[1] is not None and b[2] is not None]
        best = max(books, key=lambda b: (b[2], b[0] == "fanduel")) if books else None     # ties go to FanDuel
        first = o.get("first_p_market")
        sides.append({"side": o["side"], "p_market": round(float(o["p_market"]), 4),
                      "p_first": None if first is None else round(float(first), 4),
                      "move": None if first is None else round(float(o["p_market"]) - float(first), 4),
                      "best_book": best[0] if best else None, "best_price": best[1] if best else None,
                      "best_ev": round(float(best[2]), 4) if best else None,
                      "p_lineup": None if lineup is None else round(lineup[i], 4)})
    flags = {t: europe(cups, t, g["commence_time"], g["event_id"]) for t in (home, away)}
    out = {"sides": sides, "first_seen": g.get("first_seen"), "lineup": "confirmed" if confirmed else "expected",
           "europe": {t: e for t, e in flags.items() if e}, "lineup_record": record}
    out["summary"] = _ml_summary(out, home, away, by_team)
    return out


def _ml_summary(ml: dict, home: str, away: str, by_team: dict) -> str:
    """A few plain sentences: what the market says, how it moved, the best price, and what to watch."""
    sd = {s["side"]: s for s in ml["sides"]}
    parts = [f"The sharp market has {home} {sd[home]['p_market']:.0%}, the draw {sd['Draw']['p_market']:.0%} "
             f"and {away} {sd[away]['p_market']:.0%}."]
    moves = [s for s in ml["sides"] if s["move"] is not None and s["side"] != "Draw"]
    big = max(moves, key=lambda s: s["move"], default=None)
    if big is not None and big["move"] >= MOVE:
        parts.append(f"It has moved {big['move'] * 100:.0f} points toward {big['side']} since our first look.")
    elif moves:
        parts.append("It has barely moved since our first look.")
    priced = [s for s in ml["sides"] if s["best_ev"] is not None]
    if priced:
        b = max(priced, key=lambda s: s["best_ev"])
        book = "FanDuel" if b["best_book"] == "fanduel" else "DraftKings"
        at = f"{'The draw' if b['side'] == 'Draw' else b['side']} at {book} {_am(b['best_price'])}"
        if b["best_ev"] >= 0.03:
            parts.append(f"{at} is {b['best_ev']:+.1%} EV, a pick-level price.")
        elif b["best_ev"] > 0:
            parts.append(f"The best price: {at}, {b['best_ev']:+.1%} EV, under the 3% a pick needs.")
        else:
            parts.append(f"No side beats the sharp price at either book (closest: {at}, {b['best_ev']:+.1%} EV).")
    for team, e in ml["europe"].items():
        parts.append(f"{team} {'played' if e['days'] < 0 else 'play'} {e['opponent']} in the {e['competition']} "
                     f"{_when(e['days'])}.")
    if not ml["europe"]:
        rest = {t: by_team.get(t, {}).get("rest_days") for t in (home, away)}
        if None not in rest.values() and abs(rest[home] - rest[away]) >= 2:
            more = home if rest[home] > rest[away] else away
            parts.append(f"{more} have {abs(rest[home] - rest[away]):.0f} more days of rest.")
    lin = [s for s in ml["sides"] if s["p_lineup"] is not None]
    if lin and ml["lineup"] == "confirmed":
        g = max(lin, key=lambda s: s["p_lineup"] - s["p_market"])
        if g["p_lineup"] - g["p_market"] >= LINEUP_GAP:
            rec = ml.get("lineup_record")
            worse = bool(rec) and rec["n"] >= 10 and rec["log_loss"] > rec["log_loss_mkt"]
            parts.append(f"The lineup read leans {'the draw' if g['side'] == 'Draw' else g['side']} "
                         f"({(g['p_lineup'] - g['p_market']) * 100:+.0f} points), "
                         + ("but it has been worse than the market so far, so it has no weight."
                            if worse else "with no weight until it beats the market."))
    return " ".join(parts)


def _script(doc: dict) -> str:
    """Two or three plain sentences: who's expected to create more, and what changed."""
    h, a = doc["teams"]
    parts = []
    if h.get("xg") is not None and a.get("xg") is not None:
        fav = h if h["xg"] >= a["xg"] else a
        poss = a["team"] + ("'" if a["team"].endswith("s") else "'s")
        parts.append(f"The market has {h['team']} {h['xg']:.1f} goals to {poss} {a['xg']:.1f}"
                     + (f", so {fav['team']} should have most of the chances." if abs(h["xg"] - a["xg"]) >= 0.4 else
                        ", an even game."))
    if h.get("shots") is not None and a.get("shots") is not None:
        parts.append(f"Our shots model projects {h['shots']:.0f} shots to {a['shots']:.0f} "
                     f"({h['sot']:.1f} to {a['sot']:.1f} on target).")
    for t in (h, a):
        rot = t.get("rotation") or {}
        if rot.get("missing"):
            parts.append(f"{t['team']} start without {', '.join(rot['missing'][:3])}"
                         + (f" ({rot['changes']} change{'s' * (rot['changes'] != 1)})." if rot.get("changes") else "."))
        elif rot.get("changes") and rot["changes"] >= 4:
            parts.append(f"{t['team']} make {rot['changes']} changes from their last XI.")
    return " ".join(parts)


def build(games: list[dict], asof: pd.Timestamp, picks: dict | None = None, lines: pd.DataFrame | None = None,
          history: pd.DataFrame | None = None, find=None, lineup=None) -> dict:
    """{odds event id: analysis} for the soccer games (tracking_soccer.view's) in the next HORIZON.
    picks: {league: latest pick snapshot} for the market's xG; lines: the props tracker's rows;
    find(league, home, away, kickoff) -> ESPN id; lineup(league, espn_id) -> squad (tests pass fakes)."""
    from betlab.cards import props_soccer as C
    from betlab.sources import espn_soccer as E

    history = C._history() if history is None else history
    if history.empty:
        return {}
    find = find or E.find_event
    lineup = lineup or (lambda lg, eid: E.lineup(E.SLUGS[lg], eid))
    form = team_form(history)
    share = starter_share(history)
    todo = []
    for g in games:
        k = pd.Timestamp(g["commence_time"])
        if not (asof < k <= asof + HORIZON):
            continue
        try:
            espn_id = find(g["league"], g["home"], g["away"], k)
        except Exception:  # noqa: BLE001 - ESPN down: no analysis for this one
            espn_id = None
        if not espn_id:
            continue
        try:
            squad = lineup(g["league"], espn_id)
        except Exception:  # noqa: BLE001
            squad = pd.DataFrame()
        confirmed = squad is not None and len(squad) > 0 and squad["starter"].astype(bool).sum() >= 20
        names = None
        if confirmed:
            names = (squad.loc[squad["home"].astype(bool), "team"].iloc[0], squad.loc[~squad["home"].astype(bool), "team"].iloc[0])
        else:   # ESPN's own club names, from the scoreboard match
            from betlab.sources.soccer import similarity
            teams = form.index.tolist()
            best = lambda n: max(teams, key=lambda t: similarity(n, t)) if teams else None
            names = (best(g["home"]), best(g["away"]))
            squad = expected_squad(history, espn_id, names[0], names[1], k)
        pick = (picks or {}).get(g["league"])
        xg = C.market_xg(pick[pick["event_id"] == g["event_id"]] if pick is not None else None, g["home"], g["away"])
        todo.append((g, str(espn_id), squad, xg, confirmed, names))
    mus = C.means([(sq, g["league"], xg) for g, _, sq, xg, _, _ in todo if len(sq)], history=history) if todo else {}
    model = C.fitted()
    size = model.dispersion["shots"] if model is not None else PS.SIZE["shots"]
    out = {}
    for g, espn_id, squad, xg, confirmed, names in todo:
        m = mus.get(espn_id, {})
        teams = []
        for i, team in enumerate(names):
            if team is None:
                continue
            st = squad[(squad["team"] == team) & squad["starter"].astype(bool)]
            # team totals only when most starters have history: a cup side from outside the six leagues (Union SG,
            # Pafos, Oct 2026) summed to ~0 goals from its one or two known players, a 0% both-teams-to-score read
            known = len(st) > 0 and sum(str(p) in m for p in st["player_id"]) >= MIN_KNOWN_STARTERS
            shots = sum(m.get(str(p), {}).get("shots", 0.0) for p in st["player_id"])
            sot = sum(m.get(str(p), {}).get("sot", 0.0) for p in st["player_id"])
            goals = sum(m.get(str(p), {}).get("goals", 0.0) or 0.0 for p in st["player_id"])
            f = form.loc[team] if team in form.index else None
            rest = None
            if f is not None and pd.notna(f["last_match"]):
                rest = round((pd.Timestamp(g["commence_time"]) - f["last_match"]).total_seconds() / 86400, 1)
            teams.append({
                "team": g["home"] if i == 0 else g["away"], "espn_team": team, "home": i == 0,
                "xg": None if xg is None else round(xg[i], 2),
                "shots": round(shots / share["shots"], 1) if m and known else None,
                "sot": round(sot / share["sot"], 1) if m and known else None,
                # the lineup's goals: starters' expected goals over their share of a team's goals (soccer_goal_reads)
                "goals_model": round(goals / share.get("goals", share["sot"]), 2) if m and known and goals > 0 else None,
                "shots_for": None if f is None else round(float(f["shots_for"]), 1),
                "shots_against": None if f is None else round(float(f["shots_against"]), 1),
                "rank_for": None if f is None or pd.isna(f["rank_for"]) else int(f["rank_for"]),
                "rank_against": None if f is None or pd.isna(f["rank_against"]) else int(f["rank_against"]),
                "rest_days": rest,
                "rotation": rotation(history, squad, team) if confirmed else None})
        shooters = []
        for team in names:
            st = squad[(squad["team"] == team) & squad["starter"].astype(bool)].copy()
            st["mu"] = st["player_id"].astype(str).map(lambda p: m.get(p, {}).get("shots"))
            for r in st.dropna(subset=["mu"]).sort_values("mu", ascending=False).head(SHOOTERS).itertuples():
                mm = m[str(r.player_id)]
                fd_name = None
                if lines is not None and len(lines):
                    from betlab.sources.espn_soccer import match_player
                    cand = lines[lines["event_id"].astype(str) == str(g["event_id"])].drop_duplicates("player")
                    hit = match_player(r.player, cand[["player"]]) if len(cand) else None
                    fd_name = None if hit is None else hit["player"]
                disp = model.dispersion if model is not None else {}
                p_of = lambda t: None if mm.get(t) is None else round(PS.p_line(mm[t], 0.5, disp.get(t, float("inf"))), 3)
                shooters.append({"player": r.player, "team": g["home"] if team == names[0] else g["away"],
                                 "shots": round(mm["shots"], 2), "sot": round(mm["sot"], 2),
                                 "p_shot": round(PS.p_line(mm["shots"], 0.5, size), 3),
                                 # FanDuel's "to score", "to assist" and "to score or assist" (that last one isn't
                                 # in the odds feed: compare the fair odds with FanDuel's app)
                                 "p_goal": p_of("goals"), "p_assist": p_of("assists"), "p_ga": p_of("ga"),
                                 "fd_scorer": (_rungs(lines, g["event_id"], fd_name, "scorer") or [None])[0] if fd_name else None,
                                 "fd_ga": (_rungs(lines, g["event_id"], fd_name, "ga") or [None])[0] if fd_name else None,
                                 "pin_scorer": _pin(lines, g["event_id"], fd_name) if fd_name else None,
                                 "fd_shots": _rungs(lines, g["event_id"], fd_name, "shots") if fd_name else [],
                                 "fd_sot": _rungs(lines, g["event_id"], fd_name, "sot") if fd_name else []})
        doc = {"event_id": g["event_id"], "espn_id": espn_id, "lineup": "confirmed" if confirmed else "expected",
               "teams": teams, "shooters": shooters, "league": g.get("league"), "commence_time": str(g["commence_time"])}
        from betlab import soccer_goal_reads
        doc["goals_read"] = soccer_goal_reads.read(teams)
        if len(teams) == 2:
            doc["script"] = _script(doc)
        out[str(g["event_id"])] = doc
    cups, record = cup_games(), lineup_record()
    for g in games:                                  # every match in the horizon, with or without the analysis
        if not (asof < pd.Timestamp(g["commence_time"]) <= asof + HORIZON):
            continue
        doc = out.get(str(g["event_id"]))
        ml = moneyline(g, doc["teams"] if doc else None, cups, record, bool(doc and doc.get("lineup") == "confirmed"))
        if ml is not None:
            out.setdefault(str(g["event_id"]), {"event_id": g["event_id"], "league": g.get("league"),
                                                "commence_time": str(g["commence_time"])})["moneyline"] = ml
    return out


def write(docs: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "games": docs}, indent=2, default=str), encoding="utf-8")


def load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8")).get("games", {}) if OUT.exists() else {}
