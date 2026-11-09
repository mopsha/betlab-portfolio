"""College Game Previews (the Games tab's College view): how each game should go, and the early read.

For every FBS-vs-FBS game in the latest college odds snapshot that kicks off in the next
week (the read was tested only on those; FCS mismatches are left out):
- **The score** from the market (median spread and total), our efficiency read next to it.
- **The how** (models/game_ncaaf.py): plays, pass/run, and each unit ranked among FBS
  teams (EPA, success rate, pass and run EPA, line yards, stuff rate, explosiveness),
  plus the biggest unit matchups.
- **Kickoff weather** at the venue (CFBD venues; domes get none). Shown, not applied:
  the weather effects were fit on the NFL.
- **The early read** at FanDuel's line (else the market's): which side and how strong,
  in SDs. Strong reads (1+ SD) beat the opener 53-55% in 2022-25 and the line moved
  their way; against the close they were about break-even. Tracked in
  data/ledger/cfb_reads.csv, never priced.

Games New York rules forbid (NY colleges, games played in NY) keep the analysis but get no read.
"""

from __future__ import annotations

import pandas as pd

from betlab import config, ny_rules
from betlab.models import game_ncaaf as GC
from betlab.sources import cfbd, weather

NOTE = ("College games: the score comes from the market; the rest is our efficiency read from every "
        "play this season and last. The early read found value against Tuesday's opening numbers in "
        "2022-25 (strong totals reads won 55%), not against Saturday's closing lines, so it matters "
        "most early in the week. Tracked here, never a pick yet.")
READ_MIN = 1.0  # show a read at this strength (SDs of the fitted prediction)
UNITS = [("epa", "EPA per play"), ("success", "Success rate"), ("pass_epa", "Pass EPA"), ("rush_epa", "Run EPA"),
         ("line_yards", "Line yards"), ("stuff_rate", "Stuff rate"), ("explosiveness", "Explosiveness")]


def _lines(ev: pd.DataFrame, home_name: str) -> dict:
    """Market median spread (home favored positive) and total, and FanDuel's own lines and prices."""
    out = {}
    sp = ev[(ev["market"] == "spreads") & (ev["outcome"] == home_name)]
    tot = ev[(ev["market"] == "totals") & (ev["outcome"] == "Over")]
    if len(sp):
        out["spread_home"] = -float(sp["point"].median())
    if len(tot):
        out["total"] = float(tot["point"].median())
    fd = ev[ev["bookmaker"] == "fanduel"]
    h = fd[(fd["market"] == "spreads") & (fd["outcome"] == home_name)]
    a = fd[(fd["market"] == "spreads") & (fd["outcome"] != home_name)]
    o = fd[(fd["market"] == "totals") & (fd["outcome"] == "Over")]
    u = fd[(fd["market"] == "totals") & (fd["outcome"] == "Under")]
    if len(h) and len(a):
        out.update(fd_spread_home=-float(h["point"].iloc[0]), fd_home_price=int(h["price"].iloc[0]),
                   fd_away_price=int(a["price"].iloc[0]))
    if len(o) and len(u):
        out.update(fd_total=float(o["point"].iloc[0]), fd_over_price=int(o["price"].iloc[0]),
                   fd_under_price=int(u["price"].iloc[0]))
    return out


def _fmt_spread(team: str, home_line: float, is_home: bool) -> str:
    pts = -home_line if is_home else home_line  # the bettor's number for that team
    return f"{team} {'+' if pts > 0 else ''}{pts:g}" if pts else f"{team} pick'em"


def _read_rows(g, rd: dict, ln: dict, meta: dict) -> tuple[dict, list[dict]]:
    """The page's read (strong only) and the tracker rows (every kind with a line)."""
    shown, rows = {}, []
    if "spread" in rd:
        line = ln.get("fd_spread_home", ln.get("spread_home"))
        home_side = rd["spread"]["edge_pts"] > 0
        side = "home" if home_side else "away"
        price = ln.get("fd_home_price" if home_side else "fd_away_price")
        label = _fmt_spread(g.home_team if home_side else g.away_team, line, home_side)
        row = {**meta, "kind": "spread", "side": side, "label": label, "line": line, "price": price,
               "strength": rd["spread"]["strength"], "edge": rd["spread"]["edge_pts"],
               "book": "fanduel" if "fd_spread_home" in ln else "consensus"}
        rows.append(row)
        if abs(rd["spread"]["strength"]) >= READ_MIN:
            shown["spread"] = {"label": label, "price": price, "strength": abs(rd["spread"]["strength"]),
                               "edge_pts": abs(rd["spread"]["edge_pts"]), "drivers": rd["spread"]["drivers"]}
    if "total" in rd:
        line = ln.get("fd_total", ln.get("total"))
        over = rd["total"]["edge_pts"] > 0
        price = ln.get("fd_over_price" if over else "fd_under_price")
        label = f"{'Over' if over else 'Under'} {line:g}"
        rows.append({**meta, "kind": "total", "side": "over" if over else "under", "label": label, "line": line,
                     "price": price, "strength": rd["total"]["strength"], "edge": rd["total"]["edge_pts"],
                     "book": "fanduel" if "fd_total" in ln else "consensus"})
        if abs(rd["total"]["strength"]) >= READ_MIN:
            shown["total"] = {"label": label, "price": price, "strength": abs(rd["total"]["strength"]),
                              "edge_pts": abs(rd["total"]["edge_pts"]), "drivers": rd["total"]["drivers"]}
    return shown, rows


def _weather(venue) -> dict:
    if venue is None or pd.isna(venue.get("latitude")):
        return {"text": ""}
    if bool(venue.get("dome")):
        return {"text": f"Indoors at {venue['name']}: no weather."}
    return {"venue": venue["name"], "lat": float(venue["latitude"]), "lon": float(venue["longitude"])}


def build(asof: pd.Timestamp, days: int = 7) -> tuple[dict, list[dict]]:
    """The College view's document and the early-read rows for the tracker (cfb_reads.record)."""
    from betlab.cli import latest_snapshot

    doc = {"note": NOTE, "games": []}
    rows_all: list[dict] = []
    snap = latest_snapshot(config.settings()["leagues"]["ncaaf"]["sport_key"])
    if snap is None:
        return doc, rows_all
    games = cfbd.games()
    today = asof.tz_convert("America/New_York").tz_localize(None).normalize()
    up = games[(games["date"] >= today) & (games["date"] < today + pd.Timedelta(days=days)) & games["margin"].isna()]
    tg = GC.team_games(cfbd.advanced(), games)
    fit = GC.load_early()
    names = cfbd.team_names()
    venues = pd.read_parquet(cfbd.VENUES).set_index("venue_id") if cfbd.VENUES.exists() else None
    snap = snap[pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof]
    ratings, ranks = {}, {}
    for (home_name, away_name), ev in snap.groupby(["home_team", "away_team"]):
        home, away = names.get(home_name), names.get(away_name)
        g = up[(up["home_team"] == home) & (up["away_team"] == away)]
        if g.empty:
            g = up[(up["home_team"] == away) & (up["away_team"] == home)]
            if g.empty:
                continue
        g = g.iloc[0]
        if g["home_div"] != "fbs" or g["away_div"] != "fbs":
            continue
        if g["date"] not in ratings:
            ratings[g["date"]] = GC.fit_ratings(tg, g["date"])
            ranks[g["date"]] = GC.ranks(ratings[g["date"]])
        r, rk = ratings[g["date"]], ranks[g["date"]]
        home_odds = home_name if g["home_team"] == home else away_name
        ln = _lines(ev, home_odds)
        pr = GC.project(r, g["home_team"], g["away_team"], neutral=bool(g["neutral"]))
        market = None
        if "spread_home" in ln and "total" in ln:
            market = {"spread_home": ln["spread_home"], "total": ln["total"],
                      "home_points": (ln["total"] + ln["spread_home"]) / 2, "away_points": (ln["total"] - ln["spread_home"]) / 2}
        teams = []
        for t, o in ((g["away_team"], g["home_team"]), (g["home_team"], g["away_team"])):
            s = pr["sides"][t]
            unit = lambda side, stat: {"value": round(float(r.league[stat] + side[stat].get(t, 0.0)), 3),
                                       "rank": int(rk[f"{'off' if side is r.off else 'def'}_{stat}"].get(t, 0)) or None}
            teams.append({"team": t, "plays": round(s["plays"], 1), "pass_rate": round(s["pass_rate"], 3),
                          "points": round(s["points"], 1),
                          **{f"off_{k}": unit(r.off, k) for k, _ in UNITS}, **{f"def_{k}": unit(r.dfn, k) for k, _ in UNITS}})
        venue = venues.loc[int(g["venue_id"])].to_dict() if venues is not None and pd.notna(g["venue_id"]) \
            and int(g["venue_id"]) in venues.index else None
        wx = _weather(venue)
        if "lat" in wx:
            f = weather.forecast(wx["lat"], wx["lon"], g["kickoff"])
            wx = {"text": (f"Outdoors at {wx['venue']}: {f['temp_f']:.0f}°F, wind {f['wind_mph']:.0f} mph "
                           f"(gusts {f['gust_mph']:.0f}), {f['precip_prob'] * 100:.0f}% chance of "
                           f"{'snow' if f['temp_f'] <= 34 else 'rain'}.") if f else f"Outdoors at {wx['venue']}.",
                  "forecast": f}
        ok, why = ny_rules.allowed("ncaaf", g["home_team"], g["away_team"], venue_state=g.get("venue_state"))
        entry = {"game_id": g["game_id"], "matchup": f"{g['away_team']} @ {g['home_team']}",
                 "kickoff": pd.Timestamp(g["kickoff"]).isoformat(), "home": g["home_team"], "away": g["away_team"],
                 "market": market, "fanduel": {k: v for k, v in ln.items() if k.startswith("fd_")},
                 "ours": {"home_points": round(pr["home_points"], 1), "away_points": round(pr["away_points"], 1),
                          "margin": round(pr["margin"], 1), "total": round(pr["total"], 1)},
                 "teams": teams, "matchups": GC.matchups(r, g["home_team"], g["away_team"], n=3),
                 "weather": wx, "read": {}, "ny_blocked": None if ok else why}
        if ok and fit:
            rd = GC.early_read(GC.early_features(r, g["home_team"], g["away_team"]),
                               ln.get("fd_spread_home", ln.get("spread_home")), ln.get("fd_total", ln.get("total")), fit)
            meta = {"game_id": g["game_id"], "season": int(g["season"]), "week": int(g["week"]),
                    "kickoff": pd.Timestamp(g["kickoff"]).tz_convert("UTC").isoformat(), "matchup": entry["matchup"]}
            entry["read"], rows = _read_rows(g, rd, ln, meta)
            rows_all += rows
        doc["games"].append(entry)
    doc["games"].sort(key=lambda e: (-max([x["strength"] for x in e["read"].values()] or [0]), e["kickoff"]))
    return doc, rows_all
