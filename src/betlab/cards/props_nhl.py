"""NHL player props on the card (paper; market-first) and the NHL props tracker's rows.

- **Lines:** shots on goal, points, goalie saves and anytime scorer at each of Mike's books (FanDuel and
  DraftKings, Oct 12; FanDuel's feed has no NHL points, so points are DraftKings' alone).
- **Fair price:** the other books' no-vig chance at that book's exact number (median across
  books; neither of Mike's books counts toward the other's: docs/DRAFTKINGS_PLAN.md rule 7). Pinnacle rarely posts
  NHL props in the feed, so this is a consensus, labeled as such. Offers carry model weight 0: picks come only from
  the book being off the consensus,
  under the normal prop rules (5% EV; unders 10%).
- **Our model** (models/props_nhl.py, the ML model; saves from the game model) is shown and
  tracked next to every line, never priced, until the logged lines show it adds something.
- **The read:** a line "fits the read" when our game analysis points the same way: a shots
  or points over for a team our model expects to out-shoot its usual (team shots or goals
  projected 1+ SD above the league), or an under for a team expected well below it. Tracked
  so we learn whether the game analysis helps props against the market.
Every line at both books goes to `tracking_nhl_props` (data/ledger/nhl_prop_lines.csv), with its book.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import books as B
from betlab import odds_math as om
from betlab import players
from betlab import props_market as PM
from betlab.models import props_nhl as P

MARKETS = {"player_shots_on_goal": "shots", "player_points": "points", "player_total_saves": "saves",
           "player_goal_scorer_anytime": "goals"}
LABEL = {"shots": "shots", "points": "points", "saves": "saves", "goals": "goals"}
# Anytime goal scorer (Oct 10, Mike): FanDuel posts it (Yes only); Pinnacle posts a two-way Yes / No for most
# skaters, so the fair chance is Pinnacle's no-vig, as for soccer scorers (cards/props_soccer.pinnacle_scorer).
SCORER = "player_goal_scorer_anytime"


def _mean_for(p_over: float, line: float, size: float) -> float:
    """The negative binomial mean whose P(over line) is p_over (bisection)."""
    lo, hi = 0.01, 80.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if float(P.p_over(mid, line, size)) < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _consensus(g: pd.DataFrame, point: float, size: float | None = None, moved: list | None = None) -> tuple[float | None, int]:
    """Median no-vig P(over) across the other books (never FanDuel or DraftKings: PM.mine) at the judged book's
    number, and how many books. A book at a different number is moved to that number along the stat's negative
    binomial (size from the model's training residuals) when `size` is given, else skipped. `moved`, when given,
    gets True appended if no book quoted the exact number (the price is then a lean at most: rule 1, Oct 12)."""
    fairs, exact = [], 0
    for _, b in g[~g["bookmaker"].isin(PM.mine())].groupby("bookmaker"):
        for pt in sorted(b["point"].dropna().unique(), key=lambda x: abs(float(x) - point)):
            o = b[(b["outcome"] == "Over") & (b["point"] == pt)]
            u = b[(b["outcome"] == "Under") & (b["point"] == pt)]
            if not (len(o) and len(u)):
                continue
            p = om.no_vig_two_way(float(o["price"].iloc[0]), float(u["price"].iloc[0]))[0]
            if float(pt) != point:
                if size is None or abs(float(pt) - point) > 2:
                    continue
                p = float(P.p_over(_mean_for(p, float(pt), size), point, size))
            else:
                exact += 1
            fairs.append(p)
            break
    if moved is not None:
        moved.append(bool(fairs) and exact == 0)
    return (float(np.median(fairs)), len(fairs)) if fairs else (None, 0)


LINEUP = 18                               # skaters dressed in an NHL game


def tonight_features(skaters: pd.DataFrame, games: list[dict], injured: set[str],
                     feed_players: set[str] | None = None) -> pd.DataFrame:
    """Feature rows for tonight's skaters. games: [{game_id, team, opp, home, b2b, team_shots_proj,
    opp_shots_proj, team_xg, opp_goalie_sv}] (one per team). Each team's expected lineup: the
    skaters from its last 3 games (a rested star still counts) plus anyone in the props feed
    whose latest team it is, less the injured, the 18 with the most recent ice time."""
    from betlab.sources.nhl import _plain

    feed_players = feed_players or set()
    latest = skaters.sort_values("date").drop_duplicates("player_id", keep="last")
    rows = []
    for g in games:
        t = skaters[skaters["team"] == g["team"]]
        if t.empty:
            continue
        last3 = sorted(t["game_id"].unique())[-3:]
        cand = latest[(latest["team"] == g["team"]) & (latest["player_id"].isin(t.loc[t["game_id"].isin(last3), "player_id"])
                                                      | latest["player"].map(_plain).isin(feed_players))]
        cand = cand[~cand["player"].map(_plain).isin(injured)]
        recent_toi = t.groupby("player_id")["toi"].apply(lambda x: x.tail(10).mean())
        cand = cand.assign(rt=cand["player_id"].map(recent_toi)).sort_values("rt", ascending=False)
        lineup = pd.concat([cand[cand["player"].map(_plain).isin(feed_players)], cand]).drop_duplicates("player_id")
        lineup = lineup.sort_values("rt", ascending=False).head(LINEUP)
        for p in lineup.itertuples():
            rows.append({"game_id": g["game_id"], "season": int(t["season"].max()), "date": g["date"],
                         "player_id": p.player_id, "player": p.player, "pos": p.pos, "team": g["team"], "opp": g["opp"],
                         "home": g["home"], "toi": np.nan, "ev_toi": np.nan, "pp_toi": np.nan, "sh_toi": np.nan,
                         **{st: np.nan for st in P.STATS}, "pp_points": np.nan})
    if not rows:
        return pd.DataFrame()
    tonight = pd.DataFrame(rows)
    feats = P.features(pd.concat([skaters, tonight], ignore_index=True))
    feats = feats[feats["game_id"].isin({g["game_id"] for g in games}) & feats["shots"].isna()]
    gf = pd.DataFrame(games)[["game_id", "team", "team_shots_proj", "opp_shots_proj", "team_xg", "opp_goalie_sv", "b2b"]]
    return feats.drop(columns=[c for c in P.GAME_FEATURES if c != "home"], errors="ignore").merge(
        gf, on=["game_id", "team"], how="left")


def price(props: pd.DataFrame, asof: pd.Timestamp, games: dict, feats: pd.DataFrame, fitted: P.Fitted | None,
          goalies: dict, league: dict, saves_size: float = 37.0) -> tuple[pd.DataFrame, list[dict]]:
    """(offer rows, tracker rows) for every prop line at each of Mike's books (one tracker row per book). games: {event_id: {matchup,
    commence_time, game_ref, home, away, home_name, away_name, read: {team: {"shots": z, "goals": z}}}};
    goalies: {(event_id, plain name): {"team", "mean"}} for saves."""
    from betlab.sources.nhl import _plain

    props = props[pd.to_datetime(props["commence_time"], utc=True, format="ISO8601") > asof]
    props = props[props["market"].isin(MARKETS)]
    if props.empty:
        return pd.DataFrame(), []
    means = P.predict(fitted, feats) if fitted is not None and len(feats) else pd.DataFrame()
    by_name = {}
    if len(feats):
        f = feats.assign(plain=feats["player"].map(_plain))
        for i, r in f.iterrows():
            by_name[(r["team"], r["plain"])] = (r, means.loc[i] if len(means) else None)
    offers, track = [], []
    al = players.aliases()
    props = props.assign(_k=props["player"].map(lambda n: al.get(players.normalize(n), players.normalize(n))))
    for (eid, market, _), g in props.groupby(["event_id", "market", "_k"]):   # one player, any book's spelling
        if eid not in games:
            continue
        for book in B.targets("props"):
            mine = g[g["bookmaker"] == book]
            if mine.empty:
                continue
            _price_book(g, mine, book, eid, market, games[eid], by_name, fitted, goalies, saves_size, offers, track)
    return pd.DataFrame(offers), track


def _price_book(g, fd, book, eid, market, info, by_name, fitted, goalies, saves_size, offers, track) -> None:
    """One player's line at one book: a tracker row, and offers when the consensus prices it."""
    from betlab.sources.nhl import _plain

    player = str(fd["player"].iloc[0])
    stat = MARKETS[market]
    # puck drop from the odds feed: the NHL lists games on the hour (6:00) though play starts ~6:10, and the
    # listed time made the tracker drop a game's lines as "started" at the 6:00 tick (Oct 10)
    start = str(g["commence_time"].iloc[0]) if "commence_time" in g and pd.notna(g["commence_time"].iloc[0])             else info["commence_time"]
    scorer = market == SCORER
    o, u = fd[fd["outcome"].isin(["Over", "Yes"])], fd[fd["outcome"] == "Under"]
    if o.empty:
        return
    point = 0.5 if scorer else float(o["point"].iloc[0])
    if not scorer:                             # the under at the over's number (a book may hang two)
        u = u[u["point"] == o["point"].iloc[0]]
    size_mkt = saves_size if stat == "saves" else (fitted.dispersion.get(stat) if fitted is not None else None)
    if scorer:
        from betlab.cards.props_soccer import pinnacle_scorer
        p_mkt = pinnacle_scorer(g)
        n_books = int(p_mkt is not None)
        moved = False
    else:
        mv: list = []
        p_mkt, n_books = _consensus(g, point, size_mkt if size_mkt and np.isfinite(size_mkt) else None, mv)
        moved = bool(mv and mv[0])
    plain = _plain(player)
    spellings = [plain] + [_plain(n) for n in g["player"].dropna().unique() if _plain(n) != plain]
    known = [p for p in spellings if any((tm, p) in by_name for tm in (info["home"], info["away"]))
             or (eid, p) in goalies]
    plain = known[0] if known else plain       # the spelling our NHL data knows (any book's)
    # our model
    mean, team, size = None, None, None
    if stat == "saves":
        gl = goalies.get((eid, plain))
        if gl:
            mean, team, size = gl["mean"], gl["team"], saves_size
    else:
        for tm in (info["home"], info["away"]):
            if (tm, plain) in by_name:
                row, mu = by_name[(tm, plain)]
                team = tm
                if mu is not None:
                    mean, size = float(mu[stat]), fitted.dispersion[stat]
                break
    p_model = float(P.p_over(mean, point, size)[()]) if mean is not None else None
    read = _read(info, team, stat)
    over_pr = float(o["price"].iloc[0])
    under_pr = float(u["price"].iloc[0]) if len(u) else None
    track.append({"event_id": eid, "book": book, "game_ref": info["game_ref"], "commence_time": start,
                  "matchup": info["matchup"], "player": player, "team": team, "stat": stat, "line": point,
                  "fd_over": over_pr, "fd_under": under_pr, "p_market": p_mkt, "books": n_books,
                  "p_model": p_model, "model_mean": mean, "read": read,
                  **({k: _f(by_name[(team, plain)][0].get(k)) for k in P.PLAYER_FEATURES + P.GAME_FEATURES}
                     if (team, plain) in by_name else {})})
    if p_mkt is None:
        return
    for side, pr, pk, pm in (("Yes" if scorer else "Over", over_pr, p_mkt, p_model),
                             ("Under", under_pr, 1 - p_mkt, None if p_model is None else 1 - p_model)):
        if pr is None:
            continue
        offers.append({"league": "nhl", "event_id": eid, "game_ref": info["game_ref"],
                       "commence_time": start, "matchup": info["matchup"], "market": market,
                       "side": side, "player": player,
                       "label": f"{player} to score" if scorer else f"{player} {side.lower()} {point:g} {LABEL[stat]}",
                       "point": point, "price": pr, "book": book, "kind": "prop", "w_model": 0.0,
                       "p_model": pm if pm is not None else pk, "p_market": pk, "p_final": pk, "p_push": 0.0,
                       "ev": om.expected_value(pk, pr),
                       "market_source": "Pinnacle no-vig" if scorer else f"consensus of {n_books} books"
                       + (", moved to the book's number: a lean at most" if moved else ""), "lean_only": moved,
                       "model_number": (f"our model {mean:.2f} {LABEL[stat]}" if mean is not None else "no model"),
                       "context": (f"{player} {side.lower()} {point:g} {LABEL[stat]}: {B.name(book)} {pr:+.0f} vs the other books' "
                                   f"no-vig {pk:.1%}" + (f"; our model {pm:.1%} (no weight)" if pm is not None else "")
                                   + (f". {read}" if read else "."))})


def _f(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else float(x)


def _read(info: dict, team: str | None, stat: str) -> str:
    """'' or a sentence when our game analysis points at this team's volume (1+ SD)."""
    if team is None or stat == "saves":
        return ""
    z = (info.get("read") or {}).get(team, {}).get("goals" if stat == "points" else "shots")
    if z is None or abs(z) < 1.0:
        return ""
    what = "goals" if stat == "points" else "shots"
    return (f"Fits the read: {team} projects {abs(z):.1f} SD {'above' if z > 0 else 'below'} the league in {what} tonight "
            f"(overs {'favored' if z > 0 else 'disfavored'})")
