from datetime import datetime, timezone

from betlab import calendar_sync as C

UTC = timezone.utc
BOARD = {"events": [{"id": "1", "date": "2026-11-08T18:00Z", "name": "x", "competitions": [{"competitors": [
    {"homeAway": "home", "team": {"displayName": "New York Rangers"}}, {"homeAway": "away", "team": {"displayName": "St. Louis Blues"}}]}]},
    {"id": "2", "name": "no date"}]}
UFC = {"events": [{"id": "9", "date": "2026-11-07T22:00Z", "name": "UFC 335", "competitions": [{"competitors": [
    {"homeAway": "home", "athlete": {"displayName": "A"}}]}, {"competitors": []}]}]}


def test_a_board_becomes_rows_and_a_ufc_event_is_one_row():
    rows = C.parse_board("nhl", BOARD)
    assert rows == [{"id": "nhl:1", "league": "nhl", "sport": "nhl", "start": "2026-11-08T18:00Z", "home": "New York Rangers",
                     "away": "St. Louis Blues", "matchup": "St. Louis Blues @ New York Rangers"}]
    assert C.parse_board("epl", {"events": BOARD["events"][:1]})[0]["sport"] == "soccer"
    assert C.parse_board("ufc", UFC)[0]["matchup"] == "UFC 335"


def test_a_failed_day_keeps_its_rows_and_others_still_count():
    def get(url):
        if "dates=20261105" in url and "hockey/nhl" in url:
            raise OSError("down")
        return BOARD if "hockey/nhl" in url else {}
    rows, failed = C.fetch_all(datetime(2026, 11, 4, tzinfo=UTC), days=3, get=get)
    assert {r["id"] for r in rows} == {"nhl:1"} and failed == {("nhl", "20261105")}


def test_changes_count_new_moved_and_gone_but_keep_failed_days_and_the_past():
    now = datetime(2026, 11, 4, 12, tzinfo=UTC)
    d = lambda day: datetime(2026, 11, day, 18, tzinfo=UTC)            # noqa: E731
    old = {"nhl:1": d(8), "nhl:2": d(9), "nhl:3": d(10), "nhl:4": d(1), "nhl:5": d(12)}
    rows = [{"id": "nhl:1", "start": "2026-11-08T19:00:00Z"}, {"id": "nhl:6", "start": "2026-11-13T18:00:00Z"},
            {"id": "nhl:5", "start": "2026-11-12T18:00:00Z"}]
    new, moved, gone = C.changes(old, rows, {("nhl", "20261110")}, now)
    assert (new, moved) == (1, 1) and gone == ["nhl:2"]                 # 3's day failed, 4 is past


def test_a_row_links_to_its_game_even_when_games_holds_codes():
    rows = C.parse_board("nhl", BOARD)
    games = [{"game_id": "nhl:77", "league": "nhl", "home": "NYR", "away": "STL", "commence_time": datetime(2026, 11, 8, 18, tzinfo=UTC)},
             {"game_id": "nhl:78", "league": "nba", "home": "New York Rangers", "away": "St. Louis Blues",
              "commence_time": datetime(2026, 11, 8, 18, tzinfo=UTC)}]
    C.link(rows, games[1:])
    assert "game_id" not in rows[0]                                     # another sport's row
    C.link(rows, games)
    assert rows[0]["game_id"] == "nhl:77"
