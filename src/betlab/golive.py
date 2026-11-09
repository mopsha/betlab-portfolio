"""The go-live checklist, market by market (the page's Go-live section, exports/golive.json).

The rule for real money from Oct 18 (docs/ROADMAP.md): a market goes live only with
- at least 50 paper picks with measured closing-line value (CLV),
- average CLV of +1% or better, and
- beating the close at least 55% of the time,
plus calibration within 3 points where backtests exist and no open data or grading bugs
(those two are checked by hand at the Oct 17 review).

This reports each market's progress on the first three from the pick ledger, the same
numbers for leans (the same FanDuel-vs-sharp signal at smaller edges: supporting evidence,
not a substitute), and the research reads' tracked records (never picks).

Two readings to help decide, without changing the bar:
- **sure_positive:** the chance the market's true average CLV is above zero. It starts
  skeptical (true CLV edges are small: a normal prior centred on 0 with SD PRIOR_SD) and
  moves with the evidence as picks accumulate; the per-pick spread is never taken below
  CLV_SD_FLOOR. So two lucky picks read about 75%, not 99%.
- **pace:** picks with measured CLV per week over the last PACE_DAYS days, and the count
  that pace reaches by the review day.
And one line across every market ("all picks"): is FanDuel lagging the sharp books at all?

**Props are judged on raw CLV** (`clv_raw`: against the plain sharp close). Their fair
price is corrected for the market's lean toward overs (a 2025 finding), and the same
correction applied to the close hands every under about 4 points of CLV before the line
moves. The corrected CLV is still shown (`avg_clv_corrected`); whether the over lean
itself holds is a calibration question for the Oct 17 review (do the unders hit at the
corrected rate?), not a CLV one.

**Only the current props rule counts.** Until 2026-09-28 prop picks were priced against
the over-lean-corrected market; Mike retired that (props.shift_in_picks: false) after its
unders lost to the plain close by construction and hit 47.4% against a corrected 55.5%.
Rows priced that way (market_source "... corrected for the over lean"), picks logged
more than 36 hours before the start (the pick window since Sep 30), and any bet logged at or after its game's
earliest known start (Oct 13: possibly in-game prices), stay in the ledger
but are left out of the checklist, the Results tab's record and the page's pick list
(Mike, Sep 30: "only stuff under current rules"); `retired_excluded` says how many.

**Only real closes count** (Mike, Oct 13). Until Oct 13 the NHL and soccer prop closes (and soccer goals/BTTS)
could be the very pull a bet was logged from, which only repeats its own EV (32 of 52 graded NHL prop leans).
`real_closes` keeps such rows' results but blanks their CLV when no props pull of their market came after
`created_at` and before the start; `self_close_excluded` says how many per market. The European cups' 3-way
bets close from our own game-line pulls (cards/soccer.close_3way) and get the same check (Oct 15).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import norm

from betlab import config, ledger

MIN_PICKS = 50
MIN_AVG_CLV = 0.01
MIN_BEAT_CLOSE = 0.55
REVIEW_DAY = "2026-10-17"
MARKETS = ["NFL spreads", "NFL totals", "NFL moneyline", "NFL props",
           "NCAAF spreads", "NCAAF totals", "NCAAF moneyline"]  # always listed, even at 0 of 50
CLV_SD_FLOOR = 0.05   # per-pick CLV spread never assumed smaller than 5 points (props swing more)
PRIOR_SD = 0.02       # skeptical start: true average CLV within about +-2 points
PACE_DAYS = 14
RETIRED_SOURCE = "corrected for the over lean"   # the props rule retired 2026-09-28


def current_rule(df: pd.DataFrame, picks: bool = True) -> pd.DataFrame:
    """Drop rows priced by the retired over-lean-corrected props rule (module note) and, for
    picks, those logged more than picks.horizon_hours before the start (the pick window since
    2026-09-30; earlier edges are leans now)."""
    if not len(df):
        return df
    keep = pd.Series(True, index=df.index)
    if "market_source" in df:
        keep &= ~df["market_source"].astype(str).str.contains(RETIRED_SOURCE, regex=False)
    hours = config.settings()["picks"].get("horizon_hours")
    if picks and hours and {"created_at", "commence_time"} <= set(df.columns):
        lead = pd.to_datetime(df["commence_time"], utc=True, errors="coerce", format="ISO8601")             - pd.to_datetime(df["created_at"], utc=True, errors="coerce", format="ISO8601")
        keep &= ~(lead > pd.Timedelta(hours=hours))
    if {"created_at", "commence_time", "event_id"} <= set(df.columns):
        # never a bet logged at or after its game's scheduled start: the earliest start seen for the game (Oct 13:
        # the feed moved Monday night to 8:18 at 8:15 and three leans were logged at 8:15:31; three NHL leans came
        # 27-47 seconds after puck drop). They may carry in-game prices; the ledger keeps them, the record doesn't.
        start = pd.to_datetime(df["commence_time"], utc=True, errors="coerce", format="ISO8601")
        first = start.groupby(df["event_id"].astype(str)).transform("min")
        logged = pd.to_datetime(df["created_at"], utc=True, errors="coerce", format="ISO8601")
        keep &= ~(logged >= first)
    return df[keep]


def sure_positive(clv: pd.Series) -> float | None:
    """P(true average CLV > 0): a skeptical normal prior (mean 0, SD PRIOR_SD) updated with
    the picks' average CLV, per-pick spread floored at CLV_SD_FLOOR."""
    if len(clv) == 0:
        return None
    sd = max(float(clv.std(ddof=1)) if len(clv) >= 5 else 0.0, CLV_SD_FLOOR)
    precision = len(clv) / sd ** 2 + 1 / PRIOR_SD ** 2
    mean = (len(clv) / sd ** 2) * float(clv.mean()) / precision
    return float(norm.cdf(mean * np.sqrt(precision)))


def _real_close_index(sport_keys: set[str], days: set[str], kind: str = "props") -> dict:
    """{(sport key, event id, market): [pull times]} from the `kind` snapshots (props, or pick: the game-line
    pulls) of the given ET dates."""
    idx: dict = {}
    for key in sport_keys:
        for d in days:
            for f in (config.DATA_DIR / "odds" / key / d).glob(f"*_{kind}.parquet"):
                try:
                    snap = pd.read_parquet(f, columns=["event_id", "market", "snapshot_ts"])
                except Exception:  # noqa: BLE001 - an old file without these columns: no close from it
                    continue
                ts = pd.to_datetime(snap["snapshot_ts"], utc=True, format="ISO8601")
                for (eid, m), t in ts.groupby([snap["event_id"].astype(str), snap["market"]]).max().items():
                    idx.setdefault((key, eid, m), []).append(t)
    return idx


def real_closes(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """The rows with CLV blanked where the close was the bet's own pull (module note), and that mask. Only NHL
    and soccer props, soccer goals/BTTS and the cups' 3-way: NFL and NBA closes always needed a later pull
    (grading.prop_close), and the leagues' 3-way closes come from football-data.co.uk."""
    from betlab.cards.soccer import CUPS
    from betlab.pregame import GOALS_FEED, SOCCER

    none = pd.Series(False, index=df.index)
    if not len(df) or "clv" not in df or "created_at" not in df:
        return df, none
    league = df["league"].astype(str)
    goals = league.isin(SOCCER) & df["kind"].astype(str).eq("game_line") & df["market"].isin(GOALS_FEED)
    cup = league.isin(CUPS) & df["kind"].astype(str).eq("game_line") & df["market"].eq("h2h")
    todo = ((league.isin({*SOCCER, "nhl"}) & (df["kind"].astype(str).eq("prop") | goals) | cup)
            & (pd.to_numeric(df["clv"], errors="coerce").notna()
               | (pd.to_numeric(df["clv_raw"], errors="coerce").notna() if "clv_raw" in df else False)))
    if not todo.any():
        return df, none
    sub = df[todo]
    keys = {lg: config.settings()["leagues"][lg]["sport_key"] for lg in set(sub["league"])}
    start = pd.to_datetime(sub["commence_time"], utc=True, format="ISO8601", errors="coerce")
    days = {f"{(t - pd.Timedelta(days=d)).tz_convert('America/New_York'):%Y-%m-%d}" for t in start.dropna() for d in (0, 1)}
    idx = _real_close_index(set(keys.values()), days)
    if cup[todo].any():
        idx.update(_real_close_index({keys[lg] for lg in set(sub.loc[cup[todo], "league"])}, days, "pick"))
    logged = pd.to_datetime(sub["created_at"], utc=True, format="ISO8601", errors="coerce")
    bad = none.copy()
    for i, r in sub.iterrows():
        feed = GOALS_FEED.get(r["market"], r["market"]) if goals.at[i] else r["market"]
        times = idx.get((keys[r["league"]], str(r["event_id"]), feed), [])
        bad.at[i] = not any(logged.at[i] < t < start.at[i] for t in times)
    out = df.copy()
    for c in ("clv", "clv_raw"):
        if c in out:
            out[c] = out[c].where(~bad, np.nan)
    return out, bad


def checked_clv(df: pd.DataFrame) -> pd.Series:
    """The CLV the checklist judges: raw for props (see the module note), else clv."""
    if not len(df):
        return pd.Series(dtype=float)
    clv = pd.to_numeric(df["clv"], errors="coerce")
    if "clv_raw" in df:
        is_prop = df["kind"].astype(str).eq("prop") if "kind" in df else df["market"].astype(str).str.startswith("player_")
        clv = clv.where(~is_prop, pd.to_numeric(df["clv_raw"], errors="coerce"))
    return clv


def _stats(df: pd.DataFrame, now: datetime | None = None, days_left: int | None = None) -> dict:
    clv = checked_clv(df).dropna().astype(float)
    out = {"logged": int(len(df)), "with_clv": int(len(clv)),
           "avg_clv": round(float(clv.mean()), 4) if len(clv) else None,
           "beat_close": round(float((clv > 0).mean()), 3) if len(clv) else None,
           "sure_positive": None if (sp := sure_positive(clv)) is None else round(sp, 3)}
    if now is not None and days_left is not None:
        logged = pd.to_datetime(df["created_at"], utc=True, errors="coerce", format="ISO8601") if len(df) and "created_at" in df \
            else pd.Series(dtype="datetime64[ns, UTC]")
        recent = int((logged >= pd.Timestamp(now) - pd.Timedelta(days=PACE_DAYS)).sum()) if len(logged) else 0
        per_week = recent / (PACE_DAYS / 7)
        out["per_week"] = round(per_week, 1)
        out["by_review"] = int(round(len(clv) + (len(df) - len(clv)) + per_week * max(days_left, 0) / 7))
    return out


def status(s: dict) -> str:
    """pass / not yet (too few picks) / failing (enough picks, a bar missed)."""
    if s["with_clv"] < MIN_PICKS:
        return "not yet"
    ok = (s["avg_clv"] or 0) >= MIN_AVG_CLV and (s["beat_close"] or 0) >= MIN_BEAT_CLOSE
    return "pass" if ok else "failing"


def market_key(df: pd.DataFrame) -> pd.Series:
    """'NFL spreads', 'NFL props', 'NCAAF totals'...: player props are one market."""
    m = df["market"].where(~df["market"].astype(str).str.startswith("player_"), "props")
    names = {"h2h": "moneyline", "spreads": "spreads", "totals": "totals", "props": "props"}
    return df["league"].str.upper() + " " + m.map(lambda x: names.get(x, x))


def _count(df: pd.DataFrame, key: str) -> int:
    return int((market_key(df) == key).sum()) if len(df) else 0


def build(now: datetime | None = None) -> dict:
    from betlab import cfb_reads, tracking

    now = now or datetime.now(timezone.utc)
    all_picks, all_leans = ledger.load(), ledger.load(ledger.LEANS)
    picks, leans = current_rule(all_picks), current_rule(all_leans, picks=False)
    (picks, self_p), (leans, self_l) = real_closes(picks), real_closes(leans)
    seen = (set(market_key(picks)) if len(picks) else set()) | (set(market_key(leans)) if len(leans) else set())
    keys = MARKETS + sorted(seen - set(MARKETS))
    days_left = (pd.Timestamp(REVIEW_DAY).date() - pd.Timestamp(now).tz_convert("America/New_York").date()).days
    markets = []
    for k in keys:
        p = picks[market_key(picks) == k] if len(picks) else picks
        ln = leans[market_key(leans) == k] if len(leans) else leans
        ps, ls = _stats(p, now, days_left), _stats(ln)
        m = {"market": k, "picks": ps, "leans": ls, "status": status(ps),
             "progress": round(min(ps["with_clv"] / MIN_PICKS, 1.0), 3)}
        if k.endswith("props") and len(p):
            corrected = pd.to_numeric(p["clv"], errors="coerce").dropna()
            m["avg_clv_corrected"] = round(float(corrected.mean()), 4) if len(corrected) else None
        # rows of this market left out by current_rule (retired props rule, picks logged too early)
        retired = {"picks": _count(all_picks, k) - len(p), "leans": _count(all_leans, k) - len(ln)}
        if retired["picks"] or retired["leans"]:
            m["retired_excluded"] = retired
        # CLV blanked because the close was the bet's own pull (real_closes); the rows still count as logged
        own = {"picks": int(self_p[p.index].sum()) if len(p) else 0, "leans": int(self_l[ln.index].sum()) if len(ln) else 0}
        if own["picks"] or own["leans"]:
            m["self_close_excluded"] = own
        markets.append(m)
    # each book on its own record (docs/DRAFTKINGS_PLAN.md rule 15): FanDuel's lag edge and DraftKings' are judged
    # apart; everything before Oct 12 was FanDuel's
    book_of = lambda df: df["book"].fillna("fanduel").astype(str).str.lower() if len(df) and "book" in df else pd.Series(dtype=str)
    by_book = []
    for b, name in (("fanduel", "FanDuel"), ("draftkings", "DraftKings")):
        p = picks[book_of(picks) == b] if len(picks) else picks
        ln = leans[book_of(leans) == b] if len(leans) else leans
        by_book.append({"book": name, "picks": _stats(p), "leans": _stats(ln)})
    everything = {"picks": _stats(picks, now, days_left),
                  "picks_and_leans": _stats(pd.concat([picks, leans], ignore_index=True) if len(leans) else picks)}
    return {"generated_at": now.isoformat(timespec="seconds"), "review_day": REVIEW_DAY, "days_left": days_left,
            "rules": {"min_picks": MIN_PICKS, "min_avg_clv": MIN_AVG_CLV, "min_beat_close": MIN_BEAT_CLOSE},
            "markets": markets, "all_markets": everything, "by_book": by_book,
            "research": {"nfl_props_reads": tracking.summary(), "college_early_read": cfb_reads.summary()}}


def write() -> dict:
    doc = build()
    (config.EXPORTS_DIR / "golive.json").write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    return doc
