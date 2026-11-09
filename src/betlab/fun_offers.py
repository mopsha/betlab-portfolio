"""Every NFL same-game slip the Fun tab offers (and, since Oct 20, NBA slips): data/ledger/fun_offers.csv.

The fun ledger (fun_ledger.py) only grades slips Mike quoted or marked, so it can't say which
kind of slip is better. This one logs every offered slip once, at its first offer (like the
pick ledger), with how it was chosen (`style`: value, story or longshot) and its weakest pair's
lift (`min_pair_lift`; one_story when every pair hits together about as often as unrelated or
more, sgp.one_story). After the game each slip is graded leg by leg (fun_ledger's NFL grader).

The comparison (Mike, Oct 11: "a slip should tell one game story"): by style, and by one story
or not, hits against the fair chance's expected hits (is our joint pricing honest for each
kind?) and 1-unit profit at the naive price (the legs' FanDuel prices multiplied, an upper bound:
FanDuel's real SGP price is lower). A void or pushed leg comes off the slip as FanDuel settles
it: the rest stands at its own legs' prices and fair chance. Nothing here is a pick.
"""

from __future__ import annotations

import json
import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

PATH = config.DATA_DIR / "ledger" / "fun_offers.csv"
COLUMNS = ["sgp_id", "style", "one_story", "min_pair_lift", "lift", "theme", "event_id", "game_id", "matchup",
           "commence_time", "first_seen", "legs", "n_legs", "p_fair", "fair_price", "naive_price", "status",
           "leg_results", "p_settled", "profit_1u", "graded_at"]
TEXT = ["sgp_id", "style", "theme", "event_id", "game_id", "matchup", "commence_time", "first_seen", "legs", "status",
        "leg_results", "graded_at"]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(games: list[dict], asof: pd.Timestamp) -> int:
    """Log the offered slips of games not started that aren't logged yet; returns how many."""
    df = load()
    seen = set(df["sgp_id"]) if len(df) else set()
    now = asof.isoformat(timespec="seconds")
    rows = []
    for g in games:
        if not g.get("sgps") or pd.Timestamp(g["commence_time"]) <= asof:
            continue
        for d in g["sgps"]:
            if d["sgp_id"] in seen:
                continue
            seen.add(d["sgp_id"])
            legs = [{"label": l["label"], "price": l["price"], "p": l["p_fair"]} for l in d["legs"]]
            rows.append({"sgp_id": d["sgp_id"], "style": d.get("style") or ("longshot" if d.get("longshot") else "value"),
                         "one_story": d.get("one_story"), "min_pair_lift": d.get("min_pair_lift"), "lift": d.get("lift"),
                         "theme": d.get("theme"), "event_id": g["event_id"], "game_id": g.get("game_ref"),
                         "matchup": g["matchup"], "commence_time": g["commence_time"], "first_seen": now,
                         "legs": json.dumps(legs), "n_legs": d["n_legs"], "p_fair": d["p_fair"],
                         "fair_price": d["fair_price"], "naive_price": d["naive_price"], "status": "open"})
    if rows:
        save(pd.concat([x for x in (df, pd.DataFrame(rows).reindex(columns=COLUMNS)) if len(x)], ignore_index=True))
    return len(rows)


def settle(legs: list[dict], results: list[dict]) -> tuple[str, float | None, float | None] | None:
    """(status, fair chance of what stood, 1u profit at the naive price) from the legs' results;
    None while any leg is open or unreadable. Void and pushed legs come off the slip."""
    from betlab import odds_math as om

    outcomes = [x["result"] for x in results]
    if "unknown" in outcomes or "open" in outcomes:
        return None
    stand = [l for l, o in zip(legs, outcomes) if o not in ("void", "push")]
    if not stand:
        return "void", None, 0.0
    p = float(np.prod([float(l["p"]) for l in stand]))   # legs multiplied: the joint chance isn't stored per subset
    if "lost" in outcomes:
        return "lost", p, -1.0
    return "won", p, round(float(np.prod([om.american_to_decimal(float(l["price"])) for l in stand])) - 1, 4)


def grade(ps: pd.DataFrame | None = None, sn: pd.DataFrame | None = None, finals: pd.DataFrame | None = None,
          abbr: dict | None = None, now: pd.Timestamp | None = None, nba_box: pd.DataFrame | None = None,
          nba_sch: pd.DataFrame | None = None) -> int:
    """Grade open slips whose game's stats are out (tests pass the frames); returns how many. NFL slips from
    nflverse; NBA slips (game_id "nba|HOME|AWAY|tipoff", Oct 20) from ESPN's box scores (fun_ledger.nba_leg_results)."""
    from betlab import fun_ledger

    df = load()
    todo = df[(df["status"] == "open") & df["game_id"].notna()]
    now = now or pd.Timestamp.now(tz="UTC")
    todo = todo[pd.to_datetime(todo["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4)]
    if todo.empty:
        return 0
    stamp, n = now.isoformat(timespec="seconds"), 0
    is_nba = todo["game_id"].astype(str).str.startswith("nba|")
    if is_nba.any():
        try:      # one league's grader must never stop the other's
            box, sch = fun_ledger.nba_data(list(todo.loc[is_nba, "game_id"]), nba_box, nba_sch)
            for i, r in todo[is_nba].iterrows():
                legs = json.loads(r["legs"])
                results = fun_ledger.nba_leg_results([l["label"] for l in legs], [r["game_id"]] * len(legs), box, sch)
                n += _settle_row(df, i, legs, results, stamp)
        except Exception as exc:  # noqa: BLE001 - the NBA box scores down: the NFL slips still grade
            print(f"offered NBA slips not graded ({type(exc).__name__}: {exc})")
    if n:
        save(df)               # the NBA results stand even if nflverse fails below
    todo = todo[~is_nba]
    if todo.empty:
        return n
    if ps is None:
        from betlab.sources import nflverse

        seasons = sorted({int(str(g)[:4]) for g in todo["game_id"]})
        ps, sn = nflverse.load_player_stats(seasons), nflverse.load_snap_counts(seasons)
        finals = nflverse.load_games().drop_duplicates("game_id").set_index("game_id")
        abbr = nflverse.team_abbr_by_name()
    for i, r in todo.iterrows():
        legs = json.loads(r["legs"])
        results = fun_ledger.nfl_leg_results([l["label"] for l in legs], [r["game_id"]] * len(legs), ps, sn, finals, abbr)
        n += _settle_row(df, i, legs, results, stamp)
    if n:
        save(df)
    return n


def _settle_row(df: pd.DataFrame, i, legs: list[dict], results: list[dict] | None, stamp: str) -> int:
    """Fill one slip's result columns once every leg is settled; 1 if it was."""
    done = settle(legs, results) if results is not None else None
    if done is None:
        return 0
    status, p, profit = done
    df.loc[i, ["status", "leg_results", "p_settled", "profit_1u", "graded_at"]] = [
        status, json.dumps(results), None if p is None else round(p, 4), profit, stamp]
    return 1


def summary(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Graded slips by style and by one story or not: slips, hits, expected hits (fair chance of
    what stood), hit rate, and 1u profit at the naive price."""
    df = load() if df is None else df
    g = df[df["status"].isin(["won", "lost"])].copy()
    if g.empty:
        return pd.DataFrame(columns=["group", "slips", "hits", "expected", "hit_rate", "profit_1u"])
    g["won"] = (g["status"] == "won").astype(float)
    g["p_settled"] = pd.to_numeric(g["p_settled"], errors="coerce")
    g["profit_1u"] = pd.to_numeric(g["profit_1u"], errors="coerce")
    story = g["one_story"].astype(str).str.lower().isin(["true", "1", "1.0"])
    out = []
    for name, mask in ([(f"style {s}", g["style"] == s) for s in sorted(g["style"].dropna().unique())]
                       + [("one story", story), ("not one story", ~story)]):
        x = g[mask]
        if len(x):
            out.append({"group": name, "slips": len(x), "hits": int(x["won"].sum()), "expected": round(x["p_settled"].sum(), 1),
                        "hit_rate": round(x["won"].mean(), 3), "profit_1u": round(x["profit_1u"].sum(), 2)})
    return pd.DataFrame(out)
