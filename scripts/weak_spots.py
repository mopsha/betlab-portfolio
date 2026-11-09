"""The weak-spot review, market by market (to-do c-checklist: Oct 17, then every Tuesday review).

Free: reads only the ledgers. Uses the scorecard's rules (golive.current_rule: the current props rule, picks inside
36 hours, nothing logged at or after its game's start) and only real closes (golive.real_closes: a close from the
bet's own pull is no close).

    python scripts/weak_spots.py [--since 2026-10-06]

Prints markdown tables to paste into a review:
1. Each market (picks and leans together, then picks alone): graded, record, units at 1u, bets with a real close,
   average CLV, share beating the close, and sure_positive (the chance true CLV is above zero, golive's prior).
2. The same split by book (FanDuel, DraftKings, Novig) and by when the bet was logged before the start.
3. The weakest spots: markets with 10+ real closes, ranked by sure_positive, lowest first.
"""

from __future__ import annotations

import argparse

import pandas as pd

from betlab import golive, ledger


def rows(since: str | None) -> pd.DataFrame:
    picks = golive.real_closes(golive.current_rule(ledger.load()))[0].assign(tier="pick")
    leans = golive.real_closes(golive.current_rule(ledger.load(ledger.LEANS), picks=False))[0].assign(tier="lean")
    df = pd.concat([picks, leans], ignore_index=True)
    df = df[df["status"].isin(["won", "lost", "push"])].copy()
    if since:
        start = pd.to_datetime(df["commence_time"], utc=True, format="ISO8601", errors="coerce")
        df = df[start >= pd.Timestamp(since, tz="America/New_York")]
    df["market_key"] = golive.market_key(df)
    df["book"] = df["book"].fillna("fanduel").str.lower().map({"fanduel": "FanDuel", "draftkings": "DraftKings", "novig": "Novig"})
    lead = (pd.to_datetime(df["commence_time"], utc=True, format="ISO8601", errors="coerce")
            - pd.to_datetime(df["created_at"], utc=True, format="ISO8601", errors="coerce")).dt.total_seconds() / 3600
    df["logged"] = pd.cut(lead, [0, 3, 12, 36, 1e5], labels=["<3h", "3-12h", "12-36h", "36h+"])
    df["clv_checked"] = golive.checked_clv(df)
    return df


def summary(g: pd.DataFrame) -> dict:
    clv = g["clv_checked"].dropna().astype(float)
    sp = golive.sure_positive(clv)
    return {"graded": len(g), "record": f"{(g.status == 'won').sum()}-{(g.status == 'lost').sum()}-{(g.status == 'push').sum()}",
            "units": round(float(g["profit_flat"].astype(float).sum()), 2), "real closes": len(clv),
            "avg CLV": f"{clv.mean():+.2%}" if len(clv) else "", "beat": f"{(clv > 0).mean():.0%}" if len(clv) else "",
            "sure_positive": round(sp, 2) if sp is not None else None}


def md(t: pd.DataFrame) -> str:
    """A markdown table without the optional tabulate package."""
    cells = [[str(c) for c in t.columns]] + [["" if pd.isna(v) else str(v) for v in r] for r in t.itertuples(index=False)]
    return "\n".join("| " + " | ".join(r) + " |" for r in cells[:1] + [["---"] * len(t.columns)] + cells[1:])


def table(df: pd.DataFrame, by: str | list[str]) -> str:
    out = pd.DataFrame([{**({by: k} if isinstance(by, str) else dict(zip(by, k))), **summary(g)}
                        for k, g in df.groupby(by, observed=True)])
    return md(out) if len(out) else "(none)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="only games starting on or after this ET date")
    args = ap.parse_args()
    df = rows(args.since)
    print(f"# Weak spots ({len(df)} graded picks and leans{' since ' + args.since if args.since else ''})\n")
    print("## By market, picks and leans\n\n" + table(df, "market_key") + "\n")
    print("## By market, picks only\n\n" + table(df[df.tier == "pick"], "market_key") + "\n")
    print("## By book\n\n" + table(df, "book") + "\n")
    print("## By when it was logged\n\n" + table(df, "logged") + "\n")
    print("## By market and when it was logged\n\n" + table(df, ["market_key", "logged"]) + "\n")
    ranked = pd.DataFrame([{"market": k, **summary(g)} for k, g in df.groupby("market_key")])
    ranked = ranked[ranked["real closes"] >= 10].sort_values("sure_positive")
    print("## Weakest first (10+ real closes)\n\n" + (md(ranked) if len(ranked) else "(none yet)"))


if __name__ == "__main__":
    main()
