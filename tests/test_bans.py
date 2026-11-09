"""The ban list (bans.py): the shared cases, the fun card's scrub, and pick alerts per account."""

import json
from pathlib import Path

import pandas as pd

from betlab import alerts, bans

ROOT = Path(__file__).parent.parent
FIX = json.loads((Path(__file__).parent / "fixtures" / "bans.json").read_text(encoding="utf-8"))


def test_the_shared_cases():
    for c in FIX["cases"]:
        assert bans.banned(c["bans"], c["label"], c.get("league"), c.get("player")) == c["hit"], c


def test_the_team_table_is_one_file_in_all_three():
    one = (ROOT / "src/betlab/teams.json").read_text(encoding="utf-8")
    assert one == (ROOT / "web/lib/teams.json").read_text(encoding="utf-8")
    assert one == (ROOT / "ios/BetLab/teams.json").read_text(encoding="utf-8")


def test_bad_entries_are_dropped():
    assert bans.clean([{"kind": "team", "name": " "}, {"kind": "coach", "name": "X"}, "Jets", None,
                       {"kind": "player", "name": "Josh Allen"}]) == [{"kind": "player", "name": "Josh Allen", "league": None}]


def test_scrub_drops_banned_tickets_and_keeps_packs():
    leg = lambda label, player="": {"label": label, "player": player}   # noqa: E731
    doc = {"slates": [{"sport": "nfl", "plus": {"legs": [leg("Josh Allen 250+ passing yds", "Josh Allen"), leg("KC ML")]},
                       "td": {"legs": [leg("Travis Kelce anytime TD", "Travis Kelce")]},
                       "overs": [{"label": "Josh Allen 30+ rushing yds"}, {"label": "James Cook 60+ rushing yds"}],
                       "packs": [{"legs": [leg("Josh Allen 250+ passing yds", "Josh Allen")]}]}],
           "games": [{"sgps": [{"legs": [leg("BUF -3.5")]}, {"legs": [leg("KC +3.5")]}]}]}
    n = bans.scrub(doc, [{"kind": "player", "name": "Josh Allen"}, {"kind": "team", "name": "Bills"}])
    s = doc["slates"][0]
    assert n == 3 and s["plus"] is None and s["td"] is not None
    assert [o["label"] for o in s["overs"]] == ["James Cook 60+ rushing yds"]
    assert len(s["packs"][0]["legs"]) == 1
    assert [g["legs"][0]["label"] for g in doc["games"][0]["sgps"]] == ["KC +3.5"]


def test_ticket_search_skips_banned_minis():
    from betlab import sgp_plus

    def mini(label, p):
        return {"legs": [{"label": label, "player": label.rsplit(" ", 2)[0], "price": -110}], "n_legs": 1, "p_fair": p, "leg_value": 1.1,
                "sgp_id": label, "theme": "", "fair_price": 100}

    games = [{"event_id": str(i), "matchup": f"G{i}", "commence_time": "2026-10-26T17:00:00Z",
              "minis": [mini(f"Star{i} Player 1+ receptions", 0.5), mini(f"Other{i} Guy 1+ receptions", 0.5)]} for i in range(3)]
    cfg = {"band": [100, 2000], "max_games": 3, "min_games": 2, "max_legs": 6}
    try:
        bans.use([{"kind": "player", "name": "Star1 Player"}])
        t = sgp_plus.ticket(games, "s", "x", cfg)
    finally:
        bans.use([])
    assert t and "Star1 Player 1+ receptions" not in [l["label"] for l in t["legs"]]


def test_alerts_leave_out_a_users_banned_picks():
    rows = pd.DataFrame([{"label": "Josh Allen 250+ passing yds", "league": "nfl", "player": "Josh Allen"},
                         {"label": "KC ML", "league": "nfl", "player": float("nan")}])
    out = alerts.without_banned(rows, bans.clean([{"kind": "player", "name": "Josh Allen"}]))
    assert list(out["label"]) == ["KC ML"]
    assert len(alerts.without_banned(rows, [])) == 2
