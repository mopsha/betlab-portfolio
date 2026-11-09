"""Novig's prices from its public catalog (no key, no credits; Oct 22), for markets the Odds API doesn't carry.

The Odds API sends Novig's NFL, NBA, NHL and college lines with their bet limits, but none of its soccer, so the card
couldn't price soccer at Novig (Oct 22: the 3 PM Europa League edges were read off its website by hand). Novig's public
catalog (`/v3/public/catalog/events` and `/markets`, unsigned, throttled per IP; docs.novig.com) has every soccer
league we price. `add_rows` puts its prices into a pull's snapshot in the Odds API's flat format, bookmaker "novig",
so the evaluators price Novig like any book and `books.select` applies the same bet-limit rule.

- **Prices:** a market lists each outcome's best bid. The price to buy one side (the ask) is 1 - the best bid on its
  other side; the dollars at that price are the other side's size (qty is in hundredths of a contract) times the ask.
  The 3-way result comes as three yes/no markets (home win, draw, away win); totals as Over/Under at each line.
- **Matching:** a Novig event joins a pulled event when both start within 10 minutes and both team names match
  (Novig says "Nottm Forest" where the feed says "Nottingham Forest": compared by tokens, `_same_team`).
- **Links:** `https://novig.com/events/<outcome>/oddsapi/{wager}`, the shape of the Odds API's Novig links:
  `links.book_link` fills in the stake and it opens Novig's order slip.
- **Fees:** pregame fills pay none (`fee.charged` WHEN_LIVE); only rows for events not yet started are written.
- Read-only: BetLab never places orders (CLAUDE.md, hard rule 5).
"""

from __future__ import annotations

import difflib
import re
import time
import unicodedata
from datetime import datetime, timezone

import pandas as pd
import requests

from betlab import odds_math as om
from betlab.sources.odds_api import SNAPSHOT_COLUMNS

BASE = "https://api.novig.com/v3/public/catalog"
BOOK = "novig"
LINK = "https://novig.com/events/{outcome}/oddsapi/{{wager}}"
MATCH_MINUTES = 10
_EVENTS: dict[str, tuple[float, list[dict]]] = {}        # sport -> (fetched at, events): one catalog read per run


_LAST = [0.0]


def _get(path: str, params: dict, tries: int = 6) -> dict:
    """One catalog read. Novig takes about 10 in a burst, then answers 429 with Retry-After 1 (Oct 28: 29 of 40 market
    reads in 2.4 s were refused, and the parlay side saw those games as having no markets): reads are spaced 0.15 s
    apart and a 429 waits as told, then tries again."""
    for i in range(tries):
        wait = _LAST[0] + 0.15 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.monotonic()
        r = requests.get(f"{BASE}/{path}", params=params, headers={"User-Agent": "BetLab"}, timeout=30)
        if r.status_code == 429 and i + 1 < tries:
            time.sleep(min(float(r.headers.get("retry-after") or 1), 5.0))
            continue
        r.raise_for_status()
        return r.json()
    raise requests.HTTPError("Novig catalog: still throttled")


def open_events() -> list[dict]:
    """Every open pregame event on Novig, all sports (every page), cached for 10 minutes."""
    hit = _EVENTS.get("*")
    now = datetime.now(timezone.utc).timestamp()
    if hit and now - hit[0] < 600:
        return hit[1]
    out, after = [], None
    while True:
        page = _get("events", {"status": "OPEN_PREGAME", "limit": 5000, **({"after": after} if after else {})})
        out += page.get("items", [])
        after = page.get("next")
        if not after:
            break
    _EVENTS["*"] = (now, out)
    return out


def events(sport: str = "SOCCER") -> list[dict]:
    """Novig's open pregame events of a sport."""
    return [e for e in open_events() if e.get("sport") == sport]


def markets(event_id: str) -> list[dict]:
    out, after = [], None
    while True:
        page = _get("markets", {"event": event_id, "limit": 1000, **({"after": after} if after else {})})
        out += page.get("items", [])
        after = page.get("next")
        if not after:
            return out


_DROP = {"fc", "cf", "afc", "sc", "ac", "as", "ss", "us", "cd", "rc", "fk", "sk", "nk", "bk", "if", "club", "de", "the"}
_ALIAS = {"nottm": "nottingham", "utd": "united", "man": "manchester", "spurs": "tottenham", "wolves": "wolverhampton"}


def _tokens(name: str) -> set[str]:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    toks = [_ALIAS.get(t, t) for t in re.findall(r"[a-z0-9]+", s)]
    return {t for t in toks if t not in _DROP and len(t) > 1}


def _same_team(a: str, b: str) -> bool:
    """'Nottm Forest' = 'Nottingham Forest FC'; 'Ipswich Town' = 'Ipswich Town FC'; never 'Inter' = 'Inter Miami'
    unless every word of the shorter name is in the longer one."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if small <= big:
        return True
    return difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio() >= 0.85


def _teams(description: str) -> tuple[str, str] | None:
    """('away', 'home') from Novig's 'Away @ Home'."""
    if " @ " not in description:
        return None
    a, h = description.split(" @ ", 1)
    return a.strip(), h.strip()


def match(event: dict, novig_events: list[dict]) -> dict | None:
    """The Novig event for one pulled event (Odds API shape: home_team, away_team, commence_time), or None."""
    start = pd.Timestamp(event["commence_time"]).timestamp() * 1000
    hits = []
    for n in novig_events:
        if abs(float(n.get("startsTs", 0)) - start) > MATCH_MINUTES * 60_000:
            continue
        t = _teams(n.get("description", ""))
        if t and _same_team(t[0], event["away_team"]) and _same_team(t[1], event["home_team"]):
            hits.append(n)
    return hits[0] if len(hits) == 1 else None


def _ask(markets_outcomes: list[dict], side: int) -> tuple[float, float, str] | None:
    """(ask probability, dollars available, outcome id) for buying outcome `side` of a two-outcome market."""
    if len(markets_outcomes) != 2:
        return None
    other = markets_outcomes[1 - side].get("bid")
    if not other or other.get("price") is None:
        return None
    ask = 1.0 - float(other["price"])
    if not 0.01 <= ask <= 0.99:
        return None
    return ask, round(float(other.get("qty") or 0) / 100.0 * ask, 2), markets_outcomes[side]["outcomeId"]


def rows_for(event: dict, mkts: list[dict], sport_key: str, ts: str) -> list[dict]:
    """Snapshot rows (Odds API flat format) for one pulled event from its Novig markets: the 3-way result (h2h) and
    goal totals."""
    home, away = event["home_team"], event["away_team"]
    base = {"snapshot_ts": ts, "sport_key": sport_key, "event_id": event["id"], "commence_time": event["commence_time"],
            "home_team": home, "away_team": away, "bookmaker": BOOK, "last_update": ts, "player": None}
    out = []

    def add(market, outcome, point, got):
        ask, dollars, oid = got
        out.append(base | {"market": market, "outcome": outcome, "point": point,
                           "price": float(round(om.prob_to_american(ask))), "link": LINK.format(outcome=oid),
                           "bet_limit": dollars})

    for m in mkts:
        if m.get("status") != "OPEN":
            continue
        kind, oc = m.get("marketType"), m.get("outcomes") or []
        yes = next((i for i, o in enumerate(oc) if str(o.get("name")).lower() == "yes"), None)
        if kind == "MONEYLINE_3_WAY_DRAW" and yes is not None and (got := _ask(oc, yes)):
            add("h2h", "Draw", None, got)
        elif kind == "MONEYLINE_3_WAY_WIN" and yes is not None and (got := _ask(oc, yes)):
            team = re.sub(r"\s*MONEYLINE_3_WAY_WIN\s*$", "", str(m.get("description", ""))).strip()
            side = home if _same_team(team, home) else away if _same_team(team, away) else None
            if side and not (_same_team(team, home) and _same_team(team, away)):
                add("h2h", side, None, got)
        elif kind == "TOTAL" and m.get("strike") is not None:
            for i, o in enumerate(oc):
                name = str(o.get("name", ""))
                if name.startswith(("Over", "Under")) and (got := _ask(oc, i)):
                    add("totals", name.split()[0], float(m["strike"]), got)
    # a 3-way result needs all three outcomes, or the evaluators can't devig or price it
    if sum(1 for r in out if r["market"] == "h2h") != 3:
        out = [r for r in out if r["market"] != "h2h"]
    return out


def add_rows(df: pd.DataFrame, sport_key: str, ts: str, sport: str = "SOCCER") -> pd.DataFrame:
    """A pull's snapshot with Novig's rows added for each of its events Novig lists (none when the pull already has
    Novig's prices, as the Odds API sends for the US sports). A failed catalog read leaves the pull as it was."""
    if df is None or df.empty or (df["bookmaker"] == BOOK).any():
        return df
    try:
        listed = events(sport)
    except requests.RequestException:
        return df
    rows = []
    now = pd.Timestamp.now(tz="UTC")
    for _, ev in df.drop_duplicates("event_id").iterrows():
        e = {"id": ev["event_id"], "home_team": ev["home_team"], "away_team": ev["away_team"],
             "commence_time": ev["commence_time"]}
        if pd.Timestamp(e["commence_time"]) <= now:
            continue
        n = match(e, listed)
        if n is None:
            continue
        try:
            rows += rows_for(e, markets(n["eventId"]), sport_key, ts)
        except requests.RequestException:
            continue
    if not rows:
        return df
    return pd.concat([df, pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)], ignore_index=True)
