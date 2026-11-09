"""DraftKings day 4 (Oct 12, docs/DRAFTKINGS_PLAN.md): every parlay's DraftKings side, its quotes and quote model."""

import numpy as np
import pandas as pd

from betlab import fun_ledger, links


def _dk_rows():
    rows = [("player_pass_yds_alternate", "Over", "Matthew Stafford", p, pr) for p, pr in ((219.5, -474), (229.5, -357), (239.5, -276))]
    rows += [("player_anytime_td", "Yes", "Matthew Stafford", None, 1800), ("player_anytime_td", "Yes", "Puka Nacua", None, -125),
             ("player_reception_yds_alternate", "Over", "Keon Coleman", 24.5, -231), ("player_reception_yds_alternate", "Over", "Keon Coleman", 39.5, -114)]
    return pd.DataFrame([{"event_id": "e1", "market": m, "outcome": o, "player": pl, "point": pt, "price": pr,
                          "link": f"https://sportsbook.draftkings.com/?outcomes={i}"} for i, (m, o, pl, pt, pr) in enumerate(rows)])


def _slip(*legs):
    return {"sgp_id": "s1", "fair_price": 400, "n_legs": len(legs), "legs": list(legs)}


def test_a_rung_draftkings_lacks_moves_to_its_nearest_by_chance_never_to_a_td():
    staff = {"label": "Matthew Stafford 225+ passing yds", "stat": "passing_yards", "side": "over", "point": 224.5,
             "player": "Matthew Stafford", "price": -420, "p_fair": 0.79}
    td = {"label": "Puka Nacua anytime TD", "stat": "tds", "side": "yes", "point": 0.5, "player": "Puka Nacua", "price": -125}
    doc = {"games": [{"event_id": "e1", "sgps": [_slip(staff, td)]}]}
    links.attach_dk(doc, links.Matcher(_dk_rows()))
    s = doc["games"][0]["sgps"][0]
    assert staff["dk_price"] == -357 and staff["dk_label"] == "Matthew Stafford 230+ passing yds" and staff["dk_moved"]
    assert td["dk_price"] == -125 and not td.get("dk_moved")
    assert s["dk"]["legs"] == 2 and s["dk"]["of"] == 2 and s["dk"]["moved"] == 1 and s["dk"]["naive_price"] is not None


def test_a_leg_too_far_from_any_rung_leaves_the_slip_off_draftkings():
    coleman = {"label": "Keon Coleman 30+ receiving yds", "stat": "receiving_yards", "side": "over", "point": 29.5,
               "player": "Keon Coleman", "price": -194, "p_fair": 0.56}
    doc = {"games": [{"event_id": "e1", "sgps": [_slip(coleman)]}]}
    links.attach_dk(doc, links.Matcher(_dk_rows()))
    assert "dk_price" not in coleman and doc["games"][0]["sgps"][0]["dk"] == {"legs": 0, "of": 1, "moved": 0}


def test_fanduel_links_never_take_an_anytime_td_for_a_missing_rung():
    staff = {"label": "Matthew Stafford 225+ passing yds", "stat": "passing_yards", "side": "over", "point": 224.5,
             "player": "Matthew Stafford", "price": -420}
    links._leg(links.Matcher(_dk_rows()), staff, "e1")
    assert "link" not in staff


def _quotes(book, n, ratio):
    rng = np.random.default_rng(1)
    rows = []
    for i in range(n):
        fair = int(rng.integers(300, 3000))
        dec = (1 + fair / 100) * ratio
        rows.append({"sgp_id": f"s{i}" + ("~dk" if book == "draftkings" else ""), "book": book, "fair_price": fair,
                     "naive_price": int(fair * 1.3), "n_legs": int(rng.integers(2, 6)), "price": round((dec - 1) * 100)})
    return pd.DataFrame(rows)


def test_each_book_gets_its_own_quote_model():
    df = pd.concat([_quotes("fanduel", 60, 0.75), _quotes("draftkings", 45, 0.9)], ignore_index=True)
    fd, dk = fun_ledger.quote_model(df), fun_ledger.quote_model(df, book="draftkings")
    assert fd and dk and fd["quotes"] == 60 and dk["quotes"] == 45
    assert fun_ledger.quote_model(df.iloc[:80], book="draftkings") is None          # 20 DraftKings quotes: not yet


def test_a_draftkings_quote_is_its_own_ledger_row(tmp_path, monkeypatch):
    monkeypatch.setattr(fun_ledger, "PATH", tmp_path / "fun.csv")
    import betlab.sources.nflverse as nv
    monkeypatch.setattr(nv, "load_games", lambda: pd.DataFrame(columns=["game_id", "home_team", "away_team", "date"]))
    monkeypatch.setattr(nv, "team_abbr_by_name", lambda: {})
    q = {"sgp_id": "s1", "price": 500, "fair_price": 450, "legs": ["Matthew Stafford 225+ passing yds"], "quoted_at": "2026-10-13T12:00:00Z"}
    fun_ledger.sync([q, q | {"sgp_id": "s1~dk", "price": 520, "book": "DraftKings", "legs": ["Matthew Stafford 230+ passing yds"]}], [])
    df = fun_ledger.load().set_index("sgp_id")
    assert df.loc["s1", "book"] == "fanduel" and df.loc["s1~dk", "book"] == "draftkings"
    assert "230+" in df.loc["s1~dk", "legs"]                                        # graded as DraftKings' own rung


def test_draftkings_voids_a_soccer_slip_when_a_game_leg_pushes_fanduel_reprices():
    base = {"sport": "soccer", "price": 400, "stake": None, "marked": False, "leg_p": '[0.5, 0.6, 0.7]'}
    res = lambda: [{"leg": "Arsenal to win", "result": "won"}, {"leg": "Over 2.0 goals", "result": "push"},
                   {"leg": "Bukayo Saka 2+ shots", "result": "won"}]
    df = pd.DataFrame([base | {"book": "fanduel"}, base | {"book": "draftkings"}])
    for i in df.index:
        fun_ledger._finish(df, i, df.loc[i], res(), "now")
    assert df.loc[0, "status"] == "won" and df.loc[1, "status"] == "void"
    df = pd.DataFrame([base | {"book": "draftkings"}])                 # a player who didn't play: dropped, as at FanDuel
    fun_ledger._finish(df, 0, df.loc[0], [{"leg": "Arsenal to win", "result": "won"}, {"leg": "Over 2.5 goals", "result": "won"},
                                          {"leg": "Bukayo Saka 2+ shots", "result": "void"}], "now")
    assert df.loc[0, "status"] == "won"
