"""The go-live checklist: market names, the three bars, leans logged beside picks, repeat pulls."""

from datetime import datetime, timezone

import pandas as pd

from betlab import cli, golive, ledger


def rows(market, n, clv, league="nfl"):
    return pd.DataFrame({"league": league, "market": market, "clv": clv, "status": "won",
                         "pick_id": [f"{market}{i}" for i in range(n)]})


def test_status_bars():
    assert golive.status({"with_clv": 49, "avg_clv": 0.05, "beat_close": 0.9}) == "not yet"
    assert golive.status({"with_clv": 50, "avg_clv": 0.012, "beat_close": 0.56}) == "pass"
    assert golive.status({"with_clv": 60, "avg_clv": 0.005, "beat_close": 0.6}) == "failing"
    assert golive.status({"with_clv": 60, "avg_clv": 0.02, "beat_close": 0.5}) == "failing"


def test_market_keys_group_props():
    df = pd.DataFrame({"league": ["nfl", "nfl", "ncaaf"], "market": ["player_receptions", "h2h", "totals"]})
    assert list(golive.market_key(df)) == ["NFL props", "NFL moneyline", "NCAAF totals"]


def test_build_lists_every_market_and_counts_leans(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    monkeypatch.setattr(ledger, "LEANS", tmp_path / "leans.csv")
    picks = rows("spreads", 50, [0.02] * 35 + [-0.01] * 15)      # avg +1.1%, beat the close 70%
    leans = rows("spreads", 5, [0.01] * 5)
    ledger.save(picks.reindex(columns=ledger.COLUMNS).assign(**{k: picks[k] for k in picks}))
    ledger.save(leans.reindex(columns=ledger.COLUMNS).assign(**{k: leans[k] for k in leans}), ledger.LEANS)
    g = golive.build(datetime(2026, 10, 1, 14, tzinfo=timezone.utc))
    by = {m["market"]: m for m in g["markets"]}
    assert set(golive.MARKETS) <= set(by) and g["days_left"] == 16
    s = by["NFL spreads"]
    assert s["picks"]["with_clv"] == 50 and s["status"] == "pass" and s["leans"]["with_clv"] == 5
    assert by["NCAAF totals"]["status"] == "not yet" and by["NCAAF totals"]["progress"] == 0.0


def test_sure_positive_needs_more_than_a_few_lucky_picks():
    few = pd.Series([0.05, 0.08])
    many = pd.Series([0.02, -0.01, 0.03, 0.01] * 12)                 # avg +1.25% over 48 picks
    assert golive.sure_positive(pd.Series(dtype=float)) is None
    assert 0.6 < golive.sure_positive(few) < 0.85                      # two lucky picks: suggestive, not proof
    assert golive.sure_positive(many) > 0.9 and golive.sure_positive(-many) < 0.1
    assert golive.sure_positive(pd.concat([many] * 3)) > golive.sure_positive(many)   # more picks, more sure


def test_pace_projects_to_the_review_day(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    monkeypatch.setattr(ledger, "LEANS", tmp_path / "leans.csv")
    now = datetime(2026, 10, 3, 14, tzinfo=timezone.utc)                # 14 days before the review
    p = rows("totals", 6, [0.02] * 4 + [None] * 2, league="ncaaf")
    p["created_at"] = [(pd.Timestamp(now) - pd.Timedelta(days=d)).isoformat() for d in (1, 2, 3, 8, 9, 20)]
    ledger.save(p.reindex(columns=ledger.COLUMNS).assign(**{k: p[k] for k in p}))
    g = golive.build(now)
    t = {m["market"]: m for m in g["markets"]}["NCAAF totals"]["picks"]
    assert t["per_week"] == 2.5 and t["by_review"] == 6 + 5            # 5 in the last 14 days; 2 more weeks
    assert g["all_markets"]["picks"]["with_clv"] == 4


def test_hours_since_pull(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.config, "DATA_DIR", tmp_path)
    day = "2026-09-27"
    folder = tmp_path / "odds" / "americanfootball_nfl" / day
    folder.mkdir(parents=True)
    now = pd.Timestamp("2026-09-27 14:30", tz="America/New_York")
    assert cli._hours_since_pull("americanfootball_nfl", day, now) is None
    (folder / "101700_pick.parquet").write_bytes(b"")
    assert round(cli._hours_since_pull("americanfootball_nfl", day, now), 2) == 4.22


def test_props_are_judged_on_raw_clv(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    monkeypatch.setattr(ledger, "LEANS", tmp_path / "leans.csv")
    props = rows("player_receptions", 50, [0.05] * 50).assign(kind="prop", clv_raw=[0.005] * 50)
    ledger.save(props.reindex(columns=ledger.COLUMNS).assign(**{k: props[k] for k in props}))
    m = {x["market"]: x for x in golive.build(datetime(2026, 10, 1, 14, tzinfo=timezone.utc))["markets"]}["NFL props"]
    assert m["picks"]["avg_clv"] == 0.005 and m["status"] == "failing"   # +5% corrected is mostly the correction
    assert m["avg_clv_corrected"] == 0.05


def _quotes(*books, point=24.5, player="Wide Out", market="player_reception_yds"):
    """A props pull: each (book, over price, under price) at `point`."""
    rows = []
    for book, over, under in books:
        for side, price in (("Over", over), ("Under", under)):
            rows.append({"event_id": "e1", "market": market, "player": player, "bookmaker": book, "outcome": side,
                         "point": point, "price": price, "snapshot_ts": "2026-10-18T16:50:00Z"})
    return pd.DataFrame(rows)


BET = {"event_id": "e1", "market": "player_reception_yds", "player": "Wide Out", "side": "Under", "point": 24.5,
       "price": -110.0, "commence_time": "2026-10-18T17:00:00Z", "created_at": "2026-10-18T16:15:00Z"}


def test_a_prop_close_counts_only_from_a_sharp_book_at_the_bets_line():
    """Oct 19 (Mike): soft books' -110/-110 read as a coin flip, so 17 NFL prop closes from them were -4.8% CLV
    (7% beat) while sharp closes were flat. Only a sharp book at the bet's own line grades CLV."""
    from betlab import grading

    sharp = grading.sharp_prop_close(BET, _quotes(("draftkings", -110, -110), ("pinnacle", 105, -125)))
    assert sharp["close_source"] == "sharp:pinnacle" and sharp["p_close_raw"] > 0.5
    soft = grading.sharp_prop_close(BET, _quotes(("draftkings", -110, -110), ("fanduel", -112, -108)))
    assert soft["close_source"] == "soft" and "p_close" not in soft and soft["close_price"] == -108
    other_line = grading.sharp_prop_close(BET, _quotes(("pinnacle", 105, -125), point=25.5))
    assert other_line["close_source"] == "none"
    assert grading.sharp_prop_close(BET, None) == {}
    scorer = {**BET, "market": "player_anytime_td", "side": "Yes", "point": 0.5}
    q = _quotes(("pinnacle", 150, -190), market="player_anytime_td", point=0.5).replace({"Over": "Yes", "Under": "No"})
    assert grading.sharp_prop_close(scorer, q)["close_source"] == "sharp:pinnacle"


def test_graded_props_get_their_close_again_once_by_the_sharp_rule(monkeypatch):
    from betlab import grading

    picks = pd.DataFrame({"pick_id": ["s", "f", "n", "g", "done"], "league": ["nfl", "nfl", "nhl", "nfl", "nfl"],
                          "kind": ["prop", "prop", "prop", "game_line", "prop"], "status": ["won"] * 5,
                          "price": [-110.0] * 5, "side": ["Under"] * 5, "point": [24.5] * 5,
                          "clv": [0.02, -0.05, 0.03, 0.01, 0.04], "clv_raw": [0.02, -0.05, 0.03, None, 0.04],
                          "p_close": [0.5] * 5, "close_point": [None] * 5, "close_price": [None] * 5,
                          "close_source": [None, None, None, None, "sharp:pinnacle"]})
    monkeypatch.setattr(grading, "prop_close", lambda r: {"s": {"close_source": "sharp:lowvig", "p_close": 0.55,
                                                                 "p_close_raw": 0.53, "close_point": 24.5,
                                                                 "close_price": -110},
                                                           "f": {"close_source": "soft", "close_point": 24.5,
                                                                 "close_price": -110}}[r["pick_id"]])
    monkeypatch.setattr(grading, "nhl_prop_close", lambda r: {})
    out = grading.fill_close_source(picks).set_index("pick_id")
    assert out.loc["s", "close_source"] == "sharp:lowvig" and out.loc["s", "clv_raw"] == round(0.53 * (1 + 100 / 110) - 1, 4)
    assert out.loc["f", "close_source"] == "soft" and pd.isna(out.loc["f", "clv"]) and pd.isna(out.loc["f", "clv_raw"])
    assert out.loc["n", "close_source"] == "none" and pd.isna(out.loc["n", "clv"])       # no later pull: no close
    assert pd.isna(out.loc["g", "close_source"]) and out.loc["g", "clv"] == 0.01          # game lines untouched
    assert out.loc["done", "clv"] == 0.04                                                 # already regraded: left alone


def test_old_ledger_files_gain_new_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    pd.DataFrame({c: ["x"] for c in ledger.COLUMNS if c != "clv_raw"}).to_csv(ledger.LEDGER, index=False)
    df = ledger.load()
    assert list(df.columns) == ledger.COLUMNS and df["clv_raw"].isna().all()


def test_retired_props_rule_left_out(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    monkeypatch.setattr(ledger, "LEANS", tmp_path / "leans.csv")
    picks = rows("player_receptions", 3, [-0.05, -0.04, 0.02]).assign(
        kind="prop", clv_raw=[-0.05, -0.04, 0.02],
        market_source=["pinnacle, corrected for the over lean"] * 2 + ["pinnacle"])
    ledger.save(picks.reindex(columns=ledger.COLUMNS).assign(**{k: picks[k] for k in picks}))
    g = golive.build(datetime(2026, 10, 1, 14, tzinfo=timezone.utc))
    props = {m["market"]: m for m in g["markets"]}["NFL props"]
    assert props["picks"]["with_clv"] == 1 and props["picks"]["avg_clv"] == 0.02
    assert props["retired_excluded"]["picks"] == 2
    assert g["all_markets"]["picks"]["with_clv"] == 1


def test_record_skips_retired_props_rule(tmp_path, monkeypatch):
    from betlab.reports import review

    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    picks = rows("player_receptions", 3, [-0.05, -0.04, 0.02]).assign(
        kind="prop", clv_raw=[-0.05, -0.04, 0.02], units_flat=1.0, profit_flat=[1.0, -1.0, 1.0],
        market_source=["pinnacle, corrected for the over lean"] * 2 + ["pinnacle"])
    ledger.save(picks.reindex(columns=ledger.COLUMNS).assign(**{k: picks[k] for k in picks}))
    assert review.build()["overall"]["record"] == "1-0-0"


def test_early_logged_picks_leave_the_record():
    df = pd.DataFrame({"created_at": ["2026-09-25T16:00:00Z", "2026-10-02T14:00:00Z"],
                       "commence_time": ["2026-10-03T00:00:00Z", "2026-10-03T00:00:00Z"],
                       "market_source": ["pinnacle", "pinnacle"]})
    assert len(golive.current_rule(df)) == 1 and len(golive.current_rule(df, picks=False)) == 2


def test_pick_window_reads_start_times_with_and_without_seconds():
    df = pd.DataFrame({"created_at": ["2026-10-01T13:59:40+00:00"] * 3,
                       "commence_time": ["2026-10-02T01:30Z", "2026-10-02T01:30:00Z", "2026-10-04T01:30Z"]})
    assert len(golive.current_rule(df)) == 2      # the 60-hour-early one is a lean, not a pick


def test_retired_count_is_per_market(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    monkeypatch.setattr(ledger, "LEANS", tmp_path / "leans.csv")
    picks = rows("player_receptions", 2, [-0.05, 0.02]).assign(
        kind="prop", clv_raw=[-0.05, 0.02], market_source=["pinnacle, corrected for the over lean", "pinnacle"])
    nhl = rows("player_shots_on_goal", 1, [0.01]).assign(league="nhl", kind="prop", clv_raw=[0.01],
                                                         market_source=["pinnacle"])
    both = pd.concat([picks, nhl], ignore_index=True)
    ledger.save(both.reindex(columns=ledger.COLUMNS).assign(**{k: both[k] for k in both}))
    markets = {m["market"]: m for m in golive.build(datetime(2026, 10, 1, 14, tzinfo=timezone.utc))["markets"]}
    assert markets["NFL props"]["retired_excluded"]["picks"] == 1
    assert "retired_excluded" not in markets["NHL props"]


def test_only_real_closes_count(tmp_path, monkeypatch):
    """Oct 13: an NHL or soccer prop 'closed' against the pull it was logged from only repeats its EV, so its
    CLV leaves the scorecard; a later pull of its market (the closing look) keeps it. NFL rows are untouched."""
    from betlab import config
    from betlab.sources import odds_api

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    nhl = config.settings()["leagues"]["nhl"]["sport_key"]
    ucl = config.settings()["leagues"]["ucl"]["sport_key"]

    def snap(key, ts, eid, market):
        odds_api.save_snapshot(pd.DataFrame([{"event_id": eid, "market": market, "snapshot_ts": ts}]), key, ts, "props")

    snap(nhl, "2026-10-12T23:00:00+00:00", "own", "player_shots_on_goal")       # the pull the lean came from
    snap(nhl, "2026-10-12T23:00:00+00:00", "real", "player_shots_on_goal")
    snap(nhl, "2026-10-12T23:20:00+00:00", "real", "player_shots_on_goal")      # a later pull: a real close
    snap(ucl, "2026-10-13T18:40:00+00:00", "goals", "alternate_totals")        # soccer goals close from the ladder
    base = {"kind": "prop", "market": "player_shots_on_goal", "created_at": "2026-10-12T23:01:00+00:00",
            "commence_time": "2026-10-12T23:30:00Z", "clv": 0.02, "clv_raw": 0.02}
    df = pd.DataFrame([
        base | {"league": "nhl", "event_id": "own"},
        base | {"league": "nhl", "event_id": "real"},
        base | {"league": "nfl", "event_id": "own", "market": "player_receptions"},
        base | {"league": "ucl", "event_id": "goals", "kind": "game_line", "market": "totals",
                "created_at": "2026-10-13T18:16:00+00:00", "commence_time": "2026-10-13T19:00:00Z"}])
    out, bad = golive.real_closes(df)
    assert bad.tolist() == [True, False, False, False]
    assert pd.isna(out.at[0, "clv"]) and pd.isna(out.at[0, "clv_raw"]) and out.at[1, "clv"] == 0.02


def test_a_cup_3way_bet_needs_a_later_game_line_pull(tmp_path, monkeypatch):
    """Oct 15: the cups' 3-way close is our own last game-line pull, so the Viking-Bayern draw logged from the
    18:15 pull 'closed' at its own EV; a later pick pull is a real close."""
    from betlab import config
    from betlab.sources import odds_api

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    ucl = config.settings()["leagues"]["ucl"]["sport_key"]
    for ts, eid in (("2026-10-13T18:15:00+00:00", "own"), ("2026-10-13T18:15:00+00:00", "real"),
                    ("2026-10-13T18:50:00+00:00", "real")):
        odds_api.save_snapshot(pd.DataFrame([{"event_id": eid, "market": "h2h", "snapshot_ts": ts}]), ucl, ts, "pick")
    base = {"league": "ucl", "kind": "game_line", "market": "h2h", "created_at": "2026-10-13T18:15:26+00:00",
            "commence_time": "2026-10-13T19:00:00Z", "clv": 0.0894}
    out, bad = golive.real_closes(pd.DataFrame([base | {"event_id": "own"}, base | {"event_id": "real"}]))
    assert bad.tolist() == [True, False] and pd.isna(out.at[0, "clv"]) and out.at[1, "clv"] == 0.0894


def test_bets_logged_at_or_after_the_scheduled_start_leave_the_record():
    """Oct 12: the feed moved Monday night from 8:15 to 8:18 at 8:15 PM and leans were logged at 8:15:31; NHL leans
    came 27-47 seconds after puck drop. The earliest start seen for a game is its scheduled start."""
    df = pd.DataFrame([
        {"event_id": "mnf", "created_at": "2026-10-12T23:00:00+00:00", "commence_time": "2026-10-13T00:15:00Z"},
        {"event_id": "mnf", "created_at": "2026-10-13T00:15:31+00:00", "commence_time": "2026-10-13T00:18:00Z"},
        {"event_id": "nhl", "created_at": "2026-10-10T22:00:27+00:00", "commence_time": "2026-10-10T22:00Z"},
        {"event_id": "ok", "created_at": "2026-10-10T21:45:00+00:00", "commence_time": "2026-10-10T22:00Z"}])
    assert golive.current_rule(df, picks=False)["created_at"].tolist() == ["2026-10-12T23:00:00+00:00",
                                                                           "2026-10-10T21:45:00+00:00"]


def test_the_ledger_never_logs_a_bet_at_or_after_its_start(tmp_path):
    path = tmp_path / "leans.csv"
    rows = pd.DataFrame([{"league": "nhl", "event_id": "a", "market": "player_shots_on_goal", "label": "A over 2.5 shots",
                          "side": "Over", "player": "A", "point": 2.5, "price": 120, "commence_time": "2026-10-10T22:00Z"},
                         {"league": "nhl", "event_id": "b", "market": "player_shots_on_goal", "label": "B over 2.5 shots",
                          "side": "Over", "player": "B", "point": 2.5, "price": 120, "commence_time": "2099-10-10T22:00Z"}])
    added = ledger.add_picks(rows, "2026-10-10T22:00:27+00:00", path)
    assert added["event_id"].tolist() == ["b"]


def test_the_card_skips_games_about_to_start():
    asof = pd.Timestamp("2026-10-10T22:00:05Z")                   # the on-the-hour tick
    offers = pd.DataFrame({"commence_time": ["2026-10-10T22:00:00Z", "2026-10-10T22:01:00Z", "2026-10-10T22:30:00Z",
                                             "2026-10-10T21:00:00Z"], "label": ["now", "1 min", "30 min", "started"]})
    assert cli.not_starting(offers, asof)["label"].tolist() == ["30 min"]


def test_a_pregame_pull_of_one_game_is_not_the_mornings_pull(tmp_path, monkeypatch):
    """Nov 1-2: the 8:15 pull of one college game made the 9:55 skip the other 116."""
    from betlab import cli, config, pregame

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    now = pd.Timestamp("2026-11-02 15:00:00+00:00")                  # 10 AM ET
    day_dir = tmp_path / "odds" / "basketball_ncaab" / "2026-11-02"
    day_dir.mkdir(parents=True)
    (day_dir / "081503_pick.parquet").write_bytes(b"")
    state = pregame.load_state("basketball_ncaab", now) | {"files": ["081503_pick.parquet"]}
    pregame._save_state("basketball_ncaab", now, state)
    assert cli._hours_since_pull("basketball_ncaab", "2026-11-02", now) is None
    (day_dir / "095601_pick.parquet").write_bytes(b"")
    assert round(cli._hours_since_pull("basketball_ncaab", "2026-11-02", now), 2) == 0.07
