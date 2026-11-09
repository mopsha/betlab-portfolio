

def test_placeholder_prices_are_skipped_not_fatal():
    """Oct 23: Novig's NBA props carried -99900 placeholders; one raised in the de-vig and took down the NBA card."""
    import pandas as pd
    from betlab import props_market as PM

    rows = pd.DataFrame([{"bookmaker": "novig", "point": 1.5, "outcome": "Over", "price": 400.0},
                         {"bookmaker": "novig", "point": 1.5, "outcome": "Under", "price": -99900.0},
                         {"bookmaker": "pinnacle", "point": 1.5, "outcome": "Over", "price": -110.0},
                         {"bookmaker": "pinnacle", "point": 1.5, "outcome": "Under", "price": -110.0}])
    out = PM._two_way(rows, "Over", "Under")
    assert [b for b, _, _ in out] == ["pinnacle"] and abs(out[0][2] - 0.5) < 1e-9
