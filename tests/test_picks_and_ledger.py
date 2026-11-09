import pandas as pd
import pytest

from betlab import ledger, picks


def offer(event, market, side, ev, p_model, p_market, price=-110, kind="game_line"):
    return {"league": "nfl", "event_id": event, "market": market, "side": side, "player": None,
            "ev": ev, "p_model": p_model, "p_market": p_market, "price": price, "kind": kind,
            "label": side, "p_final": p_market, "p_push": 0.0}


def test_classify_rules():
    df = pd.DataFrame([
        offer("g1", "spreads", "BUF", 0.05, 0.56, 0.54),   # pick
        offer("g1", "h2h", "BUF", 0.04, 0.60, 0.58),       # same side group as the spread -> lean
        offer("g1", "totals", "Over", 0.035, 0.55, 0.54),  # separate group -> pick
        offer("g2", "spreads", "KC", 0.015, 0.53, 0.52),   # lean
        offer("g3", "spreads", "MIA", 0.02, 0.70, 0.52),   # 18 points apart: no pick, but under the flag bar
        offer("g5", "spreads", "DEN", 0.02, 0.78, 0.52),   # 26 points apart -> check_news
        offer("g3", "spreads", "NYJ", -0.2, 0.30, 0.48),   # the other side of that gap -> hidden
        offer("g4", "h2h", "LV", 0.08, 0.30, 0.25, price=320),  # long dog -> not even a lean
        offer("g6", "h2h", "KC", 0.08, 0.80, 0.78, price=-320),  # big favorite -> a lean, never a pick
        offer("g7", "h2h", "SEA", 0.08, 0.30, 0.28, price=250),  # at the limit -> still a pick
    ])
    tiers = dict(zip(df["event_id"] + ":" + df["market"] + ":" + df["side"], picks.classify(df)["tier"]))
    assert tiers["g1:spreads:BUF"] == "pick"
    assert tiers["g1:h2h:BUF"] == "lean"
    assert tiers["g1:totals:Over"] == "pick"
    assert tiers["g2:spreads:KC"] == "lean"
    assert tiers["g3:spreads:MIA"] == ""
    assert tiers["g5:spreads:DEN"] == "check_news"
    assert tiers["g3:spreads:NYJ"] == ""
    assert tiers["g4:h2h:LV"] == ""
    assert tiers["g6:h2h:KC"] == "lean"
    assert tiers["g7:h2h:SEA"] == "pick"


def test_prop_unders_need_ten_percent():
    def prop(player, side, ev):
        return offer("g9", "player_receptions", side, ev, 0.5, 0.5, kind="prop") | {"player": player}
    df = pd.DataFrame([prop("A", "Under", 0.139), prop("B", "Under", 0.069), prop("C", "Over", 0.06)])
    tiers = dict(zip(df["player"], picks.classify(df)["tier"]))
    assert tiers == {"A": "pick", "B": "lean", "C": "pick"}


def test_ledger_never_duplicates_or_reprices(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    first = pd.DataFrame([offer("g1", "spreads", "BUF", 0.05, 0.56, 0.54, price=-105)])
    assert len(ledger.add_picks(first, "2026-09-24T12:00:00+00:00")) == 1
    later = pd.DataFrame([offer("g1", "spreads", "BUF", 0.03, 0.55, 0.54, price=-115)])
    assert len(ledger.add_picks(later, "2026-09-25T12:00:00+00:00")) == 0
    saved = ledger.load()
    assert len(saved) == 1 and saved["price"].iloc[0] == -105  # first price stands
    assert saved["status"].iloc[0] == "open"


def test_ledger_text_columns_accept_strings_when_empty(tmp_path, monkeypatch):
    """Regression (Sep 25): an all-empty graded_at column came back as float64 and grading crashed."""
    import pandas as pd

    from betlab import ledger

    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "picks.csv")
    ledger.save(pd.DataFrame([{c: None for c in ledger.COLUMNS} | {"pick_id": "p1", "status": "open", "price": -110}]))
    df = ledger.load()
    df.at[0, "graded_at"] = "2026-09-25T13:57:12+00:00"
    df.at[0, "status"] = "won"
    df.at[0, "clv"] = 0.02
    assert df.at[0, "graded_at"].startswith("2026") and float(df.at[0, "price"]) == -110


def test_picks_only_within_36_hours():
    asof = pd.Timestamp("2026-09-30T14:00:00Z")
    near = offer("g1", "spreads", "BUF", 0.05, 0.54, 0.54) | {"commence_time": "2026-10-01T20:00:00Z"}   # 30 h
    far = offer("g2", "spreads", "KC", 0.05, 0.54, 0.54) | {"commence_time": "2026-10-04T17:00:00Z"}    # 99 h
    tiers = list(picks.classify(pd.DataFrame([near, far]), asof)["tier"])
    assert tiers == ["pick", "lean"]
