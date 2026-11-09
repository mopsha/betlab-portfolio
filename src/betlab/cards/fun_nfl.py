"""Fun same-game parlays for upcoming NFL games (the page's Fun tab).

For each game in the latest props snapshot that hasn't kicked off:
1. Match FanDuel's player names to nflverse ids within the two teams' active rosters,
   and read the official injury report: Out/Doubtful players are removed and their
   volume goes to teammates; Questionable players are flagged on their legs.
2. Simulate the game jointly (models/game_sim_nfl), with the market's spread and total.
   The raw simulation is also kept as "our read": the model's own view of each line,
   shown next to the market's for learning (it has no weight in prices yet).
3. Anchor it to the market (props_market.anchor): main lines, Pinnacle TD prices and
   the books' alt ladders.
4. Our game read (Mike, Sep 25: "our game reads should factor into the parlays"): each
   pass-game leg gets the Games tab's script lean (the offense's pass matchup, with who
   starts at QB and the weather, and its projected dropbacks; exports/previews.json).
   Legs the read favors are tagged with the game's story, and slips are ranked by value
   with the read. Fair odds and the worth-it verdict stay on the market: the lean held on
   2025 prop lines but isn't confirmed on a second season.
5. Search FanDuel's legs for the best-value correlated parlays in the payout band (sgp).

Status: preview. The correlations are backtested (`betlab backtest sgp`, Sep 25):
they match real games for QB-receiver stacks, shootouts and pass/run trade-offs, but
underrate how a receiver's TD goes with his QB's yards. Fun bucket ($10/month) only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config, explain, players, props_market as PM, sgp, sgp_plus
from betlab.models import game_sim_nfl as G
from betlab.models import props_nfl as P
from betlab.models import roles_nfl as R
from betlab.models import td_nfl as TD
from betlab.sources import nflverse

STATUS = "preview"
NOTE = ("Each player's line comes from the market; how players move together comes from our simulator, "
        "checked against 816 real games (2023-25): it gets QB-and-receiver stacks and shootouts right, but "
        "underrates how a receiver's touchdown goes with his QB's yards. Fun bucket only.")


ROLES = R.RoleParams()  # props model v0.2 (docs/MODELS.md)
MIN_DRAWS = 1000        # below this many effective draws after anchoring, a game's joint odds are noise
MAX_RAKE_ERROR = 0.02   # and a market price the simulation can't match within 2 points means the same
                        #   (Sep 27: Panthers @ Browns kept 33 of 20,000 draws and missed a price by 21.6 points)


def anchor_problem(w, err: float) -> str | None:
    """Why a game's anchored simulation can't price parlays, or None when it can."""
    eff = PM.effective_draws(w)
    if eff < MIN_DRAWS or err > MAX_RAKE_ERROR:
        return (f"no parlays for this game: the simulation couldn't match the market (it rests on {eff:,.0f} "
                f"effective draws and misses a price by {err:.1%})")
    return None


def load_history(season: int) -> R.History:
    """Player-games (with snap counts and zero-stat games) from the two seasons before
    `season` through the latest week, indexed for the role and matchup model."""
    seasons = range(season - 2, season + 1)
    df = R.prepare(nflverse.load_player_stats(seasons), nflverse.load_games(), nflverse.load_snap_counts(seasons))
    return R.History(df)


def live_roster(hist: R.History, roster: pd.DataFrame, team: str, before, featured: set[str]) -> pd.DataFrame:
    """Who we expect to play: active players with a FanDuel prop, or snaps in any of the
    team's last 3 games. Deep backups who haven't played would otherwise soak up shares."""
    recent = set()
    for gid in hist.team(team, before).tail(3)["game_id"]:
        g = hist.df[(hist.df["game_id"] == gid) & (hist.df["team"] == team)]
        recent |= set(g.loc[g["offense_pct"].fillna(0) > 0, "player_id"])
    r = roster[roster["position"].isin(P.SKILL)]
    r = r[r["gsis_id"].isin(recent | featured)]
    return r.rename(columns={"gsis_id": "player_id", "full_name": "name"})[["player_id", "name", "position"]]


def market_line(pick_snap: pd.DataFrame | None, event_id: str, home_name: str) -> tuple[float, float] | None:
    """(home expected margin, total) as the median across books in the game-line snapshot."""
    if pick_snap is None:
        return None
    ev = pick_snap[pick_snap["event_id"] == event_id]
    spread = ev[(ev["market"] == "spreads") & (ev["outcome"] == home_name)]["point"]
    total = ev[(ev["market"] == "totals") & (ev["outcome"] == "Over")]["point"]
    if spread.empty or total.empty:
        return None
    return -float(spread.median()), float(total.median())


def model_reads(sim: G.GameSim, fair: pd.DataFrame, ids: dict[str, str]) -> list[dict]:
    """Our model's own read of each main line, before any market anchoring: its median
    and chance of the over, next to the market's no-vig chance. Shown for learning; the
    model has no weight in prices until backtests against real prop lines earn it one."""
    rows = []
    for r in fair[fair["kind"] == "main"].itertuples():
        d = sim.get(ids[r.player], r.stat)
        if d is None:
            continue
        rows.append({"player": r.player, "stat": r.stat, "line": r.point,
                     "p_market": round(float(r.p_over), 3), "p_model": round(float((d > r.point).mean()), 3),
                     "model_median": round(float(pd.Series(d).median()), 1), "source": r.source})
    return rows


READ_MIN = 0.01  # a leg "fits the read" when the read raises its chance by at least 1 point


def load_script_reads() -> dict:
    """{nflverse game_id: {team: {"pass_edge", "dropbacks_vs_usual", "why"}}} from the Games
    tab's latest previews (built just before the parlays in the daily and evening runs)."""
    import json

    path = config.EXPORTS_DIR / "previews.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {g["game_id"]: g.get("script_read") or {} for g in doc.get("games", [])}


def apply_reads(legs: list, script_read: dict, coef: dict | None = None) -> None:
    """Set each pass-game leg's chance with our read (props_market.script_lean on the
    market-fair chance; alt rungs get the same log-odds move) and tag the legs it favors."""
    for leg in legs:
        r = script_read.get(leg.team)
        if not r or leg.side not in ("over", "under"):
            continue
        feats = {"pass_epa": float(r.get("pass_edge", 0.0)), "dropbacks": float(r.get("dropbacks_vs_usual", 0.0))}
        p_over = leg.p if leg.side == "over" else 1 - leg.p
        moved = PM.script_lean(p_over, leg.stat, feats, coef)
        if moved == p_over:
            continue  # not a pass-game stat
        leg.p_read = moved if leg.side == "over" else 1 - moved
        if leg.p_read - leg.p >= READ_MIN:
            leg.read = r.get("why", "")


def load_context(season: int) -> dict:
    """Everything a game needs that isn't in the odds: history, schedule, this week's
    active rosters, team names, the latest game-line snapshot and the injury report."""
    from betlab.cli import latest_snapshot

    rosters = nflverse.load_rosters_weekly([season])
    # The latest week's players, any status: nflverse posts a week's roster after its games, so
    # a player inactive last week who has a prop now is back (prepare_game keeps him).
    rosters = rosters[rosters["week"] == rosters["week"].max()]
    try:
        injuries = nflverse.load_injuries([season])
        injuries = injuries[injuries["week"] == injuries["week"].max()]
    except Exception:  # the report is a bonus; never block the build on it
        injuries = None
    return {"hist": load_history(season), "games": nflverse.load_games(), "rosters": rosters,
            "abbr": nflverse.team_abbr_by_name(), "injuries": injuries,
            "pick_snap": latest_snapshot(config.settings()["leagues"]["nfl"]["sport_key"]),
            "script_reads": load_script_reads(), "td_reads": load_td_reads(season)}


def load_td_reads(season: int):
    """The anytime TD read's live features (models/td_nfl.Reads), or None without a fit."""
    params = TD.load_params()
    if params is None:
        return None
    try:
        seasons = [season - 1, season]
        pbp = nflverse.load_pbp(seasons, columns=["game_id", "season", "week", "posteam", "yardline_100", "play_type",
                                                  "rusher_player_id", "receiver_player_id"])
        return TD.Reads(pbp, nflverse.load_player_stats(seasons), params)
    except Exception:  # the read is a bonus; never block the build on it
        return None


def apply_td_reads(legs: list, reads, sim, ids: dict, team_pts: dict, prep: dict) -> list[dict]:
    """Give each anytime TD leg our TD read (TD.READ_WEIGHT toward Pinnacle's chance: none since Oct 25) and its
    case in one line; return the rows for the TD read tracker (td_reads.py), which keeps testing the half-weight
    blend (TD.TRACK_WEIGHT)."""
    if reads is None:
        return []
    pos = sim.players.set_index("player_id")["position"].to_dict() if len(sim.players) else {}
    rows = []
    for leg in legs:
        if leg.stat != "tds" or leg.player not in ids:
            continue
        pid = ids[leg.player]
        r = reads.read(pid, pos.get(pid, ""), team_pts.get(leg.team, 21.0))
        if r is None:
            continue
        leg.p_read = TD.blend(leg.p, r["p_model"])
        leg.note = TD.note(r, leg.team, team_pts.get(leg.team, 21.0)) + f" · our TD read {r['p_model']:.0%} vs Pinnacle {leg.p:.0%}"
        if leg.p_read - leg.p >= READ_MIN:
            leg.read = f"our TD read: {leg.player}'s red-zone role"
        rows.append({"game_id": prep.get("game_ref"), "commence_time": prep["commence_time"], "matchup": prep["matchup"],
                     "player": leg.player, "player_id": pid, "team": leg.team, "position": pos.get(pid, ""),
                     "price": leg.price, "p_market": round(leg.p, 4), "p_model": round(r["p_model"], 4),
                     "p_read": round(TD.blend(leg.p, r["p_model"], TD.TRACK_WEIGHT), 4), "team_pts": round(team_pts.get(leg.team, 21.0), 2),
                     **{k: None if r[k] is None else round(r[k], 3) for k in ("rz10_share", "rz20_share", "opp_share", "td_rate")}})
    return rows


def market_td_legs(ev: pd.DataFrame, sim, ids: dict, fair: pd.DataFrame) -> list:
    """Anytime TD legs at the market's no-vig chance, for a game whose raking failed. The TD
    ticket judges a scorer by Pinnacle's price and our TD read, neither of which needs the
    simulation's weights, so the game keeps its leg (Vikings @ Buccaneers and Panthers @
    Browns fell off the Sep 27 tickets when the guardrail skipped them whole)."""
    main = fair[(fair["kind"] == "main") & (fair["stat"] == "tds")]
    p_of = dict(zip(main["player"], main["p_over"]))
    legs = [l for l in sgp.build_legs(ev, sim, ids, np.full(sim.n, 1.0 / sim.n), fair)
            if l.stat == "tds" and l.player in p_of]
    for leg in legs:
        leg.p = float(p_of[leg.player])
    return legs


def prepare_game(ev: pd.DataFrame, ctx: dict, sims: int) -> dict:
    """One game, ready to price: matched player ids, injuries, simulator inputs, and a
    simulate(adjust) function. Returns {"ok": False, "notes": [...]} if it can't be priced."""
    first = ev.iloc[0]
    abbr, games, rosters, injuries = ctx["abbr"], ctx["games"], ctx["rosters"], ctx["injuries"]
    home, away = abbr[first["home_team"]], abbr[first["away_team"]]
    prep = {"ok": False, "notes": [], "home": home, "away": away, "event_id": first["event_id"],
            "matchup": f"{first['away_team']} @ {first['home_team']}", "commence_time": first["commence_time"],
            "snapshot_ts": first["snapshot_ts"]}
    season_games = games[(games["home_team"] == home) & (games["away_team"] == away)]
    kickoff = pd.Timestamp(first["commence_time"]).tz_convert("America/New_York").tz_localize(None).normalize()
    g = season_games[season_games["date"] == kickoff]
    prep["game_ref"] = g["game_id"].iloc[0] if len(g) else None
    line = market_line(ctx["pick_snap"], first["event_id"], first["home_team"])
    if line is None:  # fall back to nflverse's line for the game
        g = season_games.tail(1)
        if g.empty or pd.isna(g["spread_line"].iloc[0]):
            prep["notes"].append("no spread/total for this game")
            return prep
        line = float(g["spread_line"].iloc[0]), float(g["total_line"].iloc[0])
    spread_home, total = line
    two = rosters[rosters["team"].isin([home, away])]
    names = [n for n in ev["player"].dropna().unique() if "D/ST" not in n and "Defense" not in n]
    ids, missing = players.match(names, two)
    # Active last week, or listed by FanDuel this week (Sep 27: Xavier Legette, inactive in week 3,
    # had props and went unmatched). The injury report below still removes anyone ruled out.
    two = two[(two["status"] == "ACT") | two["gsis_id"].isin(set(ids.values()))]
    team_rosters = {t: two[two["team"] == t] for t in (home, away)}
    if injuries is not None:
        inj = injuries[injuries["team"].isin([home, away])]
    else:
        inj = pd.DataFrame(columns=["gsis_id", "full_name", "position", "report_status", "report_primary_injury"])
    ruled_out = frozenset(inj.loc[inj["report_status"].isin(["Out", "Doubtful"]), "gsis_id"])
    questionable = {r.gsis_id: r.report_primary_injury for r in inj.itertuples()
                    if r.report_status == "Questionable"}
    ids = {name: pid for name, pid in ids.items() if pid not in ruled_out}
    featured = set(ids.values())
    p = P.PropParams()
    sp = G.SimParams(props=p)
    passers = {ids[n] for n in ev.loc[ev["market"] == "player_pass_yds", "player"].unique() if n in ids}
    inputs = {}
    for team, opp in ((home, away), (away, home)):
        playing = live_roster(ctx["hist"], team_rosters[team], team, kickoff, featured)
        playing = playing[~playing["player_id"].isin(ruled_out)]
        exp_margin = spread_home if team == home else -spread_home
        qb = playing.loc[(playing["position"] == "QB") & playing["player_id"].isin(passers), "player_id"]
        inputs[team] = R.team_inputs(ctx["hist"], team, opp, kickoff, playing, exp_margin, total, ROLES, p,
                                     ruled_out, sp, starter=qb.iloc[0] if len(qb) == 1 else None)

    def simulate(adjust):
        return G.simulate_teams(inputs, home, away, spread_home, total, sp, n=sims, adjust=adjust)

    prep.update(ok=True, ids=ids, unmatched=missing, questionable=questionable, simulate=simulate,
                spread_home=spread_home, total=total, inputs=inputs, kickoff=kickoff,
                injuries=[{"player": r.full_name, "status": r.report_status, "injury": r.report_primary_injury}
                          for r in inj.itertuples()
                          if r.report_status in ("Out", "Doubtful", "Questionable") and r.position in P.SKILL])
    return prep


def build_game(ev: pd.DataFrame, ctx: dict, fun: dict) -> dict:
    """Parlays for one game (ev = that event's rows of the props snapshot)."""
    prep = prepare_game(ev, ctx, int(fun["sims"]))
    out = {k: prep[k] for k in ("event_id", "matchup", "commence_time", "snapshot_ts", "notes")}
    hour = pd.Timestamp(prep["commence_time"]).tz_convert("America/New_York").hour
    out["primetime"] = hour >= 19 or hour < 12      # night games and the 9:30 AM international game (Oct 10)
    out["game_ref"] = prep.get("game_ref")
    out.update(sgps=[], unmatched=prep.get("unmatched", []), injuries=prep.get("injuries", []))
    if not prep["ok"]:
        return out
    ids, questionable, simulate = prep["ids"], prep["questionable"], prep["simulate"]
    sharp = config.settings()["odds_api"]["sharp_books"]
    team_pts = {prep["home"]: (prep["total"] + prep["spread_home"]) / 2, prep["away"]: (prep["total"] - prep["spread_home"]) / 2}
    raw = simulate({})
    sim, w, fair, err = PM.anchor(simulate, ev, ids, sharp)
    problem = anchor_problem(w, err)
    if problem:  # skip the game's slips rather than price them from a handful of draws
        out["notes"] = list(out.get("notes") or []) + [problem]
        out["effective_draws"], out["rake_error"] = round(PM.effective_draws(w)), round(err, 4)
        plus = fun.get("plus")
        if plus:  # its scorers don't need the draws: keep the game on the window's TD ticket
            tds = market_td_legs(ev, sim, ids, fair)
            out["td_rows"] = apply_td_reads(tds, ctx.get("td_reads"), sim, ids, team_pts, prep)
            out["tds"], out["td_chalk"] = sgp_plus.td_candidates(tds, plus), sgp_plus.td_chalk(tds, plus)
        return out
    legs = sgp.build_legs(ev, sim, ids, w, fair)
    pick = ctx.get("pick_snap")
    if pick is not None:  # moneyline, spread and total as legs too (Mike, 2026-09-26)
        first = ev.iloc[0]
        legs += sgp.game_line_legs(pick[pick["event_id"] == prep["event_id"]], sim, w, first["home_team"],
                                   first["away_team"], prep["home"], prep["away"], sharp)
    # the script read moves pass-game legs and tags the slips' stories only when fun.script_read is on (off since
    # Oct 19: 2024 lines didn't confirm it); slips are then ranked on the market's chances alone
    use_read = bool((config.settings().get("fun") or {}).get("script_read", True))
    reads = (ctx.get("script_reads", {}).get(prep.get("game_ref")) or {}) if use_read else {}
    apply_reads(legs, reads)
    out["td_rows"] = apply_td_reads(legs, ctx.get("td_reads"), sim, ids, team_pts, prep)
    out["read"] = {t: r.get("why", "") for t, r in reads.items()}
    defenses = explain.defense_table(ctx["hist"], prep["kickoff"], sorted(set(ctx["abbr"].values())))
    facts = {}
    for leg in legs:  # our model's own chance of the leg, before the market anchoring
        if leg.stat in sgp.GAME_STATS:
            continue
        d = raw.get(ids[leg.player], leg.stat)
        if d is not None:
            hit = d > leg.point if leg.side in ("over", "yes") else d < leg.point
            leg.p_raw = float(hit.mean())
        leg.injury = questionable.get(ids[leg.player])
        if leg.stat != "tds":
            key = (leg.player, leg.stat)
            if key not in facts:
                facts[key] = explain.prop_facts(prep, ctx["hist"], ids[leg.player], leg.stat, d, defenses, ctx["abbr"])
            leg.note = explain.leg_note(facts[key]) if facts[key] else ""
    cands = sgp.search(legs, w, band=tuple(fun["band"]), min_legs=int(fun["min_legs"]),
                       max_legs=int(fun["max_legs"]), min_leg_p=float(fun["min_leg_p"]),
                       max_leg_p=float(fun["max_leg_p"]), under_min_p=float(fun.get("under_min_p", 0.75)),
                       under_max_p=float(fun.get("under_max_p", 0.92)), max_unders=int(fun.get("max_unders", 1)),
                       one_per_player=bool(fun.get("one_leg_per_player", True)))
    chosen = sgp.pick(cands, k=int(fun["per_game"]))
    out["sgps"] = [sgp.to_doc(c, prep["event_id"]) | {"style": "value"} for c in chosen]
    story_k = int(fun.get("story_per_game", 0))
    if story_k:  # one-story slips beside the value slips (Mike, Oct 11), compared in fun_offers.csv
        floor = float(fun.get("story_min_pair_lift", sgp.STORY_MIN_PAIR_LIFT))
        for c in sgp.pick_story(chosen, [c for c in cands if sgp.one_story(c, floor)], story_k):
            out["sgps"].append(sgp.to_doc(c, prep["event_id"]) | {"style": "story", "script_text": explain.script_story(
                sgp.script(c["legs"], w, sim, prep["home"], prep["away"]), ctx["abbr"])})
    ls = fun.get("longshot")
    if ls:  # one long shot per game: bigger payout, longer legs, same guardrails
        long_cands = sgp.search(legs, w, band=tuple(ls["band"]), min_legs=int(ls["min_legs"]),
                                max_legs=int(ls["max_legs"]), min_leg_p=float(ls["min_leg_p"]),
                                max_leg_p=float(fun["max_leg_p"]), under_min_p=float(fun.get("under_min_p", 0.75)),
                                under_max_p=float(fun.get("under_max_p", 0.92)), max_unders=int(fun.get("max_unders", 1)),
                                one_per_player=bool(fun.get("one_leg_per_player", True)))
        # not a stretched copy of a value slip: at most 2 player-stats shared with any (sgp.pick's rule, Oct 19)
        taken = [{l.key for l in c["legs"]} for c in chosen]
        best = next((c for c in long_cands if all(len({l.key for l in c["legs"]} & t) <= 2 for t in taken)), None)
        if best:
            out["sgps"].append(sgp.to_doc(best, prep["event_id"]) | {"longshot": True, "style": "longshot"})
    for doc in out["sgps"]:
        doc["story"] = explain.slip_story(doc, prep, ctx["abbr"])
        if doc.get("script_text"):   # a one-story slip names the game it needs instead of the theme template
            doc["story"] = doc.pop("script_text") + " " + doc["story"].split(". ", 1)[-1]
    plus = fun.get("plus")
    if plus:  # pieces for the slate's SGP+ ticket and its overs to root for (sgp_plus.build)
        out["minis"] = [sgp.to_doc(c, prep["event_id"]) for c in sgp_plus.minis(legs, w, plus, fun)]
        out["overs"] = sgp_plus.rooting_overs(legs, plus)
        out["tds"] = sgp_plus.td_candidates(legs, plus)
        out["td_chalk"] = sgp_plus.td_chalk(legs, plus)
    out["reads"] = model_reads(raw, fair, ids)
    out["pack"] = sgp.leg_pack(legs, w)          # the page's parlay builder (split into fun_legs by export-page)
    out["spread_home"], out["total"] = prep["spread_home"], prep["total"]
    out["effective_draws"] = round(PM.effective_draws(w))
    out["rake_error"] = round(err, 4)
    out["legs_priced"] = len(legs)
    return out


def build(snap: pd.DataFrame, asof: pd.Timestamp, event: str | None = None) -> dict:
    """The Fun tab's document for every game in the props snapshot not yet started."""
    fun = config.settings()["fun"]
    snap = snap[pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof]
    if event:
        snap = snap[snap["event_id"] == event]
    doc = {"status": STATUS, "note": NOTE, "band": fun["band"], "stake": fun["stake"],
           "bucket_monthly": config.settings()["bankroll"]["fun_bucket_monthly"], "games": []}
    if snap.empty:
        return doc
    ctx = load_context(int(pd.Timestamp(snap["commence_time"].min()).year))
    for _, ev in snap.groupby("event_id", sort=False):
        try:
            doc["games"].append(build_game(ev, ctx, fun))
        except Exception as exc:  # one game failing must not sink the rest
            first = ev.iloc[0]
            doc["games"].append({"event_id": first["event_id"],
                                 "matchup": f"{first['away_team']} @ {first['home_team']}",
                                 "commence_time": first["commence_time"], "sgps": [],
                                 "notes": [f"failed: {type(exc).__name__}: {exc}"]})
    doc["games"].sort(key=lambda g: g["commence_time"])
    doc["_td_rows"] = [r for g in doc["games"] for r in g.pop("td_rows", [])]   # for td_reads.record, not the page
    if fun.get("plus"):
        doc["slates"] = sgp_plus.build(doc["games"], asof, fun["plus"])
        for g in doc["games"]:
            g.pop("minis", None)
            g.pop("overs", None)
            g.pop("tds", None)
            g.pop("td_chalk", None)
    return doc
