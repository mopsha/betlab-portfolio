"""The fun-parlay stack: name matching, the joint game simulator, market anchoring, parlay search."""

import numpy as np
import pandas as pd
import pytest

from betlab import players
from betlab import props_market as PM
from betlab import sgp
from betlab.models import game_sim_nfl as G
from betlab.models import props_nfl as P

# Two teams, six past games each. Per game: (position, targets, carries, receptions, rec yds, rush yds, TDs)
ROLES = {
    "QB": ("QB", 0, 3, 0, 0, 15, 0),
    "WR1": ("WR", 9, 0, 6, 80, 0, 1),
    "WR2": ("WR", 6, 0, 4, 45, 0, 0),
    "TE": ("TE", 5, 0, 4, 40, 0, 0),
    "RB": ("RB", 3, 18, 2, 15, 75, 1),
}


def history() -> pd.DataFrame:
    rows, games = [], []
    for g in range(6):
        gid = f"2025_{g:02d}_AAA_BBB"
        games.append({"game_id": gid, "date": pd.Timestamp("2025-09-07") + pd.Timedelta(weeks=g),
                      "home_team": "BBB", "away_team": "AAA", "spread_line": 3.0, "total_line": 45.0})
        for team in ("AAA", "BBB"):
            for role, (pos, tg, ca, rec, ry, rush, td) in ROLES.items():
                rows.append({"player_id": f"{team}-{role}", "position": pos, "game_id": gid, "team": team,
                             "targets": tg, "carries": ca, "attempts": 34 if pos == "QB" else 0,
                             "receptions": rec, "receiving_yards": ry, "rushing_yards": rush,
                             "passing_yards": 250 if pos == "QB" else 0, "passing_tds": 2 if pos == "QB" else 0,
                             "rushing_tds": td if pos == "RB" else 0, "receiving_tds": td if pos == "WR" else 0})
    hist = P.prepare(pd.DataFrame(rows), pd.DataFrame(games))
    return hist


def rosters() -> dict[str, pd.DataFrame]:
    return {team: pd.DataFrame([{"gsis_id": f"{team}-{r}", "full_name": f"{team} {r}", "position": ROLES[r][0]}
                                for r in ROLES]) for team in ("AAA", "BBB")}


FEATURED = {f"{t}-{r}" for t in ("AAA", "BBB") for r in ROLES}


def simulate(**kw):
    return G.simulate_game(history(), "BBB", "AAA", 3.0, 45.0, rosters(), FEATURED, n=8000, seed=3, **kw)


# ---------------------------------------------------------------- names

def test_normalize_handles_suffixes_initials_and_accents():
    assert players.normalize("Michael Penix Jr.") == "michael penix"
    assert players.normalize("A.J. Brown") == players.normalize("AJ Brown")
    assert players.normalize("Amon-Ra St. Brown") == "amon ra st brown"


def test_match_within_roster_and_refuses_ambiguity():
    roster = pd.DataFrame([
        {"gsis_id": "1", "full_name": "Michael Penix Jr.", "football_name": "Michael"},
        {"gsis_id": "2", "full_name": "Josh Allen", "football_name": "Josh"},
        {"gsis_id": "3", "full_name": "Josh Allen", "football_name": "Josh"},
    ])
    found, missing = players.match(["Michael Penix", "Josh Allen", "Nobody Here"], roster)
    assert found == {"Michael Penix": "1"}
    assert set(missing) == {"Josh Allen", "Nobody Here"}


# ---------------------------------------------------------------- simulator

def test_simulator_draws_are_sane_and_teams_are_linked():
    sim = simulate()
    for team in ("AAA", "BBB"):
        qb = sim.get(f"{team}-QB", "passing_yards")
        wr1 = sim.get(f"{team}-WR1", "receiving_yards")
        wr2 = sim.get(f"{team}-WR2", "receiving_yards")
        assert qb is not None and (qb >= 0).all()
        assert (sim.get(f"{team}-WR1", "receptions") >= 0).all()
        assert (sim.get(f"{team}-WR1", "tds") >= 0).all()
        # A QB's yards are his receivers' yards, so they move together; teammates compete for targets.
        assert np.corrcoef(qb, wr1)[0, 1] > 0.3
        assert abs(np.corrcoef(wr1, wr2)[0, 1]) < 0.25
    # Passing yards on the two sides are close to independent.
    assert abs(np.corrcoef(sim.get("AAA-QB", "passing_yards"), sim.get("BBB-QB", "passing_yards"))[0, 1]) < 0.15


def test_ruled_out_player_disappears_and_teammates_get_his_targets():
    base = simulate()
    without = simulate(out=frozenset({"AAA-WR1"}))
    assert without.get("AAA-WR1", "receptions") is None
    assert without.get("AAA-WR2", "receptions").mean() > base.get("AAA-WR2", "receptions").mean() * 1.15


def test_adjust_moves_usage():
    base = simulate()
    more = simulate(adjust={("t", "AAA-TE"): 1.8, ("vol", "AAA"): 1.2})
    assert more.get("AAA-TE", "receptions").mean() > base.get("AAA-TE", "receptions").mean() * 1.4


# ---------------------------------------------------------------- market anchoring

def test_rake_matches_every_target():
    rng = np.random.default_rng(0)
    x, y = rng.normal(size=20000), rng.normal(size=20000)
    y = 0.6 * x + 0.8 * y
    w, err = PM.rake([x > 0, y > 0.5], [0.55, 0.35], 20000)
    assert err < 1e-3
    assert w[x > 0].sum() == pytest.approx(0.55, abs=1e-3)
    assert w[y > 0.5].sum() == pytest.approx(0.35, abs=1e-3)
    assert PM.effective_draws(w) > 15000  # a gentle reweighting


def test_poisson_mean_for_inverts_the_tail():
    lam = PM.poisson_mean_for(0.5, 4.5)
    k = np.arange(5)
    from math import factorial
    p_le4 = sum(np.exp(-lam) * lam ** i / factorial(i) for i in k)
    assert 1 - p_le4 == pytest.approx(0.5, abs=1e-6)


def test_translate_uses_the_shape_between_lines():
    d = np.arange(100.0)                     # uniform 0..99
    assert PM.translate(0.5, 49.5, 59.5, d) == pytest.approx(0.4)


def snap_rows(book, market, player, rows):
    return [{"bookmaker": book, "market": market, "player": player, "outcome": o, "point": pt, "price": pr}
            for o, pt, pr in rows]


def test_reference_prefers_the_sharp_book_and_devigs():
    snap = pd.DataFrame(
        snap_rows("pinnacle", "player_reception_yds", "A", [("Over", 50.5, -110), ("Under", 50.5, -110)])
        + snap_rows("draftkings", "player_reception_yds", "A", [("Over", 52.5, -120), ("Under", 52.5, -100)])
        + snap_rows("draftkings", "player_reception_yds", "B", [("Over", 30.5, -115), ("Under", 30.5, -105)])
        + snap_rows("betmgm", "player_reception_yds", "B", [("Over", 30.5, -110), ("Under", 30.5, -110)])
        + snap_rows("caesars", "player_reception_yds", "B", [("Over", 30.5, -105), ("Under", 30.5, -115)]))
    ref = PM.reference_quotes(snap, ["pinnacle"])
    a = ref[ref["player"] == "A"]
    assert list(a["book"]) == ["pinnacle"] and a["p_over"].iloc[0] == pytest.approx(0.5)
    b = ref[ref["player"] == "B"]
    # neither of Mike's books is the other's market (docs/DRAFTKINGS_PLAN.md rule 7)
    assert set(b["book"]) == {"caesars", "betmgm"} and b["source"].iloc[0] == "consensus of 2 books"
    assert set(PM.reference_quotes(snap, ["pinnacle"], target="draftkings").query("player == 'B'")["book"]) == {"caesars", "betmgm"}


def test_ladders_drop_price_floors_and_skipped_books():
    snap = pd.DataFrame(
        snap_rows("betmgm", "player_reception_yds_alternate", "A",
                  [("Over", 49.5, 150), ("Over", 99.5, 2000), ("Over", 124.5, 2000)])
        + snap_rows("betonlineag", "player_reception_yds_alternate", "A", [("Over", 49.5, 120)]))
    lad = PM.ladder_quotes(snap)
    assert list(lad["point"]) == [49.5, 99.5]            # 124.5 repeats the floor price
    assert "betonlineag" not in set(lad["book"])


# ---------------------------------------------------------------- parlay search

def toy_legs(n=20000, seed=1, cut=0.4, price=170):
    """Two correlated legs, one independent leg, all fairly priced by 'FanDuel'."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    a = z + 0.6 * rng.normal(size=n)
    b = z + 0.6 * rng.normal(size=n)
    c = rng.normal(size=n)
    w = np.full(n, 1 / n)

    def leg(name, hit, price, source="pinnacle"):
        lg = sgp.Leg(key=(name, "receiving_yards"), label=f"{name} over", player=name, team="AAA",
                     stat="receiving_yards", side="over", point=0.5, price=price, hit=hit, source=source)
        lg.p = lg.p_model = float(w[hit].sum())
        return lg

    return [leg("A", a > cut, price), leg("B", b > cut, price), leg("C", c > cut, price)], w


def test_search_prefers_correlated_legs_inside_the_band():
    legs, w = toy_legs()
    found = sgp.search(legs, w, band=(150, 1500), min_legs=2, max_legs=3, min_leg_p=0.12)
    assert found, "expected at least one parlay"
    assert sgp.search(legs, w, band=(150, 1500), min_legs=2, max_legs=3, min_leg_p=0.12, max_leg_p=0.30) == []
    top = found[0]
    names = {l.player for l in top["legs"]}
    assert {"A", "B"} <= names                      # the correlated pair is in every suggestion
    assert top["lift"] > 1.1
    assert 1 / (1 + 1500 / 100) <= top["p"] <= 1 / (1 + 150 / 100)


def test_implausible_legs_are_dropped():
    legs, w = toy_legs()
    legs[0].price = 900                             # we'd beat FanDuel by far too much: our mistake, not theirs
    assert not sgp.plausible(legs[0])
    assert sgp.plausible(legs[1])


def test_every_leg_must_be_likely_and_parlays_have_enough_legs():
    legs, w = toy_legs()                          # each leg about 34%: too unlikely
    assert sgp.search(legs, w, band=(100, 5000), min_legs=2, max_legs=3, min_leg_p=0.55) == []
    likely, w = toy_legs(cut=-0.5, price=-200)    # each leg about 69%
    found = sgp.search(likely, w, band=(100, 5000), min_legs=3, max_legs=3, min_leg_p=0.55)
    assert found and all(len(f["legs"]) == 3 for f in found)
    assert all(l.p >= 0.55 for f in found for l in f["legs"])


def test_to_doc_reports_fair_and_naive_prices():
    legs, w = toy_legs()
    doc = sgp.to_doc(sgp.search(legs, w, band=(150, 1500), min_legs=2, min_leg_p=0.12)[0], "event1")
    assert doc["fair_price"] > 0 and doc["naive_price"] > 0
    assert len(doc["sgp_id"]) == 12 and len(doc["legs"]) >= 2
    assert "Worth it only if FanDuel pays more than" in doc["why"]


def test_pick_skips_near_duplicates():
    legs, w = toy_legs()
    cands = sgp.search(legs, w, band=(150, 1500), min_legs=2, max_legs=3, min_leg_p=0.12)
    chosen = sgp.pick(cands, k=5, max_overlap=1)
    for i, a in enumerate(chosen):
        for b in chosen[i + 1:]:
            assert len({l.label for l in a["legs"]} & {l.label for l in b["legs"]}) <= 1


def test_over_shift_moves_overs_toward_the_under_only_where_configured():
    shifts = {"receptions": -0.18}
    assert PM.over_shift(0.5, "receptions", shifts) == pytest.approx(0.455, abs=0.001)
    assert PM.over_shift(0.5, "passing_yards", shifts) == 0.5


def test_unders_only_as_locks_and_at_most_one():
    rng = np.random.default_rng(4)
    n = 20000
    z = rng.normal(size=n)
    w = np.full(n, 1 / n)

    def leg(name, hit, side, price):
        lg = sgp.Leg(key=(name, "receptions"), label=f"{name} {side}", player=name, team="AAA", stat="receptions",
                     side=side, point=2.5, price=price, hit=hit, source="pinnacle")
        lg.p = lg.p_model = float(w[hit].sum())
        return lg

    legs = [leg("O1", z + rng.normal(size=n) > -0.4, "over", -150),
            leg("O2", z + rng.normal(size=n) > -0.4, "over", -150),
            leg("O3", z + rng.normal(size=n) > -0.4, "over", -150),
            leg("U60", z + rng.normal(size=n) < 0.35, "under", -130),     # ~60%: not a lock
            leg("U85", z + rng.normal(size=n) < 1.45, "under", -450),     # ~85%: a lock
            leg("U86", z + rng.normal(size=n) < 1.5, "under", -500)]
    found = sgp.search(legs, w, band=(100, 5000), min_legs=3, max_legs=4)
    assert found
    for f in found:
        unders = [l for l in f["legs"] if l.side == "under"]
        assert len(unders) <= 1 and all(l.p >= 0.75 for l in unders)
        assert "U60" not in {l.player for l in f["legs"]}


def test_long_shot_search_lands_in_its_band():
    legs, w = toy_legs(cut=1.0, price=400)      # each leg about 16%
    found = sgp.search(legs, w, band=(1500, 6000), min_legs=2, max_legs=3, min_leg_p=0.12)
    assert found and all(1 / (1 + 60) <= f["p"] <= 1 / (1 + 15) for f in found)


def test_one_leg_per_player():
    legs, w = toy_legs()
    twin = sgp.Leg(key=("A", "receptions"), label="A catches over", player="A", team="AAA", stat="receptions",
                   side="over", point=0.5, price=170, hit=legs[0].hit, source="pinnacle")
    twin.p = twin.p_model = legs[0].p
    found = sgp.search(legs + [twin], w, band=(150, 1500), min_legs=2, max_legs=3, min_leg_p=0.12)
    assert found and all(len({l.player for l in f["legs"]}) == len(f["legs"]) for f in found)



# ---------------------------------------------------------------- our game read (Mike, Sep 25)

def test_game_read_moves_pass_legs_tags_them_and_ranks_slips_that_fit_first():
    from betlab.cards import fun_nfl

    legs, w = toy_legs()
    legs[2].team = "BBB"                                   # C plays for the other team
    coef = {"stats": ["receiving_yards"], "matchup": 0.1, "volume": 1.0}
    reads = {"BBB": {"pass_edge": 2.0, "dropbacks_vs_usual": 0.1, "why": "BBB should throw a lot."},
             "AAA": {"pass_edge": -2.0, "dropbacks_vs_usual": -0.1, "why": "AAA's passing game is in trouble."}}
    fun_nfl.apply_reads(legs, reads, coef)
    a, _, c = legs
    assert c.p_read > c.p and c.read == "BBB should throw a lot."          # the read favors C's over
    assert a.p_read < a.p and a.read == ""                                  # and fades A's
    assert c.read_value > c.value > 0 and a.read_value < a.value           # ranking uses the read
    found = sgp.search(legs, w, band=(150, 2500), min_legs=2, max_legs=3, min_leg_p=0.12)
    with_c = [f for f in found if "C" in {l.player for l in f["legs"]}]
    assert with_c and [f["read_value"] for f in found] == sorted((f["read_value"] for f in found), reverse=True)
    doc = sgp.to_doc(with_c[0], "event1")
    assert doc["fits_read"] == 1 and doc["read_price"] is not None and doc["p_read"] != doc["p_fair"]
    assert doc["fair_price"] == sgp._american(with_c[0]["p"])              # fair odds stay on the market
    assert "fit how we read the game" in doc["why"]


def test_no_read_leaves_legs_and_prices_alone():
    from betlab.cards import fun_nfl

    legs, w = toy_legs()
    fun_nfl.apply_reads(legs, {})
    doc = sgp.to_doc(sgp.search(legs, w, band=(150, 1500), min_legs=2, min_leg_p=0.12)[0], "event1")
    assert doc["read_price"] is None and doc["fits_read"] == 0 and "read the game" not in doc["why"]


def test_game_line_legs_price_at_the_sharp_no_vig_and_move_with_the_score():
    from types import SimpleNamespace

    from betlab import odds_math as om
    from betlab import sgp as S

    rng = np.random.default_rng(1)
    n = 20000
    home_pts, away_pts = 24 + 9.5 * rng.standard_normal(n), 21 + 9.5 * rng.standard_normal(n)
    sim = SimpleNamespace(points={"BUF": home_pts, "LAC": away_pts})
    w = np.full(n, 1 / n)
    rows = []
    for bk, ml, sp, tot in (("fanduel", (-160, 134), -3.5, (-110, -110)), ("pinnacle", (-150, 135), -3.5, (-105, -115))):
        for outcome, price in (("Buffalo Bills", ml[0]), ("Los Angeles Chargers", ml[1])):
            rows.append({"bookmaker": bk, "market": "h2h", "outcome": outcome, "point": None, "price": price})
        for outcome, pt in (("Buffalo Bills", sp), ("Los Angeles Chargers", -sp)):
            rows.append({"bookmaker": bk, "market": "spreads", "outcome": outcome, "point": pt, "price": -110})
        for outcome, price in (("Over", tot[0]), ("Under", tot[1])):
            rows.append({"bookmaker": bk, "market": "totals", "outcome": outcome, "point": 45.5, "price": price})
    legs = {l.label: l for l in S.game_line_legs(pd.DataFrame(rows), sim, w, "Buffalo Bills", "Los Angeles Chargers",
                                                 "BUF", "LAC", ["pinnacle"])}
    assert set(legs) == {"Buffalo Bills ML", "Los Angeles Chargers ML", "Buffalo Bills -3.5",
                         "Los Angeles Chargers +3.5", "Over 45.5 total points", "Under 45.5 total points"}
    ml = legs["Buffalo Bills ML"]
    assert ml.source == "pinnacle" and abs(ml.p - om.devig([-150, 135])[0]) < 1e-9 and 0.55 < ml.p_model < 0.65
    assert abs(legs["Over 45.5 total points"].p - om.devig([-105, -115])[0]) < 1e-9
    assert ml.key == legs["Buffalo Bills -3.5"].key and ml.player == "game side"      # one side leg per slip
    both = (w * ml.hit * legs["Buffalo Bills -3.5"].hit).sum()
    assert both > ml.p_model * legs["Buffalo Bills -3.5"].p_model                      # win and cover move together


def test_build_legs_survives_a_rung_the_simulation_never_reaches():
    """A far alt rung with zero simulated chance crashed a whole game's build (Sep 26)."""
    from types import SimpleNamespace

    from betlab import sgp as S

    draws = np.full(100, 40.0)
    sim = SimpleNamespace(players=pd.DataFrame({"player_id": ["p1"], "team": ["BUF"]}),
                          get=lambda pid, stat: draws if (pid, stat) == ("p1", "receiving_yards") else None)
    fair = pd.DataFrame([{"player": "A B", "stat": "receiving_yards", "point": 39.5, "p_over": 0.5, "source": "pinnacle", "kind": "main"},
                         {"player": "A B", "stat": "receiving_yards", "point": 99.5, "p_over": 0.02, "source": "draftkings", "kind": "rung"}])
    snap = pd.DataFrame([{"bookmaker": "fanduel", "market": "player_reception_yds", "player": "A B", "outcome": "Over", "point": 39.5, "price": -110},
                         {"bookmaker": "fanduel", "market": "player_reception_yds_alternate", "player": "A B", "outcome": "Over", "point": 99.5, "price": 1500}])
    legs = {l.point: l for l in S.build_legs(snap, sim, {"A B": "p1"}, np.full(100, 0.01), fair)}
    assert legs[99.5].p_model == 0 and abs(legs[39.5].p_model - 1.0) < 1e-9


def test_a_game_the_raking_skips_keeps_its_td_scorers_at_the_market_chance():
    from types import SimpleNamespace

    from betlab.cards import fun_nfl

    scored = np.array([1] * 30 + [0] * 70)
    sim = SimpleNamespace(n=100, players=pd.DataFrame({"player_id": ["p1", "p2"], "team": ["TB", "TB"]}),
                          get=lambda pid, stat: scored if stat == "tds" else None)
    fair = pd.DataFrame([{"player": "A B", "stat": "tds", "point": 0.5, "p_over": 0.42, "source": "pinnacle", "kind": "main"}])
    snap = pd.DataFrame([{"bookmaker": "fanduel", "market": "player_anytime_td", "player": n, "outcome": "Yes", "point": None, "price": 130}
                         for n in ("A B", "C D")])
    legs = fun_nfl.market_td_legs(snap, sim, {"A B": "p1", "C D": "p2"}, fair)
    assert [(l.player, l.p) for l in legs] == [("A B", 0.42)] and legs[0].p_model == pytest.approx(0.3)   # C D: no market price


def test_games_whose_simulation_cannot_match_the_market_get_no_parlays():
    from betlab.cards import fun_nfl

    even = np.full(20000, 1 / 20000)
    assert fun_nfl.anchor_problem(even, 0.001) is None
    few = np.zeros(20000); few[:33] = 1 / 33                      # Panthers @ Browns, Sep 27
    assert "33 effective draws" in fun_nfl.anchor_problem(few, 0.216)
    assert fun_nfl.anchor_problem(even, 0.05) is not None         # a price missed by 5 points


def test_pick_leaves_out_paused_themes():
    """Mike, 2026-10-09: 'Win it with them' (a team's win plus its players' overs) is paused."""
    hit = np.array([True, False])

    def leg(label, stat, side="over", player=None):
        lg = sgp.Leg(key=(label, stat), label=label, player=player or label, team="AAA", stat=stat, side=side,
                     point=0.5, price=-110, hit=hit, source="pinnacle")
        lg.p = 0.6
        return lg

    win_with = {"legs": [leg("AAA ML", "moneyline", "yes", ""), leg("A 60+ rushing yds", "rushing_yards")]}
    stack = {"legs": [leg("Q 225+ passing yds", "passing_yards"), leg("R 50+ receiving yds", "receiving_yards")]}
    assert sgp.theme(win_with["legs"], {}) == "Win it with them"
    assert sgp.pick([win_with, stack], k=5, paused={"Win it with them"}) == [stack]
    assert sgp.pick([win_with, stack], k=5, paused=set()) == [win_with, stack]
    assert "Win it with them" in sgp.paused_themes()          # the setting is on


def test_pick_skips_slips_that_only_nudge_the_same_players_lines():
    """Oct 19 (MNF): four of five slips were Purdy / McCaffrey / Kittle / Daniels with the yardage moved
    (225+ vs 200+). Legs compare by player and stat, so a nudged rung is the same leg."""
    def leg(player, stat, point):
        return sgp.Leg(key=(player, stat), label=f"{player} {point}+ {stat}", player=player, team="T", stat=stat,
                       side="over", point=point, price=-150, hit=np.ones(4, dtype=bool))

    def slip(*legs):
        return {"legs": list(legs)}

    base = [("Purdy", "passing_yards"), ("CMC", "receiving_yards"), ("Kittle", "receiving_yards"), ("Daniels", "passing_yards")]
    nudged = [slip(*(leg(p, s, pt + d) for (p, s), pt in zip(base, (225, 30, 50, 175)))) for d in (0, -25, 10, -5)]
    other = slip(leg("Purdy", "passing_yards", 225), leg("CMC", "receiving_yards", 30),
                 leg("Kittle", "receptions", 5), leg("White", "rushing_yards", 40))
    fresh = slip(leg("McLaurin", "receiving_yards", 50), leg("Daniels", "rushing_yards", 30),
                 leg("Jennings", "receiving_yards", 40), leg("Ekeler", "receptions", 3))
    chosen = sgp.pick(nudged + [other, fresh], k=5, paused=set())
    assert [len({l.player for l in c["legs"]}) for c in chosen] == [4, 4, 4]
    assert chosen[0] is nudged[0] and chosen[1] is other and chosen[2] is fresh


def test_story_slips_are_not_limited_by_the_value_slips():
    """Oct 19 - Nov 9: story slips were picked as more of the value slips' list, whose five slips had used up each
    player's limit, so no story slip was made. Only a story slip repeating a value slip (3+ shared legs) is left out."""
    def leg(player, stat):
        return sgp.Leg(key=(player, stat), label=f"{player} {stat}", player=player, team="T", stat=stat,
                       side="over", point=1, price=-150, hit=np.ones(4, dtype=bool))

    def slip(*pairs):
        return {"legs": [leg(p, s) for p, s in pairs]}

    value = [slip(("QB", "passing_yards"), ("WR", s), ("RB", t)) for s, t in
             (("receiving_yards", "rushing_yards"), ("receptions", "receptions"), ("tds", "tds"))]
    repeat = slip(("QB", "passing_yards"), ("WR", "receiving_yards"), ("RB", "rushing_yards"), ("TE", "receptions"))
    story = [slip(("QB", "passing_tds"), ("WR", "longest_reception"), ("TE", "receiving_yards")),
             slip(("QB", "rushing_yards"), ("RB", "receiving_yards"), ("TE", "tds"))]
    assert sgp.pick(value + [repeat] + story, k=5, paused=set())[3:] == []       # the old way: QB, WR and RB used up
    assert sgp.pick_story(value, [repeat] + story, 2, paused=set()) == story
