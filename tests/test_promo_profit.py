"""A settled bet's profit, as the apps count it (tests/fixtures/promo_profit.json: web lib/bets.ts profit and iPhone
BetMath.profit read the same cases)."""

import json
from pathlib import Path

import pytest

from betlab import fun_ledger as FL

FIX = json.loads((Path(__file__).parent / "fixtures" / "promo_profit.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", FIX["cases"], ids=lambda c: c["name"])
def test_marked_profit_matches_the_apps(case):
    b = case["bet"]
    row = {"marked": True, "stake": b["stake"], "bonus": b.get("bonus", False), "cashout": b.get("cashout"),
           "boost": b.get("boost"), "boost_cap": b.get("boost_cap"), "protect": b.get("protect", False)}
    assert FL.marked_profit(b["profit_1u"], row, b["ticket_status"]) == pytest.approx(case["profit"])
