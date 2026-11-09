"""The UFC tracker (data/ledger/ufc_lines.csv, Oct 23): every fight on every card from UFC 333 on, with DraftKings'
prices from ESPN (moneyline, the six method outcomes, total rounds, goes the distance) at our first and last look
before it, the sharp no-vig moneyline, our fight model's read, and the result. It is the history the props question
needs (ESPN keeps DraftKings' prices only for the last few cards) and keeps score of the model against the market.

Filled by `betlab ufc` (cards/analysis_ufc.py's pages, each run): a fight's first-look columns are written once, its
last-look columns follow every run until its segment starts, and the result fills in once ESPN has it. Rows are never
deleted; like the other ledgers, grading only fills the result columns.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab import config

PATH = config.DATA_DIR / "ledger" / "ufc_lines.csv"
PRICES = ["a_ml", "b_ml", "a_ko", "a_sub", "a_dec", "b_ko", "b_sub", "b_dec", "total_line", "over", "under",
          "distance_yes", "distance_no"]
COLUMNS = (["fight_id", "event_id", "event", "start", "segment", "weight_class", "rounds", "a_name", "b_name",
            "first_seen", "last_seen"]
           + [f"first_{c}" for c in PRICES] + [f"last_{c}" for c in PRICES]
           + ["sharp_p_a", "model_p_a", "model_p_dist", "debut_a", "debut_b",
              "winner", "kind", "period", "seconds", "graded_at"])


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    text = {c: "object" for c in ("fight_id", "event_id", "event", "start", "segment", "weight_class", "a_name", "b_name",
                                   "first_seen", "last_seen", "debut_a", "debut_b", "winner", "kind", "graded_at")}
    return pd.read_csv(PATH, dtype=text).reindex(columns=COLUMNS)


def _prices(g: dict) -> dict:
    """The fight's DraftKings prices in our fighter order (a = the page's first fighter)."""
    dk = g.get("dk") or {}
    out = {}
    if dk.get("ml"):
        out |= {"a_ml": dk["ml"]["a"], "b_ml": dk["ml"]["b"]}
    for k, v in (dk.get("method") or {}).items():
        out[k] = v["price"]
    if dk.get("total"):
        out |= {"total_line": dk["total"]["line"], "over": dk["total"]["over"], "under": dk["total"]["under"]}
    if dk.get("distance"):
        out |= {"distance_yes": dk["distance"]["yes"], "distance_no": dk["distance"]["no"]}
    return out


def record(games: list[dict], now: pd.Timestamp | None = None) -> int:
    """Add or refresh a row per fight on the pages; returns how many rows changed."""
    now = now or pd.Timestamp.now(tz="UTC")
    df = load()
    by_id = {str(f): i for i, f in enumerate(df["fight_id"])}
    stamp = now.isoformat(timespec="seconds")
    rows, changed = df.to_dict("records"), 0
    for g in games:
        fid = str(g.get("game_ref", "")).rsplit(":", 1)[-1]
        if not fid or pd.Timestamp(g["commence_time"]) <= now:
            continue
        prices = _prices(g)
        sharp = next((r["p_market"] for r in g.get("books") or [] if r["label"] == f"{g['fighters'][0]['name']} ML"), None)
        model = g.get("model") or {}
        live = {"last_seen": stamp, **{f"last_{k}": v for k, v in prices.items()}, "sharp_p_a": sharp,
                "model_p_a": model.get("p_a"), "model_p_dist": model.get("p_dist"),
                "debut_a": model.get("debut_a"), "debut_b": model.get("debut_b"), "start": g["commence_time"],
                "segment": g.get("segment")}
        live = {k: v for k, v in live.items() if v is not None}
        if fid in by_id:
            rows[by_id[fid]].update(live)
        else:
            rows.append({"fight_id": fid, "event_id": g["game_ref"].split(":")[1], "event": g.get("event"),
                         "weight_class": g.get("weight_class"), "rounds": g.get("rounds"),
                         "a_name": g["fighters"][0]["name"], "b_name": g["fighters"][1]["name"], "first_seen": stamp,
                         **{f"first_{k}": v for k, v in prices.items()}, **live})
            by_id[fid] = len(rows) - 1
        changed += 1
    if changed:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).reindex(columns=COLUMNS).to_csv(PATH, index=False)
    return changed


def grade(now: pd.Timestamp | None = None, fights_of=None) -> int:
    """Fill the result of every finished fight not yet graded (ESPN's fight center); returns how many."""
    from betlab.cards.analysis_ufc import method_kind
    from betlab.sources import espn_ufc as src

    now = now or pd.Timestamp.now(tz="UTC")
    df = load()
    todo = df[df["graded_at"].isna() & (pd.to_datetime(df["start"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=1))]
    if todo.empty:
        return 0
    fights_of = fights_of or (lambda eid: src.fights(src.event(str(eid), refresh=True), str(eid)))
    stamp = now.isoformat(timespec="seconds")
    n = 0
    for eid, rows in todo.groupby("event_id"):
        try:
            fc = fights_of(eid)
        except Exception:                 # ESPN down: the next run tries again
            continue
        for i, r in rows.iterrows():
            f = fc[fc["fight_id"].astype(str) == str(r["fight_id"])]
            if f.empty or not bool(f.iloc[0]["done"]):
                continue
            f = f.iloc[0]
            won = [n_ for n_, w in ((f["a_name"], f["a_win"]), (f["b_name"], f["b_win"])) if w is True or w == 1]
            winner = (None if not won else "a" if src._last(won[0]) == src._last(r["a_name"]) else "b")
            df.loc[i, ["winner", "kind", "period", "seconds", "graded_at"]] = [winner or "none", method_kind(f["result"]),
                                                                              f["period"], f["seconds"], stamp]
            n += 1
    if n:
        df.to_csv(PATH, index=False)
    return n


def summary(df: pd.DataFrame | None = None) -> list[str]:
    """The tracker's score: DraftKings' last no-vig moneyline vs our model on graded fights, and the method market's
    margin."""
    from betlab import odds_math as om
    from betlab.models.ufc import _ll

    df = load() if df is None else df
    g = df[df["winner"].isin(["a", "b"]) & df["last_a_ml"].notna() & df["model_p_a"].notna()]
    if g.empty:
        return ["UFC tracker: no graded fights with prices yet"]
    y = (g["winner"] == "a").astype(int).to_numpy()
    pm = np.array([om.no_vig_two_way(a, b)[0] for a, b in zip(g["last_a_ml"], g["last_b_ml"])])
    return [f"UFC tracker ({len(g)} graded fights): DraftKings {_ll(pm, y):.4f}, our model {_ll(g['model_p_a'], y):.4f}"]
