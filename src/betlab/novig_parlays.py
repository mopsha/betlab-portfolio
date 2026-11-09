"""Novig's side of every parlay (Mike, Oct 28: "build sgp and sgp+ in novig"): the exact price, not a likely one.

FanDuel and DraftKings only show a parlay's price in their apps, so their side of a slip is a likely quote from a model.
Novig prices any set of outcomes through its free parlay pricer (`POST /rfq/v2/quote/unauthenticated`, docs.novig.com,
Affiliates > Parlay Pricing; no key, no credits; the Oct 28 route, `/nbx/v1/parlay/request/unauthenticated`, was gone by
Oct 29 and every slip read as refused for two days): it answers 2-20 outcome ids with one price, the parlay's chance.
So each slip gets Novig's real price, and the whole slip opens in Novig's app in one tap (`events/<id>,<id>/oddsapi/<stake>`).

- **Legs:** each leg is found on Novig's public catalog by its game (`sources/novig.match`: both teams, start within 10
  minutes), then by market type and number: player props by name (`STATS`), game lines by side. Novig's two-way
  markets list the home side first (MONEY "CHI": CHI, NYK; SPREAD "MIN +9.5": MIN +9.5, BUF -9.5).
- **What Novig won't take:** the NO side of a yes/no market (a double chance is one), and some same-game pairs (two
  lines of one kind, a stat inside another on one player: docs, RFQ > Eligibility). A slip with a leg Novig doesn't
  list says how many it has; a refused slip says so.
- **Answers:** 200 a price; 400 legs it won't combine; 404 no price right now (try later); 429 over its limit (a burst
  of 10, then 1 a second; we wait its `Retry-After`). 3 slips at a time, and the answer is kept 30 minutes
  (`data/cache/novig_parlays.json`; no price 10 minutes). It no longer says the largest payout, so `stake_max` is gone.
- **A dead pricer is loud:** a route that's gone ("Cannot POST") or answers nothing usable raises `PricerError`, and when
  every slip asked failed that way, `attach` raises, so the publish log says "novig parlays (...): not priced".
- **Settlement:** a void leg counts at its fair value and the rest must win (`fun_ledger._finish`); never a push.
- Read-only: BetLab never places orders (CLAUDE.md, hard rule 5).
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import requests

from betlab import books, config
from betlab import odds_math as om
from betlab.sources import novig

PRICER = "https://api.novig.com/rfq/v2/quote/unauthenticated"
LINK = "https://novig.com/events/{ids}/oddsapi/{{wager}}"
CACHE = config.CACHE_DIR / "novig_parlays.json"
TTL, TTL_REFUSED = 30 * 60, 10 * 60
TRIES, WORKERS = 3, 3

# our stat -> Novig's market types, per sport (GET /v3/public/types/markets)
STATS = {
    "nba": {"points": "POINTS", "rebounds": "REBOUNDS", "assists": "ASSISTS", "threes": "THREE_POINTERS_MADE",
            "pra": "POINTS_REBOUNDS_ASSISTS", "pr": "POINTS_REBOUNDS", "pa": "POINTS_ASSISTS", "ra": "REBOUNDS_ASSISTS",
            "steals": "STEALS", "blocks": "BLOCKS", "double double": "DOUBLE_DOUBLE"},
    "nfl": {"receptions": "RECEPTIONS", "receiving_yards": "RECEIVING_YARDS", "rushing_yards": "RUSHING_YARDS",
            "passing_yards": "PASSING_YARDS", "tds": "ANYTIME_TOUCHDOWN_SCORER"},
    "nhl": {"shots": "SHOTS_ON_GOAL", "points": "POINTS", "assists": "ASSISTS", "goals": "PLAYER_GOALS",
            "saves": "SAVES"},
    "soccer": {"sot": "SHOTS_ON_TARGET", "goals": "PLAYER_GOALS"},
}
STATS["ncaaf"] = {}                                  # New York rules: no college player props
SPORT_OF_KEY = {"basketball_nba": "nba", "americanfootball_nfl": "nfl", "americanfootball_ncaaf": "ncaaf",
                "icehockey_nhl": "nhl", "mma_mixed_martial_arts": "ufc", "basketball_ncaab": "ncaab"}
NOT_GAME = ("game side", "", None)


def _plain(s) -> str:
    from betlab.links import _plain as p
    return p(s).replace("-", " ")


def same_player(ours: str, theirs: str) -> bool:
    """'Michael Porter Jr' = 'Michael Porter Jr.'; 'C. Borralho' = 'Caio Borralho' (Novig's UFC names)."""
    a = [t for t in _plain(ours).split() if t not in ("jr", "sr", "ii", "iii", "iv")]
    b = [t for t in _plain(theirs).split() if t not in ("jr", "sr", "ii", "iii", "iv")]
    if not a or not b:
        return False
    if a == b:
        return True
    return a[-1] == b[-1] and a[0][0] == b[0][0] and (len(a[0]) == 1 or len(b[0]) == 1)


def _player_of(market: dict) -> str:
    """'Karl-Anthony Towns 24.5 POINTS' -> 'Karl-Anthony Towns'; 'Nicolas Roy FIRST_GOAL_SCORER' -> 'Nicolas Roy'."""
    d = re.sub(r"\s+[A-Z0-9_]+$", "", str(market.get("description", "")))
    return re.sub(r"\s+-?\d+(\.\d+)?$", "", d).strip()


def _num(s) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


class Index:
    """Our games (from the pulls' rows: teams, start and sport by event id) and their Novig events and markets."""

    def __init__(self, rows: pd.DataFrame, listed: list[dict] | None = None, markets=None):
        self.games = {}
        if len(rows):
            for e, g in rows.drop_duplicates("event_id").set_index("event_id").iterrows():
                key = str(g.get("sport_key") or "")
                sport = SPORT_OF_KEY.get(key, "soccer" if key.startswith("soccer_") else key)
                self.games[str(e)] = {"home": g["home_team"], "away": g["away_team"],
                                      "start": g["commence_time"], "sport": sport}
        self._listed = listed
        self._markets_fn = markets or novig.markets
        self._markets: dict[str, list[dict]] = {}
        self._events: dict[str, dict | None] = {}

    def listed(self) -> list[dict]:
        if self._listed is None:
            try:
                self._listed = novig.open_events()
            except requests.RequestException:
                self._listed = []
        return self._listed

    def event(self, event_id) -> tuple[dict, dict] | None:
        """(our game, Novig's event) for an event id, or None."""
        g = self.games.get(str(event_id))
        if g is None:
            return None
        if str(event_id) not in self._events:
            self._events[str(event_id)] = novig.match({"home_team": g["home"], "away_team": g["away"],
                                                       "commence_time": g["start"]}, self.listed())
        n = self._events[str(event_id)]
        return (g, n) if n else None

    def markets(self, novig_event_id: str) -> list[dict]:
        if novig_event_id not in self._markets:
            try:
                self._markets[novig_event_id] = [m for m in self._markets_fn(novig_event_id) if m.get("status") == "OPEN"]
            except requests.RequestException:
                self._markets[novig_event_id] = []
        return self._markets[novig_event_id]


def _teams_by_abbr(sport: str) -> dict:
    from betlab import bans
    try:
        return {a.upper(): t["name"] for t in bans.teams().get(sport, []) for a in t.get("abbr", [])}
    except Exception:  # noqa: BLE001
        return {}


def _is_home(leg: dict, game: dict) -> bool | None:
    """Whether a game-line leg backs the home side (by its team, else its label), or None when it can't tell."""
    team = str(leg.get("team") or "").strip()
    name = _teams_by_abbr(game["sport"]).get(team.upper(), team) if team else ""
    for cand in (name, re.sub(r"\s+(ML|[-+]\d+(\.\d+)?|to win|or draw)$", "", str(leg.get("label", "")), flags=re.I)):
        if not cand:
            continue
        h, a = novig._same_team(cand, game["home"]), novig._same_team(cand, game["away"])
        if h != a:
            return h
    return None


def leg_outcome(leg: dict, game: dict, mkts: list[dict]) -> dict | None:
    """The Novig outcome for one of our legs ({outcomeId, name, ...} with `_market`), or None if Novig doesn't list it."""
    stat, side, point = str(leg.get("stat") or ""), str(leg.get("side") or "").lower(), _num(leg.get("point"))
    player = leg.get("player")

    def pick(types, test, check=None):
        hits = [(m, o) for m in mkts if m.get("marketType") in types and (check is None or check(m))
                for o in m.get("outcomes") or [] if test(m, o)]
        return hits[0][1] | {"_market": hits[0][0]} if len(hits) == 1 else None

    def at(m):
        return point is not None and _num(m.get("strike")) is not None and abs(float(m["strike"]) - point) < 1e-6

    over_under = lambda m, o: str(o.get("name", "")).lower().startswith(side) and side in ("over", "under")
    if player not in NOT_GAME and stat not in ("moneyline", "spread", "total", "puck line", "draw", "btts"):
        kind = STATS.get(game["sport"], {}).get(stat)
        if not kind:
            return None
        mine = lambda m: same_player(player, _player_of(m))
        if kind in ("ANYTIME_TOUCHDOWN_SCORER", "DOUBLE_DOUBLE") or (point is None and side == "yes"):
            return pick({kind}, lambda m, o: str(o.get("name")).lower() == "yes", mine)
        return pick({kind}, over_under, lambda m: mine(m) and at(m))
    if stat == "draw":
        return pick({"MONEYLINE_3_WAY_DRAW"}, lambda m, o: str(o.get("name")).lower() == "yes")
    if stat == "btts":
        return pick({"BOTH_TEAMS_TO_SCORE"}, lambda m, o: str(o.get("name")).lower() == ("no" if side == "no" else "yes"))
    if stat in ("total", "goals", "total points"):
        return pick({"TOTAL"}, over_under, at)
    home = _is_home(leg, game)
    if home is None:
        return None
    idx = 0 if home else 1                                   # Novig lists the home side first
    if stat == "moneyline":
        if game["sport"] == "soccer":
            team = game["home"] if home else game["away"]
            return pick({"MONEYLINE_3_WAY_WIN"}, lambda m, o: str(o.get("name")).lower() == "yes",
                        lambda m: novig._same_team(re.sub(r"\s*MONEYLINE_3_WAY_WIN\s*$", "", m.get("description", "")), team))
        return pick({"MONEY"}, lambda m, o: (m.get("outcomes") or [None, None]).index(o) == idx)
    if stat in ("spread", "puck line"):
        def mine(m, o):
            oc = m.get("outcomes") or []
            if len(oc) != 2 or oc.index(o) != idx:
                return False
            got = re.search(r"([-+]\d+(\.\d+)?)\s*$", str(o.get("name", "")))
            return got is not None and point is not None and abs(float(got.group(1)) - point) < 1e-6
        return pick({"SPREAD"}, mine)
    return None


def _ask(o: dict) -> float | None:
    """The price to buy one side of a two-way market: 1 - the best bid on the other side, when $50 stands behind it."""
    oc = o["_market"].get("outcomes") or []
    other = [x for x in oc if x.get("outcomeId") != o.get("outcomeId")]
    if len(oc) != 2 or len(other) != 1:
        return None
    other = other[0].get("bid") or {}
    p, qty = _num(other.get("price")), _num(other.get("qty")) or 0.0
    if p is None or not 0.0 < 1.0 - p < 1.0 or qty / 100.0 * (1.0 - p) < books.min_limit():
        return None                                     # a thin book's price is no price (books.min_limit, $50)
    return 1.0 - p


# ------------------------------------------------------------------ the pricer
def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class PricerError(RuntimeError):
    """The pricer didn't answer as documented (its route gone, 5xx, junk): not the same as "no price for these legs"."""


def price(ids: list[str], post=None) -> dict | None:
    """Novig's price for these outcomes: {price (American), p}, or None when it won't price them. Raises PricerError
    when the pricer itself fails, so a dead endpoint can't pass for a run of refusals (Oct 29-30)."""
    post = post or (lambda body: requests.post(PRICER, json=body, headers={"User-Agent": "BetLab"}, timeout=20))
    why = "no answer"
    for i in range(TRIES):
        try:
            r = post({"outcomeIds": list(ids)})
            body = r.json() if r.status_code != 204 else None
        except (requests.RequestException, ValueError) as e:
            r, body, why = None, None, type(e).__name__
        if r is not None:
            msg = str((body or {}).get("message") or "") if isinstance(body, dict) else ""
            if r.status_code < 300:
                p = _num(body.get("price")) if isinstance(body, dict) else None
                if p and 0.0 < p < 1.0:
                    return {"price": int(round(om.prob_to_american(p))), "p": round(p, 5)}
                why = f"{r.status_code} without a price"
            elif r.status_code == 400 or (r.status_code == 404 and not msg.startswith("Cannot ")):
                return None                                  # won't combine / no price right now
            elif r.status_code == 429:
                why = "429"
                time.sleep(min(float(_num(getattr(r, "headers", {}).get("Retry-After")) or 1.0), 5.0))
                continue
            else:
                why = f"{r.status_code} {msg}".strip()
        if i + 1 < TRIES:
            time.sleep(1.0)
    raise PricerError(why)


def price_all(sets: list[list[str]], post=None, now: float | None = None) -> dict[str, dict | None]:
    """Prices for many outcome sets (key: the ids joined in order), from the cache when fresh, else asked 3 at a time.
    A failed ask isn't cached; when every ask failed, PricerError."""
    now = now if now is not None else time.time()
    cache = _load_cache()
    out, todo = {}, []
    for ids in sets:
        key = ",".join(ids)
        hit = cache.get(key)
        if hit and now - hit["at"] < (TTL if hit.get("res") else TTL_REFUSED):
            out[key] = hit["res"]
        elif key not in todo:
            todo.append(key)
    errors = []

    def ask(key):
        try:
            return price(key.split(","), post), None
        except PricerError as e:
            return None, e

    if todo:
        with ThreadPoolExecutor(WORKERS) as ex:
            for key, (res, err) in zip(todo, ex.map(ask, todo)):
                out[key] = res
                if err is None:
                    cache[key] = {"at": now, "res": res}
                else:
                    errors.append(err)
        cache = {k: v for k, v in cache.items() if now - v["at"] < TTL}
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass
        if errors and len(errors) == len(todo):
            raise PricerError(f"all {len(todo)} asks failed: {errors[0]}")
    return out


# ------------------------------------------------------------------ the fun documents
def _leg(idx: Index, leg, event_id) -> bool:
    """Novig's outcome id (nv_id) and single price (nv_price, when its book has a bid) on one leg."""
    if not isinstance(leg, dict):
        return False
    for k in ("nv_id", "nv_price"):
        leg.pop(k, None)
    hit = idx.event(event_id)
    if hit is None:
        return False
    game, n = hit
    o = leg_outcome(leg, game, idx.markets(n["eventId"]))
    if o is None:
        return False
    leg["nv_id"] = o["outcomeId"]
    a = _ask(o)
    if a is not None:
        leg["nv_price"] = int(round(om.prob_to_american(a)))
    return True


def _started(idx: Index, event_ids) -> bool:
    now = pd.Timestamp.now(tz="UTC")
    return any(pd.Timestamp(idx.games[str(e)]["start"]) <= now for e in event_ids if str(e) in idx.games)


def watched_events() -> set[str] | None:
    """Every account's watched games as Odds API event ids (user_settings.watching, 0045), or None without the app's
    database (a local run prices every slip, as before Nov 7)."""
    url = config.secret("SUPABASE_DB_URL")
    if not url:
        return None
    try:
        import psycopg

        from betlab import alerts
        with psycopg.connect(url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
            return {e for ids in alerts.watched_events(c).values() for e in ids}
    except Exception as e:  # noqa: BLE001 - a failed read prices them all
        print(f"novig parlays: watched games unavailable ({type(e).__name__})")
        return None


def attach(doc: dict, idx: Index, post=None, watched: set[str] | None = None) -> tuple[int, int]:
    """Novig's side of the fun document: each leg's outcome id, and each slip's and ticket's `nv`: how many legs Novig
    lists, and when it lists them all, its exact price and one-tap link. Returns (slips priced, slips asked): the publish
    log's "N of M priced", which the watchdog reads (a day of 0 of many is a fault, Oct 29-30). `watched`: the event
    ids anyone watches (Nov 7): a slate's own slips get Novig's price only for those games, since every game's ride on its
    slate and only a watched game's show; None prices them all (no app database here)."""
    from betlab import links
    from betlab.sgp_plus import TICKETS

    slips: list[tuple[dict, list[dict], list]] = []        # (slip, its legs in order, their games' event ids)

    def legs_of(items, event_id):
        for leg in items or []:
            _leg(idx, leg, event_id)

    for g in doc.get("games") or []:
        for s in g.get("sgps") or []:
            legs_of(s.get("legs"), g.get("event_id"))
            slips.append((s, s.get("legs") or [], [g.get("event_id")]))
        legs_of((g.get("pack") or {}).get("legs"), g.get("event_id"))
    for sl in doc.get("slates") or []:
        for s in sl.get("sgps") or []:
            if watched is not None and str(s.get("event_id")) not in watched:
                continue          # pricing every game's slips doubled the publish (Nov 7: 119 slips, 204 s)
            legs_of(s.get("legs"), s.get("event_id"))
            slips.append((s, s.get("legs") or [], [s.get("event_id")]))
        for t in (sl.get(k) for k in TICKETS):
            if not t:
                continue
            for g in t.get("games") or []:
                legs_of(g.get("legs"), g.get("event_id"))
            flat = [l for g in t.get("games") or [] for l in g.get("legs") or []]
            for f, l in zip(t.get("legs") or [], flat):          # the flat copy, in order
                if isinstance(f, dict) and isinstance(l, dict) and f.get("label") == l.get("label"):
                    for k in ("nv_id", "nv_price"):
                        f.pop(k, None)
                        if k in l:
                            f[k] = l[k]
            if t.get("kind") != "td":
                slips.append((t, flat or t.get("legs") or [], [g.get("event_id") for g in t.get("games") or []]))
        for o in sl.get("overs") or []:
            _leg(idx, o, o.get("event_id"))
        for pk in sl.get("packs") or []:
            legs_of(pk.get("legs"), pk.get("event_id"))

    want = []
    for t, legs, eids in slips:
        legs = [l for l in legs if isinstance(l, dict)]
        ids = [l["nv_id"] for l in legs if l.get("nv_id")]
        t["nv"] = {"legs": len(ids), "of": len(legs)}
        if legs and len(ids) == len(legs) and len(set(ids)) == len(ids) and len(ids) >= 2 and not _started(idx, eids):
            want.append((t, ids))
    prices = price_all([ids for _, ids in want], post) if want else {}
    priced = 0
    for t, ids in want:
        res = prices.get(",".join(ids))
        if res:
            t["nv"] |= res | {"link": links.book_link(LINK.format(ids=",".join(ids))),
                              "priced_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            priced += 1
        else:
            t["nv"]["refused"] = True
    return priced, len(want)


# ------------------------------------------------------------------ Novig in the game pages' price tables (Oct 28)
# Mike: "Novig on the Games tab price tables". At publish, each row of the NHL lines and props, NBA player lines and
# soccer 3-way tables gets Novig's live price where $50+ stands behind it (`_ask`), with its EV against the row's own
# sharp no-vig chance: game lines `nv_price` / `nv_ev`, props `nv_over` / `nv_under` (and their EVs).
def _event_markets(idx: Index, home: str, away: str, start: str) -> list[dict] | None:
    n = novig.match({"home_team": home, "away_team": away, "commence_time": start}, idx.listed())
    return idx.markets(n["eventId"]) if n else None


def _price(o: dict | None) -> float | None:
    a = _ask(o) if o else None
    return float(round(om.prob_to_american(a))) if a is not None else None


def _ev(p, price) -> float | None:
    return round(float(p) * om.american_to_decimal(price) - 1, 4) if p is not None and price is not None else None


def _line_leg(label: str) -> dict | None:
    """'WSH ML', 'WSH -1.5', 'Over 6.5' as a leg."""
    if m := re.match(r"^(Over|Under) (\d+(?:\.\d+)?)", label):
        return {"label": label, "stat": "total", "side": m.group(1).lower(), "point": float(m.group(2)), "player": "game side"}
    if m := re.match(r"^(.+) ML$", label):
        return {"label": label, "stat": "moneyline", "side": "yes", "team": m.group(1), "point": 0.0, "player": "game side"}
    if m := re.match(r"^(.+) ([-+]\d+(?:\.\d+)?)$", label):
        return {"label": label, "stat": "spread", "side": "yes", "team": m.group(1), "point": float(m.group(2)), "player": "game side"}
    return None


def _props(rows: list[dict], game: dict, mkts: list[dict]) -> None:
    for r in rows:
        base = {"player": r.get("player"), "stat": r.get("stat"), "point": r.get("line"), "label": r.get("player")}
        over = _price(leg_outcome(base | {"side": "over"}, game, mkts))
        under = _price(leg_outcome(base | {"side": "under"}, game, mkts))
        p = r.get("p_market")
        r.update(nv_over=over, nv_under=under, nv_ev_over=_ev(p, over),
                 nv_ev_under=_ev(None if p is None else 1 - float(p), under))


def attach_tables(products: dict, idx: Index) -> int:
    """Novig's price on every row of the game pages' book tables. Returns rows priced."""
    from betlab import bans

    n = 0
    names = {a.upper(): t["name"] for t in bans.teams().get("nhl", []) for a in t["abbr"]}
    for g in (products.get("nhl") or {}).get("games") or []:
        home, away = names.get(str(g.get("home")).upper()), names.get(str(g.get("away")).upper())
        mkts = _event_markets(idx, home, away, g.get("start")) if home and away and g.get("start") else None
        if not mkts:
            continue
        game = {"home": home, "away": away, "start": g["start"], "sport": "nhl"}
        for o in g.get("fanduel") or []:
            leg = _line_leg(str(o.get("label", "")))
            price = _price(leg_outcome(leg, game, mkts)) if leg else None
            o.update(nv_price=price, nv_ev=_ev(o.get("p_market"), price))
            n += price is not None
        _props(g.get("props") or [], game, mkts)
    for g in (products.get("nba") or {}).get("games") or []:
        if not g.get("lines"):
            continue
        mkts = _event_markets(idx, g.get("home"), g.get("away"), g.get("tipoff"))
        if mkts:
            _props(g["lines"], {"home": g["home"], "away": g["away"], "start": g["tipoff"], "sport": "nba"}, mkts)
            n += sum(1 for r in g["lines"] if r.get("nv_over") is not None or r.get("nv_under") is not None)
    for g in (products.get("soccer") or {}).get("games") or []:
        mkts = _event_markets(idx, g.get("home"), g.get("away"), g.get("commence_time"))
        if not mkts:
            continue
        game = {"home": g["home"], "away": g["away"], "start": g["commence_time"], "sport": "soccer"}
        for o in g.get("lines") or []:
            side = o.get("side")
            leg = {"label": "Draw", "stat": "draw", "side": "yes", "player": "game side"} if side == "Draw" else \
                {"label": f"{side} to win", "stat": "moneyline", "side": "yes", "team": side, "player": "game side"}
            price = _price(leg_outcome(leg, game, mkts))
            o.update(nv_price=price, nv_ev=_ev(o.get("p_market"), price))
            n += price is not None
    return n
