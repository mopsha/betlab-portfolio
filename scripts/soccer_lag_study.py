"""Does FanDuel lag the sharp market in soccer? (to-do c-soccer-lag; first look 2026-10-09)

Free: reads only the saved odds snapshots (data/odds/soccer_*) and the line tracker
(data/ledger/soccer_lines.csv, graded against football-data.co.uk's Betfair close).

    python scripts/soccer_lag_study.py

1. How often FanDuel's 3-way price is +EV against Pinnacle's no-vig chance, and on which outcomes.
2. Matches with an early pull and one within 3 hours of kickoff: of each early FanDuel-Pinnacle gap,
   how much did FanDuel close, and how much did Pinnacle (a lagging FanDuel closes most of it).
3. Graded lines: CLV of FanDuel's first price against the Betfair close, by EV at the first pull.
   A slope of CLV on EV near 1 means the sharp price was right and FanDuel stale; near 0, noise.
   3-way sides only, and nothing first seen Oct 12 - Oct 13 4 PM ET (fd_price then held DraftKings' price where it
   was better, and goals/BTTS rows leaked in).
4. The direct test (Oct 19): every early FanDuel price (3h+ out) at +EV against Pinnacle, graded against Pinnacle's
   last no-vig before kickoff (a pull within 2 h). A FanDuel lag shows as positive CLV and FanDuel doing the moving.

Oct 19 result: no lag. Early gaps closed from both sides (FanDuel 51%, Pinnacle 46%); 31 early +EV prices averaged
-3.7% CLV against Pinnacle's close (beat 29%). See docs/DECISIONS.md (2026-10-19).
"""

from __future__ import annotations

import glob

import numpy as np
import pandas as pd

from betlab import odds_math as om
from betlab import tracking_soccer


def snapshot_rows() -> pd.DataFrame:
    """One row per (snapshot, match, outcome) with FanDuel's and Pinnacle's 3-way price and no-vig chance."""
    d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob("data/odds/soccer_*/*/*.parquet"))], ignore_index=True)
    d = d[(d.market == "h2h") & d.bookmaker.isin(["fanduel", "pinnacle"])].copy()
    d["ts"], d["ko"] = pd.to_datetime(d.snapshot_ts, utc=True), pd.to_datetime(d.commence_time, utc=True)
    d = d[d.ts < d.ko]
    d["imp"] = 1 / d.price.apply(om.american_to_decimal)
    key = ["snapshot_ts", "event_id", "bookmaker"]
    d = d[d.groupby(key).outcome.transform("size") == 3]
    d["nv"] = d.imp / d.groupby(key).imp.transform("sum")
    d["hold"] = d.groupby(key).imp.transform("sum") - 1
    w = d.pivot_table(index=["sport_key", "event_id", "snapshot_ts", "ts", "ko", "outcome"], columns="bookmaker",
                      values=["price", "nv", "hold"], aggfunc="first").dropna()
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.reset_index()
    w["ev"] = [om.expected_value(p, pr) for p, pr in zip(w.nv_pinnacle, w.price_fanduel)]
    return w


def main() -> None:
    pd.set_option("display.width", 200)
    w = snapshot_rows()
    m = w.drop_duplicates(["event_id", "snapshot_ts"])
    print(f"1) {len(w)} priced FanDuel outcomes in {w.event_id.nunique()} matches; 3-way hold: FanDuel "
          f"{100 * m.hold_fanduel.median():.1f}%, Pinnacle {100 * m.hold_pinnacle.median():.1f}% (medians)")
    for t in (0, 0.02, 0.03):
        s = w[w.ev > t]
        print(f"   EV > {t:.0%}: {len(s)} outcomes ({100 * len(s) / len(w):.1f}%) in {s.event_id.nunique()} matches")
    fav = w.groupby(["event_id", "snapshot_ts"]).nv_pinnacle.transform(
        lambda v: v.where(w.loc[v.index, "outcome"] != "Draw").max())
    w["role"] = np.where(w.outcome == "Draw", "draw", np.where(w.nv_pinnacle == fav, "favorite", "underdog"))
    print(w.groupby("role").ev.agg(["count", "mean", "max"]).round(4).to_string())

    g = w.sort_values("ts").groupby(["event_id", "outcome"])
    pair = g.first().join(g.last(), rsuffix="_L")
    pair = pair[(pair.ts_L > pair.ts) & ((pair.ko - pair.ts_L).dt.total_seconds() <= 3 * 3600)]
    print(f"\n2) matches with an early pull and one within 3 h of kickoff: {pair.reset_index().event_id.nunique()}")
    if len(pair) >= 6:
        gap = pair.nv_pinnacle - pair.nv_fanduel
        print(f"   of each early gap, FanDuel closed {100 * np.polyfit(gap, pair.nv_fanduel_L - pair.nv_fanduel, 1)[0]:.0f}%"
              f" and Pinnacle {100 * np.polyfit(gap, pair.nv_pinnacle - pair.nv_pinnacle_L, 1)[0]:.0f}%")

    t = tracking_soccer.load()
    t = t[(t.status == "graded") & t.p_close.notna() & ~t.side.isin(["Yes", "No", "Over", "Under"])].copy()
    seen = pd.to_datetime(t.first_seen, utc=True, format="ISO8601")
    t = t[~((seen >= pd.Timestamp("2026-10-12 04:00Z")) & (seen < pd.Timestamp("2026-10-13 20:00Z")))]
    if t.empty:
        return
    t["clv"] = [om.clv(float(p), float(c)) for p, c in zip(t.first_price, t.p_close)]
    t["ev0"] = [om.expected_value(float(q), float(p)) for q, p in zip(t.first_p_market, t.first_price)]
    print(f"\n3) graded lines {len(t)} ({t.event_id.nunique()} matches; {sorted(t.league.unique())}): "
          f"avg CLV {t.clv.mean():.4f}, slope of CLV on EV {np.polyfit(t.ev0, t.clv, 1)[0]:.2f}")
    print(t.groupby(pd.cut(t.ev0, [-1, -0.08, -0.05, -0.02, 0, 0.03, 1]), observed=True)
          .agg(n=("clv", "size"), ev=("ev0", "mean"), clv=("clv", "mean")).round(4).to_string())

    w["mins"] = (w.ko - w.ts).dt.total_seconds() / 60
    last = w.sort_values("ts").groupby(["event_id", "outcome"]).last()
    early = w[w.mins >= 180].sort_values("ts").groupby(["event_id", "outcome"]).first()
    j = early.join(last[["nv_pinnacle", "nv_fanduel", "mins"]], rsuffix="_close")
    j = j[j.mins_close <= 120]
    print(f"\n4) early pulls (3h+ out) with a close within 2h: {len(j)} outcomes in {j.reset_index().event_id.nunique()} matches")
    for thr in (0.0, 0.02, 0.04):
        s = j[j.ev > thr]
        if len(s):
            clv = s.nv_pinnacle_close * s.price_fanduel.apply(om.american_to_decimal) - 1
            print(f"   early EV > {thr:.0%}: {len(s)} prices, EV {s.ev.mean():+.3f} -> CLV vs Pinnacle's close {clv.mean():+.3f} "
                  f"(beat {100 * (clv > 0).mean():.0f}%, SE {clv.std() / np.sqrt(len(s)):.3f}); FanDuel moved "
                  f"{(s.nv_fanduel_close - s.nv_fanduel).mean():+.3f}, Pinnacle {(s.nv_pinnacle - s.nv_pinnacle_close).mean():+.3f}")


if __name__ == "__main__":
    main()
