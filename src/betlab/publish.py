"""The app's database (docs/APP_PLAN.md, 2026-10-01).

`betlab publish` writes the same products the page shows into Postgres (Supabase): games,
today's card (offers), the paper record, fun tickets, builder packs, each game's analysis and
the whole documents (scorecard, results, coverage). `betlab sync-personal` brings one user's
bets, typed prices and saved parlays back into the CSV ledgers, replacing the page's
claude/page-sync round trip.

The CSV ledgers stay the source of truth for now; these tables are the app's read model.
build_rows and page_lists are pure (tested without a database); publish and fetch_personal
do the SQL.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import pandas as pd

from betlab.cards.soccer import LEAGUES as _SOCCER
SOCCER = set(_SOCCER)
# The only paper-pick columns a publish may change: grading. Time, price, line and label are
# history (the database trigger refuses any change to them too).
PICK_GRADING = ["status", "profit_flat", "close_point", "close_price", "p_close", "close_push", "clv", "clv_raw",
                "graded_at", "current_rule"]
# What grading fills on a fun ticket or a saved parlay.
TICKET_GRADING = ["status", "leg_results", "profit_1u", "graded_at"]


def league_of(key) -> str:
    """The app's league key: every soccer competition is 'soccer'."""
    key = str(key or "").lower()
    return "soccer" if key in SOCCER or key.startswith("soccer") else key


def clean(v):
    """A value psycopg can send: NaN and inf are null, numpy scalars plain Python."""
    if v is None or isinstance(v, (list, dict)):
        return v
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def ts(v) -> datetime | None:
    v = clean(v)
    if v in (None, ""):
        return None
    t = pd.to_datetime(v, utc=True, errors="coerce")
    return None if pd.isna(t) else t.to_pydatetime()


def num(v) -> float | None:
    v = clean(v)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower()).split())


def _teams(matchup) -> tuple[str, str]:
    away, _, home = str(matchup or "").partition(" @ ")
    return away.strip(), home.strip()


class GameIndex:
    """One row per game. Games from the analysis (previews, the NHL view) keep their league id;
    odds-side items (card lines, fun tickets) find their game by league, start time (within two
    hours) and both teams, and otherwise become a game keyed by the odds event id."""

    def __init__(self, abbr: dict | None = None):
        self.rows: dict[str, dict] = {}
        self.by_event: dict[str, str] = {}
        self.abbr = {_norm(k): _norm(v) for k, v in (abbr or {}).items()}

    def add(self, league, native, when, home, away, matchup=None) -> str:
        gid = f"{league}:{native}"
        row = self.rows.setdefault(gid, {"game_id": gid, "league": league})
        row.update({k: v for k, v in {"commence_time": ts(when), "home": home, "away": away,
                                      "matchup": matchup or (f"{away} @ {home}" if home and away else None)}.items()
                    if v is not None})
        return gid

    def link(self, event_id, gid) -> None:
        if event_id and gid in self.rows:
            self.by_event[str(event_id)] = gid
            self.rows[gid]["odds_event_id"] = str(event_id)

    def _same(self, a, b) -> bool:
        na, nb = _norm(a), _norm(b)
        if not na or not nb:
            return False
        return (na == nb or na.startswith(nb + " ") or nb.startswith(na + " ")
                or self.abbr.get(na) == nb or self.abbr.get(nb) == na)

    def resolve(self, league, event_id, when, matchup) -> str | None:
        league = league_of(league)
        if event_id and str(event_id) in self.by_event:
            return self.by_event[str(event_id)]
        away, home = _teams(matchup)
        t = ts(when)
        hits = [gid for gid, r in self.rows.items()
                if r["league"] == league and r.get("odds_event_id") in (None, str(event_id))
                and t is not None and r.get("commence_time") is not None
                and abs((r["commence_time"] - t).total_seconds()) <= 7200
                and self._same(away, r.get("away")) and self._same(home, r.get("home"))]
        if len(hits) == 1:
            self.link(event_id, hits[0])
            return hits[0]
        if not event_id:
            return None
        gid = self.add(league, event_id, when, home or None, away or None, matchup or None)
        self.link(event_id, gid)
        return gid


def _book(b) -> str:
    """'fanduel' -> 'FanDuel', 'draftkings' -> 'DraftKings' (books.NAME); a missing book is FanDuel."""
    from betlab.books import name
    return name(clean(b) or "fanduel")


def _books(v) -> list[dict] | None:
    if not isinstance(v, list):
        return None
    keep = ("book", "price", "point", "ev", "tier", "units_tier", "bet_limit", "link", "link_main")
    out = [{k: (num(e.get(k)) if k in ("price", "point", "ev", "units_tier", "bet_limit") else e.get(k)) for k in keep if k in e}
           for e in v if isinstance(e, dict) and e.get("book")]
    for e in out:                              # the offers table's tier names
        e["tier"] = {"check_news": "check"}.get(e.get("tier"), e.get("tier")) or None
    return out


def _offer(r: dict, tier: str, games: GameIndex) -> dict:
    return {"offer_id": r["pick_id"], "tier": tier, "league": league_of(r.get("league")),
            "game_id": games.resolve(r.get("league"), r.get("event_id"), r.get("commence_time"), r.get("matchup")),
            "odds_event_id": clean(r.get("event_id")), "commence_time": ts(r.get("commence_time")),
            "matchup": r.get("matchup"), "market": r.get("market"), "kind": r.get("kind"), "side": clean(r.get("side")),
            "player": clean(r.get("player")), "label": r.get("label"), "point": num(r.get("point")),
            "price": num(r.get("price")), "book": _book(r.get("book")),
            "other_book": _book(r.get("other_book")) if clean(r.get("other_book")) else None,
            "other_point": num(r.get("other_point")), "other_price": num(r.get("other_price")), "other_ev": num(r.get("other_ev")),
            "bet_limit": num(r.get("bet_limit")),        # Novig's dollars available at this price (Oct 22; migration 0013)
            **{k: num(r.get(k)) for k in ("p_model", "p_market", "p_final", "p_push", "ev",
                                          "units_flat", "units_tier", "units_kelly")},
            "market_source": clean(r.get("market_source")), "why": clean(r.get("why")),
            "context": clean(r.get("context")), "fd_url": clean(r.get("link")),
            # every book's own read and link (books.per_book, Nov 6): an account with a book off sees the bet elsewhere
            "books": _books(r.get("books"))}   # the betslip link at the offer's own book (FanDuel or DraftKings; name from before Oct 12)


def _paper(df: pd.DataFrame | None, tier: str, current: set) -> list[dict]:
    if df is None or not len(df):
        return []
    out = []
    for r in df.to_dict(orient="records"):
        out.append({"pick_id": r["pick_id"], "tier": tier, "created_at": ts(r.get("created_at")),
                    "league": league_of(r.get("league")), "odds_event_id": clean(r.get("event_id")),
                    "game_ref": clean(r.get("game_ref")), "commence_time": ts(r.get("commence_time")),
                    **{k: clean(r.get(k)) for k in ("matchup", "market", "side", "player", "label", "book", "kind",
                                                    "market_source", "why", "status")},
                    **{k: num(r.get(k)) for k in ("point", "price", "p_model", "p_market", "p_final", "p_push", "ev",
                                                  "units_flat", "units_tier", "units_kelly", "profit_flat",
                                                  "close_point", "close_price", "p_close", "close_push", "clv", "clv_raw")},
                    "graded_at": ts(r.get("graded_at")), "current_rule": r["pick_id"] in current})
    return out


def _grading(fun_df: pd.DataFrame | None) -> dict[str, dict]:
    if fun_df is None or not len(fun_df):
        return {}
    cols = [c for c in ("sgp_id", "status", "leg_results", "profit_1u", "graded_at") if c in fun_df]
    return {r["sgp_id"]: r for r in fun_df[cols].to_dict(orient="records")}


def _ticket(t: dict, kind: str, sport, games: GameIndex, grading: dict, *, event_id=None, matchup=None,
            when=None, slate=None) -> dict:
    g = grading.get(t["sgp_id"], {})
    legs = clean(g.get("leg_results"))
    return {"sgp_id": t["sgp_id"], "kind": kind, "sport": league_of(sport or "nfl"), "slate": slate,
            "game_id": games.resolve(sport or "nfl", event_id, when, matchup) if event_id else None,
            "odds_event_id": clean(event_id), "matchup": matchup or t.get("matchup"),
            "commence_time": ts(when), "fair_price": num(t.get("fair_price")), "p_fair": num(t.get("p_fair")),
            "naive_price": num(t.get("naive_price")), "price": num(t.get("price")), "body": t,
            "status": clean(g.get("status")), "profit_1u": num(g.get("profit_1u")), "graded_at": ts(g.get("graded_at")),
            "leg_results": json.loads(legs) if isinstance(legs, str) and legs.strip()[:1] in "[{" else None}


OWN = ("custom", "novig-")                 # sgp_id prefixes of a user's own bets, kept out of the shared tables


def build_rows(products: dict, picks: pd.DataFrame | None, leans: pd.DataFrame | None,
               fun_df: pd.DataFrame | None, packs: list[tuple[str, dict]], current: set,
               abbr: dict | None = None) -> dict[str, list[dict]]:
    """Table rows from the page products (cli.page_products), the full paper ledgers, the fun
    ledger (for grading), the builder packs (cli.page_docs' fun_legs) and the current-rule ids.

    abbr maps sportsbook team names to the analysis' codes (nflverse.team_abbr_by_name)."""
    games = GameIndex(abbr)
    analysis: list[dict] = []

    for kind, key, league in (("nfl_preview", "previews", "nfl"), ("ncaaf_preview", "previews_ncaaf", "ncaaf")):
        for g in (products.get(key) or {}).get("games", []):
            gid = games.add(league, g["game_id"], g.get("kickoff"), g.get("home"), g.get("away"), g.get("matchup"))
            analysis.append({"game_id": gid, "kind": kind, "body": g})
    for g in (products.get("nhl") or {}).get("games", []):
        gid = games.add("nhl", g["game_id"], g.get("start"), g.get("home"), g.get("away"), g.get("matchup"))
        analysis.append({"game_id": gid, "kind": "nhl", "body": g})
    for g in (products.get("ufc") or {}).get("games", []):      # keyed by event id, as the card's UFC lines (Oct 23)
        gid = games.add("ufc", g["event_id"], g.get("commence_time"), None, None, g.get("matchup"))
        games.link(g["event_id"], gid)
        analysis.append({"game_id": gid, "kind": "ufc", "body": g})
    for g in (products.get("soccer") or {}).get("games", []):   # keyed by event id, as the card's soccer lines
        gid = games.add("soccer", g["event_id"], g.get("commence_time"), g.get("home"), g.get("away"), g.get("matchup"))
        games.link(g["event_id"], gid)
        analysis.append({"game_id": gid, "kind": "soccer", "body": g})

    for league, events in (products.get("schedule") or {}).items():   # every NBA and college game, priced or not
        for e in events:
            games.link(e["id"], games.add(league, e["id"], e.get("commence_time"), e.get("home_team"), e.get("away_team")))

    fun = products.get("fun") or {}
    for g in fun.get("games", []):         # NFL fun games carry both ids: the odds event and nflverse's
        if g.get("game_ref") and f"nfl:{g['game_ref']}" in games.rows:
            games.link(g.get("event_id"), f"nfl:{g['game_ref']}")
    for g in (products.get("nba") or {}).get("games", []):
        gid = games.resolve("nba", g.get("event_id"), g.get("tipoff"), g.get("matchup"))
        if gid:
            analysis.append({"game_id": gid, "kind": "nba", "body": g})

    card = products.get("card") or {}
    offers = [_offer(r, tier, games) for tier, key in (("pick", "picks"), ("lean", "leans"), ("check", "check_news"))
              for r in card.get(key) or []]

    grading = _grading(fun_df)
    tickets: list[dict] = []
    nfl_slips: list[dict] = []     # an NFL game's slips, unless its slate carries them (every slate does, Nov 7)
    for g in fun.get("games", []):
        gid = games.resolve("nfl", g.get("event_id"), g.get("commence_time"), g.get("matchup"))
        for s in g.get("sgps") or []:
            nfl_slips.append(_ticket(s, "sgp", "nfl", games, grading, event_id=g.get("event_id"),
                                     matchup=g.get("matchup"), when=g.get("commence_time")))
        extra = {k: v for k, v in g.items() if k not in ("sgps", "pack")}
        if gid:
            analysis.append({"game_id": gid, "kind": "nfl_fun", "body": extra})
    slates = []
    seen: set[str] = set()
    for doc in (fun, products.get("fun_nba") or {}):
        for sl in doc.get("slates", []):
            sport = sl.get("sport") or "nfl"
            ids = []
            for kind, key in (("sgp_plus", "plus"), ("sgp_plus", "plus_short"), ("td", "td")):
                if sl.get(key):
                    tickets.append(_ticket(sl[key], kind, sport, games, grading, when=sl.get("kickoff"),
                                           slate=sl.get("slate"), matchup=sl[key].get("matchup")))
                    ids.append(sl[key]["sgp_id"])
            for s in sl.get("sgps") or []:   # every game's own slips, shown for watched games (Nov 7)
                if s["sgp_id"] not in seen:     # one row per slip: the upsert can't take a key twice
                    seen.add(s["sgp_id"])
                    tickets.append(_ticket(s, "sgp", s.get("sport") or sport, games, grading, event_id=s.get("event_id"),
                                           matchup=s.get("matchup"), when=s.get("commence_time"), slate=sl.get("slate")))
                ids.append(s["sgp_id"])
            for o in sl.get("overs") or []:
                tickets.append(_ticket(o, "over", o.get("sport") or sport, games, grading, event_id=o.get("event_id"),
                                       matchup=o.get("matchup"), when=o.get("commence_time"), slate=sl.get("slate")))
                ids.append(o["sgp_id"])
            slates.append({k: v for k, v in sl.items() if k not in ("plus", "plus_short", "td", "overs", "packs", "games", "sgps")}
                          | {"sport": league_of(sport), "ticket_ids": ids})
    for row in nfl_slips:              # an NFL game no slate carries (a build without slates) keeps its slips
        if row["sgp_id"] not in seen:
            seen.add(row["sgp_id"])
            tickets.append(row)

    # Tickets get graded the day after, when they're no longer on the card: every generated slip
    # in the fun ledger goes in too (inactive), so a marked parlay's result reaches My bets.
    # Custom slips and synced Novig bets are a user's own: graded in custom_parlays (grade_customs, the Novig sync),
    # never here. Oct 29: a "novig-" bet published as a shared ticket stayed "open" there, and my_bets reads the
    # ticket's status first, so a Novig win showed open in My bets (and the bet sat in a shared table).
    current_ids = {t["sgp_id"] for t in tickets}
    history = []
    if fun_df is not None and len(fun_df):
        for r in fun_df.to_dict(orient="records"):
            sid = str(r.get("sgp_id") or "")
            if not sid or sid in current_ids or sid.startswith(OWN):
                continue
            legs = clean(r.get("legs"))
            history.append(_ticket({"sgp_id": sid, "matchup": clean(r.get("matchup")), "fair_price": r.get("fair_price"),
                                    "p_fair": r.get("p_fair"), "naive_price": r.get("naive_price"), "price": r.get("price"),
                                    "legs": json.loads(legs) if isinstance(legs, str) and legs.startswith("[") else []},
                                   ticket_kind(sid), clean(r.get("sport")) or "nfl", games, grading,
                                   matchup=clean(r.get("matchup"))) | {"odds_event_id": clean(r.get("event_id")) or None,
                                                                       "active": False})

    leg_packs = [{"pack_key": key, "odds_event_id": clean(b.get("event_id")), "sport": league_of(b.get("sport") or "nfl"),
                  "commence_time": ts(b.get("commence_time")), "body": b} for key, b in packs]

    docs = [{"collection": "app", "doc_id": k, "body": products[k]}
            for k in ("results", "golive", "fun_results", "coverage", "meta") if products.get(k)]
    docs.append({"collection": "card", "doc_id": "meta",
                 "body": {k: v for k, v in card.items() if k not in ("picks", "leans", "check_news")}})
    docs.append({"collection": "fun", "doc_id": "meta", "body": {k: v for k, v in fun.items() if k not in ("games", "slates")}})
    docs.append({"collection": "fun", "doc_id": "slates", "body": {"slates": slates}})
    for doc_id, key, part in (("nfl", "previews", "track_record"), ("ncaaf", "previews_ncaaf", "track_record"),
                              ("nhl", "nhl", "tracker"), ("nhl_props", "nhl", "props_tracker"), ("nba", "nba", "tracker")):
        body = (products.get(key) or {}).get(part)
        if body:
            docs.append({"collection": "track", "doc_id": doc_id, "body": body})
    for key in ("previews", "previews_ncaaf", "nhl", "nba"):
        if products.get(key):
            docs.append({"collection": "analysis", "doc_id": key,
                         "body": {k: v for k, v in products[key].items() if k != "games"}})

    return {"games": list(games.rows.values()), "offers": offers,
            "paper_picks": _paper(picks, "pick", current) + _paper(leans, "lean", current),
            "fun_tickets": tickets, "fun_history": history, "leg_packs": leg_packs, "game_analysis": analysis, "docs": docs}


# ------------------------------------------------------------------------------------------- SQL

KEYS = {"games": ["game_id"], "offers": ["offer_id"], "paper_picks": ["pick_id", "tier"], "fun_tickets": ["sgp_id"],
        "leg_packs": ["pack_key"], "game_analysis": ["game_id", "kind"], "docs": ["collection", "doc_id"]}
STAMP = {"games": "updated_at", "offers": "published_at", "fun_tickets": "published_at", "leg_packs": "published_at",
         "game_analysis": "published_at", "docs": "published_at"}


def _jsonable(v):
    from psycopg.types.json import Jsonb

    from betlab.cli import finite
    return Jsonb(finite(v)) if isinstance(v, (dict, list)) else v


def upsert(cur, table: str, rows: list[dict], update: list[str] | None = None) -> int:
    """Insert rows, updating existing ones by primary key (only `update` columns when given)."""
    if not rows:
        return 0
    cols = sorted({c for r in rows for c in r})
    keys = KEYS[table]
    sets = [c for c in (update or cols) if c not in keys]
    sql = (f"insert into {table} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
           f"on conflict ({', '.join(keys)}) do update set "
           + ", ".join([f"{c} = excluded.{c}" for c in sets] + ([f"{STAMP[table]} = now()"] if table in STAMP else [])))
    cur.executemany(sql, [[_jsonable(r.get(c)) for c in cols] for r in rows])
    return len(rows)


MOVED = ("select g.game_id as old, n.gid as new from games g "
         "join unnest(%s::text[], %s::text[]) as n(ev, gid) on g.odds_event_id = n.ev and g.game_id <> n.gid")


def merge_games(cur, games: list[dict]) -> int:
    """A game first seen only on the odds side is stored under its odds event id; once its preview
    arrives it gets its league id and claims the same event (odds_event_id is unique: Oct 2, a
    college game). Move the older row's lines and tickets onto the new id and drop it."""
    pairs = [(g["odds_event_id"], g["game_id"]) for g in games if g.get("odds_event_id")]
    if not pairs:
        return 0
    args = [[e for e, _ in pairs], [g for _, g in pairs]]
    for table in ("offers", "fun_tickets"):
        cur.execute(f"update {table} t set game_id = m.new from ({MOVED}) m where t.game_id = m.old", args)
    cur.execute(f"delete from game_analysis a using ({MOVED}) m where a.game_id = m.old", args)
    cur.execute(f"delete from games g using ({MOVED}) m where g.game_id = m.old", args)
    return getattr(cur, "rowcount", 0) or 0


STALE = ("select game_id, league, odds_event_id, home, away, commence_time from games "
         "where game_id = league || ':' || odds_event_id and commence_time > now() - interval '1 day'")


def claim_stale(stale: list[tuple], games: list[dict]) -> int:
    """Oct 25: card leans seen before their games' previews (the 3 AM publish had 3 NFL previews) stored the games
    under their odds event ids ("CIN @ BAL"); by the 9:55 publish the leans were gone, so nothing named the event, the
    preview's row never claimed it and the game showed twice. A published league row with no event claims a stored
    event-keyed row (stale: game_id, league, odds_event_id, home, away, commence_time) of the same league, start
    (within two hours) and teams, by code or name; merge_games then moves the old row. Returns how many it claimed."""
    def names(r, side):
        away, home = _teams(r.get("matchup"))
        return {_norm(r.get(side)), _norm(home if side == "home" else away)} - {""}

    n, published = 0, {g["game_id"] for g in games} | {g.get("odds_event_id") for g in games}
    for gid, league, event, home, away, when in stale:
        if gid in published or event in published:
            continue        # still published under its event (odds_event_id is unique): GameIndex links those
        t = pd.Timestamp(when)
        hits = [g for g in games if g.get("league") == league and not g.get("odds_event_id")
                and g.get("commence_time") is not None and abs((pd.Timestamp(g["commence_time"]) - t).total_seconds()) <= 7200
                and _norm(home) in names(g, "home") and _norm(away) in names(g, "away")]
        if len(hits) == 1:
            hits[0]["odds_event_id"] = event
            n += 1
    return n


def publish(conn, rows: dict[str, list[dict]]) -> dict[str, int]:
    """Write every table in one transaction. Card lines and tickets the latest products no longer
    contain turn inactive; builder packs are replaced; paper picks only take new grading."""
    counts = {}
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(STALE)
        claim_stale(cur.fetchall() or [], rows["games"])
        counts["games_merged"] = merge_games(cur, rows["games"])
        for table in ("games", "game_analysis", "docs"):
            counts[table] = upsert(cur, table, rows[table])
        counts["paper_picks"] = upsert(cur, "paper_picks", rows["paper_picks"], update=PICK_GRADING)
        for table, key in (("offers", "offer_id"), ("fun_tickets", "sgp_id")):
            counts[table] = upsert(cur, table, [r | {"active": True} for r in rows[table]])
            cur.execute(f"update {table} set active = false where active and not ({key} = any(%s))",
                        [[r[key] for r in rows[table]]])
        counts["fun_history"] = upsert(cur, "fun_tickets", rows.get("fun_history", []), update=TICKET_GRADING)
        cur.execute("delete from leg_packs where not (pack_key = any(%s))", [[r["pack_key"] for r in rows["leg_packs"]]])
        counts["leg_packs"] = upsert(cur, "leg_packs", rows["leg_packs"])
    return counts


def pulse(conn) -> None:
    """Tell open apps the card changed (`app_pulse`, migration 0033). Only a nudge, so a failure never fails the publish."""
    try:
        with conn.transaction():
            conn.execute("update app_pulse set at = now() where key = 'card'")
    except Exception as e:  # noqa: BLE001
        print(f"live pulse: not sent ({type(e).__name__}: {e})")


# ------------------------------------------------------------------------- personal -> ledgers

def ticket_kind(sgp_id: str) -> str:
    """A fun-ledger slip's kind from its id: plus-… SGP+, td-… the TD ticket, else a one-game SGP."""
    return {"plus": "sgp_plus", "td": "td", "over": "over"}.get(str(sgp_id).split("-", 1)[0], "sgp")


# A custom bet entered straight into bets (Oct 20 on: Mike's FanDuel slips from screenshots, his Novig bets) has no
# saved parlay, and my_bets reads a custom bet's result only from one: 16 bets stayed open in My bets though the
# ledger had graded them (Oct 22). Each gets its row from the bet itself before grades are copied.
MISSING_CUSTOMS = """
insert into custom_parlays (user_id, sgp_id, price, legs, games, matchup, odds_event_id, n_legs, quoted_at)
select b.user_id, b.sgp_id, b.price, coalesce(b.legs, '[]'::jsonb), b.games, b.matchup, b.odds_event_id,
       jsonb_array_length(coalesce(b.legs, '[]'::jsonb)), b.placed_at
from bets b
where b.user_id = %s and b.sgp_id like 'custom%%'
on conflict (user_id, sgp_id) do nothing
"""


def grade_customs(conn, user_id: str, fun_df: pd.DataFrame | None) -> int:
    """Copy the fun ledger's grading onto the owner's saved parlays (custom_parlays), so their
    results reach My bets without the slip ever entering a shared table. A custom bet with no saved
    parlay gets one first (MISSING_CUSTOMS)."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(MISSING_CUSTOMS, [user_id])
    if fun_df is None or not len(fun_df):
        return 0
    rows = []
    for sid, g in _grading(fun_df).items():
        if not str(sid).startswith("custom") or clean(g.get("status")) in (None, "", "open"):
            continue
        legs = clean(g.get("leg_results"))
        rows.append([clean(g.get("status")), _jsonable(json.loads(legs)) if isinstance(legs, str) and legs.strip()[:1] in "[{" else None,
                     num(g.get("profit_1u")), ts(g.get("graded_at")), user_id, sid])
    if rows:
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany("update custom_parlays set status = %s, leg_results = %s, profit_1u = %s, graded_at = %s "
                            "where user_id = %s and sgp_id = %s", rows)
    return len(rows)


def page_tap_rows(taken: list[dict], fun_taken: list[dict], fun_quotes: list[dict],
                  lean_ids: set, pick_ids: set) -> dict[str, list[dict]]:
    """The old page's marks and typed prices (the lists the page sync saves) as one user's
    database rows: bets, quotes, and custom_parlays for the user's own slips. Pure."""
    def jl(v):
        return v if isinstance(v, list) else None

    bets = [{"kind": "lean" if t["pick_id"] in lean_ids and t["pick_id"] not in pick_ids else "pick",
             "pick_id": t["pick_id"], "mode": t.get("mode") or "paper", "price": num(t.get("price")),
             "stake": num(t.get("stake")), "label": t.get("label"), "matchup": t.get("matchup"),
             "placed_at": ts(t.get("placed_at"))} for t in taken if t.get("pick_id")]
    bets += [{"kind": "custom" if str(t["sgp_id"]).startswith("custom") else "parlay", "sgp_id": t["sgp_id"],
              "mode": t.get("mode") or "paper", "price": num(t.get("price")), "stake": num(t.get("stake")),
              "label": None, "matchup": t.get("matchup"), "fair_price": num(t.get("fair_price")),
              "p_fair": num(t.get("p_fair")), "legs": jl(t.get("legs")), "games": jl(t.get("games")),
              "odds_event_id": t.get("event_id") or None, "placed_at": ts(t.get("placed_at"))}
             for t in fun_taken if t.get("sgp_id")]
    quotes, customs = [], []
    for q in fun_quotes:
        if not q.get("sgp_id") or num(q.get("price")) is None:
            continue
        row = {"sgp_id": q["sgp_id"], "price": num(q.get("price")), "fair_price": num(q.get("fair_price")),
               "naive_price": num(q.get("naive_price")), "p_fair": num(q.get("p_fair")),
               "n_legs": int(q["n_legs"]) if num(q.get("n_legs")) is not None else None,
               "legs": jl(q.get("legs")), "games": jl(q.get("games")), "matchup": q.get("matchup"),
               "odds_event_id": q.get("event_id") or None, "sport": q.get("sport"), "quoted_at": ts(q.get("quoted_at")),
               **({"book": q["book"]} if q.get("book") else {})}
        if str(q["sgp_id"]).startswith("custom"):
            customs.append(row | {"legs": row["legs"] or [], "grade": q.get("grade"), "grade_parts": q.get("grade_parts")})
        else:
            quotes.append(row)
    return {"bets": bets, "quotes": quotes, "custom_parlays": customs}


def import_page_taps(conn, user_id: str, rows: dict[str, list[dict]]) -> dict[str, int]:
    """Add the old page's marks and prices for one user. Insert-only: a row the user already has
    (same pick or slip) is left alone, so it's safe to run every day while both apps are in use."""
    counts = {}
    with conn.transaction(), conn.cursor() as cur:
        for table, items in rows.items():
            n = 0
            for r in items:
                r = {k: v for k, v in r.items() if v is not None} | {"user_id": user_id}
                cols = sorted(r)
                cur.execute(f"insert into {table} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
                            "on conflict do nothing", [_jsonable(r[c]) for c in cols])
                n += max(cur.rowcount or 0, 0)
            counts[table] = n
    return counts


def iso(v) -> str:
    """A database timestamp as the ISO text the ledgers sort and parse ('2026-10-01T16:57:00+00:00')."""
    return v.isoformat() if isinstance(v, datetime) else str(v or "")


def page_lists(bets: list[dict], quotes: list[dict], customs: list[dict]) -> tuple[list, list, list]:
    """One user's database rows in the shapes the page's sync produced (taken, fun_quotes,
    fun_taken), so ledger.apply_taken and fun_ledger.sync work unchanged."""
    def ev(r):
        return {k: v for k, v in r.items() if k != "odds_event_id"} | {"event_id": r.get("odds_event_id") or ""}

    taken = [{"pick_id": b["pick_id"], "mode": b.get("mode"), "price": num(b.get("price")), "stake": num(b.get("stake")),
              "book": b.get("book"), "bonus": bool(b.get("bonus")),
              "label": b.get("label"), "matchup": b.get("matchup"), "placed_at": iso(b.get("placed_at"))}
             for b in bets if b.get("pick_id")]
    fun_taken = [ev({k: v for k, v in b.items() if k in ("sgp_id", "mode", "stake", "price", "fair_price", "p_fair", "legs", "sport",
                                                          "matchup", "odds_event_id", "games")})
                 | {"placed_at": iso(b.get("placed_at")), "bonus": bool(b.get("bonus")), "cashout": num(b.get("cashout")), "boost": num(b.get("boost")),
                    "boost_cap": num(b.get("boost_cap")),                    # a boost's max extra winnings (0029, Oct 30)
                    "protect": bool(b.get("protect"))}                       # Bet Protect+ (0023, Oct 26)
                 for b in bets if b.get("sgp_id")]
    fun_quotes = [ev({k: v for k, v in q.items() if k != "user_id"}) | {"quoted_at": iso(q.get("quoted_at"))}
                  for q in [*quotes, *customs]]
    for lst in (fun_taken, fun_quotes):
        for r in lst:
            for k in ("price", "stake", "fair_price", "naive_price", "p_fair"):
                if k in r:
                    r[k] = num(r[k])
            r.pop("user_id", None)
    return taken, fun_quotes, fun_taken


def app_users(conn) -> list[str]:
    """Every account with a bet, a typed price or a saved parlay (Oct 10: more than the owner's)."""
    rows = conn.execute("select user_id::text from bets union select user_id::text from quotes "
                        "union select user_id::text from custom_parlays").fetchall()
    return sorted(r[0] for r in rows)


def others_as_quotes(quotes: list[dict], fun_taken: list[dict]) -> list[dict]:
    """Another account's typed prices and marked parlays as plain quotes for the fun ledger: every slip
    gets graded and its FanDuel price counts in the parlay-price stats (Mike, Oct 10: combine them), while
    the ledger's marked / stake / profit stay the owner's fun bucket. Their money is in their own My bets."""
    return quotes + [{k: v for k, v in t.items() if k not in ("mode", "stake")} for t in fun_taken
                     if t.get("sgp_id")]


def fetch_personal(conn, user_id: str) -> tuple[list, list, list]:
    """The owner's bets, typed prices and saved parlays (the service connection bypasses
    row-level security, so the user is named explicitly)."""
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cur:
        out = []
        for table in ("bets", "quotes", "custom_parlays"):
            cur.execute(f"select * from {table} where user_id = %s", [user_id])
            out.append(cur.fetchall())
        # The app saves a marked or quoted multi-game ticket (SGP+, TD) without its games, and the fun ledger
        # can only grade a ticket whose legs it can tie to games (Oct 9: an Oct 4 SGP+ sat open for days).
        # The published ticket has them: fill the games and sport from fun_tickets.
        # A DraftKings quote ("<id>~dk", Oct 12) takes the ticket's games with its own legs (DraftKings' labels: a rung
        # moved to DraftKings' nearest number grades as that rung), in the same order.
        base = lambda sid: str(sid).removesuffix("~dk")
        need = sorted({base(r["sgp_id"]) for rows in out[:2] for r in rows if r.get("sgp_id") and not r.get("games")})
        if need:
            cur.execute("select sgp_id, sport, body->'games' as games from fun_tickets "
                        "where sgp_id = any(%s) and jsonb_typeof(body->'games') = 'array'", [need])
            tickets = {t["sgp_id"]: t for t in cur.fetchall()}
            for rows in out[:2]:
                for r in rows:
                    t = tickets.get(base(r.get("sgp_id")))
                    if t and not r.get("games"):
                        games = t["games"]
                        own = r.get("legs") if str(r.get("sgp_id")).endswith("~dk") else None
                        if own and len(own) == sum(len(g.get("legs") or []) for g in games):
                            it = iter(own)
                            games = [g | {"legs": [(l if isinstance(l, str) else l) | {"label": next(it)} if isinstance(l, dict)
                                                   else next(it) for l in g.get("legs") or []]} for g in games]
                        r["games"] = games
                        r["sport"] = r.get("sport") or t["sport"]
    return tuple(out)


# ------------------------------------------------------------------------------ migrations


def migrations_dir():
    from betlab import config
    return config.ROOT / "supabase" / "migrations"


def migrate(conn, files=None, already: set | None = None) -> list[str]:
    """Apply supabase/migrations/*.sql that haven't run yet, in name order, each in its own
    transaction, recording it in betlab_meta.migrations (a schema the app's API never exposes).
    `already` marks files applied by hand before this table existed (0001 ran in the SQL editor)."""
    conn.execute("create schema if not exists betlab_meta")
    conn.execute("create table if not exists betlab_meta.migrations (name text primary key, applied_at timestamptz not null default now())")
    conn.execute("revoke all on schema betlab_meta from public")
    for name in sorted(already or ()):
        conn.execute("insert into betlab_meta.migrations (name) values (%s) on conflict do nothing", [name])
    done = {r[0] for r in conn.execute("select name from betlab_meta.migrations").fetchall()}
    ran = []
    for f in sorted(files or migrations_dir().glob("*.sql")):
        if f.name in done:
            continue
        with conn.transaction():
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("insert into betlab_meta.migrations (name) values (%s)", [f.name])
        ran.append(f.name)
    return ran
