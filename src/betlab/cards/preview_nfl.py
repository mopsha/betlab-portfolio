"""Game Previews for upcoming NFL games (the page's Games tab): how each game should go.

For every NFL game in the next week:
- **The score** comes from the market (spread and total), which predicts it better
  than our ratings; our own read is shown next to it.
- **The how** comes from the game-flow engine (models/game_nfl.py): plays and pace,
  pass/run mix under the market's game script, and each unit against its opposite
  number, ranked against the league.
- **Who plays and where:** the expected starting QB (top of the latest depth chart who
  isn't Out or Doubtful) moves the pass offense by his gap to the QBs behind the
  team's rating; injured regulars are listed with their snap share; outdoor games get
  the kickoff forecast, and wind, rain and cold move passing by amounts fit on
  2012-25 games (`betlab backtest game`).
- **Lines that fit the script** (off since Oct 28, `preview.script_lean.show`): FanDuel's main
  pass-game props where the pass matchup and projected dropbacks move the market's fair price
  (props_market.script_lean). 2025 lines said yes (54.6% vs 50.2%); 2024 and 2026's lines didn't,
  so the Games tab no longer shows them. Every line is still tracked with its script read.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config, explain
from betlab import injuries_nfl as INJ
from betlab import odds_math as om
from betlab import props_market as PM
from betlab.cards import fun_nfl
from betlab.cards import notebook_nfl as NB
from betlab.models import game_nfl as GN
from betlab.models import matchups_nfl as MU
from betlab.sources import nflverse, weather

NOTE = ("The score comes from the betting market, which has predicted it better than our ratings. "
        "The rest is our read on how the game goes: pace, run/pass mix and unit matchups from every "
        "play this season and last two, adjusted for who starts at QB and the kickoff weather.")
MIN_LEAN = 0.01  # show a line when the script moves its chance by at least a point
MAX_LINES = 8
ROLE_MIN = 0.35  # list injured players who took at least this share of snaps lately (plus any QB)
MAX_INJURED = 6  # per team
THIN_RECORD = 150  # weighted dropbacks under which a QB is rated mostly as a typical backup


def _market(pick_snap, home_name: str, away_name: str):
    """(home expected margin, total) from the game-line snapshot's median book, else None."""
    if pick_snap is None:
        return None
    ev = pick_snap[(pick_snap["home_team"] == home_name) & (pick_snap["away_team"] == away_name)]
    spread = ev[(ev["market"] == "spreads") & (ev["outcome"] == home_name)]["point"]
    total = ev[(ev["market"] == "totals") & (ev["outcome"] == "Over")]["point"]
    if spread.empty or total.empty:
        return None
    return -float(spread.median()), float(total.median())


def _rank(rk: pd.DataFrame, col: str, team: str):
    return int(rk.loc[team, col]) if team in rk.index and col in rk else None


def _team_row(pr: dict, team: str, r: GN.Ratings, rk: pd.DataFrame, name, points_mkt: float) -> dict:
    """One offense's projected volume and each unit's rating (value, league rank)."""
    s = pr["sides"][team]
    unit = lambda side, stat: {"value": round(float(r.league[stat] + side[stat].get(team, 0.0)), 3),
                               "rank": _rank(rk, f"{'off' if side is r.off else 'def'}_{stat}", team)}
    return {"team": team, "name": name(team), "market_points": round(points_mkt, 1),
            "our_points": round(float(s["proj_points"]), 1), "plays": round(float(s["plays"]), 1),
            "sec_per_play": round(float(s["sec_per_play"]), 1), "pass_rate": round(float(s["pass_rate"]), 3),
            "dropbacks": round(float(s["dropbacks"]), 1), "rushes": round(float(s["rushes"]), 1),
            "pass_off": unit(r.off, "pass_epa"), "rush_off": unit(r.off, "rush_epa"),
            "pass_def": unit(r.dfn, "pass_epa"), "rush_def": unit(r.dfn, "rush_epa"),
            "protection": unit(r.off, "pressure"), "pass_rush": unit(r.dfn, "pressure"),
            "red_zone": unit(r.off, "rz_td")}


def _why(team: str, opp: str, feats: dict, pr: dict, rk: pd.DataFrame, name, extra: str = "") -> str:
    """The football behind a team's pass-game lean, in one line."""
    o, d = _rank(rk, "off_pass_epa", team), _rank(rk, "def_pass_epa", opp)
    db = pr["sides"][team]["dropbacks"]
    usual = db / np.exp(feats["dropbacks"])
    edge = "favors the offense" if feats["pass_epa"] > 0 else "favors the defense"
    return (f"{name(team)} passing game ({GN._ord(o)}) vs {name(opp)} pass defense ({GN._ord(d)}) {edge}"
            f"{extra}; about {db:.0f} dropbacks vs {usual:.0f} usual.")


def _starter(team: str, depth: pd.DataFrame | None, inj: pd.DataFrame | None):
    """(player_id, name, QBs passed over) for the expected starter: the highest QB on the
    team's latest depth chart who isn't Out or Doubtful. (None, None, []) without a chart."""
    if depth is None:
        return None, None, []
    out = set()
    if inj is not None:
        out = set(inj.loc[(inj["team"] == team) & inj["report_status"].isin(["Out", "Doubtful"]), "gsis_id"])
    skipped = []
    for q in depth[depth["team"] == team].sort_values("rank").itertuples():
        if q.player_id in out:
            skipped.append(q.name)
            continue
        return q.player_id, q.name, skipped
    return None, None, skipped


def _poss(n: str) -> str:
    return n + ("'" if n.endswith("s") else "'s")


def _qb_read(team: str, qa: dict, qbr: pd.DataFrame, sid, sname, skipped, qb_name, name,
             status: dict | None = None) -> dict:
    """Who starts at QB and what it does to the passing game, in numbers and one sentence.
    A change is a different starter from the team's last game; the size is always
    measured against the QB mix behind the team's rating (which can include last season)."""
    last_id, usual_id = qa["last_id"], qa["usual_id"]
    sname = sname or qb_name(last_id)
    # Replaced: a different starter from last game, or (this season) the one who took over
    # from the QB behind most of the team's numbers. A QB who left in the offseason isn't
    # "replaced", but the numbers still lean on him (said below).
    this_season = qa["usual_days_ago"] is not None and qa["usual_days_ago"] <= 150
    replaced = (last_id if sid and last_id and sid != last_id
                else usual_id if sid and usual_id and sid != usual_id and this_season else None)
    change = replaced is not None
    thin = sid is not None and float(qbr["w"].get(sid, 0.0)) < THIN_RECORD
    adj = qa["adj"]
    text = ""
    if change:
        note = (status or {}).get(replaced) or ("out" if qb_name(replaced) in skipped else "")
        text = (f"{sname} starts for the {name(team)} in place of {qb_name(replaced)}"
                + (f" ({note.lower()})" if note else "") + f": their passing game moves {adj:+.2f} EPA per dropback"
                + (" (little NFL record, so he's rated near a typical backup)" if thin else "") + ".")
    elif sid and usual_id and sid != usual_id and abs(adj) >= 0.02:
        text = (f"{sname} at QB: the {_poss(name(team))} passing numbers still lean on {qb_name(usual_id)} "
                f"from last season, so ours moves {adj:+.2f} EPA per dropback with him.")
    elif abs(adj) >= 0.03:
        text = (f"{sname} at QB: the {_poss(name(team))} passing numbers include other QBs lately, so ours "
                f"moves {adj:+.2f} EPA per dropback with him.")
    return {"name": sname, "id": sid, "replaces": qb_name(replaced) if change else None, "change": bool(change),
            "adj": round(adj, 3),
            "rating": round(qa["starter_est"], 3), "thin_record": bool(thin), "text": text}


def _injured(inj: pd.DataFrame | None, team: str, roles: pd.Series) -> list[dict]:
    """The team's players on this week's report who are regulars (snap share over
    ROLE_MIN in the last 3 games) or quarterbacks: game status (Out, Doubtful,
    Questionable, set on Friday for Sunday games) or, before that, missed or limited
    practice."""
    if inj is None:
        return []
    order = {"Out": 0, "Doubtful": 1, "Questionable": 2, "Missed practice": 3, "Limited practice": 4}
    practice = {"Did Not Participate In Practice": "Missed practice",
                "Limited Participation in Practice": "Limited practice"}
    rows = []
    for x in inj[inj["team"] == team].itertuples():
        status = x.report_status if isinstance(x.report_status, str) else practice.get(x.practice_status)
        share = float(roles.get(x.gsis_id, 0.0))
        if status not in order or (share < ROLE_MIN and x.position != "QB"):
            continue
        rows.append({"name": x.full_name, "position": x.position, "status": status,
                     "injury": x.report_primary_injury if isinstance(x.report_primary_injury, str) else "",
                     "snap_share": round(share, 2)})
    return sorted(rows, key=lambda r: (order[r["status"]], -r["snap_share"]))[:MAX_INJURED]


def _weather(stadium_id, stadium, kickoff) -> dict:
    """The venue, the kickoff forecast if it's outdoors and within 16 days, its effect on
    both teams (game_nfl.weather_effects), and a sentence."""
    v = weather.venue(stadium_id, stadium)
    if v is None:
        return {"roof": None, "venue": stadium, "forecast": None, "effects": {}, "text": ""}
    base = {"roof": v["roof"], "venue": v["name"], "forecast": None, "effects": {}}
    if v["roof"] == "dome":
        return {**base, "text": f"Indoors at {v['name']}: no weather."}
    if v["roof"] == "retractable":
        return {**base, "text": f"Retractable roof at {v['name']}, usually closed in bad weather: no weather effect."}
    wx = weather.forecast(v["lat"], v["lon"], kickoff)
    if wx is None:
        return {**base, "text": f"Outdoors at {v['name']}: the forecast comes in within 16 days of kickoff."}
    eff = GN.weather_effects(wx)
    kind = "snow" if wx["temp_f"] <= 34 else "rain"
    text = (f"Outdoors at {v['name']}: {wx['temp_f']:.0f}°F, wind {wx['wind_mph']:.0f} mph "
            f"(gusts {wx['gust_mph']:.0f}), {wx['precip_prob'] * 100:.0f}% chance of {kind}.")
    if eff["pass_epa"] <= -0.015 or eff["neutral_pass"] <= -0.01:
        pts = round(eff["neutral_pass"] * 100)
        text += (f" That costs both passing games about {abs(eff['pass_epa']):.2f} EPA per dropback"
                 + (f" and {abs(pts)} point{'s' if abs(pts) != 1 else ''} of pass rate" if pts else "")
                 + ".")
    else:
        text += " Not enough to change how the game is played."
    return {**base, "forecast": wx, "effects": {k: round(v, 4) for k, v in eff.items()}, "text": text}


def _prop_rows(ev: pd.DataFrame, ctx: dict, feats: dict, pr: dict, mrt: dict | None, positions: pd.Series,
               meta: dict) -> list[dict]:
    """Every FanDuel main line in the game: the market's fair P(over), the script lean, the
    receiver matchups and our reads. These rows are what the tracker keeps
    (tracking.record) and what the Games tab's lines and notes are drawn from."""
    prep = fun_nfl.prepare_game(ev, ctx, sims=10000)
    if not prep["ok"]:
        return []
    sim = prep["simulate"]({})
    fair = PM.fair_main(sim, ev, prep["ids"], config.settings()["odds_api"]["sharp_books"])
    team_of = {pid: t for t, inp in prep["inputs"].items() for pid in inp["players"].get("player_id", [])}
    main = PM.fanduel_main(ev).drop_duplicates(["player", "stat"]).set_index(["player", "stat"])
    cfg = (config.settings().get("preview") or {}).get("matchup_read") or {}
    rows = []
    for f in fair[fair["stat"] != "tds"].itertuples():
        pid = prep["ids"].get(f.player)
        team = team_of.get(pid)
        if team is None or (f.player, f.stat) not in main.index:
            continue
        opp = meta["away"] if team == meta["home"] else meta["home"]
        q = main.loc[(f.player, f.stat)]
        p_s = PM.script_lean(f.p_over, f.stat, feats[team])
        mf = MU.features(mrt, pid, positions.get(pid), opp) if mrt is not None and f.stat in cfg.get("stats", []) else {}
        p_m, score = MU.read(p_s, mf, cfg) if mf else (p_s, 0.0)
        rows.append({**{k: meta[k] for k in ("season", "week", "game_id", "commence_time", "matchup")},
                     "player": f.player, "player_id": pid, "team": team, "opp": opp, "stat": f.stat,
                     "line": float(f.point), "fd_over": int(q["over"]), "fd_under": int(q["under"]),
                     "p_market": round(float(f.p_over), 4), "pass_edge": round(feats[team]["pass_epa"], 3),
                     "dropbacks_log": round(feats[team]["dropbacks"], 4),
                     "pass_adj": round(pr["sides"][team].get("pass_adj", 0.0), 4),
                     "ypt": round(mf["ypt"], 4) if "ypt" in mf else None,
                     "deep": round(mf["deep"], 4) if "deep" in mf else None,
                     "p_script": round(p_s, 4),
                     "script_side": ("over" if p_s > f.p_over else "under") if abs(p_s - f.p_over) >= MIN_LEAN else None,
                     "matchup_score": round(score, 4), "p_matchup": round(p_m, 4) if mf else None,
                     "matchup_side": ("over" if score > 0 else "under") if mf and abs(score) >= cfg.get("show_min", 9) else None,
                     "_mf": mf})
    return rows


def _script_lines(rows: list[dict], why: dict) -> list[dict]:
    """The Games tab's lines that fit the script: the biggest script leans. None while script_lean.show is off
    (Oct 28: below the market on 2026's lines, as on 2024's); the rows stay tracked (p_script, script_side)."""
    if not ((config.settings().get("preview") or {}).get("script_lean") or {}).get("show", True):
        return []
    out = []
    for r in rows:
        if not r["script_side"]:
            continue
        over = r["script_side"] == "over"
        price = r["fd_over"] if over else r["fd_under"]
        p_side, p_mkt = (r["p_script"], r["p_market"]) if over else (1 - r["p_script"], 1 - r["p_market"])
        out.append({"player": r["player"], "team": r["team"], "stat": r["stat"], "line": r["line"],
                    "side": r["script_side"], "label": f"{r['player']} {r['script_side']} {r['line']:g} {PM.STAT_LABEL[r['stat']]}",
                    "price": price, "p_market": round(p_mkt, 3), "p_script": round(p_side, 3),
                    "lean": round(abs(p_side - p_mkt), 3), "ev_if_right": round(float(om.expected_value(p_side, price)), 3),
                    "why": why[r["team"]]})
    return sorted(out, key=lambda x: (-round(x["lean"], 2), -x["ev_if_right"]))[:MAX_LINES]


def _matchup_notes(rows: list[dict], name) -> list[dict]:
    """Receivers whose matchup read is strong (UNCONFIRMED; settings preview.matchup_read). None while
    matchup_read.show is off (Oct 19: 2024 lines didn't confirm either matchup); the rows stay tracked."""
    if not ((config.settings().get("preview") or {}).get("matchup_read") or {}).get("show", True):
        return []
    out = []
    for r in rows:
        if not r["matchup_side"]:
            continue
        mf, over = r["_mf"], r["matchup_side"] == "over"
        bits = []
        if "ypt_allowed" in mf:
            rk = mf["ypt_rank"]
            where = f"{GN._ord(33 - rk)}-most" if rk > 16 else f"{GN._ord(rk)}-fewest"
            bits.append(f"the {name(r['opp'])} allow {mf['ypt_allowed']:.1f} yards per target to his position ({where})")
        if "deep_share" in mf and abs(mf["deep"]) >= 0.01:
            rk = mf["deep_rank"]
            where = f"{GN._ord(33 - rk)}-most" if rk > 16 else f"{GN._ord(rk)}-fewest"
            bits.append(f"{mf['deep_share']:.0%} of his targets are deep (league {mf['deep_lg']:.0%}), against "
                        f"{mf['deep_ypa']:.1f} yards per deep throw allowed ({where})")
        price = r["fd_over"] if over else r["fd_under"]
        out.append({"player": r["player"], "team": r["team"], "stat": r["stat"], "line": r["line"],
                    "side": r["matchup_side"], "price": price,
                    "label": f"{r['player']} {r['matchup_side']} {r['line']:g} {PM.STAT_LABEL[r['stat']]}",
                    "p_market": round(r["p_market"] if over else 1 - r["p_market"], 3),
                    "p_script": round(r["p_script"] if over else 1 - r["p_script"], 3),
                    "p_matchup": round(r["p_matchup"] if over else 1 - r["p_matchup"], 3),
                    "why": "; ".join(bits) + "."})
    return sorted(out, key=lambda x: -abs(x["p_matchup"] - x["p_script"]))[:MAX_LINES]


def build(asof: pd.Timestamp, days: int = 7) -> tuple[dict, list[dict]]:
    """The Games tab's document (one preview per NFL game kicking off in the next `days`
    days) and every prop line row for the tracker (tracking.record)."""
    from betlab.cli import latest_snapshot

    sport = config.settings()["leagues"]["nfl"]["sport_key"]
    games = nflverse.load_games()
    today = asof.tz_convert("America/New_York").tz_localize(None).normalize()
    up = games[(games["date"] >= today) & (games["date"] < today + pd.Timedelta(days=days)) & games["margin"].isna()]
    doc = {"note": NOTE, "games": []}
    all_rows: list[dict] = []
    if up.empty:
        return doc, all_rows
    season = int(up["season"].max())
    pbp = nflverse.load_pbp(range(season - 2, season + 1))
    tg, qg = GN.team_games(pbp, games), GN.qb_games(pbp, games)
    rosters = nflverse.load_rosters_weekly([season - 1, season])
    positions = rosters.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id", keep="last").set_index("gsis_id")["position"]
    targets = MU.targets(pbp, games, positions)
    del pbp
    ctx = fun_nfl.load_context(season)
    try:
        depth = nflverse.load_qb_depth(season)
    except Exception:  # the preview still stands on the usual starters
        depth = None
    try:
        injuries = nflverse.load_injuries([season])
    except Exception:
        injuries = None
    snaps = nflverse.load_snap_counts([season - 1, season]).merge(games[["game_id", "date"]], on="game_id")
    try:  # who is missing, in numbers (injuries_nfl): every player's snaps and stats this season
        all_snaps = nflverse.load_snap_counts_all([season]).merge(games[["game_id", "date"]], on="game_id")
        all_stats = nflverse.load_player_stats_all([season]).merge(games[["game_id", "date"]], on="game_id")
        week_rosters = nflverse.load_rosters_weekly([season])     # every status: reserve/IR, cut, traded
    except Exception:
        all_snaps = all_stats = week_rosters = None
    snaps["share"] = snaps[["offense_pct", "defense_pct"]].max(axis=1)
    qb_names = dict(zip(rosters["gsis_id"], rosters["full_name"]))
    if depth is not None:
        qb_names |= dict(zip(depth["player_id"], depth["name"]))
    qb_name = lambda pid: qb_names.get(pid, pid)
    names = ctx["abbr"]
    name = lambda a: explain.nickname(a, names)
    full = {a: n for n, a in names.items()} | explain.TEAM_NAME  # current names for relocated teams
    pick_snap = latest_snapshot(sport)
    props = latest_snapshot(sport, kind="props")
    ratings, qb_r, mu_r = {}, {}, {}
    for g in up.sort_values("kickoff").itertuples():
        if g.date not in ratings:
            ratings[g.date] = GN.fit_ratings(tg, g.date)
            qb_r[g.date] = GN.qb_ratings(qg, ratings[g.date], g.date)
            mu_r[g.date] = MU.ratings(targets, g.date)
        r, qbr = ratings[g.date], qb_r[g.date]
        inj = injuries[injuries["week"] == g.week] if injuries is not None else None
        inj = inj if inj is not None and len(inj) else None
        wx = _weather(g.stadium_id, g.stadium, g.kickoff)
        qbs, adjust, injured = {}, {}, {}
        recent = snaps[snaps["date"] < g.date]
        for team in (g.away_team, g.home_team):
            sid, sname, skipped = _starter(team, depth, inj)
            qa = GN.qb_adjust(qg, qbr, team, sid, g.date)
            status = {}
            if inj is not None:
                for x in inj[inj["team"] == team].itertuples():
                    s = x.report_status if isinstance(x.report_status, str) else {
                        "Did Not Participate In Practice": "missed practice",
                        "Limited Participation in Practice": "limited in practice"}.get(x.practice_status)
                    if s:
                        status[x.gsis_id] = s
            qbs[team] = _qb_read(team, qa, qbr, sid, sname, skipped, qb_name, lambda a: explain.nickname(a, names),
                                 status)
            adjust[team] = {"pass_epa": qa["adj"] + wx["effects"].get("pass_epa", 0.0),
                            "neutral_pass": wx["effects"].get("neutral_pass", 0.0),
                            "explosive": wx["effects"].get("explosive", 0.0)}
            last3 = recent[recent["team"] == team]["game_id"].drop_duplicates().tail(3)
            roles = recent[recent["game_id"].isin(last3) & (recent["team"] == team)].groupby("player_id")["share"].mean()
            injured[team] = _injured(inj, team, roles)
        # Non-QB regulars ruled Out or Doubtful move the numbers too (injuries_nfl.EFFECTS).
        missing = {}
        if all_snaps is not None:  # the roster (IR, cuts, trades) counts even before the injury report is out
            for team in (g.away_team, g.home_team):
                out = inj[(inj["team"] == team) & inj["report_status"].isin(["Out", "Doubtful"])]["full_name"]                     if inj is not None else pd.Series(dtype=str)
                wr = week_rosters[(week_rosters["team"] == team)
                                  & (week_rosters["week"] == min(g.week, week_rosters["week"].max()))]
                missing[team] = INJ.live(all_snaps, all_stats, team, g.date, set(out.dropna()),
                                         wr[["full_name", "status"]])
        injury_text = {}
        for team, opp in ((g.away_team, g.home_team), (g.home_team, g.away_team)):
            for stat, change in INJ.adjustments(missing, team, opp).items():
                adjust[team][stat] = adjust[team].get(stat, 0.0) + change
            injury_text[team] = INJ.sentence(missing, team, opp, lambda a: explain.nickname(a, names))
        home_name, away_name = full.get(g.home_team, g.home_team), full.get(g.away_team, g.away_team)
        mkt = _market(pick_snap, home_name, away_name)
        if mkt is None and pd.notna(g.spread_line):
            mkt = (float(g.spread_line), float(g.total_line))
        pr = GN.project(r, g.home_team, g.away_team, neutral=bool(g.neutral),
                        market_margin_home=mkt[0] if mkt else None, adjust=adjust)
        market = None
        if mkt:
            market = {"spread_home": mkt[0], "total": mkt[1], "home_points": (mkt[1] + mkt[0]) / 2,
                      "away_points": (mkt[1] - mkt[0]) / 2}
        rk = GN.ranks(r)
        pairs = ((g.away_team, g.home_team, "away_points"), (g.home_team, g.away_team, "home_points"))
        feats = {t: GN.script_features(r, tg, pr, t, o, g.date) for t, o, _ in pairs}
        extra = {t: (f" with {qbs[t]['name']} at QB" if qbs[t]["change"] else "")
                 + (" and the weather" if wx["effects"].get("pass_epa", 0.0) <= -0.015 else "")
                 + (" once injuries are counted" if injury_text.get(t) else "") for t, _, _ in pairs}
        why = {t: _why(t, o, feats[t], pr, rk, name, extra[t]) for t, o, _ in pairs}
        story = " ".join([GN.script_text(pr, market, name)] + [qbs[t]["text"] for t, _, _ in pairs if qbs[t]["text"]])
        entry = {"game_id": g.game_id, "matchup": f"{away_name} @ {home_name}", "kickoff": g.kickoff.isoformat(),
                 "home": g.home_team, "away": g.away_team, "market": market,
                 "ours": {"home_points": round(pr["home_points"], 1), "away_points": round(pr["away_points"], 1),
                          "margin": round(pr["margin"], 1), "total": round(pr["total"], 1)},
                 "script": story, "weather": wx, "qbs": qbs, "injuries": injured,
                 "injury_effects": {t: txt for t, txt in injury_text.items() if txt},
                 "teams": [_team_row(pr, t, r, rk, name, (market or {}).get(k, pr[k])) | {"qb": qbs[t]}
                           for t, _, k in pairs],
                 "matchups": GN.matchups(r, g.home_team, g.away_team, name)[:5],
                 "script_read": {t: {"pass_edge": round(feats[t]["pass_epa"], 2),
                                     "dropbacks_vs_usual": round(feats[t]["dropbacks"], 3), "why": why[t]}
                                 for t, _, _ in pairs},
                 "lines": [], "matchup_notes": [], "notes": []}
        ev = None
        if props is not None:
            ev = props[(props["home_team"] == home_name) & (props["away_team"] == away_name)]
            if len(ev):
                ev = ev[pd.to_datetime(ev["commence_time"], utc=True, format="ISO8601") > asof]
        if ev is not None and len(ev):
            try:
                meta = {"season": int(g.season), "week": int(g.week), "game_id": g.game_id, "home": g.home_team,
                        "away": g.away_team, "commence_time": g.kickoff.tz_convert("UTC").isoformat(),
                        "matchup": entry["matchup"]}
                rows = _prop_rows(ev, ctx, feats, pr, mu_r[g.date], positions, meta)
                entry["lines"] = _script_lines(rows, why)
                entry["matchup_notes"] = _matchup_notes(rows, name)
                all_rows += [{k: v for k, v in r.items() if k != "_mf"} for r in rows]
            except Exception as exc:  # the preview still stands without player lines
                entry["notes"].append(f"Player lines failed: {type(exc).__name__}: {exc}")
        else:
            entry["notes"].append("Player lines appear once props are pulled for this game (about 36 hours before).")
        if inj is None:
            entry["notes"].append(f"This week's injury report isn't out yet (teams file it from Wednesday); "
                                  "QBs come from the latest depth chart.")
        try:  # the Notebook (cards/notebook_nfl.py): words only, never a price
            entry["notebook"] = NB.build(entry, all_stats, g.date, name)
        except Exception as exc:
            entry["notes"].append(f"Notebook failed: {type(exc).__name__}: {exc}")
        doc["games"].append(entry)
    return doc, all_rows
