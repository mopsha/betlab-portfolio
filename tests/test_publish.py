"""The app's database (docs/APP_PLAN.md): build_rows maps the page products to tables, publish
writes them, page_lists brings a user's rows back in the page's old sync format."""

import copy
from datetime import datetime, timezone

import pandas as pd

from betlab import cli, ledger, publish


def products():
    return {
        "previews": {"games": [{"game_id": "2026_04_PIT_CLE", "kickoff": "2026-10-01T20:15:00-04:00", "home": "CLE",
                                "away": "PIT", "matchup": "Pittsburgh Steelers @ Cleveland Browns"}],
                     "track_record": {"graded": 3}},
        "previews_ncaaf": {"games": [{"game_id": "401862791", "kickoff": "2026-10-03T12:00:00-04:00", "home": "Air Force",
                                      "away": "Navy", "matchup": "Navy @ Air Force"}]},
        "nhl": {"games": [{"game_id": "2026020011", "start": "2026-10-01T23:00Z", "home": "CBJ", "away": "BUF",
                           "matchup": "BUF @ CBJ"}], "tracker": {"graded": 0}},
        "card": {"generated_at": "t", "notes": ["n"], "picks": [],
                 "leans": [
                     {"pick_id": "l1", "league": "ncaaf", "event_id": "ev-navy", "matchup": "Navy Midshipmen @ Air Force Falcons",
                      "commence_time": "2026-10-03T16:00:00Z", "label": "Over 45.5", "price": -110, "ev": 0.02,
                      "link": "https://ny.sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=2"},
                     {"pick_id": "l2", "league": "nhl", "event_id": "ev-buf", "matchup": "BUF @ CBJ",
                      "commence_time": "2026-10-01T23:00:00Z", "label": "Anders Lee under 1.5 shots", "price": 154.0}],
                 "check_news": [
                     {"pick_id": "c1", "league": "ncaaf", "event_id": "ev-sam", "matchup": "Samford @ UAB",
                      "commence_time": "2026-10-03T19:30:00Z", "label": "UAB -20", "price": -110}]},
        "fun": {"generated_at": "t", "stake": 1, "games": [
                    {"event_id": "ev-pit", "game_ref": "2026_04_PIT_CLE", "matchup": "Pittsburgh Steelers @ Cleveland Browns",
                     "commence_time": "2026-10-02T00:15:00Z", "read": {"x": "y"},
                     "sgps": [{"sgp_id": "s1", "fair_price": 226, "p_fair": 0.31, "naive_price": 260, "legs": []}]}],
                "slates": [
                    {"slate": "2026-10-01-night", "kickoff": "2026-10-02T00:15:00Z", "label": "Thu", "n_games": 1,
                     "plus": None, "packs": [{"event_id": "x", "legs": [{"label": "a", "p": 0.5}]}],
                     "overs": [{"sgp_id": "o1", "event_id": "ev-pit", "matchup": "Pittsburgh Steelers @ Cleveland Browns",
                                "commence_time": "2026-10-02T00:15:00Z", "price": 102, "fair_price": 120, "p_fair": 0.45}]},
                    {"slate": "2026-10-01-nhl", "sport": "nhl", "kickoff": "2026-10-01T23:00:00Z", "n_games": 2,
                     "plus": {"sgp_id": "p1", "fair_price": 900, "p_fair": 0.1, "matchup": "SGP+"}, "overs": []}]},
        "golive": {"markets": []}, "coverage": {"rows": []}, "meta": {"synced_at": "t"},
    }


def ledgers():
    cols = {"created_at": "2026-09-27T14:00:00+00:00", "commence_time": "2026-09-27T17:00:00Z", "league": "nfl",
            "label": "x", "price": 120.0, "point": 0.5, "status": "lost", "profit_flat": -1.0, "close_push": 0.1}
    picks = pd.DataFrame([{**cols, "pick_id": "p-old"}, {**cols, "pick_id": "p-retired", "clv": float("nan")}])
    leans = pd.DataFrame([{**cols, "pick_id": "lean-1", "status": "open"}])
    fun = pd.DataFrame([{"sgp_id": "s1", "status": "won", "leg_results": '[{"leg": "a", "result": "won"}]',
                         "profit_1u": 2.26, "graded_at": "2026-10-02T10:00:00Z"}])
    return picks, leans, fun


def rows():
    picks, leans, fun = ledgers()
    return publish.build_rows(products(), picks, leans, fun, [("x", {"event_id": "x", "sport": "nfl"})],
                              current={"p-old", "lean-1"}, abbr={"Pittsburgh Steelers": "PIT", "Cleveland Browns": "CLE"})


def test_card_lines_land_on_their_games():
    r = {o["offer_id"]: o for o in rows()["offers"]}
    assert r["l1"]["game_id"] == "ncaaf:401862791"          # 'Navy Midshipmen' starts with the preview's 'Navy'
    assert r["l2"]["game_id"] == "nhl:2026020011"            # same codes, same start
    assert r["c1"]["game_id"] == "ncaaf:ev-sam"              # no preview (an FCS opponent): its own game
    assert {o["tier"] for o in r.values()} == {"lean", "check"}
    assert r["l1"]["fd_url"].startswith("https://ny.sportsbook.fanduel.com/")
    assert r["l1"]["commence_time"] == datetime(2026, 10, 3, 16, tzinfo=timezone.utc)


def test_nfl_fun_games_link_the_odds_event_to_the_nflverse_game():
    out = rows()
    games = {g["game_id"]: g for g in out["games"]}
    assert games["nfl:2026_04_PIT_CLE"]["odds_event_id"] == "ev-pit"
    tickets = {t["sgp_id"]: t for t in out["fun_tickets"]}
    assert tickets["s1"]["game_id"] == tickets["o1"]["game_id"] == "nfl:2026_04_PIT_CLE"
    assert tickets["p1"]["kind"] == "sgp_plus" and tickets["p1"]["game_id"] is None and tickets["p1"]["sport"] == "nhl"
    assert tickets["s1"]["status"] == "won" and tickets["s1"]["leg_results"] == [{"leg": "a", "result": "won"}]
    assert ("nfl:2026_04_PIT_CLE", "nfl_fun") in {(a["game_id"], a["kind"]) for a in out["game_analysis"]}


def test_two_games_at_the_same_time_never_mix():
    idx = publish.GameIndex()
    idx.add("nfl", "A", "2026-10-04T17:00Z", "BUF", "NE")
    idx.add("nfl", "B", "2026-10-04T17:00Z", "CHI", "NYJ")
    assert idx.resolve("nfl", "e1", "2026-10-04T17:00Z", "NYJ @ CHI") == "nfl:B"
    assert idx.resolve("nfl", "e2", "2026-10-04T17:00Z", "MIA @ CHI") == "nfl:e2"     # one team off: not a match
    assert idx.resolve("nfl", "e1", None, None) == "nfl:B"                            # remembered by event id


def test_paper_record_flags_current_rule_and_keeps_both_ledgers():
    pp = {p["pick_id"]: p for p in rows()["paper_picks"]}
    assert pp["p-old"]["tier"] == "pick" and pp["p-old"]["current_rule"]
    assert not pp["p-retired"]["current_rule"] and pp["p-retired"]["clv"] is None    # NaN goes out as null
    assert pp["lean-1"]["tier"] == "lean"


def test_documents_and_slates_index():
    docs = {(d["collection"], d["doc_id"]): d["body"] for d in rows()["docs"]}
    assert {("app", "golive"), ("app", "coverage"), ("app", "meta"), ("card", "meta"), ("fun", "slates"),
            ("track", "nfl"), ("track", "nhl")} <= set(docs)
    assert "leans" not in docs[("card", "meta")]
    slate = docs[("fun", "slates")]["slates"][0]
    assert slate["ticket_ids"] == ["o1"] and "packs" not in slate and "overs" not in slate


def test_build_rows_leaves_the_products_unchanged():
    p = products()
    before = copy.deepcopy(p)
    picks, leans, fun = ledgers()
    publish.build_rows(p, picks, leans, fun, [], set())
    assert p == before


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def executemany(self, sql, params):
        self.log.append((sql, list(params)))

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self):
        self.log = []

    def transaction(self):
        return FakeCursor(self.log)

    def cursor(self, **kw):
        return FakeCursor(self.log)


def test_publish_updates_only_grading_on_paper_picks_and_retires_stale_rows():
    conn = FakeConn()
    counts = publish.publish(conn, rows())
    assert counts["offers"] == 3 and counts["paper_picks"] == 3
    sql = {s.split()[2]: s for s, _ in conn.log if s.startswith("insert")}
    upd = sql["paper_picks"].split("do update set ", 1)[1]
    assert "status = excluded.status" in upd and "clv = excluded.clv" in upd
    assert "close_push = excluded.close_push" in upd
    assert next(p for p in rows()["paper_picks"] if p["pick_id"] == "p-old")["close_push"] == 0.1
    for frozen in ("price", "point", "label", "created_at"):
        assert f" {frozen} = excluded" not in " " + upd
    stale = [s for s, _ in conn.log if s.startswith("update")]
    assert any("offers set active = false" in s for s in stale) and any("fun_tickets set active = false" in s for s in stale)
    assert any(s.startswith("delete from leg_packs") for s, _ in conn.log)


def test_a_game_that_gets_its_league_id_takes_over_the_odds_side_row():
    # Oct 2: Memphis @ Charlotte was stored as ncaaf:<event id>, then its preview claimed the event
    conn = FakeConn()
    publish.publish(conn, rows())
    sqls = [s for s, _ in conn.log]
    first_insert = next(i for i, s in enumerate(sqls) if s.startswith("insert into games"))
    merge = [i for i, s in enumerate(sqls) if "unnest(" in s]
    assert merge and max(merge) < first_insert
    assert any(s.startswith("update offers") for s in sqls) and any(s.startswith("delete from games") for s in sqls)
    ev, gids = next(p for s, p in conn.log if s.startswith("delete from games"))
    assert len(ev) == len(gids) and all(ev)


def test_personal_rows_come_back_in_the_page_sync_format():
    bets = [{"user_id": "u", "pick_id": "p-old", "sgp_id": None, "mode": "paper", "price": 120, "stake": None,
             "label": "x", "matchup": "m", "placed_at": "2026-09-27T15:58:15Z"},
            {"user_id": "u", "pick_id": None, "sgp_id": "s1", "mode": "paper", "price": 250, "stake": 1,
             "fair_price": 226, "p_fair": 0.31, "legs": ["a", "b"], "matchup": "PIT @ CLE",
             "odds_event_id": "ev-pit", "games": None, "placed_at": "2026-10-01T20:00:00Z"}]
    quotes = [{"user_id": "u", "sgp_id": "s1", "price": 250, "fair_price": 226, "legs": ["a", "b"],
               "odds_event_id": "ev-pit", "quoted_at": "2026-10-01T19:00:00Z"}]
    customs = [{"user_id": "u", "sgp_id": "custom-1", "price": 450, "legs": ["c"], "grade": "B", "odds_event_id": None}]
    taken, fun_quotes, fun_taken = publish.page_lists(bets, quotes, customs)
    assert taken == [{"pick_id": "p-old", "mode": "paper", "price": 120.0, "stake": None, "book": None, "bonus": False,
                      "label": "x", "matchup": "m", "placed_at": "2026-09-27T15:58:15Z"}]
    assert fun_taken[0]["bonus"] is False
    assert fun_taken[0]["sgp_id"] == "s1" and fun_taken[0]["event_id"] == "ev-pit" and fun_taken[0]["stake"] == 1.0
    assert "odds_event_id" not in fun_taken[0] and "user_id" not in fun_quotes[0]
    assert {q["sgp_id"] for q in fun_quotes} == {"s1", "custom-1"} and fun_quotes[1]["grade"] == "B"


def test_apply_taken_marks_picks_and_leans(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    monkeypatch.setattr(ledger, "LEANS", tmp_path / "leans.csv")
    base = {c: None for c in ledger.COLUMNS}
    ledger.save(pd.DataFrame([base | {"pick_id": "a"}, base | {"pick_id": "b"}]), ledger.LEDGER)
    ledger.save(pd.DataFrame([base | {"pick_id": "l"}]), ledger.LEANS)
    n = ledger.apply_taken([{"pick_id": "b", "price": 110, "stake": 1, "book": "DraftKings"}, {"pick_id": "l", "price": -105}])
    assert n == 2
    picks, leans = ledger.load(), ledger.load(ledger.LEANS)
    assert picks.set_index("pick_id")["taken_book"].to_dict()["b"] == "DraftKings"   # where it was placed (Oct 12)
    assert leans.loc[0, "taken_book"] == "FanDuel"                                     # bets from before: FanDuel
    assert picks.set_index("pick_id")["taken"].astype(str).to_dict() == {"a": "False", "b": "True"}   # read back as text, as always
    assert leans.loc[0, "taken_price"] == -105


def test_bonus_bets_reach_the_ledgers(tmp_path, monkeypatch):
    """Oct 19: a bonus bet (the book's credit) is flagged in picks.csv and the fun ledger's rows."""
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    monkeypatch.setattr(ledger, "LEANS", tmp_path / "leans.csv")
    base = {c: None for c in ledger.COLUMNS}
    ledger.save(pd.DataFrame([base | {"pick_id": "a"}, base | {"pick_id": "b"}]), ledger.LEDGER)
    bets = [{"pick_id": "a", "sgp_id": None, "mode": "real", "price": 300, "stake": 2, "bonus": True},
            {"pick_id": "b", "sgp_id": None, "mode": "real", "price": 110, "stake": 1},
            {"pick_id": None, "sgp_id": "s1", "mode": "real", "price": 400, "stake": 1.94, "bonus": True}]
    taken, _, fun_taken = publish.page_lists(bets, [], [])
    ledger.apply_taken(taken)
    assert ledger.load().set_index("pick_id")["taken_bonus"].to_dict() == {"a": "True", "b": "False"}
    assert fun_taken[0]["bonus"] is True


def test_page_docs_does_not_change_the_products(tmp_path, monkeypatch):
    p = products()
    p["picks"] = None
    before = copy.deepcopy(p)
    docs = list(cli.page_docs(p))
    assert p == before
    assert ("fun_legs" in {c for c, _, _ in docs}) and ("app", "meta") in {(c, d) for c, d, _ in docs}


def test_graded_slips_off_the_card_still_reach_the_database():
    picks, leans, _ = ledgers()
    fun = pd.DataFrame([
        {"sgp_id": "s1", "status": "won", "profit_1u": 2.26, "graded_at": "2026-10-02T10:00:00Z", "legs": '["a"]'},
        {"sgp_id": "old-hex", "status": "lost", "profit_1u": -1.0, "graded_at": "2026-09-28T10:00:00Z", "sport": "nfl",
         "matchup": "A @ B", "event_id": "ev-old", "legs": '["x", "y"]', "leg_results": '[{"leg": "x", "result": "lost"}]'},
        {"sgp_id": "plus-abc", "status": "won", "profit_1u": 9.0, "graded_at": "2026-09-28T10:00:00Z", "legs": "[]"},
        {"sgp_id": "custom-mine", "status": "won", "profit_1u": 1.04, "graded_at": "2026-09-25T10:00:00Z", "legs": '["c"]'},
        {"sgp_id": "novig-01a17f52", "status": "open", "legs": '["Jordan Kyrou 1+ goals"]'}])
    r = publish.build_rows(products(), picks, leans, fun, [], set())
    hist = {t["sgp_id"]: t for t in r["fun_history"]}
    assert set(hist) == {"old-hex", "plus-abc"}          # s1 is on today's card; custom slips and Novig bets stay private
    assert hist["old-hex"]["status"] == "lost" and hist["old-hex"]["active"] is False
    assert hist["old-hex"]["kind"] == "sgp" and hist["plus-abc"]["kind"] == "sgp_plus"
    assert hist["old-hex"]["body"]["legs"] == ["x", "y"] and hist["old-hex"]["leg_results"][0]["result"] == "lost"
    conn = FakeConn()
    counts = publish.publish(conn, r)
    assert counts["fun_history"] == 2
    ins = [s for s, _ in conn.log if s.startswith("insert into fun_tickets") and "active" in s.split("values")[0]]
    upd = ins[-1].split("do update set ", 1)[1]
    assert "status = excluded.status" in upd and "active = excluded" not in upd and "body = excluded" not in upd


def test_page_taps_become_one_users_rows():
    taken = [{"pick_id": "p-old", "price": 120, "mode": "paper", "label": "x", "placed_at": "2026-09-27T15:58:15.930Z"},
             {"pick_id": "lean-1", "price": -113, "placed_at": "2026-09-27T15:58:09Z"}]
    fun_taken = [{"sgp_id": "311b", "price": 1246, "stake": 1, "fair_price": 1787, "legs": ["a", "b"], "event_id": "ev",
                  "placed_at": "2026-09-27T23:58:27Z"},
                 {"sgp_id": "plus-aa", "price": 1530, "event_id": "", "games": [{"legs": ["c"]}], "legs": ["c"],
                  "placed_at": "2026-09-27T16:02:54Z"}]
    quotes = [{"sgp_id": "016c", "price": 235, "fair_price": 330, "n_legs": 4, "legs": ["a"], "quoted_at": "2026-09-26T18:09:48Z"},
              {"sgp_id": "custom-dk", "price": 176, "legs": ["w", "l"], "book": "draftkings", "quoted_at": "2026-09-24T20:45:00Z"},
              {"sgp_id": "no-price", "price": None}]
    r = publish.page_tap_rows(taken, fun_taken, quotes, lean_ids={"lean-1"}, pick_ids={"p-old"})
    assert [(b["kind"], b.get("pick_id") or b.get("sgp_id")) for b in r["bets"]] == [
        ("pick", "p-old"), ("lean", "lean-1"), ("parlay", "311b"), ("parlay", "plus-aa")]
    assert r["bets"][3]["odds_event_id"] is None and r["bets"][2]["legs"] == ["a", "b"]
    assert r["bets"][0]["placed_at"].year == 2026
    assert [q["sgp_id"] for q in r["quotes"]] == ["016c"] and r["quotes"][0]["n_legs"] == 4
    assert [c["sgp_id"] for c in r["custom_parlays"]] == ["custom-dk"] and r["custom_parlays"][0]["legs"] == ["w", "l"]


def test_import_page_taps_is_insert_only():
    class Cur(FakeCursor):
        rowcount = 1
    class Conn(FakeConn):
        def cursor(self, **kw):
            return Cur(self.log)
    conn = Conn()
    counts = publish.import_page_taps(conn, "u1", {"bets": [{"kind": "pick", "pick_id": "p", "price": 1.0, "stake": None}],
                                                   "quotes": [], "custom_parlays": []})
    assert counts == {"bets": 1, "quotes": 0, "custom_parlays": 0}
    sql, params = [x for x in conn.log if x[0].startswith("insert")][0]
    assert sql.endswith("on conflict do nothing") and "stake" not in sql and "u1" in params


def test_fetch_personal_fills_a_tickets_games_from_the_published_ticket():
    """Oct 9: the app saved an SGP+ mark and quote without their games, so the ticket never graded."""
    games = [{"game_ref": "2026_04_IND_WAS", "matchup": "IND @ WAS", "legs": [{"label": "Daniel Jones 200+ passing yds"}]}]
    tables = {"bets": [{"sgp_id": "plus-x", "mode": "paper", "games": None},
                       {"pick_id": "p1", "mode": "real"}],
              "quotes": [{"sgp_id": "plus-x", "price": 2065, "games": None},
                         {"sgp_id": "plus-nhl", "price": 850}],
              "custom_parlays": []}

    class Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, args):
            if "from fun_tickets" in sql:
                self.rows = [{"sgp_id": "plus-x", "sport": "nfl", "games": games},
                             {"sgp_id": "plus-nhl", "sport": "nhl", "games": games}]
            else:
                self.rows = [dict(r) for r in tables[sql.split(" from ")[1].split()[0]]]
        def fetchall(self): return self.rows

    class Conn:
        def cursor(self, row_factory=None): return Cur()

    bets, quotes, _ = publish.fetch_personal(Conn(), "u")
    assert bets[0]["games"] == games and bets[0]["sport"] == "nfl"
    assert "games" not in bets[1]                                  # a straight pick: untouched
    assert quotes[0]["games"] == games and quotes[1]["sport"] == "nhl"
    _, fun_quotes, fun_taken = publish.page_lists(bets, quotes, [])
    assert fun_taken[0]["games"] == games and fun_taken[0]["sport"] == "nfl"


def test_another_accounts_slips_join_the_fun_ledger_as_quotes(tmp_path, monkeypatch):
    """Oct 10 (a second account, Mike: combine them): her typed prices and marked parlays become plain quotes,
    so every slip is graded and her FanDuel prices count, while marked / stake stay the owner's."""
    from betlab import fun_ledger, publish

    q = [{"sgp_id": "plus-a", "price": 900.0, "legs": ["X to win"], "quoted_at": "2026-10-11T12:00:00+00:00"}]
    ft = [{"sgp_id": "plus-b", "mode": "real", "stake": 5.0, "price": 1200.0, "legs": ["Y to win"],
           "placed_at": "2026-10-11T12:05:00+00:00"}]
    out = publish.others_as_quotes(q, ft)
    assert [r["sgp_id"] for r in out] == ["plus-a", "plus-b"]
    assert "stake" not in out[1] and "mode" not in out[1] and out[1]["price"] == 1200.0
    monkeypatch.setattr(fun_ledger, "PATH", tmp_path / "fun.csv")
    monkeypatch.setattr("betlab.sources.nflverse.load_games", lambda: __import__("pandas").DataFrame(
        columns=["game_id", "home_team", "away_team", "gameday", "gametime"]))
    monkeypatch.setattr("betlab.sources.nflverse.team_abbr_by_name", lambda: {})
    fun_ledger.sync(out, [])
    led = fun_ledger.load().set_index("sgp_id")
    assert set(led.index) == {"plus-a", "plus-b"} and not led.loc["plus-b", "marked"]


def _migration_columns() -> dict[str, set]:
    """Every table's columns as the migrations create them (create table blocks plus add column)."""
    import re

    sql = "\n".join(f.read_text(encoding="utf-8") for f in sorted(publish.migrations_dir().glob("*.sql")))
    sql = re.sub(r"--[^\n]*", "", sql)
    cols: dict[str, set] = {}
    for table, body in re.findall(r"create table (?:if not exists )?(\w+)\s*\((.*?)\n\);", sql, re.S):
        for line in body.split("\n"):
            m = re.match(r"\s*([a-z_][a-z0-9_]*)\s+[a-z]", line)
            if m and m.group(1) not in ("primary", "unique", "constraint", "check", "foreign"):
                cols.setdefault(table, set()).add(m.group(1))
    for table, body in re.findall(r"alter table (\w+)(.*?);", sql, re.S):
        for col in re.findall(r"add column (?:if not exists )?(\w+)", body):
            cols.setdefault(table, set()).add(col)
    return cols


def test_every_column_publish_sends_exists_in_a_migration():
    """Oct 12: DraftKings day 1 sent offers.other_book with no migration, and every publish failed for 6 hours."""
    cols = _migration_columns()
    g = publish.GameIndex()
    offer = publish._offer({"pick_id": "x", "league": "nfl", "event_id": "e1"}, "pick", g) | {"active": True}
    paper = publish._paper(pd.DataFrame([{"pick_id": "x"}]), "pick", set())[0]
    ticket = publish._ticket({"sgp_id": "s"}, "sgp", "nfl", g, {}) | {"active": True}
    for table, row in (("offers", offer), ("paper_picks", paper), ("fun_tickets", ticket)):
        missing = set(row) - cols.get(table, set())
        assert not missing, f"{table} has no column for {sorted(missing)}: add a migration"


def test_a_preview_row_claims_the_odds_side_row_a_lean_left_behind():
    """Oct 25: CIN @ BAL showed twice. A 3 AM lean stored the game under its odds event ("CIN @ BAL"); the 9:55 publish
    had the preview but no lean, so nothing linked them. The league row claims the stored event-keyed row now."""
    games = [{"game_id": "nfl:2026_07_CIN_BAL", "league": "nfl", "home": "BAL", "away": "CIN",
              "matchup": "Cincinnati Bengals @ Baltimore Ravens", "commence_time": pd.Timestamp("2026-10-25T17:00Z")},
             {"game_id": "nfl:2026_07_GB_DET", "league": "nfl", "home": "DET", "away": "GB", "odds_event_id": "e9",
              "matchup": "Green Bay Packers @ Detroit Lions", "commence_time": pd.Timestamp("2026-10-25T20:25Z")}]
    stale = [("nfl:e1", "nfl", "e1", "BAL", "CIN", pd.Timestamp("2026-10-25T17:00Z")),
             ("nfl:e2", "nfl", "e2", "Baltimore Ravens", "Cincinnati Bengals", pd.Timestamp("2026-10-25T17:00Z")),
             ("nfl:e3", "nfl", "e3", "BAL", "CIN", pd.Timestamp("2026-11-01T17:00Z")),      # another week
             ("nhl:e4", "nhl", "e4", "BAL", "CIN", pd.Timestamp("2026-10-25T17:00Z"))]
    assert publish.claim_stale(stale[:1], games) == 1 and games[0]["odds_event_id"] == "e1"
    games[0].pop("odds_event_id")
    assert publish.claim_stale(stale[1:], games) == 1 and games[0]["odds_event_id"] == "e2"   # by name
    assert publish.claim_stale(stale[2:], [dict(games[0], odds_event_id=None)]) == 0
    still = dict(games[1], game_id="nfl:e5", odds_event_id="e5")
    assert publish.claim_stale([("nfl:e5", "nfl", "e5", "BAL", "CIN", pd.Timestamp("2026-10-25T17:00Z"))],
                               [dict(games[0], odds_event_id=None), still]) == 0


def test_the_schedule_lists_every_nba_and_college_game_and_a_priced_one_keeps_its_row():
    picks, leans, fun = ledgers()
    p = products() | {"schedule": {"ncaab": [{"id": "cb1", "commence_time": "2026-11-02T23:00:00Z", "home_team": "Duke Blue Devils",
                                              "away_team": "Army Knights"}],
                                   "nba": [{"id": "n1", "commence_time": "2026-11-02T23:00:00Z", "home_team": "Boston Celtics",
                                            "away_team": "Miami Heat"}]}}
    p["nba"] = {"games": [{"event_id": "n1", "tipoff": "2026-11-02T23:00:00Z", "matchup": "Miami Heat @ Boston Celtics"}]}
    out = publish.build_rows(p, picks, leans, fun, [], set())
    games = {g["game_id"]: g for g in out["games"]}
    assert games["ncaab:cb1"]["matchup"] == "Army Knights @ Duke Blue Devils" and games["ncaab:cb1"]["odds_event_id"] == "cb1"
    assert games["nba:n1"]["league"] == "nba"
    assert sum(g["league"] == "nba" for g in out["games"]) == 1                  # the same row the NBA's analysis lands on
    assert [a["game_id"] for a in out["game_analysis"] if a["kind"] == "nba"] == ["nba:n1"]


def test_a_failed_pulse_never_fails_the_publish(capsys):
    from contextlib import nullcontext

    class Conn:
        sql = []

        def transaction(self):
            return nullcontext()

        def execute(self, sql):
            self.sql.append(sql)
            if len(self.sql) > 1:
                raise RuntimeError("no table")

    publish.pulse(Conn())
    assert "app_pulse" in Conn.sql[0] and "'card'" in Conn.sql[0]
    publish.pulse(Conn())
    assert "live pulse: not sent" in capsys.readouterr().out
