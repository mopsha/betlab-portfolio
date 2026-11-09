"""NHL game previews (the Games tab's NHL view) from free data: exports/nhl.json.

For every game today and tomorrow with a DraftKings line on ESPN:
- the line (moneyline, puck line, total) and its no-vig chances;
- the starting goalies: ESPN's Confirmed or Probable starter, else our guess (the goalie
  with the most recent starts, and his partner on the second night of a back-to-back),
  marked as such;
- our model (models/nhl.py): each team's expected goals, the win chance and fair
  moneyline, the expected total and the chance of the over at DraftKings' number;
- the teams' ranks (shots, goals, 5-on-5 control), records and back-to-backs;
- a **read** where our win chance and DraftKings' no-vig chance differ by `nhl.read_min`
  or more. Reads are tracked (tracking_nhl.py), never picks: the model hasn't beaten the
  market (docs/MODELS.md, "NHL"), and these are DraftKings' lines, not FanDuel's.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import fields
from types import SimpleNamespace

import numpy as np
import pandas as pd

from betlab import config
from betlab import odds_math as om
from betlab.models import nhl as M
from betlab.sources import nhl as src

PARAMS = config.DATA_DIR / "models" / "nhl.json"
ET = "America/New_York"


def load_params() -> M.Params:
    """The backtest's tuned settings (data/models/nhl.json), else the defaults."""
    if not PARAMS.exists():
        return M.Params()
    raw = json.loads(PARAMS.read_text(encoding="utf-8")).get("params", {})
    names = {f.name for f in fields(M.Params)}
    return M.Params(**{k: v for k, v in raw.items() if k in names})


def _norm(name: str | None) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace(".", " ").replace("-", " ").split())


def _goalie_key(name: str | None, team: str, gg: pd.DataFrame) -> str | None:
    """ESPN's goalie name as the NHL spells it (accents and initials differ between feeds)."""
    if not name:
        return None
    n = _norm(name)
    names = gg["goalie"].dropna().unique()
    exact = [g for g in names if _norm(g) == n]
    if exact:
        return exact[0]
    last = n.split()[-1]
    same = gg[(gg["team"] == team) & (gg["goalie"].map(lambda g: _norm(g).split()[-1] == last))]
    return same["goalie"].iloc[-1] if len(same) else name


def _guess_goalie(team: str, gg: pd.DataFrame, b2b: bool) -> str | None:
    """Most starts in the team's last 10 games; on a back-to-back, whoever didn't start last night."""
    st = gg[(gg["team"] == team) & (gg["started"] == 1)].sort_values("date")
    if st.empty:
        return None
    last10 = st.tail(10)["goalie"].value_counts()
    first = last10.index[0]
    if b2b and st["goalie"].iloc[-1] == first and len(last10) > 1:
        return last10.index[1]
    return first


def _record(tg: pd.DataFrame, team: str, season: int) -> str:
    t = tg[(tg["team"] == team) & (tg["season"] == season)]
    if t.empty:
        return "0-0-0"
    w = int(t["win"].sum())
    otl = int(((t["win"] == 0) & (t["extra"] == 1)).sum())
    return f"{w}-{len(t) - w - otl}-{otl}"


def build(asof: pd.Timestamp | None = None) -> tuple[dict, list[dict]]:
    """(page document, tracker rows)."""
    asof = asof or pd.Timestamp.now(tz="UTC")
    local = asof.tz_convert(ET)
    season = src.current_season(local)
    s = config.settings().get("nhl", {})
    read_min = float(s.get("read_min", 0.04))
    raw = src.load_team_games([season - 2, season - 1, season])
    tg = M.team_games(raw)
    gg = src.load_goalie_games([season - 2, season - 1, season])
    p = load_params()
    today = local.tz_localize(None).normalize()
    r = M.fit(tg, gg, today, p)
    rk = M.ranks(r)
    from betlab.cards import analysis_nhl as A

    try:
        sr = M.special_ratings(tg, src.load_special_teams([season - 1, season]), today)
    except Exception:
        sr = pd.DataFrame()
    try:
        skaters = src.load_skater_games([season - 1, season])
        injuries = src.injuries_now()
    except Exception:
        skaters, injuries = pd.DataFrame(columns=["team", "date", "game_id", "player", "toi", "shots"]), pd.DataFrame()
    board = pd.concat([src.scoreboard((local + pd.Timedelta(days=d)).strftime("%Y%m%d")) for d in (0, 1)],
                      ignore_index=True)
    if board.empty:
        return {"generated_at": asof.isoformat(timespec="seconds"), "games": [], "note": NOTE}, []
    board = board[(board["state"] == "pre") & (board["season_type"] == 2)]
    try:
        sched = src.schedule(local.strftime("%Y-%m-%d"))
    except Exception:
        sched = pd.DataFrame(columns=["game_id", "start", "home", "away"])
    played = pd.concat([tg[["team", "date"]],
                        sched.assign(date=pd.to_datetime(sched["start"], utc=True, format="ISO8601").dt.tz_convert(ET).dt.tz_localize(None).dt.normalize())
                             .melt(id_vars=["date"], value_vars=["home", "away"], value_name="team")[["team", "date"]]])
    fd = _fanduel_offers(asof)
    fd_lines = _fanduel_lines(asof)
    games, rows, ctx = [], [], {}
    for b0 in board.itertuples():
        # FanDuel's prices against Pinnacle's no-vig chance when today's pull has the game;
        # DraftKings from ESPN otherwise (the goalies always come from ESPN).
        b = SimpleNamespace(**b0._asdict())
        sharp = fd_lines.get(f"{b.away} @ {b.home}")
        if sharp:
            for k in ("ml_home_close", "ml_away_close", "total_close", "over_close", "under_close", "pl_home_close",
                      "pl_home_close_price", "pl_away_close_price"):
                setattr(b, k, sharp[k])
            b.ml_home_open = b.ml_away_open = None
            b.book = "FanDuel"
        start = pd.Timestamp(b.start)
        day = start.tz_convert(ET).tz_localize(None).normalize()
        match = sched[(sched["home"] == b.home) & (sched["away"] == b.away)
                      & (pd.to_datetime(sched["start"], utc=True, format="ISO8601").dt.tz_convert(ET).dt.tz_localize(None).dt.normalize() == day)]
        game_id = str(match["game_id"].iloc[0]) if len(match) else f"espn-{b.espn_id}"
        b2b = {t: bool(((played["team"] == t) & (played["date"] == day - pd.Timedelta(days=1))).any()) for t in (b.home, b.away)}
        goalies = {}
        for side, team in (("home", b.home), ("away", b.away)):
            espn_name, status = getattr(b, f"{side}_goalie"), getattr(b, f"{side}_goalie_status")
            if isinstance(espn_name, str) and espn_name:
                goalies[side] = (_goalie_key(espn_name, team, gg), str(status or "probable").lower())
            else:
                goalies[side] = (_guess_goalie(team, gg, b2b[team]), "our guess")
        pr = M.project(r, b.home, b.away, goalies["home"][0], goalies["away"][0], b2b[b.home], b2b[b.away])
        has_ml = pd.notna(getattr(b, "ml_home_close", None)) and pd.notna(getattr(b, "ml_away_close", None))
        p_mkt = om.no_vig_two_way(b.ml_home_close, b.ml_away_close)[0] if has_ml else None
        total = getattr(b, "total_close", None)
        has_tot = pd.notna(total) and pd.notna(getattr(b, "over_close", None)) and pd.notna(getattr(b, "under_close", None))
        p_over_mkt = om.no_vig_two_way(b.over_close, b.under_close)[0] if has_tot else None
        if sharp:                          # the market is the sharp book's no-vig chance, not FanDuel's own
            p_mkt = sharp["p_home"] if sharp["p_home"] is not None else p_mkt
            p_over_mkt = sharp["p_over"] if sharp["p_over"] is not None else p_over_mkt
        p_over_model = None
        if pd.notna(total):
            po, push = M.p_over(pr, float(total))
            p_over_model = po / max(1 - push, 1e-6)
        gap = (pr["p_home"] - p_mkt) if p_mkt is not None else None
        read = None
        if gap is not None and abs(gap) >= read_min:
            side_home = gap > 0
            team = b.home if side_home else b.away
            price = b.ml_home_close if side_home else b.ml_away_close
            read = {"side": team, "label": f"{team} ML", "price": price, "gap": round(float(abs(gap)), 3),
                    "p_model": round(pr["p_home"] if side_home else 1 - pr["p_home"], 3),
                    "p_market": round(p_mkt if side_home else 1 - p_mkt, 3)}
        team_row = lambda t, side: {
            "team": t, "record": _record(tg, t, season), "b2b": b2b[t],
            "xg": round(pr[f"{side}_xg"], 2), "shots": round(pr[f"{side}_shots"], 1),
            "goalie": goalies[side][0], "goalie_status": goalies[side][1],
            "goalie_sv": round(M.goalie_sv(r, goalies[side][0]), 3),
            "ranks": {k: (int(v) if pd.notna(v) else None) for k, v in (rk.loc[t].to_dict() if t in rk.index else {}).items()}}
        hurt_rows = {t: A.hurt(injuries, skaters, t, today) for t in (b.home, b.away)}
        doc = {"game_id": game_id, "espn_id": str(b.espn_id), "start": b.start, "matchup": f"{b.away} @ {b.home}",
               "script": A.script(b.home, b.away, pr, sr, goalies, b2b, hurt_rows, r),
               "matchups": A.matchups(r, sr, b.home, b.away, goalies["home"][0], goalies["away"][0]),
               "injuries": hurt_rows,
               "special": {t: ({k: (int(v) if k.endswith("rank") else round(float(v), 3)) for k, v in sr.loc[t].items()}
                               if len(sr) and t in sr.index else None) for t in (b.home, b.away)},
               "home": b.home, "away": b.away, "book": _str(getattr(b, "book", None)),
               "teams": [team_row(b.away, "away"), team_row(b.home, "home")],
               "line": {"ml_home": _num(getattr(b, "ml_home_close", None)), "ml_away": _num(getattr(b, "ml_away_close", None)),
                        "ml_home_open": _num(getattr(b, "ml_home_open", None)), "ml_away_open": _num(getattr(b, "ml_away_open", None)),
                        "total": _num(total), "over": _num(getattr(b, "over_close", None)), "under": _num(getattr(b, "under_close", None)),
                        "puck_home": _num(getattr(b, "pl_home_close", None)), "puck_home_price": _num(getattr(b, "pl_home_close_price", None)),
                        "puck_away_price": _num(getattr(b, "pl_away_close_price", None)),
                        "p_home": _r(p_mkt), "p_over": _r(p_over_mkt)},
               "model": {"p_home": _r(pr["p_home"]), "fair_home": _num(om.prob_to_american(pr["p_home"])),
                         "fair_away": _num(om.prob_to_american(1 - pr["p_home"])), "exp_total": round(pr["exp_total"], 2),
                         "p_over": _r(p_over_model), "p_tie_reg": _r(pr["p_tie_reg"]),
                         "p_home_cover": _r(M.p_cover(pr, float(b.pl_home_close))) if pd.notna(getattr(b, "pl_home_close", None)) else None},
               "gap": _r(gap), "read": read,
               "fanduel": [{"label": o["label"], "price": o["price"], "p_market": _r(o["p_market"]),
                            "ev": _r(o["ev"]), "source": o["market_source"],
                            "dk_price": o.get("dk_price"), "dk_ev": _r(o["dk_ev"]) if o.get("dk_ev") is not None else None}
                           for o in fd.get(f"{b.away} @ {b.home}", [])]}
        games.append(doc)
        ctx[(b.home, b.away)] = {"game_id": game_id, "date": day, "start": b.start, "pr": pr, "goalies": goalies,
                                 "b2b": b2b, "matchups": doc["matchups"], "doc": doc}
        rows.append({"game_id": game_id, "espn_id": b.espn_id, "start": b.start, "home": b.home, "away": b.away,
                     "book": _str(getattr(b, "book", None)), "ml_home": _num(getattr(b, "ml_home_close", None)),
                     "ml_away": _num(getattr(b, "ml_away_close", None)), "total": _num(total),
                     "over": _num(getattr(b, "over_close", None)), "under": _num(getattr(b, "under_close", None)),
                     "p_mkt": _r(p_mkt), "p_model": _r(pr["p_home"]), "p_over_mkt": _r(p_over_mkt),
                     "p_over_model": _r(p_over_model), "home_goalie": goalies["home"][0], "away_goalie": goalies["away"][0],
                     "home_goalie_status": goalies["home"][1], "away_goalie_status": goalies["away"][1],
                     "home_xg": round(pr["home_xg"], 3), "away_xg": round(pr["away_xg"], 3),
                     "exp_total": round(pr["exp_total"], 3)})
    from betlab import tracking_nhl, tracking_nhl_props

    try:
        offers, track = _props(asof, ctx, skaters, injuries, r)
    except Exception as exc:              # props are a bonus: never block the game view
        print(f"NHL props skipped ({type(exc).__name__}: {exc})")
        offers, track = pd.DataFrame(), []
    doc = {"generated_at": asof.isoformat(timespec="seconds"), "season": season, "read_min": read_min,
           "note": NOTE, "tracker": tracking_nhl.summary(), "props_tracker": tracking_nhl_props.summary(),
           "games": sorted(games, key=lambda g: g["start"]),
           "_prop_offers": offers.to_dict("records") if len(offers) else [], "_prop_track": track}
    return doc, rows


def _props(asof: pd.Timestamp, ctx: dict, skaters: pd.DataFrame, injuries: pd.DataFrame, r: M.Ratings):
    """FanDuel's and DraftKings' NHL props from today's props pull, priced (cards/props_nhl.py) with the ML
    model's chances and the game analysis's read; each game's page rows go on its document."""
    import joblib

    from betlab.cards import props_nhl as PN
    from betlab.models import props_nhl as P

    key = config.settings()["leagues"]["nhl"]["sport_key"]
    files = sorted((config.DATA_DIR / "odds" / key).glob("*/*_props.parquet"))
    if not files:
        return pd.DataFrame(), []
    props = pd.read_parquet(files[-1])
    if props.empty or asof - pd.to_datetime(props["snapshot_ts"], utc=True).max() > pd.Timedelta(hours=24):
        return pd.DataFrame(), []
    model_path = config.DATA_DIR / "models" / "nhl_props.joblib"
    fitted = joblib.load(model_path) if model_path.exists() else None
    meta_path = config.DATA_DIR / "models" / "nhl_props_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    codes = src.team_codes()
    injured = set(injuries.loc[~injuries["status"].fillna("").str.contains("Day", case=False), "plain"]) \
        if len(injuries) else set()
    sd_goals = float(np.std(r.off["goals"])) * np.sqrt(2) or 0.3
    games, team_rows, goalies = {}, [], {}
    for eid, ev in props.groupby("event_id"):
        home, away = src.code_for(ev["home_team"].iloc[0], codes), src.code_for(ev["away_team"].iloc[0], codes)
        c = ctx.get((home, away))
        if c is None:
            continue
        pr = c["pr"]
        shots_z = {m["team"]: m["size"] for m in c["matchups"] if m["kind"] == "shots"}
        read = {t: {"shots": shots_z.get(t), "goals": (pr[f"{side}_xg"] - r.league["goals"]) / sd_goals}
                for t, side in ((home, "home"), (away, "away"))}
        games[eid] = {"matchup": f"{away} @ {home}", "commence_time": c["start"], "game_ref": c["game_id"],
                      "home": home, "away": away, "read": read}
        for t, o, side, oside in ((home, away, "home", "away"), (away, home, "away", "home")):
            team_rows.append({"game_id": int(c["game_id"]) if str(c["game_id"]).isdigit() else c["game_id"],
                              "date": c["date"], "team": t, "opp": o, "home": int(side == "home"),
                              "b2b": float(c["b2b"][t]), "team_shots_proj": pr[f"{side}_shots"],
                              "opp_shots_proj": pr[f"{oside}_shots"], "team_xg": pr[f"{side}_xg"],
                              "opp_goalie_sv": pr[f"{oside}_goalie_sv"]})
            gname = c["goalies"][side][0]
            if gname:
                mean = P.saves_mean(pr[f"{oside}_shots"], M.goalie_sv(r, gname)) * float(meta.get("saves_bias", 1.0))
                goalies[(eid, src._plain(gname))] = {"team": t, "mean": mean}
    if not games:
        return pd.DataFrame(), []
    feed = set(props["player"].dropna().map(src._plain))
    feats = PN.tonight_features(skaters, team_rows, injured, feed)
    offers, track = PN.price(props, asof, games, feats, fitted, goalies, {}, float(meta.get("saves_size", 37.0)))
    for eid, info in games.items():
        doc = ctx[(info["home"], info["away"])]["doc"]
        # the game page: FanDuel's lines, plus DraftKings' where FanDuel has none (points); both books on day 3
        mine = [t for t in track if t["event_id"] == eid]
        fd_has = {(t["player"], t["stat"]) for t in mine if t.get("book", "fanduel") == "fanduel"}
        mine = [t for t in mine if t.get("book", "fanduel") == "fanduel" or (t["player"], t["stat"]) not in fd_has]
        evs = {(o["player"], o["market"], o["side"], o["book"]): o["ev"]
               for o in (offers.to_dict("records") if len(offers) else []) if o["event_id"] == eid}
        doc["props"] = sorted([{"player": t["player"], "book": t.get("book", "fanduel"), "team": t["team"], "stat": t["stat"], "line": t["line"],
                                "fd_over": t["fd_over"], "fd_under": t["fd_under"], "p_market": _r(t["p_market"]),
                                "p_model": _r(t["p_model"]), "model_mean": _r(t["model_mean"], 2), "read": t["read"],
                                "ev_over": _r(evs.get((t["player"], _market(t["stat"]), "Yes" if t["stat"] == "goals" else "Over", t.get("book", "fanduel")))),
                                "ev_under": _r(evs.get((t["player"], _market(t["stat"]), "Under", t.get("book", "fanduel"))))} for t in mine],
                              key=lambda x: (x["stat"], x["team"] or "", x["player"]))
    return offers, track


def _market(stat: str) -> str:
    """The feed's market for a tracked stat (cards/props_nhl.MARKETS, inverted; goals = anytime scorer)."""
    from betlab.cards.props_nhl import MARKETS

    return {v: k for k, v in MARKETS.items()}[stat]


def _fanduel_lines(asof: pd.Timestamp) -> dict[str, dict]:
    """FanDuel's moneyline, total and puck line for each game in today's NHL pull, with the
    sharp book's no-vig home and over chances (Pinnacle first): {matchup: {...}}."""
    from betlab.cards import nhl as card
    from betlab.market import two_way

    key = config.settings()["leagues"]["nhl"]["sport_key"]
    files = sorted((config.DATA_DIR / "odds" / key).glob("*/*_pick.parquet"))
    if not files:
        return {}
    snap = pd.read_parquet(files[-1])
    if snap.empty or asof - pd.to_datetime(snap["snapshot_ts"], utc=True).max() > pd.Timedelta(hours=24):
        return {}
    try:
        codes = src.team_codes()
    except Exception:
        return {}
    out = {}
    for _, ev in snap.groupby("event_id"):
        hn, an = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        home, away = src.code_for(hn, codes), src.code_for(an, codes)
        ml = two_way(ev, "h2h", "fanduel", hn, an)
        if not (home and away and ml):
            continue
        row = {"ml_home_close": float(ml[0][1]), "ml_away_close": float(ml[1][1]), "total_close": None, "over_close": None,
               "under_close": None, "pl_home_close": None, "pl_home_close_price": None, "pl_away_close_price": None,
               "p_home": card._fair(ev, "h2h", hn, an)[0], "p_over": None}
        tot = two_way(ev, "totals", "fanduel", "Over", "Under")
        if tot:
            row.update(total_close=float(tot[0][0]), over_close=float(tot[0][1]), under_close=float(tot[1][1]),
                       p_over=card._fair(ev, "totals", "Over", "Under", point_a=tot[0][0])[0])
        pl = two_way(ev, "spreads", "fanduel", hn, an)
        if pl:
            row.update(pl_home_close=float(pl[0][0]), pl_home_close_price=float(pl[0][1]), pl_away_close_price=float(pl[1][1]))
        out[f"{away} @ {home}"] = row
    return out


def _fanduel_offers(asof: pd.Timestamp) -> dict[str, list[dict]]:
    """FanDuel's prices against the sharp book from today's NHL odds pull (cards/nhl.py), by
    matchup; {} before the first pull or when it's more than 24 hours old."""
    from betlab.cards import nhl as card

    key = config.settings()["leagues"]["nhl"]["sport_key"]
    files = sorted((config.DATA_DIR / "odds" / key).glob("*/*_pick.parquet"))
    if not files:
        return {}
    snap = pd.read_parquet(files[-1])
    if snap.empty or asof - pd.to_datetime(snap["snapshot_ts"], utc=True).max() > pd.Timedelta(hours=24):
        return {}
    try:
        offers = card.evaluate(snap, asof)
    except Exception:
        return {}
    try:                                          # DraftKings beside it (the game page's price table, Oct 13)
        dk = card.evaluate(snap, asof, book="draftkings")
    except Exception:
        dk = pd.DataFrame()
    dk_by = {(o["matchup"], o["label"]): o for o in dk.to_dict("records")} if len(dk) else {}
    out: dict[str, list[dict]] = {}
    for o in offers.to_dict("records") if len(offers) else []:
        d = dk_by.get((o["matchup"], o["label"]))
        out.setdefault(o["matchup"], []).append(o | ({"dk_price": d["price"], "dk_ev": d["ev"]} if d else {}))
    return out


NOTE = ("FanDuel's lines, judged against Pinnacle's no-vig chance (DraftKings from ESPN when today's FanDuel pull "
        "isn't in). The model's win chances come from shots, "
        "scoring and tonight's goalies; it hasn't beaten the market, so reads are tracked, never picks.")


def _num(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) or pd.isna(x) else float(x)


def _str(x):
    """Text or None: the ESPN fallback leaves a missing book as NaN, which isn't JSON."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return {"Draft Kings": "DraftKings"}.get(str(x), str(x))   # ESPN writes it with a space


def _r(x, d: int = 4):
    return None if x is None or pd.isna(x) else round(float(x), d)


def write(doc: dict) -> None:
    config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.EXPORTS_DIR / "nhl.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
