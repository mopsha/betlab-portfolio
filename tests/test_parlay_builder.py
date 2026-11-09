"""The page's parlay builder: leg packs, their split into documents, and the grade's ledger side."""

import base64
import json

import numpy as np
import pandas as pd
import pytest

from betlab import fun_ledger, sgp
from betlab.cli import pack_docs


def legs_and_weights(n=4000):
    rng = np.random.default_rng(0)
    x = rng.standard_normal(n)
    y = 0.6 * x + 0.8 * rng.standard_normal(n)
    mk = lambda label, hit, p, player="P1", side="over": sgp.Leg(key=(player, label), label=label, player=player, team="AAA",
                                                                  stat="receiving_yards", side=side, point=0.5, price=-110,
                                                                  hit=hit, p=p, p_model=float(hit.mean()), source="pinnacle")
    legs = [mk("A over", x > 0, 0.5), mk("A under", ~(x > 0), 0.5, side="under"), mk("B 1+", y > -0.5, 0.65, "P2"),
            mk("never", x > 99, 0.01, "P3")]
    return legs, np.full(n, 1 / n)


def test_pack_bitsets_rebuild_the_joint_and_unders_point_at_their_over():
    legs, w = legs_and_weights()
    pack = sgp.leg_pack(legs, w, n=2000, seed=1)
    by = {l["label"]: l for l in pack["legs"]}
    assert "never" not in by                                          # under 2%: left out
    assert by["A under"]["not"] == "A over" and "bits" not in by["A under"]
    bits = lambda lb: np.unpackbits(np.frombuffer(base64.b64decode(by[lb]["bits"]), np.uint8))[:2000].astype(bool)
    assert bits("A over").mean() == pytest.approx(by["A over"]["p_pack"], abs=1e-4)
    joint = (bits("A over") & bits("B 1+")).mean()
    assert joint / (by["A over"]["p_pack"] * by["B 1+"]["p_pack"]) > 1.1    # the correlation survives the resample


def test_big_packs_split_into_documents_under_the_limit():
    pack = {"event_id": "e1", "draws": 3000, "legs": [{"label": f"L{i}", "bits": "x" * 500} for i in range(900)]}
    docs = pack_docs(pack, limit=200_000)
    assert [k for k, _ in docs][:2] == ["e1", "e1-2"] and all(d["parts"] == len(docs) for _, d in docs)
    assert all(len(json.dumps(d)) < 256_000 for _, d in docs)
    assert sum(len(d["legs"]) for _, d in docs) == 900


def quotes_frame():
    rows = []
    for i in range(12):                                   # small parlays: FanDuel pays ~78% of fair
        rows.append({"sgp_id": f"s{i}", "book": "fanduel", "fair_price": 200, "price": 134})
    for i in range(12):                                   # long shots: FanDuel pays more than fair
        rows.append({"sgp_id": f"l{i}", "book": "fanduel", "fair_price": 2000, "price": 2200})
    rows.append({"sgp_id": "over-x", "book": "fanduel", "fair_price": 200, "price": 1000})   # a straight: not a parlay
    return pd.DataFrame(rows)


def test_typical_payout_is_by_parlay_size():
    t = fun_ledger.typical_ratio(quotes_frame())
    b = {x["max_fair"]: x for x in t["bands"]}
    assert b[300]["ratio"] == pytest.approx(2.34 / 3.0, abs=0.01) and b[300]["from_quotes"]
    assert b[None]["ratio"] > 1.0                          # FanDuel's long-shot generosity stays in its own band
    assert b[700]["ratio"] == 0.79 and not b[700]["from_quotes"]    # too few quotes: the prior
    assert t["quotes"] == 24


def test_custom_parlays_record_by_grade():
    df = pd.DataFrame([{**{c: None for c in fun_ledger.COLUMNS}, "sgp_id": f"custom-{i}", "status": s, "grade": g,
                        "p_fair": p, "profit_1u": u}
                       for i, (s, g, p, u) in enumerate([("won", "B+", 0.4, 1.2), ("lost", "B", 0.35, -1.0),
                                                         ("lost", "C", 0.1, -1.0), ("open", "A", 0.3, None)])])
    c = fun_ledger.custom_summary(df)
    assert c["slips"] == 4 and c["graded"] == 3 and c["won"] == 1
    assert {g["grade"]: g["graded"] for g in c["by_grade"]} == {"B": 2, "C": 1}     # B+ and B count as B
