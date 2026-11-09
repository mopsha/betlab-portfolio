"""SGP+ tickets: kickoff windows, one mini-parlay per game, fair odds as the product across games."""

import pandas as pd

from betlab import sgp_plus as SP

CFG = {"band": [500, 4000], "min_games": 2, "max_games": 4, "max_legs": 10, "overs_per_slate": 6}


def mini(game, p, value=0.9, n=2):
    legs = [{"label": f"{game} player {i} over 3.5 receptions", "price": -150, "read": ""} for i in range(n)]
    return {"sgp_id": f"{game}-{p}", "theme": "stack", "p_fair": p, "fair_price": 100, "p_read": None,
            "leg_value": value, "read_value": value, "n_legs": n, "legs": legs}


def game(name, kickoff, minis, overs=()):
    return {"event_id": name, "matchup": f"{name} Away @ {name} Home", "commence_time": kickoff,
            "minis": minis, "overs": list(overs)}


def test_windows_by_eastern_kickoff():
    assert SP.slate_of("2026-09-27T17:00:00Z")[0] == "2026-09-27-early"      # 1 PM ET
    assert SP.slate_of("2026-09-27T20:25:00Z")[0] == "2026-09-27-late"       # 4:25 PM ET
    assert SP.slate_of("2026-09-28T00:20:00Z")[0] == "2026-09-27-night"      # 8:20 PM ET, still Sunday


def test_ticket_takes_the_most_games_that_fit_and_multiplies_them():
    games = [game(g, "2026-09-27T17:00:00Z", [mini(g, 0.45), mini(g, 0.35, 0.95)]) for g in "ABCD"]
    t = SP.ticket(games, "s", "Sun early", CFG)
    assert t["n_games"] == 4 and t["n_legs"] == 8
    p = 1.0
    for g in t["games"]:
        p *= g["p_fair"]
    assert abs(t["p_fair"] - round(p, 5)) < 1e-9 and 500 <= t["fair_price"] <= 4000
    # the better-value mini wherever the band allows: four of them would be +6500, past +4000
    assert sorted(g["p_fair"] for g in t["games"]) == [0.35, 0.35, 0.45, 0.45]
    # no four-game ticket fits a tight band: it falls back to fewer games
    t3 = SP.ticket(games, "s", "Sun early", CFG | {"band": [500, 1200]})
    assert t3["n_games"] == 3 and 500 <= t3["fair_price"] <= 1200


def test_build_groups_windows_and_skips_single_games_and_started_games():
    over = {"label": "X over 50.5 receiving yds", "price": 150, "p_fair": 0.4, "p_read": None, "fair_price": 150}
    docs = [game("A", "2026-09-27T17:00:00Z", [mini("A", 0.4)], [over]),
            game("B", "2026-09-27T17:00:00Z", [mini("B", 0.4)]),
            game("C", "2026-09-28T00:20:00Z", [mini("C", 0.4)], [over]),
            game("D", "2026-09-26T17:00:00Z", [mini("D", 0.4)])]                # already started
    slates = SP.build(docs, pd.Timestamp("2026-09-27T12:00:00Z"), CFG)
    assert [s["slate"] for s in slates] == ["2026-09-27-early", "2026-09-27-night"]
    early, night = slates
    assert early["plus"]["n_games"] == 2 and early["plus"]["sgp_id"].startswith("plus-")
    assert night["plus"] is None and night["overs"][0]["kind"] == "over"
    assert early["overs"][0]["matchup"] == "A Away @ A Home" and early["overs"][0]["sgp_id"].startswith("over-")


def test_td_ticket_takes_one_scorer_per_game_at_the_product_of_prices():
    from betlab import odds_math as om

    def td(player, p, price):
        return {"label": f"{player} anytime TD", "player": player, "stat": "tds", "side": "yes", "price": price,
                "p_fair": p, "fair_price": 100, "source": "pinnacle"}
    games = [game("A", "2026-09-27T17:00:00Z", [mini("A", 0.4)]) | {"tds": [td("A1", 0.55, -130), td("A2", 0.4, 140)]},
             game("B", "2026-09-27T17:00:00Z", [mini("B", 0.4)]) | {"tds": [td("B1", 0.5, -110)]},
             game("C", "2026-09-27T17:00:00Z", [mini("C", 0.4)])]                      # no scorer: left out
    t = SP.td_ticket(games, "s", "Sun early")
    assert [l["player"] for l in t["legs"]] == ["A1", "B1"] and t["n_games"] == 2
    dec = om.american_to_decimal(-130) * om.american_to_decimal(-110)
    assert abs(t["p_fair"] - 0.275) < 1e-9 and abs(t["ev"] - round(0.275 * dec - 1, 4)) < 1e-9
    assert t["kind"] == "td" and t["sgp_id"].startswith("td-") and t["games"][0]["legs"][0]["player"] == "A1"
    assert SP.td_ticket(games[:1], "s", "x") is None                                  # one game is not a parlay


def test_kickoff_slices_and_titles():
    """College: noon, 3:30 and 7:30 PM kickoffs; soccer: early Europe, late Europe, MLS; NHL: matinees, 7 PM,
    West Coast (Eastern time). Titles name the day, the slice and games or matches (Oct 10)."""
    from betlab.sgp_plus import slice_names, slice_of

    assert slice_of("2026-10-10T16:00:00Z", "ncaaf") == ("2026-10-10", "noon")        # 12:00 PM ET
    assert slice_of("2026-10-10T19:30:00Z", "ncaaf") == ("2026-10-10", "afternoon")   # 3:30 PM
    assert slice_of("2026-10-10T23:30:00Z", "ncaaf") == ("2026-10-10", "night")       # 7:30 PM
    assert slice_of("2026-10-11T04:30:00Z", "ncaaf") == ("2026-10-10", "night")       # 12:30 AM: the night before
    # soccer: one slice per kickoff cluster, each within ~30 minutes so every lineup is in at the lock (Oct 13)
    for utc, name in (("11:30", "early"), ("13:00", "nine"), ("13:30", "nine"), ("14:00", "ten"), ("14:15", "ten"),
                      ("15:15", "eleven"), ("15:30", "eleven"), ("16:00", "noon"), ("16:30", "noon"),
                      ("16:45", "lunch"), ("18:30", "three"), ("18:45", "three"), ("19:00", "three"),
                      ("23:00", "mls"), ("23:30", "mls")):
        assert slice_of(f"2026-10-17T{utc}:00Z", "soccer") == ("2026-10-17", name), utc
    assert slice_of("2026-10-18T00:30:00Z", "soccer") == ("2026-10-17", "evening")    # 8:30 PM MLS
    assert slice_of("2026-10-18T02:30:00Z", "soccer") == ("2026-10-17", "night")      # 10:30 PM MLS
    assert slice_of("2026-10-13T16:45:00Z", "soccer")[1] != slice_of("2026-10-13T19:00:00Z", "soccer")[1]   # cups
    assert slice_names("soccer", "2026-10-17", "nine", 6)["title"] == "Soccer 9 AM matches"
    # Oct 24: a 5:30 PM match gets its own slice, not the 7:30 one's, and a slice is titled by its real first kickoff
    assert slice_of("2026-10-24T21:30:00Z", "soccer") == ("2026-10-24", "five")
    assert slice_of("2026-10-24T23:30:00Z", "soccer") == ("2026-10-24", "mls")
    assert slice_names("soccer", "2026-10-24", "five", 1, "2026-10-24T21:30:00Z")["title"] == "Soccer 5:30 PM match"
    assert slice_names("soccer", "2026-10-24", "night", 2, "2026-10-25T01:30:00Z")["title"] == "Soccer 9:30 PM matches"
    assert slice_names("soccer", "2026-10-24", "noon", 2, "2026-10-24T16:00:00Z")["title"] == "Soccer noon matches"
    assert slice_of("2026-10-11T13:30:00Z", "nfl") == ("2026-10-11", "morning")       # 9:30 AM London: on its own
    assert slice_of("2026-10-11T17:00:00Z", "nfl") == ("2026-10-11", "early")         # 1 PM
    assert slice_of("2026-10-10T17:00:00Z", "nhl") == ("2026-10-10", "afternoon")     # 1 PM matinee
    assert slice_of("2026-10-10T23:00:00Z", "nhl") == ("2026-10-10", "evening")       # 7 PM
    assert slice_of("2026-10-11T02:00:00Z", "nhl") == ("2026-10-10", "late")          # 10 PM
    assert slice_names("ncaaf", "2026-10-10", "noon", 12) == {
        "slate": "2026-10-10-ncaaf-noon", "label": "Sat Oct 10 · college football noon games", "title": "College football noon games"}
    assert slice_names("soccer", "2026-10-11", "three", 6)["title"] == "Soccer 3 PM matches"
    assert slice_names("nfl", "2026-10-11", "night", 1) == {
        "slate": "2026-10-11-night", "label": "Sun Oct 11 · NFL night game", "title": "NFL night game"}
    assert slice_names("nhl", "2026-10-10", "late", 3)["slate"] == "2026-10-10-nhl-late"


def _slate(sid, sport, ticket, kick="2026-10-10T19:30:00Z", locked=None):
    return {"slate": sid, "sport": sport, "kickoff": kick, "packs": ["p"], "overs": ["o"], "locked_at": locked,
            "plus": {"sgp_id": ticket, "games": [{"commence_time": kick}]} if ticket else None}


def test_a_slice_locks_15_minutes_before_it_starts():
    """Mike, Oct 10: tickets follow the news until 15 minutes before a slice's first kickoff; that build is
    final, and nothing new appears as its games start. Every sport is locked the same way."""
    import pandas as pd

    from betlab.sgp_plus import keep_tickets

    kick = "2026-10-10T19:30:00Z"                                        # 3:30 PM ET: locks at the 3:15 tick
    at = lambda hhmm: pd.Timestamp(f"2026-10-10T{hhmm}:00Z")
    # 3:00 PM: a preview, the new build wins
    got = keep_tickets([_slate("d-ncaaf-afternoon", "ncaaf", "B", kick)], [_slate("d-ncaaf-afternoon", "ncaaf", "A", kick)], at("19:01"))
    assert got[0]["plus"]["sgp_id"] == "B" and not got[0].get("locked_at")
    # 3:16 PM: the lock tick, its fresh build (the latest news) is final
    got = keep_tickets([_slate("d-ncaaf-afternoon", "ncaaf", "C", kick)], [_slate("d-ncaaf-afternoon", "ncaaf", "B", kick)], at("19:16"))
    assert got[0]["plus"]["sgp_id"] == "C" and got[0]["locked_at"] == "2026-10-10T19:16:00+00:00"
    # 3:45 PM: games started, the rebuild from the rest is ignored
    got = keep_tickets([_slate("d-ncaaf-afternoon", "ncaaf", "D", "2026-10-10T20:00:00Z")], got, at("19:45"))
    assert got[0]["plus"]["sgp_id"] == "C" and got[0]["kickoff"] == kick
    # the same for the NFL (old-style ids), the NHL and soccer
    for sid, sport in (("d-early", "nfl"), ("d-nhl-evening", "nhl"), ("d-soccer-three", "soccer")):
        locked = [_slate(sid, sport, "X", kick, locked="t")]
        assert keep_tickets([_slate(sid, sport, "Y", kick)], locked, at("19:45"))[0]["plus"]["sgp_id"] == "X"


def test_a_locked_slice_stays_until_4_hours_after_kickoff_and_empty_locks_hold():
    import pandas as pd

    from betlab.sgp_plus import keep_tickets

    old = [_slate("d-ncaaf-noon", "ncaaf", "N", "2026-10-10T16:00:00Z", locked="t"),
           _slate("d-ncaaf-afternoon", "ncaaf", None, locked="t"),                   # locked with no ticket
           _slate("d-ncaaf", "ncaaf", "OLD", "2026-10-10T16:00:00Z")]                # a day-long ticket from before
    new = [_slate("d-ncaaf-afternoon", "ncaaf", "LATE")]
    got = {s["slate"]: s for s in keep_tickets(new, old, pd.Timestamp("2026-10-10T19:45:00Z"))}
    assert got["d-ncaaf-noon"]["plus"]["sgp_id"] == "N" and got["d-ncaaf-noon"]["packs"] == [] == got["d-ncaaf-noon"]["overs"]
    assert got["d-ncaaf-afternoon"]["plus"] is None                    # nothing new once locked, even none
    assert "d-ncaaf" not in got
    later = keep_tickets(new, old, pd.Timestamp("2026-10-10T20:30:00Z"))
    assert "d-ncaaf-noon" not in {s["slate"] for s in later}


def test_lock_due_and_the_lock_notification():
    import pandas as pd

    from betlab import alerts
    from betlab.sgp_plus import lock_due

    slates = [_slate("d-ncaaf-afternoon", "ncaaf", "C"), _slate("d-ncaaf-night", "ncaaf", "E", "2026-10-10T23:30:00Z"),
              _slate("d-nba", "nba", "Z")]
    assert lock_due(slates, pd.Timestamp("2026-10-10T19:16:00Z")) == ["d-ncaaf-afternoon"]
    assert lock_due(slates, pd.Timestamp("2026-10-10T19:01:00Z")) == []
    slates[0] |= {"locked_at": "t", "title": "College football afternoon games",
                  "plus": slates[0]["plus"] | {"n_games": 4, "n_legs": 7, "fair_price": 4187}}
    now = pd.Timestamp("2026-10-10T19:17:00Z")
    todo = alerts.locked(slates, set(), now)
    assert [s["slate"] for s in todo] == ["d-ncaaf-afternoon"]
    assert alerts.locked(slates, {"lock:d-ncaaf-afternoon"}, now) == []          # announced once
    msg = alerts.lock_message(todo[0])
    assert msg["title"] == "Locked: College football afternoon games SGP+"
    assert msg["body"].startswith("4 games, 7 legs, fair +4187. First game 3:30 PM ET.")


def test_nba_slices_merge_re_pulls_and_lock():
    """Oct 21 (Mike: "early and late slices"): a night's NBA games group into afternoon, early (before 9 PM) and late
    slices. A news re-pull of one game merges into its slice's slate, which locks like the other sports'."""
    import pandas as pd

    from betlab.cards import fun_nba
    from betlab.sgp_plus import keep_tickets, lock_due

    fun = {"nba": {"min_games": 99, "overs_per_slate": 3}}        # no ticket math here: just the slates
    game = lambda eid, tip: {"event_id": eid, "matchup": eid, "commence_time": tip, "game_ref": eid,
                             "minis": [], "overs": [], "pack": {"legs": [eid]}}
    tip = "2026-10-21T23:00:00+00:00"                                # 7:00 PM ET
    first = fun_nba._slate([game("bos", tip), game("nyk", tip), game("mia", "2026-10-22T00:40:00+00:00")], fun)
    assert first["slate"] == "2026-10-21-nba-early" and first["title"] == "NBA early games"
    assert "pack" not in first["games"][0] and len(first["packs"]) == 3
    repull = fun_nba._slate([game("mia", "2026-10-22T00:40:00+00:00")], fun)
    merged = fun_nba.merge([repull], [first], fun)[0]
    assert merged["slate"] == "2026-10-21-nba-early" and merged["n_games"] == 3
    assert sorted(p["legs"][0] for p in merged["packs"]) == ["bos", "mia", "nyk"]

    first["plus"] = {"sgp_id": "plus-N", "games": [{"commence_time": tip}]}
    first["plus_short"] = {"sgp_id": "plus-S", "games": [{"commence_time": tip}]}
    assert lock_due([first], pd.Timestamp("2026-10-21T22:45:00Z")) == ["2026-10-21-nba-early"]
    locked = keep_tickets([first], [first], pd.Timestamp("2026-10-21T22:45:00Z"), ("nba",))[0]
    assert locked["locked_at"] and locked["plus"]["sgp_id"] == "plus-N" and locked["plus_short"]["sgp_id"] == "plus-S"
    later = keep_tickets([merged | {"plus": None, "plus_short": None}], [locked], pd.Timestamp("2026-10-21T23:30:00Z"), ("nba",))[0]
    assert later["plus"]["sgp_id"] == "plus-N" and later["plus_short"]["sgp_id"] == "plus-S"   # a re-pull after the lock


def test_nba_slices_on_the_oct_21_schedule():
    """Oct 21's eleven tips made six 30-minute windows; as slices they are two: 7:00-8:40 early, 10:00-10:40 late."""
    import pandas as pd

    from betlab.cards import fun_nba

    fun = {"nba": {"min_games": 99, "overs_per_slate": 3}}
    et = ["19:00", "19:10", "19:30", "19:40", "19:40", "20:10", "20:10", "20:40", "22:00", "22:10", "22:40"]
    tip = lambda hm: pd.Timestamp(f"2026-10-21 {hm}", tz="America/New_York").tz_convert("UTC").isoformat()
    games = [{"event_id": f"g{i}", "matchup": f"g{i}", "commence_time": tip(t), "game_ref": f"g{i}", "minis": [],
              "overs": [], "pack": {"legs": []}} for i, t in enumerate(et)]
    s = fun_nba.slates_from(games, fun)
    assert [(x["slate"], x["n_games"]) for x in s] == [("2026-10-21-nba-early", 8), ("2026-10-21-nba-late", 3)]
    assert s[1]["label"] == "Wed Oct 21 · NBA late games"
    assert fun_nba.slice_key(tip("13:00")) == ("2026-10-21", "afternoon")
    assert fun_nba.slice_key("2026-10-22T04:30:00Z") == ("2026-10-21", "late")      # 12:30 AM: the night before


def test_a_slice_gone_from_one_build_before_its_games_stays_a_preview():
    """Nov 6: the Premier League's lines aged past 24 hours after the 9:55 daily stopped, so a 1:46 PM build had
    none of tomorrow's EPL matches, and its 7:30 AM and 10 AM slices were carried over as locked (packs emptied),
    with lock alerts. A missing slice is held as locked only once its games have begun; a mistaken lock heals."""
    import pandas as pd

    from betlab.sgp_plus import keep_tickets

    kick = "2026-11-07T12:30:00Z"
    now = pd.Timestamp("2026-11-06T18:46:00Z")
    old = [_slate("2026-11-07-soccer-early", "soccer", "A", kick)]
    got = keep_tickets([], old, now)
    assert len(got) == 1 and not got[0].get("locked_at") and got[0]["packs"] == ["p"]
    # its games back in the next build: the new build wins, still a preview
    got = keep_tickets([_slate("2026-11-07-soccer-early", "soccer", "B", kick)], got, now + pd.Timedelta(minutes=15))
    assert got[0]["plus"]["sgp_id"] == "B" and not got[0].get("locked_at")
    # a slice locked by the old carry-over (packs and overs emptied, before its lock time) rebuilds
    bad = [_slate("2026-11-07-soccer-early", "soccer", "A", kick, locked="2026-11-06T18:46:57+00:00") | {"packs": [], "overs": []}]
    got = keep_tickets([_slate("2026-11-07-soccer-early", "soccer", "C", kick)], bad, pd.Timestamp("2026-11-07T03:00:00Z"))
    assert got[0]["plus"]["sgp_id"] == "C" and not got[0].get("locked_at")
    # and it still locks at its time
    got = keep_tickets([_slate("2026-11-07-soccer-early", "soccer", "D", kick)], got, pd.Timestamp("2026-11-07T12:16:00Z"))
    assert got[0]["plus"]["sgp_id"] == "D" and got[0]["locked_at"]
    # a real lock keeps its tickets, even before kickoff
    real = [_slate("2026-11-07-soccer-early", "soccer", "R", kick, locked="2026-11-07T11:00:00+00:00")]
    assert keep_tickets([_slate("2026-11-07-soccer-early", "soccer", "S", kick)], real, pd.Timestamp("2026-11-07T11:30:00Z"))[0]["plus"]["sgp_id"] == "R"


def test_a_mistaken_lock_dressed_with_new_packs_still_heals():
    """Nov 7: the Nov 6 repair judged a mistaken lock by its emptied packs and overs, but every rebuild after the
    carry-over had given the two slices fresh packs (the "locked earlier" branch keeps each build's packs), so
    they looked like real locks, kept Friday's tickets through their kickoffs and sent no lock alert. A lock
    stamped hours before the slice's first kickoff is never real: an early lock needs every game's pre-game
    pull, at most 85 minutes out."""
    import pandas as pd

    from betlab.sgp_plus import keep_tickets

    kick = "2026-11-07T15:00:00Z"                                                     # 10 AM ET
    bad = [_slate("2026-11-07-soccer-ten", "soccer", "A", kick, locked="2026-11-06T18:46:57+00:00")
           | {"packs": ["p1", "p2", "p3"], "overs": ["o1"]}]                          # re-dressed by later builds
    got = keep_tickets([_slate("2026-11-07-soccer-ten", "soccer", "C", kick)], bad, pd.Timestamp("2026-11-07T11:46:00Z"))
    assert got[0]["plus"]["sgp_id"] == "C" and not got[0].get("locked_at")
    # news in for every game at 9:33 AM: the early lock now works, with the day's build
    got = keep_tickets([_slate("2026-11-07-soccer-ten", "soccer", "D", kick)], got, pd.Timestamp("2026-11-07T14:33:00Z"),
                       early={"2026-11-07-soccer-ten"})
    assert got[0]["plus"]["sgp_id"] == "D" and got[0]["locked_at"] == "2026-11-07T14:33:00+00:00"
    # that lock, 27 minutes out, is real: the next build keeps it
    got2 = keep_tickets([_slate("2026-11-07-soccer-ten", "soccer", "E", kick)], got, pd.Timestamp("2026-11-07T14:48:00Z"))
    assert got2[0]["plus"]["sgp_id"] == "D" and got2[0]["locked_at"] == got[0]["locked_at"]
    # a real lock at the usual time, 85 minutes out at the earliest (NFL's pull window), is kept too
    real = [_slate("2026-11-08-early", "nfl", "R", "2026-11-08T18:00:00Z", locked="2026-11-08T16:35:00+00:00")]
    assert keep_tickets([_slate("2026-11-08-early", "nfl", "S", "2026-11-08T18:00:00Z")], real,
                        pd.Timestamp("2026-11-08T16:50:00Z"))[0]["plus"]["sgp_id"] == "R"


def test_every_games_own_slips_ride_on_its_slice():
    """Nov 7 (Mike): mark the games you'll watch and get their parlays, instead of the Knicks rule and the lone
    prime-time game's. Each slip carries its game (for the apps' filter, links, Novig, publish and grading); a one-leg
    mini isn't a parlay; the NFL's and NBA's full slips keep their own style."""
    from betlab.sgp_plus import own_slips

    leg = lambda s, p=None: {"label": s, "price": p, "_price": -110}
    games = [{"event_id": "e1", "game_ref": "r1", "matchup": "A @ B", "commence_time": "2026-11-08T18:00:00Z",
              "minis": [{"sgp_id": "m1", "legs": [leg("A ML"), leg("Over 2.5")]}, {"sgp_id": "m2", "legs": [leg("A ML")]}]},
             {"event_id": "e2", "game_ref": "r2", "matchup": "C @ D", "commence_time": "2026-11-08T18:00:00Z",
              "sgps": [{"sgp_id": "s1", "style": "longshot", "legs": [leg("x"), leg("y"), leg("z")]}]}]
    got = own_slips(games, "nhl")
    assert [s["sgp_id"] for s in got] == ["m1"]
    s = got[0]
    assert (s["event_id"], s["matchup"], s["sport"], s["style"]) == ("e1", "A @ B", "nhl", "mini")
    assert all("_price" not in l for l in s["legs"])
    assert s["games"] == [{"event_id": "e1", "game_ref": "r1", "matchup": "A @ B", "commence_time": "2026-11-08T18:00:00Z",
                           "legs": ["A ML", "Over 2.5"]}]
    full = own_slips(games, "nfl", "sgps")
    assert [(x["sgp_id"], x["style"], x["event_id"]) for x in full] == [("s1", "longshot", "e2")]


def test_novig_prices_a_slates_own_slips_only_for_watched_games():
    """Nov 7: pricing every game's own slips at Novig took the publish from ~100 s to 204 s (119 slips); only a watched
    game's show, so only those are asked. None (no app database) asks them all."""
    from betlab import novig_parlays as N

    asked = []
    doc = {"slates": [{"sgps": [{"sgp_id": "a", "event_id": "e1", "legs": [{"label": "x"}, {"label": "y"}]},
                                {"sgp_id": "b", "event_id": "e2", "legs": [{"label": "x"}, {"label": "y"}]}]}]}

    class Idx:
        pass

    seen = []
    orig_leg, orig_price = N._leg, N.price_all
    try:
        N._leg = lambda idx, leg, eid: seen.append(eid)
        N.price_all = lambda sets, post=None: asked.extend(sets) or {}
        N.attach(doc, Idx(), watched={"e2"})
        assert seen == ["e2", "e2"]
        seen.clear()
        N.attach(doc, Idx(), watched=None)
        assert seen == ["e1", "e1", "e2", "e2"]
    finally:
        N._leg, N.price_all = orig_leg, orig_price


def test_a_watched_games_slips_come_from_its_pack_by_the_fun_rules():
    """Nov 7 (Mike: "if a game is watched that means i want single game slips for it"): for the sports with no full slips
    (college, soccer, the NHL, UFC), each game's slips come from its Build-tab pack, priced as Build prices them; one leg
    per market (a team's moneyline and its own spread are one), at most one player under and only a near-lock one."""
    import base64

    import numpy as np

    from betlab import sgp

    rng = np.random.default_rng(1)
    n = 3000
    home_win = rng.random(n) < 0.55
    goals = rng.poisson(5.8, n)
    star = rng.random(n) < np.where(home_win, 0.6, 0.35)          # the home star shoots more when they win
    bits = lambda h: base64.b64encode(np.packbits(h.astype(np.uint8)).tobytes()).decode()
    def leg(label, h, stat, side, player="", team=""):
        return {"label": label, "p": round(float(h.mean()), 4), "p_pack": round(float(h.mean()), 4), "bits": bits(h),
                "stat": stat, "side": side, "player": player, "team": team, "price": -110}
    pack = {"draws": n, "legs": [leg("H to win", home_win, "moneyline", "home"), leg("H -1.5", home_win & (rng.random(n) < .6), "puck line", "home"),
                                 leg("Over 5.5 goals", goals > 5.5, "goals", "over"), leg("Under 5.5 goals", goals < 5.5, "goals", "under"),
                                 leg("Star over 2.5 shots", star, "shots", "over", "Star"), leg("Star under 2.5 shots", ~star, "shots", "under", "Star")]}
    game = {"event_id": "e1", "matchup": "A @ H", "commence_time": "2026-11-08T00:00:00Z", "game_ref": "r"}
    out = sgp.pack_slips(pack, game, "nhl", band=(100, 1000))
    assert out, "a pack with related legs makes slips"
    for s in out:
        labels = [l["label"] for l in s["legs"]]
        assert not ({"H to win", "H -1.5"} <= set(labels))                       # who wins: one leg
        assert not ({"Over 5.5 goals", "Under 5.5 goals"} <= set(labels))
        assert "Star under 2.5 shots" not in labels                             # a 50/50 player under never
        assert s["sgp_id"] and s["fair_price"] and s["p_fair"] > 0
    best = out[0]
    assert {"H to win", "Star over 2.5 shots"} <= {l["label"] for l in best["legs"]}    # the legs that move together
    assert best["lift"] > 1.0
    from betlab.sgp_plus import pack_own_slips
    own = pack_own_slips([pack | game], "nhl")
    assert own and own[0]["event_id"] == "e1" and own[0]["games"][0]["legs"] == [l["label"] for l in own[0]["legs"]]
    # a lines-only game (college, a UFC fight) gets its best single at FanDuel instead (Nov 7: "just give a pick"), never
    # one priced at a stand-in for a leg FanDuel doesn't list
    lines = {"draws": n, "legs": [leg("H to win", home_win, "moneyline", "home") | {"price": -105},
                                  leg("A to win", ~home_win, "moneyline", "away") | {"price": -120},
                                  leg("Over 5.5 goals", goals > 5.5, "goals", "over") | {"price": 400, "source": "fair price (FanDuel's isn't in the feed)"}]}
    single = pack_own_slips([lines | game], "ncaaf")
    assert [s["style"] for s in single] == ["single"] and single[0]["legs"][0]["label"] == "H to win"
    assert single[0]["price"] == -105 and "EV" in single[0]["why"]
