"""College basketball on the card (paper): FanDuel vs the sharp market, plus the model's reads.

- **Offers:** every FanDuel spread, total and moneyline against the sharp book's no-vig
  price at FanDuel's number. Where the sharp book hangs a different number, its price is
  moved along a normal curve (margin SD 11, total SD 16.5, from the backtest's errors).
  Model weight 0, so picks come only from FanDuel lagging the sharp price, under the
  normal game-line rules.
- **Reads** (`reads`): games where our margin (efficiency ratings plus the roster-change
  shift, models/ncaab.py) and FanDuel's spread differ by READ_MIN points or more. In 2024-26
  the line moved toward the model after the opener: +0.52 pts at 3+ (both test seasons
  agree), +0.97 at 5+ (mostly 2025-26). Without the roster shift it was +0.38 and +0.56:
  early-season reads against a team's roster change were mostly stale ratings. Reads start
  at 3 points, keep the gap, and are judged by live CLV by size before they're trusted
  with picks (data/ledger/ncaab_reads.csv).
- **New York rules:** no games involving a New York college, and no college games played in
  New York (the schedule's venue state; Madison Square Garden and Barclays included). A game
  whose venue the schedule can't confirm is skipped too: 2025-26 had 20+ New York games
  between two out-of-state teams (MSG events, the Big East tournament, NCAA games in
  Buffalo), so an unknown venue is never assumed legal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from betlab import books, config, ny_rules
from betlab import odds_math as om
from betlab.market import reference_books, two_way
from betlab.models import ncaab as M
from betlab.sources import cbbd

MARGIN_SD = 11.0
TOTAL_SD = 16.5
READ_MIN = 3.0
TOTAL_READ_MIN = 4.0     # a tracked totals read (Oct 12): our total vs the posted total; the gap is kept


def _center_spread(ev, books, home, away):
    """Median home expected margin implied by the reference books' spreads."""
    centers = []
    for b in books:
        tw = two_way(ev, "spreads", b, home, away)
        if tw:
            (pt_h, pr_h), (_, pr_a) = tw
            p = om.devig([pr_h, pr_a])[0]          # P(home covers pt_h)
            centers.append(MARGIN_SD * norm.ppf(np.clip(p, 1e-4, 1 - 1e-4)) - pt_h)
    return float(np.median(centers)) if centers else None


def _center_total(ev, books):
    centers = []
    for b in books:
        tw = two_way(ev, "totals", b, "Over", "Under")
        if tw:
            (line, pr_o), (_, pr_u) = tw
            p = om.devig([pr_o, pr_u])[0]
            centers.append(line + TOTAL_SD * norm.ppf(np.clip(p, 1e-4, 1 - 1e-4)))
    return float(np.median(centers)) if centers else None


def _game_row(sched: pd.DataFrame, home: str, away: str, kickoff) -> pd.Series | None:
    """The schedule's row for this game. At neutral sites the feeds can disagree on which
    team is "home", so the swapped pair counts there (and only there)."""
    day = pd.Timestamp(kickoff).tz_convert("America/New_York").tz_localize(None).normalize()
    near = sched[(sched["date"] - day).abs() <= pd.Timedelta(days=1)]
    g = near[(near["home_team"] == home) & (near["away_team"] == away)]
    if g.empty:
        g = near[(near["home_team"] == away) & (near["away_team"] == home) & near["neutral"].fillna(False).astype(bool)]
    return g.iloc[0] if len(g) else None


def roster_dval(season: int) -> dict:
    """Each team's roster value change for `season` (models/ncaab.roster_dval): {} before its
    rosters are saved; teams whose saved roster is still last season's list are left out."""
    ro = cbbd.rosters()
    if not (ro["season"] == season).any():
        return {}
    rec = cbbd.recruits() if cbbd.RECRUITS.exists() else None     # freshmen's expected value (Oct 20)
    return M.roster_dval(cbbd.players(), ro, season, rec)


def price(snap: pd.DataFrame, asof: pd.Timestamp, data=None) -> tuple[pd.DataFrame, list[dict], list[str]]:
    """(offer rows, read rows, notes) for every game in the snapshot not yet started.
    data: (schedule, team games, name map[, roster dval]) for tests; loaded from
    sources/cbbd otherwise."""
    s = config.settings()
    snap = snap[pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof]
    if snap.empty:
        return pd.DataFrame(), [], []
    season = cbbd.current_season(pd.Timestamp(asof).tz_convert("America/New_York"))
    if data is None:
        feed = sorted(set(snap["home_team"]) | set(snap["away_team"]))
        data = (cbbd.schedule(), cbbd.team_games(), cbbd.team_names(feed_names=feed), roster_dval(season))
    sched, tg, names = data[:3]
    dval = data[3] if len(data) > 3 else {}
    days = M.season_day(asof, season)
    ratings = M.fit(tg, asof)
    rows, reads, notes, unmatched = [], [], [], set()
    if not dval:
        notes.append("NCAAB: no rosters saved for this season, so early ratings miss roster changes")
    elif days < 3 * M.ROSTER_TAU:
        notes.append(f"NCAAB: roster change counted for {len(dval)} teams (the rest: no current roster yet)")
    ny_skipped, no_venue = [], []
    for event_id, ev in snap.groupby("event_id"):
        home_name, away_name = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        home, away = names.get(home_name), names.get(away_name)
        if home is None or away is None:
            unmatched |= {n for n, t in ((home_name, home), (away_name, away)) if t is None}
            continue
        kickoff = ev["commence_time"].iloc[0]
        g = _game_row(sched, home, away, kickoff)
        state = g.get("state") if g is not None else None
        ok, why = ny_rules.allowed("ncaab", home, away, venue_state=state)
        if not ok:
            ny_skipped.append(f"{away} @ {home}")
            continue
        if g is None or not isinstance(state, str) or not state:   # can't confirm it isn't played in New York
            no_venue.append(f"{away} @ {home}")
            continue
        neutral = bool(g["neutral"])
        proj = ratings.project(home, away, neutral)
        shift = M.roster_shift(dval, home, away, days)
        proj["margin"] += shift
        matchup = f"{away} @ {home}" + (" (neutral)" if neutral else "")
        # Until conference tournaments the lines are ESPN's free DraftKings numbers
        # (sources/espn_odds.py): reads only, since there's no FanDuel price or sharp book.
        book = "fanduel" if (ev["bookmaker"] == "fanduel").any() else "draftkings"
        # The card prices every book Mike bets at against the same sharp market (Oct 30: FanDuel only until then,
        # so a better DraftKings or Novig price never reached the card); books.select keeps the better one.
        priced = [b for b in books.targets() if (ev["bookmaker"] == b).any()] if book == "fanduel" else []
        base = {"league": "ncaab", "event_id": event_id, "game_ref": g["game_id"],
                "commence_time": kickoff, "matchup": matchup, "player": None,
                "kind": "game_line", "w_model": 0.0}
        # ---- spread
        sharp, source = reference_books(ev, "spreads", s["odds_api"]["sharp_books"], book)
        center = _center_spread(ev, sharp, home_name, away_name)
        for b in priced:
            if center is None or not (q := two_way(ev, "spreads", b, home_name, away_name)):
                continue
            (pt_h, pr_h), (pt_a, pr_a) = q
            p_mkt = float(norm.cdf((center + pt_h) / MARGIN_SD))
            p_mod = float(norm.cdf((proj["margin"] + pt_h) / MARGIN_SD))
            note = f"our margin {home} {proj['margin']:+.1f}, market {center:+.1f}" + (
                f" (roster change {shift:+.1f})" if abs(shift) >= 0.5 else "")
            for side, label, pt, pr, pm, pk in ((home, f"{home} {pt_h:+g}", pt_h, pr_h, p_mod, p_mkt),
                                                (away, f"{away} {pt_a:+g}", pt_a, pr_a, 1 - p_mod, 1 - p_mkt)):
                rows.append(base | {"book": b, "market": "spreads", "side": side, "label": label, "point": pt,
                                    "price": pr, "model_number": note, "p_model": pm, "p_market": pk, "p_final": pk,
                                    "p_push": 0.0, "ev": om.expected_value(pk, pr), "market_source": source,
                                    "context": f"{books.name(b)} {home} {pt_h:+g}; the sharp market's center is {home} "
                                               f"{center:+.1f} and our efficiency ratings say {proj['margin']:+.1f}."})
        fd = two_way(ev, "spreads", book, home_name, away_name)
        if fd:
            (pt_h, pr_h), (pt_a, pr_a) = fd
            gap = proj["margin"] + pt_h                       # model margin minus FanDuel's implied home margin
            if abs(gap) >= READ_MIN:
                side_home = gap > 0
                reads.append({"event_id": event_id, "game_id": g["game_id"],
                              "commence_time": kickoff, "matchup": matchup, "home": home, "away": away,
                              "side": home if side_home else away, "line": pt_h if side_home else pt_a,
                              "price": pr_h if side_home else pr_a, "home_line": pt_h,
                              "model_margin": round(proj["margin"], 2), "roster_shift": round(shift, 2),
                              "market_center": round(center if center is not None else -pt_h, 2), "book": book,
                              "gap": round(float(gap), 2)})
        # ---- total
        fd = two_way(ev, "totals", book, "Over", "Under")
        sharp, source = reference_books(ev, "totals", s["odds_api"]["sharp_books"], book)
        center = _center_total(ev, sharp)
        if fd and abs(proj["total"] - float(fd[0][0])) >= TOTAL_READ_MIN:   # a tracked totals read (Oct 12)
            (line, pr_o), (_, pr_u) = fd
            over = proj["total"] > line
            reads.append({"kind": "total", "event_id": event_id, "game_id": g["game_id"], "commence_time": kickoff,
                          "matchup": matchup, "home": home, "away": away, "side": "Over" if over else "Under",
                          "line": float(line), "price": pr_o if over else pr_u, "model_total": round(proj["total"], 2),
                          "market_center": round(center if center is not None else float(line), 2), "book": book,
                          "gap": round(float(proj["total"] - line), 2)})
        for b in priced:
            if center is None or not (q := two_way(ev, "totals", b, "Over", "Under")):
                continue
            (line, pr_o), (_, pr_u) = q
            p_mkt = float(1 - norm.cdf((line - center) / TOTAL_SD))
            p_mod = float(1 - norm.cdf((line - proj["total"]) / TOTAL_SD))
            note = f"our total {proj['total']:.1f}, market {center:.1f}"
            for side, pr, pm, pk in (("Over", pr_o, p_mod, p_mkt), ("Under", pr_u, 1 - p_mod, 1 - p_mkt)):
                rows.append(base | {"book": b, "market": "totals", "side": side, "label": f"{side} {line:g}",
                                    "point": line, "price": pr, "model_number": note, "p_model": pm, "p_market": pk,
                                    "p_final": pk, "p_push": 0.0, "ev": om.expected_value(pk, pr),
                                    "market_source": source,
                                    "context": f"Total {line:g}: sharp center {center:.1f}, our ratings {proj['total']:.1f}."})
        # ---- moneyline
        sharp, source = reference_books(ev, "h2h", s["odds_api"]["sharp_books"], book)
        fairs = [om.devig([tw[0][1], tw[1][1]])[0] for x in sharp if (tw := two_way(ev, "h2h", x, home_name, away_name))]
        for b in priced:
            if not fairs or not (q := two_way(ev, "h2h", b, home_name, away_name)):
                continue
            (_, pr_h), (_, pr_a) = q
            p_mkt, p_mod = float(np.median(fairs)), float(norm.cdf(proj["margin"] / MARGIN_SD))
            for side, pr, pm, pk in ((home, pr_h, p_mod, p_mkt), (away, pr_a, 1 - p_mod, 1 - p_mkt)):
                rows.append(base | {"book": b, "market": "h2h", "side": side, "label": f"{side} ML", "point": None,
                                    "price": pr, "model_number": f"our margin {home} {proj['margin']:+.1f}",
                                    "p_model": pm, "p_market": pk, "p_final": pk, "p_push": 0.0,
                                    "ev": om.expected_value(pk, pr), "market_source": source,
                                    "context": f"Moneyline: sharp no-vig {pk:.1%}."})
    if unmatched:
        notes.append("NCAAB: couldn't match " + ", ".join(sorted(unmatched)))
    if ny_skipped:
        notes.append(f"NCAAB: skipped {len(ny_skipped)} under New York rules: " + ", ".join(sorted(ny_skipped)))
    if no_venue:
        notes.append(f"NCAAB: skipped {len(no_venue)} with no confirmed venue: " + ", ".join(sorted(no_venue)))
    out = pd.DataFrame(rows)
    return (books.attach_limits(out, snap) if len(out) else out), reads, notes


def evaluate(snap: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    return price(snap, asof)[0]
