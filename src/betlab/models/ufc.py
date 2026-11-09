"""A UFC fight model from ESPN's results since 2021 (Oct 23): who wins, and whether it goes the distance.

Tracked only, no weight (CLAUDE.md, hard rule 3): the only prices to test it against are ESPN's DraftKings lines for
the last few cards, so it shows on the fight pages as a read until a backfill of past closes says otherwise.

- **Each fighter's state before a fight**, from their earlier UFC fights in the data only: an Elo rating (K=32, a
  finish counts 1.25x), fights so far, significant strikes landed and absorbed per minute, accuracy, takedowns for
  and against per 15 minutes, knockdowns for and against, control share, submission attempts, win and finish rates,
  how often they were stopped, days since their last fight. Rates are shrunk toward the average fighter by
  PRIOR_MINUTES of average output, so a debut is the average fighter.
- **Who wins:** a logistic regression on the two fighters' differences, trained on both orders of every fight (ESPN
  lists the favorite or the champion first more often, which must not leak), walk-forward by year.
- **Goes the distance:** a logistic regression on the pair's combined finishing (knockdowns, finish rates, stopped
  rates, submissions), the gap between them, five rounds and the weight class's decision rate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ELO_START, ELO_K, FINISH_X = 1500.0, 32.0, 1.25
PRIOR_MINUTES = 15.0
RATES = ("sig", "sig_abs", "td", "td_abs", "kd", "kd_abs", "subatt", "ctrl", "ctrl_abs")
WIN_FEATURES = ["elo", "exp", "slpm", "sapm", "acc", "td15", "tdabs15", "kd15", "kdabs15", "sub15", "ctrl_share",
                "win_rate", "finish_rate", "stopped_rate", "layoff"]


def _kind(result: str) -> str:
    r = str(result or "")
    return "dec" if r.startswith("decision") else "ko" if ("ko" in r or "tko" in r) else "sub" if r == "submission" else "other"


def _weight_class(note) -> str:
    return str(note or "").split(" - ")[0].strip() or "Unknown"


class _State:
    def __init__(self):
        self.elo, self.n, self.wins, self.finishes, self.stopped = ELO_START, 0, 0, 0, 0
        self.minutes, self.sums, self.att = 0.0, dict.fromkeys(RATES, 0.0), {"sig": 0.0}
        self.last = None


def _rates(st: _State, avg: dict) -> dict:
    m = st.minutes + PRIOR_MINUTES
    r = {k: (st.sums[k] + avg[k] * PRIOR_MINUTES) / m for k in RATES}
    acc = (st.sums["sig"] + 0.45 * 20) / (st.att["sig"] + 20)
    ctrl = r["ctrl"] + r["ctrl_abs"]
    n = st.n
    return {"elo": st.elo, "exp": np.log1p(n), "slpm": r["sig"], "sapm": r["sig_abs"], "acc": acc,
            "td15": r["td"] * 15, "tdabs15": r["td_abs"] * 15, "kd15": r["kd"] * 15, "kdabs15": r["kd_abs"] * 15,
            "sub15": r["subatt"] * 15, "ctrl_share": r["ctrl"] / ctrl if ctrl > 0 else 0.5,
            "win_rate": (st.wins + 1) / (n + 2), "finish_rate": (st.finishes + 0.5) / (n + 1),
            "stopped_rate": (st.stopped + 0.3) / (n + 1)}


def features(hist: pd.DataFrame) -> pd.DataFrame:
    """One row per finished fight, in date order, with both fighters' pre-fight state (a_*, b_*) and the outcome."""
    h = hist.copy()
    h["date"] = pd.to_datetime(h["event_start"], utc=True, format="ISO8601")
    h = h.sort_values(["date", "fight_id"]).reset_index(drop=True)
    states: dict[str, _State] = {}
    # league-average output per minute (the shrinkage target), from the whole history: a constant, not a leak of who won
    mins = h["seconds"].fillna(0) / 60
    avg = {}
    for k in RATES:
        base, opp = k.replace("_abs", ""), k.endswith("_abs")
        col = (h[f"b_{base}"] if opp else h[f"a_{base}"]).fillna(0) + (h[f"a_{base}"] if opp else h[f"b_{base}"]).fillna(0)
        avg[k] = float(col.sum() / max(2 * mins.sum(), 1))
    rows = []
    for r in h.itertuples(index=False):
        a, b = str(r.a_id), str(r.b_id)
        sa, sb = states.setdefault(a, _State()), states.setdefault(b, _State())
        fa, fb = _rates(sa, avg), _rates(sb, avg)
        fa["layoff"] = min((r.date - sa.last).days, 1000) / 365 if sa.last is not None else 1.0
        fb["layoff"] = min((r.date - sb.last).days, 1000) / 365 if sb.last is not None else 1.0
        kind = _kind(r.result)
        a_win, b_win = bool(r.a_win) if r.a_win is not None and not pd.isna(r.a_win) else False, \
            bool(r.b_win) if r.b_win is not None and not pd.isna(r.b_win) else False
        row = {"fight_id": r.fight_id, "date": r.date, "a_name": r.a_name, "b_name": r.b_name, "rounds": r.rounds,
               "weight_class": _weight_class(r.note), "kind": kind, "a_win": a_win, "b_win": b_win,
               "decided": a_win or b_win, "debut_a": sa.n == 0, "debut_b": sb.n == 0,
               **{f"a_{k}": v for k, v in fa.items()}, **{f"b_{k}": v for k, v in fb.items()}}
        for c in ("a_ml", "b_ml", "distance_yes", "distance_no"):
            row[c] = getattr(r, c, np.nan)
        rows.append(row)
        # update both fighters after the fight
        if a_win or b_win:
            exp_a = 1 / (1 + 10 ** ((sb.elo - sa.elo) / 400))
            k = ELO_K * (FINISH_X if kind in ("ko", "sub") else 1.0)
            delta = k * ((1.0 if a_win else 0.0) - exp_a)
            sa.elo, sb.elo = sa.elo + delta, sb.elo - delta
        minutes = (r.seconds or 0) / 60 if not pd.isna(r.seconds) else 0
        for me, opp, side, other, won, lost in ((sa, sb, "a", "b", a_win, b_win), (sb, sa, "b", "a", b_win, a_win)):
            me.n += 1
            me.wins += int(won)
            me.finishes += int(won and kind in ("ko", "sub"))
            me.stopped += int(lost and kind in ("ko", "sub"))
            me.minutes += minutes
            for k in RATES:
                base, is_opp = k.replace("_abs", ""), k.endswith("_abs")
                v = getattr(r, f"{other if is_opp else side}_{base}", np.nan)
                me.sums[k] += 0.0 if v is None or pd.isna(v) else float(v)
            att = getattr(r, f"{side}_sig_att", np.nan)
            me.att["sig"] += 0.0 if att is None or pd.isna(att) else float(att)
            me.last = r.date
    return pd.DataFrame(rows)


def win_matrix(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Both orders of every decided fight: X = a - b differences, y = a won."""
    d = f[f["decided"]]
    xa = np.column_stack([d[f"a_{k}"] - d[f"b_{k}"] for k in WIN_FEATURES])
    y = d["a_win"].to_numpy().astype(int)
    return np.vstack([xa, -xa]), np.concatenate([y, 1 - y])


def _diffs(f: pd.DataFrame) -> np.ndarray:
    return np.column_stack([f[f"a_{k}"] - f[f"b_{k}"] for k in WIN_FEATURES])


def dist_matrix(f: pd.DataFrame, class_rate: dict) -> np.ndarray:
    s = lambda k: f[f"a_{k}"] + f[f"b_{k}"]
    return np.column_stack([s("kd15"), s("kdabs15"), s("finish_rate"), s("stopped_rate"), s("sub15"), s("slpm"),
                            (f["a_elo"] - f["b_elo"]).abs() / 100, (f["rounds"] == 5).astype(float),
                            f["weight_class"].map(class_rate).fillna(np.mean(list(class_rate.values()) or [0.47]))])


def fit_win(f: pd.DataFrame):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X, y = win_matrix(f)
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.5, fit_intercept=False, max_iter=1000)).fit(X, y)


def fit_distance(f: pd.DataFrame):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    rate = f.groupby("weight_class")["kind"].apply(lambda k: float((k == "dec").mean())).to_dict()
    X, y = dist_matrix(f, rate), (f["kind"] == "dec").to_numpy().astype(int)
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=1000)).fit(X, y)
    return model, rate


def predict_win(model, f: pd.DataFrame) -> np.ndarray:
    """P(a wins), symmetric: the mean of both orders."""
    x = _diffs(f)
    return (model.predict_proba(x)[:, 1] + 1 - model.predict_proba(-x)[:, 1]) / 2


def walk_forward(f: pd.DataFrame, years=(2023, 2024, 2025, 2026)) -> pd.DataFrame:
    """Out-of-sample predictions: each year from a model fit on every earlier fight."""
    out = []
    for y in years:
        train, test = f[f["date"].dt.year < y], f[f["date"].dt.year == y].copy()
        if test.empty or train["decided"].sum() < 300:
            continue
        wm = fit_win(train)
        dm, rate = fit_distance(train)
        test["p_win"] = predict_win(wm, test)
        test["p_dist"] = dm.predict_proba(dist_matrix(test, rate))[:, 1]
        # Elo alone, for comparison
        test["p_elo"] = 1 / (1 + 10 ** ((test["b_elo"] - test["a_elo"]) / 400))
        out.append(test)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _ll(p, y) -> float:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def report(hist: pd.DataFrame) -> list[str]:
    """`betlab backtest ufc`: walk-forward log loss of the win and distance models, against Elo, the base rate and,
    where ESPN kept them, DraftKings' no-vig prices."""
    from betlab import odds_math as om

    f = features(hist)
    wf = walk_forward(f)
    d = wf[wf["decided"]]
    y = d["a_win"].astype(int).to_numpy()
    lines = [f"who wins, out of sample ({len(d)} fights): model {_ll(d['p_win'], y):.4f}, Elo {_ll(d['p_elo'], y):.4f}, "
             f"coin 0.6931; picks the winner {np.mean((d['p_win'] > 0.5) == y):.1%}"]
    dd = wf[wf["kind"] != "other"]
    yd = (dd["kind"] == "dec").astype(int).to_numpy()
    base = float(f[f["date"].dt.year < 2023]["kind"].eq("dec").mean())
    lines.append(f"goes the distance ({len(dd)}): model {_ll(dd['p_dist'], yd):.4f}, base rate {_ll(np.full(len(dd), base), yd):.4f}")
    m = d[d["a_ml"].notna() & d["b_ml"].notna()]
    if len(m):
        ym = m["a_win"].astype(int).to_numpy()
        pm = np.array([om.no_vig_two_way(a, b)[0] for a, b in zip(m["a_ml"], m["b_ml"])])
        lines.append(f"vs DraftKings' moneyline ({len(m)}): market {_ll(pm, ym):.4f}, model {_ll(m['p_win'], ym):.4f}, "
                     f"half and half {_ll((pm + m['p_win']) / 2, ym):.4f}")
    k = wf[wf["distance_yes"].notna() & wf["distance_no"].notna() & (wf["kind"] != "other")]
    if len(k):
        yk = (k["kind"] == "dec").astype(int).to_numpy()
        pk = np.array([om.no_vig_two_way(a, b)[0] for a, b in zip(k["distance_yes"], k["distance_no"])])
        lines.append(f"vs DraftKings' distance ({len(k)}): market {_ll(pk, yk):.4f}, model {_ll(k['p_dist'], yk):.4f}")
    return lines


def reads(hist: pd.DataFrame, card: pd.DataFrame) -> dict[str, dict]:
    """{fight_id: {p_a, p_dist}} for upcoming fights (card: fight_id, a_id, b_id, a_name, b_name, rounds, note), from
    models fit on every finished fight: the fighters' state as of now."""
    if card is None or card.empty or hist is None or hist.empty:
        return {}
    up = card.assign(event_start=pd.Timestamp.now(tz="UTC").isoformat(), result="", period=0, seconds=np.nan,
                     a_win=None, b_win=None, done=False)
    f = features(pd.concat([hist, up[[c for c in up.columns if c in hist.columns or c in up.columns]]], ignore_index=True))
    past, now = f.iloc[: len(hist)], f.iloc[len(hist):]
    wm = fit_win(past)
    dm, rate = fit_distance(past[past["kind"] != "other"])
    p = predict_win(wm, now)
    pdist = dm.predict_proba(dist_matrix(now, rate))[:, 1]
    return {str(fid): {"p_a": round(float(a), 4), "p_dist": round(float(b), 4), "debut_a": bool(da), "debut_b": bool(db)}
            for fid, a, b, da, db in zip(now["fight_id"], p, pdist, now["debut_a"], now["debut_b"])}
