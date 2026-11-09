from datetime import date, timedelta

from betlab import watchdog as W

DAY = date(2026, 10, 30)


def publish(nv="3 of 5", clv="2 of 3", tables=140, offers=58):
    return ("pregame", "publish", 0, f"novig parlays (fun): {nv} priced\nnovig parlays (fun_nba): 0 of 0 priced\n"
                                     f"novig tables: {tables} rows priced\nlive CLV: {clv} open bet(s) priced\n"
                                     f"published: games 185, offers {offers}, fun_tickets 24")


def normal_day(**kw):
    return [publish(**kw) for _ in range(12)] + [("pregame", "card", 0, "card written: 0 picks (0 new in ledger), 58 leans"),
                                                 ("pregame", "lock-due", 0, "slices to lock: 2026-10-30-soccer-lunch")]


def week(**kw):
    return {DAY - timedelta(d): normal_day() for d in range(1, 8)} | {DAY: normal_day(**kw)}


def test_a_normal_day_says_nothing():
    assert W.check(week(), DAY) == []


def test_novig_pricing_none_of_many_slips_is_a_finding():
    """Oct 29-30: Novig's pricer moved and every publish priced 0 of the slips it lists every leg of."""
    lines = W.check(week(nv="0 of 4"), DAY)
    assert lines == ["Novig parlays priced none (0 of 48 over the day)"]


def test_honest_zeros_are_quiet():
    """No slip fully on Novig, no open bet, few publishes: nothing to price, nothing wrong."""
    assert W.check(week(nv="0 of 0", clv="0 of 0"), DAY) == []
    days = week()
    days[DAY] = [publish(nv="0 of 0", tables=0, offers=0)] * 3      # a quiet day: 3 publishes only
    assert W.check(days, DAY) == []


def test_a_count_that_goes_quiet_on_a_normal_day_is_a_finding():
    lines = W.check(week(tables=0), DAY)
    assert lines == ["Novig game-page prices gone (0 today, above 0 on 7 of the last 7 days; 12 publishes)"]
    days = week()
    days[DAY] = [d for d in days[DAY] if d[1] != "lock-due"]
    assert W.check(days, DAY)[0].startswith("no slice locked (0 today")


def test_a_new_count_needs_most_of_a_week_first():
    days = week(tables=0)
    for d in range(3, 8):                                          # the tables only began 2 days ago
        days[DAY - timedelta(d)] = normal_day(tables=0)
    assert W.check(days, DAY) == []


def test_a_swallowed_error_is_reported_once_per_kind():
    days = week()
    days[DAY] += [("daily", "card", 0, "NBA absences skipped (TypeError: '<' not supported between instances)")] * 2
    days[DAY] += [("pregame", "publish", 0, "novig tables: not priced (PricerError: all 3 asks failed: 500)")]
    days[DAY] += [("pregame", "card", 1, "Traceback (most recent call last)")]       # a failed step shows in runs already
    lines = W.check(days, DAY)
    assert len(lines) == 2
    assert lines[0].startswith("swallowed error in card (NBA absences skipped [TypeError:")
    assert lines[1].startswith("swallowed error in publish (novig tables: not priced [PricerError:")


def test_alert_body_names_each_problem():
    """alerts.problem keeps the text before ' (' and ':' of each line as the alert's body."""
    lines = W.check(week(nv="0 of 4", tables=0), DAY)
    assert sorted({ln.split(" (")[0].split(":")[0].strip() for ln in lines}) == [
        "Novig game-page prices gone", "Novig parlays priced none"]


def test_the_overnight_jobs_failed_steps_reach_the_morning():
    """Nov 9: sync-personal and grade failed with exit 1 at 3 AM and nobody heard. The worker keeps the phone quiet at
    night (worker.QUIET_JOBS), so the 9:55 watchdog names them; a warning (3, grade's own alert) and a skip don't count."""
    rows = [("overnight", "sync-personal", 1, "psycopg.OperationalError: timeout (x)"),
            ("overnight", "grade --no-alert", 1, "boom\n\nKeyError: 'close'\n"),
            ("overnight", "export-page", None, ""), ("overnight", "refresh", 3, "not graded"),
            ("pregame", "publish", 1, "elsewhere")]
    lines = W.overnight_failures(rows)
    assert [ln.split(" (")[0] for ln in lines] == ["overnight sync-personal failed", "overnight grade --no-alert failed"]
    assert "KeyError: 'close'" in lines[1] and "(" not in lines[0].split(" (", 1)[1]


def test_one_weather_blip_is_not_an_alert():
    from datetime import date

    from betlab import watchdog

    day = date(2026, 11, 8)
    blip = ("pregame", "preview", 0, "weather: Open-Meteo failed 2 times in a row; no forecasts for the rest of this run")
    assert not any("swallowed" in ln for ln in watchdog.check({day: [blip]}, day))
    assert any("swallowed" in ln for ln in watchdog.check({day: [blip] * 3}, day))


def test_a_day_whose_watchdog_never_ran_is_made_up():
    """Nov 6: the daily died at a hard step before its watchdog, so Nov 5 was never checked."""
    ran = ("daily", "watchdog", 0, "watchdog: nothing quietly at zero")
    days = {DAY - timedelta(d): normal_day() + [ran] for d in range(0, 4)}
    days[DAY - timedelta(1)] = normal_day()            # the watchdog for DAY - 2 never ran
    assert W.missed(days, DAY) == [DAY - timedelta(2)]
    assert W.missed(days | {DAY - timedelta(1): normal_day() + [ran]}, DAY) == []
