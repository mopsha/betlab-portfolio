"""Settle open picks and measure closing line value (CLV).

CLV asks: if the no-vig closing price is the truth, what was our bet worth?
Beating the close consistently is the best early evidence of a real edge;
win/loss records take many hundreds of bets to mean anything.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from functools import partial

import numpy as np
import pandas as pd

from betlab import ledger
from betlab import odds_math as om


def settle(side_margin: float, point: float | None) -> str:
    """won / lost / push for a side that needs side_margin + point > 0."""
    value = side_margin + (point or 0.0)
    return "won" if value > 0 else "lost" if value < 0 else "push"


def profit(status: str, price: float, units: float) -> float:
    """Units won or lost for a settled bet at an American price (a push is 0)."""
    if status == "won":
        return units * (om.american_to_decimal(price) - 1)
    return -units if status == "lost" else 0.0


def grade_football(picks: pd.DataFrame, league: str = "nfl") -> pd.DataFrame:
    """Settle NFL or college picks from final scores; CLV against the closing lines in the games table."""
    card = importlib.import_module(f"betlab.cards.{league}")
    games = card.LEAGUE.load_games()
    p, md, td = card.load_model(games)
    done = games.dropna(subset=["margin"]).set_index("game_id")
    out = picks.copy()
    for i, r in out.iterrows():
        if r["league"] != league or r["status"] != "open" or r["game_ref"] not in done.index:
            continue
        if r.get("kind") == "prop":
            continue  # player props: grade_props
        g = done.loc[r["game_ref"]]
        is_home = r["side"] == g["home_team"]
        side_margin = g["margin"] if is_home else -g["margin"]
        close = {}
        if r["market"] == "spreads":
            status = settle(side_margin, r["point"])
            if pd.notna(g["spread_line"]) and pd.notna(g["home_spread_odds"]):
                fair_home = om.devig([g["home_spread_odds"], g["away_spread_odds"]])[0]
                center = md.center_for(g["spread_line"], p.market_margin_sd, fair_home)
                home_line = -r["point"] if is_home else r["point"]   # home favored by this much
                over, push, under = md.over_push_under(center, p.market_margin_sd, home_line)
                cover = over if is_home else under
                close = {"close_point": -g["spread_line"] if is_home else g["spread_line"],
                         "close_price": g["home_spread_odds"] if is_home else g["away_spread_odds"],
                         "p_close": cover / (1 - push), "push": push}
        elif r["market"] == "totals":
            direction = 1 if r["side"] == "Over" else -1
            status = settle(direction * (g["total"] - r["point"]), 0)
            if pd.notna(g["total_line"]) and pd.notna(g["over_odds"]):
                fair_over = om.devig([g["over_odds"], g["under_odds"]])[0]
                center = td.center_for(g["total_line"], p.market_total_sd, fair_over)
                over, push, under = td.over_push_under(center, p.market_total_sd, r["point"])
                close = {"close_point": g["total_line"],
                         "close_price": g["over_odds"] if direction == 1 else g["under_odds"],
                         "p_close": (over if direction == 1 else under) / (1 - push), "push": push}
        else:  # moneyline; NFL refunds a tie
            status = settle(side_margin, 0)
            if pd.notna(g["home_moneyline"]):
                fair_home = om.devig([g["home_moneyline"], g["away_moneyline"]])[0]
                close = {"close_point": None,
                         "close_price": g["home_moneyline"] if is_home else g["away_moneyline"],
                         "p_close": fair_home if is_home else 1 - fair_home, "push": 0.0}
        out.at[i, "status"] = status
        out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
        if close:
            out.at[i, "close_point"] = close["close_point"]
            out.at[i, "close_price"] = close["close_price"]
            out.at[i, "p_close"] = round(close["p_close"], 4)
            out.at[i, "close_push"] = close["push"]
            out.at[i, "clv"] = round(om.clv(r["price"], close["p_close"] * (1 - close["push"]), close["push"]), 4)
        out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def settle_prop(value: float, side: str, point: float) -> str:
    """won / lost / push for an over/under player prop."""
    diff = (value - point) if side == "Over" else (point - value)
    return "won" if diff > 0 else "lost" if diff < 0 else "push"


SHARP_PROP_BOOKS = ("pinnacle", "lowvig", "betonlineag")
SCORER_MARKETS = {"player_anytime_td", "player_goal_scorer_anytime"}   # yes/no: Pinnacle's two-way price is the close


def props_files(sport: str, kickoff) -> list:
    """The props snapshots that can hold a game's close: its Eastern day and the day before (a late game's pull
    files under the day it was pulled). Regrading an old bet needs its own days, not the latest files."""
    from betlab import config

    ko = pd.Timestamp(kickoff).tz_convert("America/New_York")
    days = {f"{ko:%Y-%m-%d}", f"{ko - pd.Timedelta(days=1):%Y-%m-%d}"}
    root = config.DATA_DIR / "odds" / sport
    return sorted(f for d in days for f in (root / d).glob("*_props.parquet"))


def last_props_rows(r, sport: str, files=None) -> pd.DataFrame | None:
    """The bet's market and player in our last props pull after it was logged and before the start (the pull a bet
    came from is no close: Oct 13), or None when there is no such pull."""
    kickoff = pd.Timestamp(r["commence_time"])
    logged = pd.Timestamp(r["created_at"]) if pd.notna(r.get("created_at")) else pd.Timestamp.min.tz_localize("UTC")
    best, best_ts = None, None
    for f in files if files is not None else props_files(sport, kickoff):
        s = pd.read_parquet(f) if not isinstance(f, pd.DataFrame) else f
        s = s[(s["event_id"] == r["event_id"]) & (s["market"] == r["market"]) & (s["player"] == r["player"])]
        if s.empty:
            continue
        ts = pd.to_datetime(s["snapshot_ts"], utc=True, format="ISO8601").max()
        if logged < ts < kickoff and (best_ts is None or ts > best_ts):
            best, best_ts = s, ts
    return best


def sharp_prop_close(r, rows: pd.DataFrame | None, shift_stat: str | None = None) -> dict:
    """A prop bet's close (Mike, Oct 19: "only grade CLV against a sharp book at the bet's line"): the no-vig of the
    first sharp book (SHARP_PROP_BOOKS) quoting both sides at the bet's own line in `rows` (last_props_rows).
    close_source "sharp:<book>" carries p_close (corrected for the over lean when `shift_stat` is given) and
    p_close_raw; "soft" (only other books quote it) and "none" (nobody does) carry no chance, so the bet gets no
    CLV. Soft books often hang a prop at -110/-110, a coin flip by default: 17 NFL prop "closes" from them read
    -4.8% (7% beat) while sharp ones read flat (scripts/weak_spots.py, Oct 19). {} when there is no later pull."""
    from betlab import props_market as PM

    if rows is None or rows.empty:
        return {}
    fd = rows[(rows["bookmaker"] == "fanduel") & (rows["outcome"] == r["side"]) & (rows["point"] == r["point"])]
    out = {"close_point": r["point"], "close_price": float(fd["price"].iloc[0]) if len(fd) else None}
    if r["market"] in SCORER_MARKETS:                     # yes/no scorer markets: Pinnacle's two-way price only
        from betlab.cards.props_soccer import pinnacle_scorer
        p_yes = pinnacle_scorer(rows)
        if p_yes is None:
            return out | {"close_source": "soft" if len(rows) else "none"}
        p = p_yes if r["side"] in ("Yes", "Over") else 1 - p_yes
        return out | {"close_source": "sharp:pinnacle", "p_close": p, "p_close_raw": p}
    quotes = [q for q in PM._two_way(rows, "Over", "Under") if q[1] == float(r["point"])]
    sharp = [q for b in SHARP_PROP_BOOKS for q in quotes if q[0] == b]
    if not sharp:
        return out | {"close_source": "soft" if quotes else "none"}
    book, _, raw = sharp[0]
    p_over = PM.over_shift(raw, shift_stat) if shift_stat else raw
    return out | {"close_source": f"sharp:{book}", "p_close": p_over if r["side"] == "Over" else 1 - p_over,
                  "p_close_raw": raw if r["side"] == "Over" else 1 - raw}


def prop_close(r, files=None) -> dict:
    """An NFL or NBA prop bet's close (sharp_prop_close) from the game's own props snapshots."""
    from betlab import config
    from betlab import props_market as PM

    league = r.get("league") or "nfl"
    sport = config.settings()["leagues"][league]["sport_key"]
    stat = (PM.NBA_MAIN if league == "nba" else PM.MAIN).get(r["market"])
    return sharp_prop_close(r, last_props_rows(r, sport, files), shift_stat=stat)


def set_prop_close(out: pd.DataFrame, i, r, close: dict) -> None:
    """Write a prop bet's close: its source always; p_close and CLV only from a sharp book, else blanked."""
    if not close:
        return
    out.at[i, "close_source"] = close["close_source"]
    out.at[i, "close_point"] = close.get("close_point")
    out.at[i, "close_price"] = close.get("close_price")
    if close.get("p_close") is None:
        for c in ("p_close", "clv", "clv_raw"):
            out.at[i, c] = np.nan
        return
    out.at[i, "p_close"] = round(close["p_close"], 4)
    out.at[i, "clv"] = round(om.clv(r["price"], close["p_close"]), 4)
    out.at[i, "clv_raw"] = round(om.clv(r["price"], close["p_close_raw"]), 4)


def grade_props(picks: pd.DataFrame, league: str = "nfl") -> pd.DataFrame:
    """Settle NFL player props from nflverse player stats. A player who took a snap but
    has no stats row counts as zero; one who didn't play voids the bet (stake back).
    Picks stay open until both the stats and the snap counts for the game are out."""
    from betlab import players
    from betlab import props_market as PM
    from betlab.sources import nflverse

    out = picks.copy()
    if "kind" not in out.columns or not (out["kind"] == "prop").any():
        return out
    todo = out[(out["league"] == league) & (out["status"] == "open") & (out["kind"] == "prop")
               & out["game_ref"].notna()]
    todo = todo[pd.to_datetime(todo["commence_time"], utc=True, format="ISO8601") < pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=4)]
    if todo.empty:
        return out
    seasons = sorted({int(str(g)[:4]) for g in todo["game_ref"]})
    ps = nflverse.load_player_stats(seasons)
    sn = nflverse.load_snap_counts(seasons)
    for i, r in todo.iterrows():
        g_ps, g_sn = ps[ps["game_id"] == r["game_ref"]], sn[sn["game_id"] == r["game_ref"]]
        if g_ps.empty or g_sn.empty:
            continue  # not published yet
        roster = pd.concat([
            g_ps[["player_id", "player_display_name"]].set_axis(["gsis_id", "full_name"], axis=1),
            g_sn[["player_id", "player"]].set_axis(["gsis_id", "full_name"], axis=1),
        ]).drop_duplicates("gsis_id").assign(football_name=None)
        pid = players.match([r["player"]], roster)[0].get(r["player"])
        stat = PM.MAIN.get(r["market"])
        if pid is not None and (g_ps["player_id"] == pid).any():
            status = settle_prop(float(g_ps.loc[g_ps["player_id"] == pid, stat].iloc[0]), r["side"], r["point"])
        elif pid is not None and ((g_sn["player_id"] == pid) & (g_sn["offense_snaps"] > 0)).any():
            status = settle_prop(0.0, r["side"], r["point"])
        else:
            status = "void"
        out.at[i, "status"] = status
        out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
        set_prop_close(out, i, r, prop_close(r))
        out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def grade_nfl(picks: pd.DataFrame) -> pd.DataFrame:
    """NFL game lines from final scores, then player props from player stats."""
    return grade_props(grade_football(picks, league="nfl"), league="nfl")


NBA_BOX = {"points": ("points",), "rebounds": ("rebounds",), "assists": ("assists",),
           "threes": ("three_point_field_goals_made",), "pra": ("points", "rebounds", "assists"),
           "pr": ("points", "rebounds"), "pa": ("points", "assists"), "ra": ("rebounds", "assists")}


def nba_close(r, snaps: list[pd.DataFrame] | None = None) -> tuple[float, float] | None:
    """(the sharp no-vig chance of a game-line pick's side, conditional on no push; the push
    chance) in our last pull before tip: the hourly NBA run pulls each game's lines 15-75
    minutes before it. Spreads and totals at the pick's own number (cards/nba.fair)."""
    from betlab.cards import nba as card

    if snaps is None:
        from betlab import config
        sport = config.settings()["leagues"]["nba"]["sport_key"]
        snaps = [pd.read_parquet(f) for f in sorted((config.DATA_DIR / "odds" / sport).glob("*/*_pick.parquet"))]
    start, best = pd.Timestamp(r["commence_time"]), None
    for snap in snaps:
        ev = snap[snap["event_id"] == r["event_id"]]
        if len(ev) and pd.to_datetime(ev["snapshot_ts"], utc=True, format="ISO8601").max() < start and (
                best is None or ev["snapshot_ts"].max() > best["snapshot_ts"].max()):
            best = ev
    if best is None:
        return None
    home, away = best["home_team"].iloc[0], best["away_team"].iloc[0]
    if r["market"] == "totals":
        p, _, _ = card.fair(best, "totals", "Over", "Under", point_a=r["point"])
        p = None if p is None else (p if r["side"] == "Over" else 1 - p)
    elif r["market"] == "spreads":
        is_home = r["side"] == home
        p, _, _ = card.fair(best, "spreads", home, away, point_a=r["point"] if is_home else -r["point"])
        p = None if p is None else (p if is_home else 1 - p)
    else:
        p, _, _ = card.fair(best, "h2h", home, away)
        p = None if p is None else (p if r["side"] == home else 1 - p)
    if p is None:
        return None
    return p, card.push_chance(r["market"], r["point"]) if r["market"] != "h2h" else 0.0


def _grade_nba_lines(out: pd.DataFrame, todo: pd.DataFrame, sched: pd.DataFrame | None, snaps) -> pd.DataFrame:
    """Settle NBA moneylines, spreads and totals from ESPN's final scores (overtime counts)."""
    if sched is None:
        from betlab.sources import nba
        seasons = sorted({nba.current_season(pd.Timestamp(t).tz_convert("America/New_York")) for t in todo["commence_time"]})
        sched = nba.load_schedules(seasons, max_age_hours=1.0)
    sched = sched[sched["status_type_completed"].fillna(False).astype(bool)]
    day = pd.to_datetime(sched["tipoff"], utc=True, format="ISO8601").dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    final = {(h, a, d): (float(hs), float(as_)) for h, a, d, hs, as_ in
             zip(sched["home_display_name"], sched["away_display_name"], day, sched["home_score"], sched["away_score"])}
    for i, r in todo.iterrows():
        away, _, home = str(r["matchup"]).partition(" @ ")
        d = pd.Timestamp(r["commence_time"]).tz_convert("America/New_York").strftime("%Y-%m-%d")
        if (home, away, d) not in final:
            continue                                  # not final (or not published) yet
        hs, as_ = final[(home, away, d)]
        margin = hs - as_ if r["side"] == home else as_ - hs
        if r["market"] == "totals":
            status = settle((1 if r["side"] == "Over" else -1) * (hs + as_ - float(r["point"])), 0)
        elif r["market"] == "spreads":
            status = settle(margin, float(r["point"]))
        else:
            status = settle(margin, 0)
        out.at[i, "status"] = status
        out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
        close = nba_close(r, snaps)
        if close is not None:
            p, push = close
            out.at[i, "p_close"] = round(p, 4)
            out.at[i, "close_push"] = push
            out.at[i, "clv"] = round(om.clv(r["price"], p * (1 - push), push), 4)
        out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def did_not_play(player: str, matchup, day_box: pd.DataFrame, box: pd.DataFrame) -> bool:
    """True when a player missing from his game's box sat out: both teams' boxes for "Away @ Home" are in `day_box`,
    and the season's box (`box`) knows him on one of those two teams. The box files leave out a player who didn't
    play, so without this his prop stayed open for good (Kyrie Irving, Oct 24; Ausar Thompson, Oct 25). A name the
    season's box never matched, or a game whose box isn't in (an ESPN hiccup), is not a DNP: it stays open."""
    from betlab import players

    away, _, home = str(matchup or "").partition(" @ ")
    if not home or "team_display_name" not in box:
        return False
    teams = {home.strip(), away.strip()}
    if not teams <= set(day_box["team_display_name"].dropna()):
        return False                                  # the game's box isn't (all) in
    roster = pd.DataFrame({"gsis_id": box["athlete_id"], "full_name": box["athlete_display_name"],
                           "football_name": None}).drop_duplicates("gsis_id")
    aid = players.match([player], roster)[0].get(player)
    return aid is not None and bool(set(box.loc[box["athlete_id"] == aid, "team_display_name"]) & teams)


def grade_nba(picks: pd.DataFrame, box: pd.DataFrame | None = None, now: pd.Timestamp | None = None,
              sched: pd.DataFrame | None = None, snaps: list[pd.DataFrame] | None = None) -> pd.DataFrame:
    """Settle NBA game lines from final scores (_grade_nba_lines), then player props from ESPN
    box scores (the tip-off's Eastern date). A player who didn't play voids the bet. Prop CLV
    comes from the last props snapshot before tip-off (the NBA pull re-prices games with open
    picks when it can: cli._pull_props_nba)."""
    from betlab import players
    from betlab import props_market as PM

    out = picks.copy()
    now = now or pd.Timestamp.now(tz="UTC")
    lines = out[(out["league"] == "nba") & (out["status"] == "open") & (out["kind"] != "prop")]
    lines = lines[pd.to_datetime(lines["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=3)]
    if len(lines):
        out = _grade_nba_lines(out, lines, sched, snaps)
    todo = out[(out["league"] == "nba") & (out["status"] == "open") & (out["kind"] == "prop")]
    todo = todo[pd.to_datetime(todo["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4)]
    if todo.empty:
        return out
    if box is None:
        from betlab.sources import nba
        box = nba.load_player_box([nba.current_season()], max_age_hours=GRADE_BOX_HOURS)
    box = box.assign(day=pd.to_datetime(box["game_date"]).dt.strftime("%Y-%m-%d"))
    for i, r in todo.iterrows():
        day = pd.Timestamp(r["commence_time"]).tz_convert("America/New_York").strftime("%Y-%m-%d")
        b = box[box["day"] == day]
        if b.empty:
            continue  # not published yet
        roster = pd.DataFrame({"gsis_id": b["athlete_id"], "full_name": b["athlete_display_name"],
                               "football_name": None}).drop_duplicates("gsis_id")
        aid = players.match([r["player"]], roster)[0].get(r["player"])
        if aid is None:
            if not did_not_play(r["player"], r.get("matchup"), b, box):
                continue  # name not matched, or the game's box isn't in: stays open for a look (never guess)
            status = "void"   # Nov 9: the box leaves out a player who sat (Kyrie, Oct 24), and books void his props
        elif not (pd.to_numeric(b[b["athlete_id"] == aid].iloc[0]["minutes"], errors="coerce") > 0):
            status = "void"
        else:
            g = b[b["athlete_id"] == aid].iloc[0]
            value = sum(float(g[c]) for c in NBA_BOX[PM.NBA_MAIN[r["market"]]])
            status = settle_prop(value, r["side"], float(r["point"]))
        out.at[i, "status"] = status
        out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
        set_prop_close(out, i, r, prop_close(r))
        out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def grade_soccer(picks: pd.DataFrame, league: str, now: pd.Timestamp | None = None, lookup=None,
                 scorer=None, scorer_close=None, goals_result=None, goals_close=None) -> pd.DataFrame:
    """Settle 3-way soccer picks from football-data.co.uk (score and the sharp close:
    Pinnacle, else Betfair Exchange, else the books' average). A match stays open until
    its file has it (the current season's files update a few times a week).
    Anytime-scorer picks (Oct 10) settle from ESPN's box score (void when the player didn't play),
    CLV against Pinnacle's no-vig in the last props pull before kickoff."""
    from betlab.cards.soccer import CUPS
    from betlab.sources import soccer

    lookup = lookup or soccer.result
    out = picks.copy()
    now = now or pd.Timestamp.now(tz="UTC")
    todo = out[(out["league"] == league) & (out["status"] == "open")]
    todo = todo[pd.to_datetime(todo["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=3)]
    for i, r in todo.iterrows():
        home, away = str(r["matchup"]).split(" vs ", 1)
        if r.get("market") == "player_goal_scorer_anytime":
            from betlab.cards import props_soccer
            from betlab.sources import espn_soccer

            try:
                st, row = (scorer or espn_soccer.player_result)(league, home, away, r["commence_time"], r["player"])
            except Exception:  # noqa: BLE001 - ESPN down: grade tomorrow
                continue
            if st == "open":
                continue
            status = "void" if st == "void" else "won" if float(row["goals"] or 0) >= 1 else "lost"
            out.at[i, "status"] = status
            out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
            p_close = (scorer_close or props_soccer.scorer_close)(league, r["event_id"], r["player"], r["commence_time"],
                                                                  r.get("created_at"))
            if p_close is not None:
                out.at[i, "p_close"] = round(p_close, 4)
                out.at[i, "clv"] = round(om.clv(r["price"], p_close), 4)
            out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            continue
        if r.get("market") in ("totals", "btts"):        # goals and BTTS (cards/soccer_goals, Oct 12)
            from betlab.cards import soccer_goals
            from betlab.fun_ledger import _soccer_result

            res = (goals_result or _soccer_result)(league, home, away, pd.Timestamp(r["commence_time"]))
            if res is None:
                continue
            status = soccer_goals.settle(r["market"], r["side"], r.get("point"), res["hg"], res["ag"])
            out.at[i, "status"] = status
            out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
            p_close = (goals_close or soccer_goals.close)(league, r["event_id"], r["market"], r["side"], r.get("point"),
                                                          r["commence_time"], r.get("created_at"))
            if p_close is not None:
                out.at[i, "p_close"] = round(p_close, 4)
                out.at[i, "clv"] = round(om.clv(r["price"], p_close), 4)
            out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            continue
        if league in CUPS and lookup is soccer.result:     # the cups: ESPN's score and our own close
            from betlab.cards.soccer import cup_result
            res = cup_result(league, home, away, pd.Timestamp(r["commence_time"]), r["event_id"], r.get("created_at"))
        else:
            res = lookup(league, home, away, pd.Timestamp(r["commence_time"]))
        if res is None:
            continue
        idx = {home: 0, "Draw": 1, away: 2}.get(r["side"])
        if idx is None:
            continue
        outcome = 0 if res["hg"] > res["ag"] else 1 if res["hg"] == res["ag"] else 2
        status = "won" if outcome == idx else "lost"
        out.at[i, "status"] = status
        out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
        if res["close"] is not None:
            out.at[i, "p_close"] = round(res["close"][idx], 4)
            out.at[i, "clv"] = round(om.clv(r["price"], res["close"][idx]), 4)
        out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def grade_ncaab(picks: pd.DataFrame, games: pd.DataFrame | None = None, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Settle college basketball picks from CollegeBasketballData's scores. CLV is against
    the closing consensus: spreads and totals at a no-vig center on the closing number
    (normal, SD 11 / 16.5), moneylines from the closing moneylines (probability median)."""
    from scipy.stats import norm

    out = picks.copy()
    now = now or pd.Timestamp.now(tz="UTC")
    todo = out[(out["league"] == "ncaab") & (out["status"] == "open")]
    todo = todo[pd.to_datetime(todo["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4)]
    if todo.empty:
        return out
    if games is None:
        from betlab.sources import cbbd
        games = cbbd.games()
    by_id = games.set_index("game_id")
    for i, r in todo.iterrows():
        gid = str(r.get("game_ref")) if pd.notna(r.get("game_ref")) else None
        if gid is None or gid not in by_id.index:
            continue
        g = by_id.loc[gid]
        home = g["home_team"]
        margin, total = float(g["margin"]), float(g["total"])
        p_close = None
        if r["market"] == "spreads":
            is_home = r["side"] == home
            status = settle(margin if is_home else -margin, r["point"])
            if pd.notna(g.get("spread_line")):
                mu = float(g["spread_line"]) if is_home else -float(g["spread_line"])
                p_close = float(norm.cdf((mu + float(r["point"])) / 11.0))
        elif r["market"] == "totals":
            d = 1 if r["side"] == "Over" else -1
            status = settle(d * (total - float(r["point"])), 0)
            if pd.notna(g.get("total_line")):
                p_over = float(1 - norm.cdf((float(r["point"]) - float(g["total_line"])) / 16.5))
                p_close = p_over if d == 1 else 1 - p_over
        else:
            is_home = r["side"] == home
            status = settle(margin if is_home else -margin, 0)
            if pd.notna(g.get("home_moneyline")) and pd.notna(g.get("away_moneyline")):
                fair_home = om.devig([g["home_moneyline"], g["away_moneyline"]])[0]
                p_close = fair_home if is_home else 1 - fair_home
        out.at[i, "status"] = status
        out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
        if p_close is not None:
            out.at[i, "p_close"] = round(p_close, 4)
            out.at[i, "clv"] = round(om.clv(r["price"], p_close), 4)
        out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def nhl_close(r, snaps: list[pd.DataFrame] | None = None) -> float | None:
    """The sharp books' no-vig chance of a pick's side in our last pull before the start
    (the closing price we have: the midday re-price is the latest pull on most nights).
    Spreads and totals only at the pick's own number."""
    from betlab.cards import nhl as card
    from betlab.sources import nhl as src

    if snaps is None:
        from betlab import config
        sport = config.settings()["leagues"]["nhl"]["sport_key"]
        snaps = [pd.read_parquet(f) for f in sorted((config.DATA_DIR / "odds" / sport).glob("*/*_pick.parquet"))]
    start = pd.Timestamp(r["commence_time"])
    best = None
    for snap in snaps:
        ev = snap[snap["event_id"] == r["event_id"]]
        if ev.empty or pd.to_datetime(ev["snapshot_ts"], utc=True, format="ISO8601").max() >= start:
            continue
        if best is None or ev["snapshot_ts"].max() > best["snapshot_ts"].max():
            best = ev
    if best is None:
        return None
    home, away = best["home_team"].iloc[0], best["away_team"].iloc[0]
    try:
        codes = src.team_codes()
    except Exception:
        codes = {}
    home_code = src.code_for(home, codes) if codes else None
    if r["market"] == "totals":
        p_over, _ = card._fair(best, "totals", "Over", "Under", point_a=r["point"])
        return None if p_over is None else (p_over if r["side"] == "Over" else 1 - p_over)
    is_home = r["side"] in (home, home_code)
    if r["market"] == "spreads":
        home_pt = r["point"] if is_home else -r["point"]
        p_home, _ = card._fair(best, "spreads", home, away, point_a=home_pt)
    else:
        p_home, _ = card._fair(best, "h2h", home, away)
    return None if p_home is None else (p_home if is_home else 1 - p_home)


NHL_PROP_STAT = {"player_shots_on_goal": "shots", "player_points": "points", "player_total_saves": "saves",
                 "player_goal_scorer_anytime": "goals"}


def _grade_nhl_prop(out: pd.DataFrame, i, r, boxes: dict, snaps=None) -> pd.DataFrame:
    """Settle one NHL prop pick from the NHL's box score (a player who didn't play is void);
    CLV against a sharp book's no-vig at the bet's line in our last props pull before the start and after the pick
    was logged (Oct 13: the pull a pick came from only repeats its own EV; Oct 19: soft books' closes don't count)."""
    from betlab.sources import nhl as src

    gid = str(r.get("game_ref")) if pd.notna(r.get("game_ref")) else None
    if gid is None or not gid.isdigit():
        return out
    if gid not in boxes:
        try:
            boxes[gid] = (src.skater_box(gid), src.goalie_box(gid))
        except Exception:
            return out
    sk, gl = boxes[gid]
    stat = NHL_PROP_STAT.get(r["market"])
    box = gl if stat == "saves" else sk
    if stat is None or box is None or box.empty:
        return out
    row = box[box["plain"] == src._plain(r["player"])]
    if row.empty:
        status = "void"
    else:
        v = float(row[stat].iloc[0])
        d = 1 if r["side"] in ("Over", "Yes") else -1
        point = float(r["point"]) if pd.notna(r.get("point")) else 0.5      # anytime scorer: 1+ goals
        status = settle(d * (v - point), 0)
    out.at[i, "status"] = status
    out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
    set_prop_close(out, i, r, nhl_prop_close(r, snaps))
    out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def nhl_prop_close(r, snaps=None) -> dict:
    """An NHL prop bet's close: sharp_prop_close on our last props pull after it was logged (no over-lean shift in
    hockey). Until Oct 19 it was the other books' consensus, moved between lines; now a sharp book at the bet's
    own line, or no CLV. `snaps`: snapshot frames (tests); by default the game's own props files."""
    from betlab import config

    sport = config.settings()["leagues"]["nhl"]["sport_key"]
    return sharp_prop_close(r, last_props_rows(r, sport, snaps))


def grade_nhl(picks: pd.DataFrame, team_games: pd.DataFrame | None = None, now: pd.Timestamp | None = None,
              snaps: list[pd.DataFrame] | None = None) -> pd.DataFrame:
    """Settle NHL picks from the NHL's final scores (the shootout winner's goal counts, as books
    settle totals and puck lines); CLV against the sharp price in our last pull before the start."""
    out = picks.copy()
    now = now or pd.Timestamp.now(tz="UTC")
    todo = out[(out["league"] == "nhl") & (out["status"] == "open")]
    todo = todo[pd.to_datetime(todo["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4)]
    if todo.empty:
        return out
    if team_games is None:
        from betlab.sources import nhl as src
        seasons = sorted({src.current_season(pd.Timestamp(t).tz_convert("America/New_York")) for t in todo["commence_time"]})
        team_games = src.load_team_games(seasons, max_age_hours=1.0)
    home_rows = team_games[team_games["home"] == 1]
    by_id = home_rows.set_index(home_rows["game_id"].astype(str))
    boxes: dict = {}
    for i, r in todo.iterrows():
        if r.get("kind") == "prop":          # player props: from the game's box score
            out = _grade_nhl_prop(out, i, r, boxes, snaps)
            continue
        g = None
        if pd.notna(r.get("game_ref")) and str(r["game_ref"]) in by_id.index:
            g = by_id.loc[str(r["game_ref"])]
        else:                                     # by date and teams ("PIT @ PHI")
            away, _, home = str(r["matchup"]).partition(" @ ")
            day = pd.Timestamp(r["commence_time"]).tz_convert("America/New_York").tz_localize(None).normalize()
            m = home_rows[(home_rows["team"] == home) & (home_rows["opp"] == away) & (home_rows["date"] == day)]
            g = m.iloc[0] if len(m) else None
        if g is None:
            continue
        margin, total = float(g["gf"] - g["ga"]), float(g["gf"] + g["ga"])
        is_home = r["side"] == g["team"]
        if r["market"] == "totals":
            d = 1 if r["side"] == "Over" else -1
            status = settle(d * (total - float(r["point"])), 0)
        elif r["market"] == "spreads":
            status = settle(margin if is_home else -margin, float(r["point"]))
        else:
            status = settle(margin if is_home else -margin, 0)
        out.at[i, "status"] = status
        out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
        p_close = nhl_close(r, snaps)
        if p_close is not None:
            out.at[i, "p_close"] = round(p_close, 4)
            out.at[i, "clv"] = round(om.clv(r["price"], p_close), 4)
        out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def ufc_close(r, snaps: list[pd.DataFrame] | None = None) -> float | None:
    """A UFC bet's close: the sharp books' no-vig chance of its side in our last game-line pull of the fight after
    the bet was logged and before its segment started (pregame.py's closing look). None without one: a pull at or
    before the bet only repeats its own price."""
    from betlab.cards import ufc as card

    if snaps is None:
        from betlab import config
        sport = config.settings()["leagues"]["ufc"]["sport_key"]
        snaps = [pd.read_parquet(f) for f in sorted((config.DATA_DIR / "odds" / sport).glob("*/*_pick.parquet"))]
    start, logged = pd.Timestamp(r["commence_time"]), pd.Timestamp(r["created_at"])
    best = None
    for snap in snaps:
        ev = snap[snap["event_id"].astype(str) == str(r["event_id"])]
        if ev.empty:
            continue
        t = pd.to_datetime(ev["snapshot_ts"], utc=True, format="ISO8601")
        ev = ev[(t > logged) & (t < start)]
        if len(ev) and (best is None or ev["snapshot_ts"].max() > best["snapshot_ts"].max()):
            best = ev
    if best is None:
        return None
    best = best[best["snapshot_ts"] == best["snapshot_ts"].max()]
    if r["market"] == "totals":
        p, _ = card._fair(best, "totals", "Over", "Under", str(r.get("book") or "fanduel"), point_a=r["point"])
        return None if p is None else (p if r["side"] == "Over" else 1 - p)
    x, y = best["home_team"].iloc[0], best["away_team"].iloc[0]
    other = y if r["side"] == x else x
    p, _ = card._fair(best, "h2h", r["side"], other, str(r.get("book") or "fanduel"))
    return p


def ufc_outcome(fight: pd.Series, r) -> str | None:
    """won / lost / push for a UFC bet on its finished fight: a draw or no contest voids the moneyline; total rounds
    from the time fought (Over 2.5 needs more than 2.5 x 5 minutes)."""
    from betlab.sources import espn_ufc as src

    if not fight["done"]:
        return None
    if r["market"] == "totals":
        if fight["seconds"] is None or pd.isna(fight["seconds"]):
            return None
        d = 1 if r["side"] == "Over" else -1
        return settle(d * (float(fight["seconds"]) - float(r["point"]) * src.ROUND_SECONDS), 0)
    a_win, b_win = (bool(v) if v is not None and not pd.isna(v) else False for v in (fight["a_win"], fight["b_win"]))
    if not a_win and not b_win:
        return "push"                                   # draw or no contest
    winner = fight["a_name"] if a_win else fight["b_name"]
    return "won" if src._last(winner) == src._last(r["side"]) else "lost"


def grade_ufc(picks: pd.DataFrame, fights: pd.DataFrame | None = None, now: pd.Timestamp | None = None,
              snaps: list[pd.DataFrame] | None = None) -> pd.DataFrame:
    """Settle UFC bets from ESPN's fight center; CLV from ufc_close. `fights`: espn_ufc.fights rows (tests)."""
    from betlab.sources import espn_ufc as src

    out = picks.copy()
    now = now or pd.Timestamp.now(tz="UTC")
    todo = out[(out["league"] == "ufc") & (out["status"] == "open")]
    todo = todo[pd.to_datetime(todo["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=1)]
    if todo.empty:
        return out
    if fights is None:
        frames = []
        for day in sorted({pd.Timestamp(t).tz_convert("America/New_York").strftime("%Y%m%d") for t in todo["commence_time"]}):
            for eid in src.scheduled(day)["espn_event"].dropna().unique():
                frames.append(src.fights(src.event(str(eid), refresh=True), str(eid)))
        fights = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    card_done = len(fights) > 0 and bool(fights["done"].all())
    for i, r in todo.iterrows():
        x, _, y = str(r["matchup"]).partition(" vs ")
        f = src.find(fights, x, y)
        if f is None:
            # off a finished card: cancelled or a new opponent, so the book voids it (no action)
            if card_done and pd.Timestamp(r["commence_time"]) < now - pd.Timedelta(hours=12):
                out.at[i, "status"], out.at[i, "profit_flat"] = "void", 0.0
                out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            continue
        status = ufc_outcome(f, r)
        if status is None:
            continue
        out.at[i, "status"] = status
        out.at[i, "profit_flat"] = round(profit(status, r["price"], r["units_flat"]), 4)
        p_close = ufc_close(r, snaps)
        if p_close is not None:
            out.at[i, "p_close"] = round(p_close, 4)
            out.at[i, "clv"] = round(om.clv(r["price"], p_close), 4)
        out.at[i, "graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


from betlab.cards.soccer import LEAGUES as SOCCER   # the leagues and the European cups
GRADE_BOX_HOURS = 1.0   # grading re-downloads this season's box scores (the worker caches them 12 h)

GRADERS = {"nfl": grade_nfl, "ncaaf": partial(grade_football, league="ncaaf"), "nba": grade_nba, "ncaab": grade_ncaab,
           "nhl": grade_nhl, "ufc": grade_ufc,
           **{lg: partial(grade_soccer, league=lg) for lg in SOCCER}}


def fill_close_source(picks: pd.DataFrame) -> pd.DataFrame:
    """Graded prop bets with no close_source (graded before Oct 19): their close again by today's rule, a sharp
    book at the bet's line or no CLV (set_prop_close), from the game's own snapshots. Only result columns change,
    each row once; a row with no later pull is "none"."""
    out = picks.copy()
    if "close_source" not in out:
        out["close_source"] = None
    todo = out[(out["kind"] == "prop") & out["status"].isin(["won", "lost", "push"]) & out["close_source"].isna()
               & out["league"].isin(["nfl", "nba", "nhl"])]
    for i, r in todo.iterrows():
        try:
            close = nhl_prop_close(r) if r["league"] == "nhl" else prop_close(r)
        except Exception as exc:  # noqa: BLE001 - a bad snapshot file: try again next run
            print(f"prop close not regraded for {r.get('pick_id')} ({type(exc).__name__}: {exc})")
            continue
        set_prop_close(out, i, r, close or {"close_source": "none"})
    return out


def grade_all(path=None) -> int:
    """Grade every league's open rows in a ledger file (the picks by default, or
    ledger.LEANS); returns how many were settled."""
    picks = ledger.load(path)
    if picks.empty:
        return 0
    before = (picks["status"] == "open").sum()
    for league, grader in GRADERS.items():
        if ((picks["league"] == league) & (picks["status"] == "open")).any():
            try:
                picks = grader(picks)
            except Exception as exc:  # noqa: BLE001 - a missing results file (the NBA's new season) waits a day
                print(f"grading {league}: not graded ({type(exc).__name__}: {exc}); the rest still grade")
    picks = fill_close_source(picks)
    ledger.save(picks, path)
    return int(before - (picks["status"] == "open").sum())
