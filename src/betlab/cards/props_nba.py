"""NBA player props on the card (paper) and in the tracker (the ML layer's training set).

For every FanDuel two-way main line (points, rebounds, assists, threes, and the combos) in a
fresh NBA props snapshot:
- **p_market:** the market's no-vig chance at FanDuel's line: a sharp book if it has the
  player (settings odds_api.sharp_books), else the other books; a quote at a different
  point is moved to FanDuel's with the player model's negative binomial shape.
- **p_model:** player model v3's chance (`pre_lineup` settings; lineups aren't out yet when
  this runs), from tonight's rows (models/live_nba.py). Weight 0 until it beats the market
  on logged lines (rule 3).
- **Tracker rows** (tracking_nba.py): every line with the market, the model and every feature.

Picks come from FanDuel's price vs the market only, and stay paper like the NFL props.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize
from scipy import stats as st

from betlab import books as B
from betlab import config, players
from betlab import odds_math as om
from betlab import props_market as PM
from betlab.models import live_nba as L
from betlab.sources import nba

W_MODEL = 0.0
MAX_AGE_HOURS = 2
LABEL = {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes": "threes",
         "pra": "pts + reb + ast", "pr": "pts + reb", "pa": "pts + ast", "ra": "reb + ast"}
MARKET_OF = {v: k for k, v in PM.NBA_MAIN.items()}


def team_abbr_by_name(sch: pd.DataFrame) -> dict:
    """'Los Angeles Lakers' -> 'LAL' (ESPN's names and abbreviations, latest season wins)."""
    s = sch.sort_values("tipoff")
    pairs = list(zip(s["home_display_name"], s["home_abbreviation"])) + list(zip(s["away_display_name"], s["away_abbreviation"]))
    return dict(pairs)


def _p_over(mu: float, point: float, r: float) -> float:
    return float(st.nbinom.sf(np.floor(point), r, r / (r + max(mu, 1e-6))))


def mu_for_quote(p_over: float, point: float, r: float) -> float:
    """The mean at which a negative binomial with dispersion r gives P(X > point) = p_over."""
    f = lambda mu: _p_over(mu, point, r) - p_over
    lo, hi = 1e-3, max(5.0, point * 4 + 10)
    if f(lo) > 0 or f(hi) < 0:
        return float(point + 0.5)
    return float(optimize.brentq(f, lo, hi))


def fair_at(quotes: pd.DataFrame, point: float, r: float) -> float:
    """Median no-vig P(over) at `point` from quotes at any points (moved with the NB shape)."""
    ps = [q.p_over if q.point == point else _p_over(mu_for_quote(q.p_over, q.point, r), point, r)
          for q in quotes.itertuples()]
    return float(np.median(ps))


def _load_history(asof: pd.Timestamp):
    """Box scores for last season and this one (this season's files appear once games are played)."""
    season = nba.current_season(asof.tz_convert("America/New_York"))
    frames = {"sch": [], "tb": [], "pb": []}
    for s in (season - 1, season):
        try:
            frames["sch"].append(nba.load_schedules([s]))
            frames["tb"].append(nba.load_team_box([s]))
            frames["pb"].append(nba.load_player_box([s]))
        except Exception:  # no file yet for a season that hasn't started
            continue
    return tuple(pd.concat(frames[k], ignore_index=True) for k in ("sch", "tb", "pb"))


def _injuries():
    """(ids sitting tonight, ids day-to-day) from ESPN's live report."""
    try:
        inj = nba.injuries_now()
    except Exception:
        return set(), set()
    return set(inj.loc[inj["sits"], "athlete_id"]), set(inj.loc[~inj["sits"], "athlete_id"])


def _spreads(pick_snap: pd.DataFrame | None) -> dict:
    """(home name, away name) -> points the home team is favored by (median of books)."""
    if pick_snap is None or pick_snap.empty:
        return {}
    out = {}
    for (h, a), ev in pick_snap.groupby(["home_team", "away_team"]):
        sp = ev[(ev["market"] == "spreads") & (ev["outcome"] == h)]["point"]
        if len(sp):
            out[(h, a)] = -float(sp.median())
    return out


def _rosters():
    try:
        return nba.rosters_now()
    except Exception:  # fall back to rosters rebuilt from box scores
        return None


# nba.com's team abbreviations where ESPN's differ
NBA_TO_ESPN = {"NYK": "NY", "GSW": "GS", "NOP": "NO", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH"}
STARTERS = 5      # a team's confirmed lineup counts only with all five starters matched to ESPN ids


def confirmed_lineups(games: pd.DataFrame, roster: pd.DataFrame, lineups: pd.DataFrame) -> tuple[dict, set]:
    """({game_id: starter athlete ids} for games whose two lineups nba.com has confirmed, with
    all ten starters matched to ESPN ids; ids nba.com lists as Inactive on a confirmed team).
    "Expected" lineups are projections, so they're never used."""
    if lineups is None or lineups.empty or roster is None or roster.empty:
        return {}, set()
    lu = lineups.assign(team=lineups["team"].map(lambda t: NBA_TO_ESPN.get(t, t)))
    starters, inactive = {}, set()
    for g in games.itertuples():
        ids_game, ok = set(), True
        for team in (g.home, g.away):
            t = lu[lu["team"] == team]
            ros = roster[roster["team_abbreviation"] == team]
            if t.empty or ros.empty or not (t["lineup_status"] == "Confirmed").all():
                ok = False
                continue
            names = pd.DataFrame({"gsis_id": ros["athlete_id"], "full_name": ros["athlete_display_name"], "football_name": None})
            ids, _ = players.match(t["player"].tolist(), names)
            inactive |= {ids[p] for p in t.loc[t["roster_status"] == "Inactive", "player"] if p in ids}
            s = {ids[p] for p in t.loc[t["starter"], "player"] if p in ids}
            if len(s) != STARTERS:
                ok = False
            ids_game |= s
        if ok:
            starters[g.game_id] = ids_game
    return starters, inactive


def _lineups(asof: pd.Timestamp) -> pd.DataFrame:
    try:
        return nba.lineups(asof.tz_convert("America/New_York").strftime("%Y%m%d"))
    except Exception:  # no lineups: every game prices with pre_lineup
        return pd.DataFrame()


def price(snap: pd.DataFrame, asof: pd.Timestamp, pick_snap: pd.DataFrame | None = None, data=None,
          injuries: tuple[set, set] | None = None, live_rosters: bool = True,
          lineups: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """(card offer rows, tracker rows) for every main NBA line at each of Mike's books (FanDuel, DraftKings) in games
    not started. Tracker rows carry their book; each book's names are matched to the roster on their own.

    data: (schedules, team box, player box) and injuries: (sitting ids, day-to-day ids) are
    fetched live when not given (tests and replays pass them). live_rosters: use ESPN's
    current rosters (False rebuilds them from box scores, as a replay of a past night must).
    lineups: nba.com's lineups (nba.lineups), fetched live when not given: a game whose two
    lineups are confirmed is priced with the `lineup` settings (knowing tonight's starters cut
    the minutes error 7% in the backtest), the rest with `pre_lineup`."""
    if snap is None or snap.empty:
        return pd.DataFrame(), []
    if asof - pd.to_datetime(snap["snapshot_ts"], utc=True).max() > pd.Timedelta(hours=MAX_AGE_HOURS):
        return pd.DataFrame(), []
    snap = snap[pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof]
    if snap.empty:
        return pd.DataFrame(), []
    sch, tb, pb = data or _load_history(asof)
    abbr = team_abbr_by_name(sch)
    spreads = _spreads(pick_snap)
    events = snap.drop_duplicates("event_id")[["event_id", "commence_time", "home_team", "away_team"]].reset_index(drop=True)
    games = pd.DataFrame({"game_id": [L.PENDING_BASE + i for i in range(len(events))],
                          "tipoff": pd.to_datetime(events["commence_time"], utc=True, format="ISO8601"),
                          "home": events["home_team"].map(abbr), "away": events["away_team"].map(abbr),
                          "spread_home": [spreads.get((h, a), np.nan) for h, a in zip(events["home_team"], events["away_team"])]})
    games = games.dropna(subset=["home", "away"])
    out_ids, dtd_ids = injuries if injuries is not None else _injuries()
    roster = _rosters() if live_rosters else None
    # live runs fetch tonight's lineups; replays and tests pass their own (or none)
    lu = (_lineups(asof) if live_rosters else pd.DataFrame()) if lineups is None else lineups
    ros = roster if roster is not None else L.rosters(pb, sch, set(games["home"]) | set(games["away"]), games["tipoff"].min())
    starters, inactive = confirmed_lineups(games, ros, lu)
    out_ids = set(out_ids) | inactive
    params_of = {"pre_lineup": L.load_params("pre_lineup"), "lineup": L.load_params("lineup") if starters else None}
    parts = []
    known = games["game_id"].isin(list(starters))
    if (~known).any():
        parts.append(L.tonight(pb, tb, sch, games[~known], out_ids, dtd_ids, params_of["pre_lineup"], roster=roster)
                     .assign(lineup_known=False))
    if known.any():
        parts.append(L.tonight(pb, tb, sch, games[known], out_ids, dtd_ids, params_of["lineup"], roster=roster,
                               starters=set().union(*starters.values())).assign(lineup_known=True))
    live = pd.concat(parts, ignore_index=True)
    sharp = config.settings()["odds_api"]["sharp_books"]
    offers, rows = [], []
    for i, ev_row in events.iterrows():
        gid = L.PENDING_BASE + i
        ev = snap[snap["event_id"] == ev_row["event_id"]]
        lv = live[live["game_id"] == gid]
        if lv.empty:
            continue
        roster = pd.DataFrame({"gsis_id": lv["athlete_id"], "full_name": lv["athlete_display_name"], "football_name": None})
        for book in B.targets("props"):                   # each of Mike's books at its own numbers (Oct 12)
            fd = PM.book_main(ev, book, main=PM.NBA_MAIN)
            ids, _ = players.match(fd["player"].unique(), roster)
            ref = PM.reference_quotes(ev, sharp, book, main=PM.NBA_MAIN)
            matchup = f"{ev_row['away_team']} @ {ev_row['home_team']}"
            for r in fd.itertuples():
                aid = ids.get(r.player)
                q = ref[(ref["player"] == r.player) & (ref["stat"] == r.stat)]
                if aid is None or q.empty:
                    continue
                p = lv[lv["athlete_id"] == aid].iloc[0]
                params = params_of["lineup" if bool(p["lineup_known"]) else "pre_lineup"]
                disp = params["dispersion"][r.stat] * params.get("tuning", {}).get(r.stat, {}).get("disp_mult", 1.0)
                mu = float(p[f"mu_{r.stat}"])
                p_over_model = _p_over(mu, r.point, disp)
                p_over_market = fair_at(q, float(r.point), disp)
                moved = not bool((q["point"].astype(float) == float(r.point)).any())   # a lean at most (rule 1, Oct 12)
                push = 0.0 if float(r.point) % 1 else float(st.nbinom.pmf(int(r.point), disp, disp / (disp + mu)))
                rows.append({"event_id": ev_row["event_id"], "tipoff": ev_row["commence_time"], "matchup": matchup,
                             "book": book, "player": r.player, "athlete_id": aid, "team": p["team"], "opp": p["opp"], "stat": r.stat,
                             "line": float(r.point), "fd_over": int(r.over), "fd_under": int(r.under),
                             "p_market": round(p_over_market, 4), "p_model": round(p_over_model, 4), "mu": round(mu, 2),
                             "min_proj": round(float(p["mu_minutes"]), 1), "ewm_min": round(float(p["ewm_min"]), 1),
                             "start_share": round(float(p["start_share"]), 2), "missing_min": round(float(p["missing_min"]), 1),
                             "missing_points_share": round(float(p["missing_points_share"]), 3),
                             "abs_margin": None if pd.isna(p["abs_margin"]) else round(float(p["abs_margin"]), 1),
                             "returning": float(p["returning"]), "pace_factor": round(float(p["pace_factor"]), 3),
                             "questionable": bool(p["questionable"]), "market_source": q["source"].iloc[0],
                             "lineup_known": bool(p["lineup_known"]),
                             "starter_now": None if not p["lineup_known"] else float(p["starter_now"]),
                             # for the fun tickets (cards/fun_nba.py), not the tracker's columns
                             "home": abbr.get(ev_row["home_team"]), "away": abbr.get(ev_row["away_team"]),
                             "home_name": ev_row["home_team"], "away_name": ev_row["away_team"], "disp": round(disp, 4)})
                for side, price_, pm, pmod in (("Over", r.over, p_over_market, p_over_model),
                                               ("Under", r.under, 1 - p_over_market, 1 - p_over_model)):
                    offers.append({"league": "nba", "event_id": ev_row["event_id"], "game_ref": None,
                                   "commence_time": ev_row["commence_time"], "matchup": matchup,
                                   "market": MARKET_OF[r.stat], "side": side, "player": r.player, "player_key": aid,
                                   "label": f"{r.player} {side.lower()} {r.point:g} {LABEL[r.stat]}", "point": float(r.point),
                                   "price": float(price_), "book": book, "kind": "prop",
                                   "model_number": f"model {mu:.1f} {LABEL[r.stat]} in {float(p['mu_minutes']):.0f} min",
                                   "p_model": round(pmod, 4), "p_market": round(pm, 4), "p_final": round(pm, 4),
                                   "p_push": round(push, 4), "ev": round(om.expected_value(pm, float(price_), push), 4),
                                   "market_source": q["source"].iloc[0] + (", moved to the book's number: a lean at most" if moved else ""),
                               "w_model": W_MODEL, "lean_only": moved,
                                   "context": (f"{r.player}: about {float(p['mu_minutes']):.0f} minutes projected"
                                               + (f"; {float(p['missing_min']):.0f} teammate minutes out tonight" if p["missing_min"] > 5 else "")
                                               + ("; listed day-to-day" if p["questionable"] else "") + ".")})
    return pd.DataFrame(offers), rows


def evaluate(snap: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Card offer rows only (the card's evaluator interface)."""
    return price(snap, asof)[0]
