"""Football game lines at FanDuel (NFL and college), priced by our ratings and the sharp market.

For each FanDuel spread, total and moneyline we compute:
- p_model:  our probability (ratings -> margin/total -> key-number distribution)
- p_market: the sharp market's no-vig probability *at FanDuel's line*. If the
  sharp book hangs a different number (-3 vs FanDuel's -3.5), its price is
  converted through the key-number distribution.
- p_final:  the backtest-weighted blend of the two, and the EV at FanDuel's price.
All probabilities are conditional on no push; p_push is reported separately.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from betlab import config, explain, ny_rules
from betlab import odds_math as om
from betlab.edge import blend_prob
from betlab.market import reference_books, two_way
from betlab.models import football as M

ET = "America/New_York"


@dataclass
class FootballLeague:
    """Per-league configuration for the shared football evaluator."""

    key: str                                  # "nfl" or "ncaaf"
    load_games: Callable[[], pd.DataFrame]    # model-ready games table
    team_names: Callable[[], dict[str, str]]  # Odds API name -> games-table name
    params_path: Path
    first_season: int = 2009
    base: M.GameParams | None = None           # rating memory/shrinkage for this league


def load_model(league: FootballLeague, games: pd.DataFrame):
    """Saved settings plus fresh key-number distributions; fits and saves the settings if missing."""
    done = games.dropna(subset=["margin"])
    if league.params_path.exists():
        p = M.GameParams.load(league.params_path)
        md, td = M.fit_distributions(done)
    else:
        p, md, td = M.production_params(games, league.first_season, league.base)
        p.save(league.params_path)
    return p, md, td


def upcoming(games: pd.DataFrame, asof: pd.Timestamp, p: M.GameParams, days: int = 8) -> pd.DataFrame:
    """Unplayed games in the next `days` days (ET), with rating features and model margin/total."""
    day = asof.tz_convert(ET).tz_localize(None).normalize()
    target = games[(games["date"] >= day) & (games["date"] < day + pd.Timedelta(days=days)) & games["margin"].isna()]
    return M.apply(M.rating_features(games, target, day, p), p)


def _center(ev, market, books, home, away, dist, sd):
    """Median market center (home margin or game total) across reference books."""
    centers = []
    for book in books:
        if market == "spreads":
            tw = two_way(ev, "spreads", book, home, away)
            if tw:
                (pt_h, pr_h), (_, pr_a) = tw
                line, fair = -pt_h, om.devig([pr_h, pr_a])[0]
        else:
            tw = two_way(ev, "totals", book, "Over", "Under")
            if tw:
                (line, pr_o), (_, pr_u) = tw
                fair = om.devig([pr_o, pr_u])[0]
        if tw:
            try:
                centers.append(dist.center_for(line, sd, fair))
            except ValueError:
                pass
    return statistics.median(centers) if centers else None


def _base(league, g, ev, market, side, label, point, price, number_note, book="fanduel"):
    """Columns every offer row shares."""
    return {
        "league": league, "event_id": ev["event_id"].iloc[0], "game_ref": g["game_id"],
        "commence_time": ev["commence_time"].iloc[0], "matchup": f"{g['away_team']} @ {g['home_team']}",
        "market": market, "side": side, "player": None, "label": label, "point": point,
        "price": price, "book": book, "model_number": number_note, "kind": "game_line",
    }


def evaluate(league: FootballLeague, snap: pd.DataFrame, asof: pd.Timestamp, book: str = "fanduel") -> pd.DataFrame:
    """Price every spread, total and moneyline of `book` (FanDuel, or DraftKings since Oct 12) in `snap`.

    One row per side (columns listed in cards/README.md). Games that can't be matched
    to the games table, or that New York rules forbid, are skipped.
    """
    s = config.settings()["odds_api"]
    games = league.load_games()
    p, md, td = load_model(league, games)
    names = league.team_names()
    feats = upcoming(games, asof, p)
    by_pair = {(r["home_team"], r["away_team"]): r for _, r in feats.iterrows()}
    rows = []
    for event_id, ev in snap.groupby("event_id"):
        home_name, away_name = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        g = by_pair.get((names.get(home_name), names.get(away_name)))
        if g is None or not ny_rules.allowed(league.key, home_name, away_name,
                                             venue_state=g.get("venue_state"))[0]:
            continue
        home, away = g["home_team"], g["away_team"]
        early = g["week"] <= p.early_weeks  # ratings not ready yet: trust the market alone
        nick = names if league.key == "nfl" else None
        w_spread, w_total, w_ml = (0.0, 0.0, 0.0) if early else (p.w_spread, p.w_total, p.w_ml)

        # ---- spread
        fd = two_way(ev, "spreads", book, home_name, away_name)
        books, source = reference_books(ev, "spreads", s["sharp_books"], "fanduel")
        center = _center(ev, "spreads", books, home_name, away_name, md, p.market_margin_sd)
        if fd and center is not None:
            (pt_h, pr_h), (pt_a, pr_a) = fd
            line = -pt_h
            cover, push = M.spread_probs(g["model_margin"], line, p, md)
            m_over, m_push, m_under = md.over_push_under(center, p.market_margin_sd, line)
            p_model, p_market = cover / (1 - push), m_over / (m_over + m_under)
            p_final = float(blend_prob(p_model, p_market, w_spread))
            note = f"our line {home} {-g['model_margin']:+.1f}, market {home} {-center:+.1f}"
            for side, label, pt, pr, pm, pk, pf in (
                (home, f"{home} {pt_h:+g}", pt_h, pr_h, p_model, p_market, p_final),
                (away, f"{away} {pt_a:+g}", pt_a, pr_a, 1 - p_model, 1 - p_market, 1 - p_final),
            ):
                rows.append(_base(league.key, g, ev, "spreads", side, label, pt, pr, note, book) | {
                    "p_model": pm, "p_market": pk, "p_final": pf, "p_push": m_push,
                    "ev": om.expected_value(pf * (1 - m_push), pr, m_push), "market_source": source,
                    "w_model": w_spread,
                    "context": explain.game_line_story(g, "spreads", home, away, center, w_spread, early, nick)})

        # ---- total
        fd = two_way(ev, "totals", book, "Over", "Under")
        books, source = reference_books(ev, "totals", s["sharp_books"], "fanduel")
        center = _center(ev, "totals", books, home_name, away_name, td, p.market_total_sd)
        if fd and center is not None:
            (line, pr_o), (_, pr_u) = fd
            over, push = M.total_probs(g["model_total"], line, p, td)
            m_over, m_push, m_under = td.over_push_under(center, p.market_total_sd, line)
            p_model, p_market = over / (1 - push), m_over / (m_over + m_under)
            p_final = float(blend_prob(p_model, p_market, w_total))
            note = f"our total {g['model_total']:.1f}, market {center:.1f}"
            for side, pr, pm, pk, pf in (("Over", pr_o, p_model, p_market, p_final),
                                         ("Under", pr_u, 1 - p_model, 1 - p_market, 1 - p_final)):
                rows.append(_base(league.key, g, ev, "totals", side, f"{side} {line:g}", line, pr, note, book) | {
                    "p_model": pm, "p_market": pk, "p_final": pf, "p_push": m_push,
                    "ev": om.expected_value(pf * (1 - m_push), pr, m_push), "market_source": source,
                    "w_model": w_total,
                    "context": explain.game_line_story(g, "totals", home, away, center, w_total, early, nick)})

        # ---- moneyline
        fd = two_way(ev, "h2h", book, home_name, away_name)
        books, source = reference_books(ev, "h2h", s["sharp_books"], "fanduel")
        fairs = [om.devig([tw[0][1], tw[1][1]])[0] for b in books
                 if (tw := two_way(ev, "h2h", b, home_name, away_name))]
        if fd and fairs:
            (_, pr_h), (_, pr_a) = fd
            p_model, p_market = M.ml_prob(g["model_margin"], p, md), statistics.median(fairs)
            p_final = float(blend_prob(p_model, p_market, w_ml))
            note = f"our line {home} {-g['model_margin']:+.1f}"
            for side, pr, pm, pk, pf in ((home, pr_h, p_model, p_market, p_final),
                                         (away, pr_a, 1 - p_model, 1 - p_market, 1 - p_final)):
                rows.append(_base(league.key, g, ev, "h2h", side, f"{side} ML", None, pr, note, book) | {
                    "p_model": pm, "p_market": pk, "p_final": pf, "p_push": 0.0,
                    "ev": om.expected_value(pf, pr), "market_source": source, "w_model": w_ml,
                    "context": explain.game_line_story(g, "h2h", home, away, None, w_ml, early, nick)})
    return pd.DataFrame(rows)
