"""The shots model on tonight's soccer lineups (Oct 10): each announced player's expected shots and
shots on target, for the props tracker (tracking_soccer_props: `p_model`, `model_mean`, weight 0).

Tonight's squad (ESPN, about an hour before kickoff) is added to the player history as a match not
yet played, so every feature comes from earlier matches exactly as in the backtest
(models/props_soccer.features); the market's expected goals come from the sharp 1X2 and goals line
in the latest odds pull (cards/fun_soccer.targets + fit_goals). Only starters are priced: the model
learned starters.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from betlab import config
from betlab.models import props_soccer as PS

MODEL_PATH = config.DATA_DIR / "models" / "soccer_props.joblib"
# ESPN counts about 7% fewer shots on target than football-data.co.uk's (Opta-style) counts, which
# FanDuel's settlement follows (2024-25, three leagues: 4.58 vs 4.83 a team; total shots agree within
# 1%). The model learned ESPN's counts, so its shots-on-target means are scaled up to the book's.
SOT_SCALE = 1.07


@lru_cache(maxsize=1)
def fitted() -> PS.Fitted | None:
    import joblib

    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


@lru_cache(maxsize=1)
def _history() -> pd.DataFrame:
    """The last two seasons of every league (enough for the long averages), loaded once per run."""
    from betlab.sources.espn_soccer import load_history

    df = load_history()
    return df[df["season"] >= df["season"].max() - 2] if len(df) else df


def market_xg(ev: pd.DataFrame | None, odds_home: str, odds_away: str) -> tuple[float, float] | None:
    """(home, away) expected goals from the sharp market in this match's odds pull."""
    from betlab.cards.fun_soccer import fit_goals, targets

    if ev is None or ev.empty:
        return None
    t = targets(ev, odds_home, odds_away)
    if t is None:
        return None
    lh, la, err = fit_goals(t)
    return (lh, la) if err <= 0.05 else None


def means(matches: list[tuple[pd.DataFrame, str, tuple[float, float] | None]],
          history: pd.DataFrame | None = None, model: PS.Fitted | None = None) -> dict[str, dict[str, dict]]:
    """{ESPN event id: {ESPN player id: {"shots": mean, "sot": mean}}} for tonight's starters.
    matches: [(squad from espn_soccer.lineup, league, (home xG, away xG) or None)], all in one pass."""
    model = model or fitted()
    history = _history() if history is None else history
    matches = [m for m in matches if m[0] is not None and len(m[0])]
    if model is None or not matches or history.empty:
        return {}
    season = int(history["season"].max())
    tonight, xg_rows = [], []
    from betlab.cards.soccer import CUPS

    home_league = history.sort_values("kickoff").groupby("player_id")["league"].last()
    for squad, league, xg in matches:
        eid = str(squad["event_id"].iloc[0])
        sq = squad.assign(league=league, minutes=1, shots=np.nan, sot=np.nan, season=season)
        if league in CUPS:                      # a cup match: each player's own league; no history, no read
            sq["league"] = sq["player_id"].map(home_league)
            sq = sq[sq["league"].notna()]
            if sq.empty:
                continue
        tonight.append(sq)
        if xg is not None:                      # "minutes 1": tonight counts as played, its features from before
            for r in squad.drop_duplicates("team")[["team", "home"]].itertuples():
                xg_rows.append({"event_id": eid, "team": r.team, "team_xg": xg[0] if r.home else xg[1],
                                "opp_xg": xg[1] if r.home else xg[0]})
    if not tonight:
        return {}
    tonight = pd.concat(tonight, ignore_index=True)
    ids = set(tonight["event_id"].astype(str))
    hist = history[~history["event_id"].astype(str).isin(ids)]
    f = PS.features(pd.concat([hist, tonight], ignore_index=True), pd.DataFrame(xg_rows) if xg_rows else None)
    f = f[f["event_id"].astype(str).isin(ids) & f["starter"].astype(bool)]
    if f.empty:
        return {}
    mu = PS.predict(model, f)
    out: dict[str, dict[str, dict]] = {}
    for i, r in f.iterrows():
        out.setdefault(str(r["event_id"]), {})[str(r["player_id"])] = {
            t: float(mu.loc[i, t]) * (SOT_SCALE if t == "sot" else 1.0) for t in mu.columns}
    return out


# ------------------------------------------------------------------- anytime scorer picks (Oct 10, Mike)
SCORER = "player_goal_scorer_anytime"


def pinnacle_scorer(g: pd.DataFrame) -> float | None:
    """Pinnacle's no-vig chance a player scores (its two-way Yes / No), or None when it doesn't post."""
    from betlab import odds_math as om

    pin = g[g["bookmaker"] == "pinnacle"]
    y, n = pin[pin["outcome"] == "Yes"], pin[pin["outcome"] == "No"]
    if y.empty or n.empty:
        return None
    method = config.settings()["picks"].get("devig_two_way", "power")
    return om.no_vig_two_way(float(y["price"].iloc[0]), float(n["price"].iloc[0]), method)[0]


def scorer_offers(snap: pd.DataFrame, league: str, asof: pd.Timestamp, book: str = "fanduel") -> pd.DataFrame:
    """Anytime scorer offers for the card: a book's Yes price (FanDuel or DraftKings) against Pinnacle's no-vig
    chance, the only sharp two-way scorer price in the feed (it posts a few players a match). Market-only (model
    weight 0): the normal prop rules make a pick from 5% EV (picks.classify). Each book's names are matched to
    Pinnacle's on their own (espn_soccer.match_player: accents, initials, extra names), so a spelling that differs
    by book still finds its price (docs/DRAFTKINGS_PLAN.md rule 8). Offers carry the book's spelling."""
    from betlab import books
    from betlab import odds_math as om
    from betlab.sources.espn_soccer import match_player

    snap = snap[(snap["market"] == SCORER) & (pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof)]
    rows = []
    for eid, ev in snap.groupby("event_id"):
        pin = pd.DataFrame({"player": sorted(ev.loc[ev["bookmaker"] == "pinnacle", "player"].dropna().unique())})
        mine = ev[(ev["bookmaker"] == book) & (ev["outcome"] == "Yes")].drop_duplicates("player")
        for r in mine.itertuples():
            hit = r.player if r.player in set(pin["player"]) else match_player(r.player, pin)
            name = hit if isinstance(hit, str) else (None if hit is None else hit["player"])
            p = pinnacle_scorer(ev[ev["player"] == name]) if name else None
            if p is None:
                continue
            price = float(r.price)
            home, away = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
            rows.append({"league": league, "event_id": str(eid), "commence_time": ev["commence_time"].iloc[0],
                         "matchup": f"{home} vs {away}", "market": SCORER, "side": "Yes", "player": r.player,
                         "label": f"{r.player} to score", "point": None, "price": price, "book": book, "kind": "prop",
                         "w_model": 0.0, "p_model": p, "p_market": p, "p_final": p, "p_push": 0.0,
                         "ev": om.expected_value(p, price),
                         "market_source": "Pinnacle no-vig", "model_number": "no model (market only)",
                         "context": f"{r.player} anytime scorer: {books.name(book)} {price:+.0f} vs Pinnacle's no-vig {p:.1%}."})
    return pd.DataFrame(rows)


def scorer_close(league: str, event_id: str, player: str, kickoff, logged=None) -> float | None:
    """Pinnacle's no-vig scorer chance in the last props pull before kickoff and after the pick was logged
    (the pregame pull, or pregame's closing look): the close for a scorer pick's CLV. None when no pull followed
    the pick: the pull it came from would only repeat its own EV (Oct 13)."""
    key = config.settings()["leagues"][league]["sport_key"]
    k = pd.Timestamp(kickoff)
    days = {f"{(k - pd.Timedelta(days=d)).tz_convert('America/New_York'):%Y-%m-%d}" for d in (0, 1)}
    files = sorted(f for d in days for f in (config.DATA_DIR / "odds" / key / d).glob("*_props.parquet"))
    for f in reversed(files):
        snap = pd.read_parquet(f)
        g = snap[(snap["event_id"].astype(str) == str(event_id)) & (snap["market"] == SCORER) & (snap["player"] == player)]
        if g.empty or pd.to_datetime(g["snapshot_ts"], utc=True).max() > k:
            continue
        if logged is not None and pd.notna(logged) and pd.to_datetime(g["snapshot_ts"], utc=True).max() <= pd.Timestamp(logged):
            return None
        p = pinnacle_scorer(g)
        if p is not None:
            return p
    return None
