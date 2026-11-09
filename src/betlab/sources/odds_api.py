"""The Odds API client, with a credit guard so the monthly quota never runs dry.

Cost rules (https://the-odds-api.com/liveapi/guides/v4/):
- /sports and /events are free.
- /odds and /events/{id}/odds cost markets x regions; every 10 named
  bookmakers count as one region.
- Historical endpoints cost 10x.
Every response reports the balance in x-requests-remaining / x-requests-used.
"""

from __future__ import annotations

import csv
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from betlab import config

USAGE_LOG = config.DATA_DIR / "odds_api_usage.csv"
USAGE_FIELDS = ["ts", "endpoint", "sport", "markets", "cost", "remaining", "used"]
SNAPSHOT_COLUMNS = [
    "snapshot_ts", "sport_key", "event_id", "commence_time", "home_team", "away_team",
    "bookmaker", "market", "last_update", "outcome", "player", "point", "price", "link", "bet_limit",
]
# Every odds request asks for the books' betslip links (free): FanDuel's "addToBetslip?marketId=..&
# selectionId=.." per outcome, which the page turns into "Open in FanDuel" buttons (links.py).
# Exchanges (Novig, Oct 22) also send each price's bet limit: the dollars available at that price (free too).
LINK_PARAMS = {"includeLinks": "true", "includeSids": "true", "includeBetLimits": "true"}
GAME_MARKETS = ("h2h", "spreads", "totals")
# NFL player props: main over/under lines, the one-sided alt ladders ("60+ yards")
# and anytime TD. Each market that comes back costs one credit per event.
NFL_PROP_MARKETS = ("player_receptions", "player_reception_yds", "player_rush_yds", "player_pass_yds")
NFL_ALT_MARKETS = tuple(f"{m}_alternate" for m in NFL_PROP_MARKETS)
NFL_TD_MARKETS = ("player_anytime_td",)
# NBA props: points, rebounds, assists, threes and the combos (about 8 credits a game)
NBA_PROP_MARKETS = ("player_points", "player_rebounds", "player_assists", "player_threes",
                    "player_points_rebounds_assists", "player_points_rebounds", "player_points_assists",
                    "player_rebounds_assists")
# NBA alt ladders ("25+ points"), for the fun tickets' 55-80% legs (Mike, 2026-09-28): about 4 more
# credits a game
# Soccer player props (Mike, 2026-10-10: every market): FanDuel posts shots and shots on target as
# over-only ladders, anytime scorer and assists; cards come from DraftKings. About 5 credits a match.
# `player_to_score_or_assist` isn't in The Odds API's market list, but the key works (found Oct 10 from
# Mike's FanDuel screenshot): FanDuel and Fanatics, Yes only, with betslip links.
SOCCER_PROP_MARKETS = ("player_shots", "player_shots_on_target", "player_goal_scorer_anytime", "player_assists",
                       "player_to_receive_card", "player_to_score_or_assist")
NBA_ALT_MARKETS = ("player_points_alternate", "player_rebounds_alternate", "player_assists_alternate",
                   "player_threes_alternate")


def estimate_cost(n_markets: int, n_bookmakers: int, historical: bool = False) -> int:
    regions = max(1, math.ceil(n_bookmakers / 10))
    return (10 if historical else 1) * n_markets * regions


class CreditBudgetExceeded(RuntimeError):
    pass


class OddsApiError(RuntimeError):
    pass


class CreditGuard:
    """Refuses calls that would push one key's balance below its reserve.

    The balance is taken from the API's own headers and persisted to a CSV that
    is committed with the data, so every scheduled run starts from the true
    balance. Only priority="closing" calls (closing lines for picks already
    made) may spend the reserve. The quota resets monthly on reset_day (the 1st
    for the free plan, the subscription day for a paid plan).
    """

    def __init__(self, log_path: Path = USAGE_LOG, monthly_credits: int = 500, reserve: int = 50,
                 reset_day: int = 1):
        self.log_path = log_path
        self.monthly_credits = monthly_credits
        self.reserve = reserve
        self.reset_day = reset_day
        self.remaining = self._last_remaining()

    def period_start(self, now: datetime | None = None) -> datetime:
        """When the current quota period began (UTC)."""
        now = now or datetime.now(timezone.utc)
        year, month = now.year, now.month
        if now.day < self.reset_day:
            year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        return datetime(year, month, min(self.reset_day, 28), tzinfo=timezone.utc)

    def next_reset(self, now: datetime | None = None) -> datetime:
        start = self.period_start(now)
        year, month = (start.year, start.month + 1) if start.month < 12 else (start.year + 1, 1)
        return start.replace(year=year, month=month)

    def _last_remaining(self) -> int | None:
        if not self.log_path.exists():
            return None
        with self.log_path.open(newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["remaining"]]
        if not rows:
            return None
        last = rows[-1]
        if datetime.fromisoformat(last["ts"]) < self.period_start():
            return None  # the quota has reset since; re-read it from the next response
        return int(float(last["remaining"]))

    def balance(self) -> int:
        return self.remaining if self.remaining is not None else self.monthly_credits

    def check(self, cost: int, priority: str = "normal") -> None:
        floor = 0 if priority == "closing" else self.reserve
        if self.balance() - cost < floor:
            raise CreditBudgetExceeded(
                f"call needs {cost} credits; balance {self.balance()}, floor {floor} ({priority})"
            )

    def record(self, endpoint: str, sport: str, markets: str, cost: int, headers) -> None:
        remaining = headers.get("x-requests-remaining")
        used = headers.get("x-requests-used")
        cost = int(float(headers.get("x-requests-last", cost)))
        before = self.remaining
        self.remaining = int(float(remaining)) if remaining is not None else self.balance() - cost
        if cost == 0 and before is not None and self.remaining == before:
            # A free call that changed nothing: logging it made the worker's 15-minute pregame
            # tick commit ~11 rows every time (Oct 7: 70 commits a day for no news).
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.log_path.exists()
        with self.log_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=USAGE_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "endpoint": endpoint, "sport": sport, "markets": markets, "cost": cost,
                "remaining": self.remaining, "used": used if used is not None else "",
            })


# Seconds to wait before asking again when every key is rate limited (Nov 2: a 429 on the only key with credits
# stopped the 8 PM tick's pull). The limit is per second, so a short wait clears it.
RATE_LIMIT_WAITS = (2, 5)


def _session() -> requests.Session:
    """The API sometimes answers 502 for a moment (Oct 8: twice on a free /events call, which
    stopped that pregame tick for every league). Retry server errors with backoff (1+2+4 s);
    raise_on_status=False hands the last response back, so the error stays sanitized."""
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=(500, 502, 503, 504),
                  allowed_methods=("GET",), raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def usage_log(label: str) -> Path:
    """The free key keeps the original log; any other key gets its own file."""
    return USAGE_LOG if label == "free" else config.DATA_DIR / f"odds_api_usage_{label}.csv"


def configured_keys() -> list[tuple[str, str, CreditGuard]]:
    """[(label, key, guard)] for every key in settings odds_api.keys that is set, in order.
    Only labels are ever printed or logged; the keys stay inside the client."""
    out = []
    for k in config.settings()["odds_api"]["keys"]:
        value = config.secret(k["secret"])
        if value:
            guard = CreditGuard(usage_log(k["label"]), monthly_credits=k["monthly_credits"],
                                reserve=k["reserve"], reset_day=k["reset_day"])
            out.append((k["label"], value, guard))
    return out


def any_key() -> bool:
    return any(config.secret(k["secret"]) for k in config.settings()["odds_api"]["keys"])


class OddsApiClient:
    """Client for the few endpoints we use. Every paid call goes through a CreditGuard.

    With several keys (settings odds_api.keys: the free key first, then the paid
    one), each paid call uses the first key whose guard allows it, and moves to the
    next key if the API answers 401 (out of credits, or a bad key). Historical
    calls skip the free key: the free plan can't use them.
    """

    def __init__(self, api_key: str | None = None, guard: CreditGuard | None = None, session=None):
        s = config.settings()["odds_api"]
        if api_key:
            self.keys = [("key", api_key, guard or CreditGuard())]
        else:
            self.keys = configured_keys()
        if not self.keys:
            raise OddsApiError("no Odds API key is set (see .env.example)")
        self.base_url = s["base_url"]
        self.bookmakers = list(s["bookmakers"])
        self.session = session or _session()

    @property
    def guard(self) -> CreditGuard:
        """The first key's guard (single-key callers and tests)."""
        return self.keys[0][2]

    def balances(self) -> dict[str, int]:
        return {label: g.balance() for label, _, g in self.keys}

    def balance_note(self) -> str:
        """'free 476, paid 20000' for logs and the page."""
        return ", ".join(f"{label} {n}" for label, n in self.balances().items())

    def _get(self, path: str, params: dict, cost: int = 0, sport: str = "", markets: str = "",
             priority: str = "normal", paid_only: bool = False):
        """GET with a key added; checks the budget first and records the balance after."""
        errors = []
        for wait in (*RATE_LIMIT_WAITS, None):
            errors = []
            for label, key, guard in self.keys:
                if paid_only and label == "free":
                    continue
                if cost:
                    try:
                        guard.check(cost, priority)
                    except CreditBudgetExceeded as exc:
                        errors.append(f"{label}: {exc}")
                        continue
                resp = self._send(path, key, params)
                if resp.status_code in (401, 429):
                    # Out of credits (or a bad key), or this key's rate limit (Oct 10: the free key's burst of
                    # /events calls on a busy Saturday skipped the NHL tick): try the next key. Never surface
                    # the URL: it holds the key.
                    errors.append(f"{label}: HTTP {resp.status_code} {resp.text[:120]}")
                    continue
                if resp.status_code != 200:
                    raise OddsApiError(f"{path} failed ({label} key): HTTP {resp.status_code} {resp.text[:200]}")
                guard.record(path, sport, markets, cost, resp.headers)
                return resp.json()
            if wait is None or not any("HTTP 429" in e for e in errors):
                break
            time.sleep(wait)                                    # every key refused and one was only rate limited
        if errors and all("HTTP 401" not in e and "HTTP 429" not in e for e in errors):
            raise CreditBudgetExceeded(f"{path}: no key has the credits ({'; '.join(errors)})")
        raise OddsApiError(f"{path} failed on every key: {'; '.join(errors) or 'no usable key'}")

    def _send(self, path: str, key: str, params: dict):
        """One GET. Network errors name the URL, which holds the key: re-raise without it."""
        try:
            return self.session.get(f"{self.base_url}{path}", params={"apiKey": key, **params}, timeout=30)
        except requests.RequestException as exc:
            raise OddsApiError(f"{path} failed: {type(exc).__name__}") from None

    def sync_balance(self) -> dict[str, int]:
        """Refresh every key's credit balance with a free call each."""
        for label, key, guard in self.keys:
            resp = self._send("/sports", key, {})
            if resp.status_code == 200:
                guard.record("/sports", "", "", 0, resp.headers)
        return self.balances()

    def events(self, sport_key: str) -> list[dict]:
        """Upcoming events for a sport (free): ids, teams, kickoff times."""
        return self._get(f"/sports/{sport_key}/events", {"dateFormat": "iso"}, sport=sport_key)

    def odds(self, sport_key: str, markets=GAME_MARKETS, priority: str = "normal",
             event_ids: list[str] | None = None) -> list[dict]:
        """Game-line odds for every upcoming event of a sport, or only `event_ids` (same cost:
        markets x regions)."""
        cost = estimate_cost(len(markets), len(self.bookmakers))
        only = {"eventIds": ",".join(event_ids)} if event_ids else {}
        return self._get(
            f"/sports/{sport_key}/odds",
            {"bookmakers": ",".join(self.bookmakers), "markets": ",".join(markets),
             "oddsFormat": "american", "dateFormat": "iso", **LINK_PARAMS, **only},
            cost=cost, sport=sport_key, markets=",".join(markets), priority=priority,
        )

    def event_odds(self, sport_key: str, event_id: str, markets, priority: str = "normal") -> dict:
        """Odds for one event, including player-prop markets (cost: markets returned x regions)."""
        cost = estimate_cost(len(markets), len(self.bookmakers))
        return self._get(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {"bookmakers": ",".join(self.bookmakers), "markets": ",".join(markets),
             "oddsFormat": "american", "dateFormat": "iso", **LINK_PARAMS},
            cost=cost, sport=sport_key, markets=",".join(markets), priority=priority,
        )

    def historical_events(self, sport_key: str, date: str) -> dict:
        """Events as they stood at an ISO date (paid plans only; 1 credit)."""
        return self._get(f"/historical/sports/{sport_key}/events", {"date": date, "dateFormat": "iso"},
                         cost=1, sport=sport_key, markets="events", paid_only=True)

    def historical_odds(self, sport_key: str, markets, date: str) -> dict:
        """Every event's game lines as they stood at an ISO date: one call for the whole slate
        (paid plans only; 10x the cost). Returns {"timestamp", "data": [events], ...}."""
        cost = estimate_cost(len(markets), len(self.bookmakers), historical=True)
        return self._get(
            f"/historical/sports/{sport_key}/odds",
            {"bookmakers": ",".join(self.bookmakers), "markets": ",".join(markets), "date": date,
             "oddsFormat": "american", "dateFormat": "iso"},
            cost=cost, sport=sport_key, markets=",".join(markets), paid_only=True,
        )

    def historical_event_odds(self, sport_key: str, event_id: str, markets, date: str) -> dict:
        """One event's odds as they stood at an ISO date (paid plans only; 10x the cost)."""
        cost = estimate_cost(len(markets), len(self.bookmakers), historical=True)
        return self._get(
            f"/historical/sports/{sport_key}/events/{event_id}/odds",
            {"bookmakers": ",".join(self.bookmakers), "markets": ",".join(markets), "date": date,
             "oddsFormat": "american", "dateFormat": "iso"},
            cost=cost, sport=sport_key, markets=",".join(markets), paid_only=True,
        )


def flatten(payload, sport_key: str, snapshot_ts: str) -> pd.DataFrame:
    """One row per (event, bookmaker, market, outcome). Props put the player in `player`."""
    events = payload if isinstance(payload, list) else [payload]
    rows = []
    for ev in events:
        for book in ev.get("bookmakers", []):
            for market in book.get("markets", []):
                for oc in market.get("outcomes", []):
                    rows.append({
                        "snapshot_ts": snapshot_ts, "sport_key": sport_key, "event_id": ev["id"],
                        "commence_time": ev["commence_time"], "home_team": ev["home_team"],
                        "away_team": ev["away_team"], "bookmaker": book["key"], "market": market["key"],
                        "last_update": market.get("last_update", book.get("last_update")),
                        "outcome": oc["name"], "player": oc.get("description"),
                        "point": oc.get("point"), "price": oc["price"], "link": oc.get("link"),
                        "bet_limit": oc.get("bet_limit"),
                    })
    return pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)


def save_snapshot(df: pd.DataFrame, sport_key: str, snapshot_ts: str, kind: str) -> Path:
    """Write one pull to data/odds/<sport>/<ET date>/<ET HHMMSS>_<kind>.parquet (committed to git).

    Folders use the Eastern date because `pull --auto` asks "did we pull today?" by
    Eastern date: a 9 PM ET pull must not count as tomorrow's. The exact UTC time is
    in the `snapshot_ts` column.
    """
    ts = datetime.fromisoformat(snapshot_ts).astimezone(ZoneInfo(config.settings()["timezone"]))
    sport_dir = config.DATA_DIR / "odds" / sport_key
    path = sport_dir / ts.strftime("%Y-%m-%d") / f"{ts.strftime('%H%M%S')}_{kind}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    readme = sport_dir / "README.md"  # every folder in the repo documents itself
    if not readme.exists():
        readme.write_text(f"# data/odds/{sport_key}/\n\nOdds snapshots for `{sport_key}`, one folder per "
                          "Eastern date. File naming and columns: `../README.md`.\n", encoding="utf-8")
    df.to_parquet(path, index=False)
    return path
