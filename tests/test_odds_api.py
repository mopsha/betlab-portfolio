import csv

import pytest

from betlab.sources import odds_api as oa


def test_estimate_cost():
    assert oa.estimate_cost(3, 10) == 3          # 10 named books = 1 region
    assert oa.estimate_cost(3, 11) == 6
    assert oa.estimate_cost(1, 2, historical=True) == 10


def test_guard_protects_reserve(tmp_path):
    guard = oa.CreditGuard(tmp_path / "usage.csv", monthly_credits=500, reserve=50)
    guard.record("/sports/x/odds", "x", "h2h", 3, {"x-requests-remaining": "60", "x-requests-used": "440"})
    guard.check(3)                                # 57 left, above the reserve
    with pytest.raises(oa.CreditBudgetExceeded):
        guard.check(11)                           # would leave 49 < 50
    guard.check(11, priority="closing")           # closing lines may use the reserve
    with pytest.raises(oa.CreditBudgetExceeded):
        guard.check(61, priority="closing")       # but never go negative


def test_guard_balance_persists_across_runs(tmp_path):
    log = tmp_path / "usage.csv"
    oa.CreditGuard(log).record("/sports", "", "", 0, {"x-requests-remaining": "321"})
    assert oa.CreditGuard(log).balance() == 321


def test_free_calls_that_change_nothing_are_not_logged(tmp_path):
    log = tmp_path / "usage.csv"
    g = oa.CreditGuard(log)
    g.record("/sports", "", "", 0, {"x-requests-remaining": "321"})       # first balance: logged
    g.record("/sports/x/events", "x", "", 0, {"x-requests-remaining": "321"})
    g.record("/sports/x/odds", "x", "h2h", 2, {"x-requests-remaining": "319", "x-requests-last": "2"})
    g.record("/sports", "", "", 0, {"x-requests-remaining": "319"})
    assert len(log.read_text().splitlines()) == 3                         # header + 2 rows
    assert oa.CreditGuard(log).balance() == 319


def test_guard_assumes_reset_in_a_new_month(tmp_path):
    log = tmp_path / "usage.csv"
    with log.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=oa.USAGE_FIELDS)
        writer.writeheader()
        writer.writerow({"ts": "2020-01-31T23:00:00+00:00", "endpoint": "/x", "sport": "", "markets": "",
                         "cost": 3, "remaining": 2, "used": 498})
    assert oa.CreditGuard(log, monthly_credits=500).balance() == 500


SAMPLE = [{
    "id": "ev1", "sport_key": "americanfootball_nfl", "commence_time": "2026-09-27T17:00:00Z",
    "home_team": "Buffalo Bills", "away_team": "Miami Dolphins",
    "bookmakers": [{
        "key": "fanduel", "last_update": "2026-09-23T15:00:00Z",
        "markets": [
            {"key": "spreads", "last_update": "2026-09-23T15:00:00Z", "outcomes": [
                {"name": "Buffalo Bills", "price": -110, "point": -6.5},
                {"name": "Miami Dolphins", "price": -110, "point": 6.5}]},
            {"key": "player_receptions", "outcomes": [
                {"name": "Over", "description": "Tyreek Hill", "price": -120, "point": 5.5},
                {"name": "Under", "description": "Tyreek Hill", "price": -105, "point": 5.5}]},
        ],
    }],
}]


def test_flatten_game_and_prop_markets():
    df = oa.flatten(SAMPLE, "americanfootball_nfl", "2026-09-23T15:05:00+00:00")
    assert len(df) == 4
    spread = df[(df.market == "spreads") & (df.outcome == "Buffalo Bills")].iloc[0]
    assert spread.point == -6.5 and spread.price == -110
    prop = df[df.market == "player_receptions"].iloc[0]
    assert prop.player == "Tyreek Hill" and prop.point == 5.5
    assert prop.last_update == "2026-09-23T15:00:00Z"  # falls back to the bookmaker's timestamp
    assert "bet_limit" in df and df["bet_limit"].isna().all()   # sportsbooks send none; exchanges (Novig) do


def test_flatten_keeps_an_exchange_prices_bet_limit():
    ev = {"id": "e", "commence_time": "2026-10-22T23:00:00Z", "home_team": "New Jersey Devils", "away_team": "Anaheim Ducks",
          "bookmakers": [{"key": "novig", "markets": [{"key": "h2h", "outcomes": [
              {"name": "Anaheim Ducks", "price": 194, "bet_limit": 3500, "link": "https://novig.com/events/x/oddsapi/{wager}"}]}]}]}
    r = oa.flatten([ev], "icehockey_nhl", "2026-10-22T16:40:00+00:00").iloc[0]
    assert r.bookmaker == "novig" and r.bet_limit == 3500 and r.price == 194
    assert oa.LINK_PARAMS["includeBetLimits"] == "true"


def test_snapshots_are_filed_by_eastern_date(tmp_path, monkeypatch):
    # 01:30 UTC on the 25th is 9:30 PM ET on the 24th: it belongs to the 24th,
    # or the next morning's "already pulled today?" check would skip its pull.
    monkeypatch.setattr(oa.config, "DATA_DIR", tmp_path)
    df = oa.flatten(SAMPLE, "americanfootball_nfl", "2026-09-25T01:30:00+00:00")
    path = oa.save_snapshot(df, "americanfootball_nfl", "2026-09-25T01:30:00+00:00", "pick")
    assert path.parent.name == "2026-09-24" and path.name == "213000_pick.parquet"
    assert (tmp_path / "odds" / "americanfootball_nfl" / "README.md").exists()  # new sport folders document themselves


class _FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers, self.text = status, body, headers or {}, str(body)

    def json(self):
        return self._body


class _FakeSession:
    def __init__(self, response):
        self.response, self.calls = response, []

    def get(self, url, params, timeout):
        self.calls.append((url, params))
        return self.response


def test_client_records_cost_and_never_leaks_key(tmp_path):
    guard = oa.CreditGuard(tmp_path / "usage.csv")
    ok = _FakeSession(_FakeResponse(200, SAMPLE, {"x-requests-remaining": "497", "x-requests-last": "3"}))
    client = oa.OddsApiClient(api_key="SECRET123", guard=guard, session=ok)
    client.odds("americanfootball_nfl")
    assert guard.balance() == 497
    assert ok.calls[0][1]["markets"] == "h2h,spreads,totals"

    bad = _FakeSession(_FakeResponse(401, {"message": "invalid key"}))
    client = oa.OddsApiClient(api_key="SECRET123", guard=guard, session=bad)
    with pytest.raises(oa.OddsApiError) as err:
        client.events("americanfootball_nfl")
    assert "SECRET123" not in str(err.value)


class _KeyedSession:
    """Answers by key: {key: response}."""

    def __init__(self, by_key):
        self.by_key, self.calls = by_key, []

    def get(self, url, params, timeout):
        self.calls.append((url, params["apiKey"]))
        return self.by_key[params["apiKey"]]


def two_key_client(tmp_path, by_key, free_left=None):
    client = oa.OddsApiClient(api_key="FREE", guard=oa.CreditGuard(tmp_path / "free.csv", 500, reserve=0),
                              session=_KeyedSession(by_key))
    client.keys = [("free", "FREE", client.keys[0][2]),
                   ("paid", "PAID", oa.CreditGuard(tmp_path / "paid.csv", 20000, reserve=50, reset_day=24))]
    if free_left is not None:
        client.keys[0][2].remaining = free_left
    return client


def test_free_key_is_used_first(tmp_path):
    ok = _FakeResponse(200, SAMPLE, {"x-requests-remaining": "480", "x-requests-last": "3"})
    client = two_key_client(tmp_path, {"FREE": ok, "PAID": ok})
    client.odds("americanfootball_nfl")
    assert [k for _, k in client.session.calls] == ["FREE"]
    assert client.keys[0][2].balance() == 480


def test_switches_to_paid_when_free_runs_low_or_is_refused(tmp_path):
    ok = _FakeResponse(200, SAMPLE, {"x-requests-remaining": "19990", "x-requests-last": "3"})
    client = two_key_client(tmp_path, {"FREE": ok, "PAID": ok}, free_left=2)   # 3 credits won't fit
    client.odds("americanfootball_nfl")
    assert [k for _, k in client.session.calls] == ["PAID"]

    out = _FakeResponse(401, {"message": "Usage quota has been reached"})
    client = two_key_client(tmp_path, {"FREE": out, "PAID": ok})
    client.odds("americanfootball_nfl")
    assert [k for _, k in client.session.calls] == ["FREE", "PAID"]


def test_a_rate_limited_key_hands_off_to_the_next(tmp_path):
    """Oct 10: the free key answered 429 to a free /events call and the NHL pre-game tick was skipped."""
    ok = _FakeResponse(200, [], {"x-requests-remaining": "19000", "x-requests-last": "0"})
    slow = _FakeResponse(429, {"message": "Rate Exceeded."})
    client = two_key_client(tmp_path, {"FREE": slow, "PAID": ok})
    client.events("icehockey_nhl")
    assert [k for _, k in client.session.calls] == ["FREE", "PAID"]


def test_a_rate_limit_on_every_key_waits_and_asks_again(tmp_path, monkeypatch):
    """Nov 2: the free key had no credits, the paid key answered 429 once, and the 8 PM tick's pull stopped."""
    waits = []
    monkeypatch.setattr(oa.time, "sleep", waits.append)
    ok = _FakeResponse(200, [], {"x-requests-remaining": "19000", "x-requests-last": "0"})
    slow = _FakeResponse(429, {"message": "Rate Exceeded."})

    class ThenFine(_FakeSession):
        def get(self, url, params, timeout):
            self.calls.append((url, params))
            return slow if len(self.calls) <= 2 else ok

    client = oa.OddsApiClient(api_key="K", guard=oa.CreditGuard(tmp_path / "u.csv"), session=ThenFine(ok))
    client.events("basketball_nba")
    assert len(client.session.calls) == 3 and waits == list(oa.RATE_LIMIT_WAITS)


def test_a_rate_limit_that_lasts_still_fails_and_a_bad_key_never_waits(tmp_path, monkeypatch):
    waits = []
    monkeypatch.setattr(oa.time, "sleep", waits.append)
    guard = oa.CreditGuard(tmp_path / "u.csv")
    slow = oa.OddsApiClient(api_key="K", guard=guard, session=_FakeSession(_FakeResponse(429, {"m": "Rate"})))
    with pytest.raises(oa.OddsApiError):
        slow.events("basketball_nba")
    assert waits == list(oa.RATE_LIMIT_WAITS) and len(slow.session.calls) == 3
    waits.clear()
    bad = oa.OddsApiClient(api_key="K", guard=guard, session=_FakeSession(_FakeResponse(401, {"m": "no"})))
    with pytest.raises(oa.OddsApiError):
        bad.events("basketball_nba")
    assert waits == [] and len(bad.session.calls) == 1


def test_historical_calls_skip_the_free_key(tmp_path):
    ok = _FakeResponse(200, {"data": []}, {"x-requests-remaining": "19000", "x-requests-last": "40"})
    client = two_key_client(tmp_path, {"FREE": ok, "PAID": ok})
    client.historical_event_odds("americanfootball_nfl", "e1", ["player_receptions"], "2025-10-05T16:00:00Z")
    assert [k for _, k in client.session.calls] == ["PAID"]


def test_errors_never_show_either_key(tmp_path):
    out = _FakeResponse(401, {"message": "Usage quota has been reached"})
    client = two_key_client(tmp_path, {"FREE": out, "PAID": out})
    with pytest.raises(oa.OddsApiError) as err:
        client.odds("americanfootball_nfl")
    assert "FREE" not in str(err.value) and "PAID" not in str(err.value)


def test_quota_period_follows_the_reset_day():
    from datetime import datetime, timezone
    g = oa.CreditGuard(reset_day=24)
    assert g.period_start(datetime(2026, 10, 10, tzinfo=timezone.utc)).day == 24
    assert g.period_start(datetime(2026, 10, 10, tzinfo=timezone.utc)).month == 9
    assert g.next_reset(datetime(2026, 9, 24, 12, tzinfo=timezone.utc)).month == 10

