"""The UFC fight pages (Games tab, Oct 23): what each fight looks like, from free data, for every fight on the next
UFC card (`betlab ufc` -> exports/ufc.json -> publish, kind "ufc").

Per fight: the card segment, weight class and rounds; each fighter's record, age, height, reach and stance (ESPN);
their last five UFC fights and how they win and lose (ESPN results since 2021, `espn_ufc.history`); how often the
weight class goes the distance at this length; DraftKings' method, distance and total-rounds prices from ESPN's fight
center, as no-vig chances (the method market carries a ~20% margin, so its chances are normalized across all six
outcomes); and, once the card's odds are pulled, each of Mike's books against the sharp no-vig moneyline. Pages
exist from the free event list, so a card shows up before its paid pulls; they key on the Odds API's event id, as the
card's offers do.
"""

from __future__ import annotations

import pandas as pd

from betlab import config
from betlab import odds_math as om
from betlab.books import name as _bk
from betlab.cards import ufc
from betlab.market import two_way
from betlab.sources import espn_ufc as src

SEGMENT = {"main": "Main card", "prelims1": "Prelims", "prelims2": "Early prelims"}
METHOD = {"kotko": "KO/TKO", "tko---doctors-stoppage": "TKO (doctor)", "submission": "Submission",
          "decision---unanimous": "Decision", "decision---split": "Split decision",
          "decision---majority": "Majority decision", "draw": "Draw", "no-contest": "No contest"}


def method_kind(result: str) -> str:
    """ko / sub / dec / other from ESPN's result name."""
    r = str(result or "")
    return "dec" if r.startswith("decision") else "ko" if ("ko" in r or "tko" in r) else "sub" if r == "submission" else "other"


def _weight_class(note) -> str:
    return str(note or "").split(" - ")[0].strip() or "Unknown"


def fighter_form(hist: pd.DataFrame, athlete_id, before: pd.Timestamp, n: int = 5) -> dict:
    """A fighter's UFC fights since 2021 before `before`: the last n, and wins/losses by method."""
    if hist is None or hist.empty or not athlete_id:
        return {"fights": 0, "last": [], "wins": {}, "losses": {}, "distance": None}
    aid = str(athlete_id)
    rows = []
    for side, other in (("a", "b"), ("b", "a")):
        m = hist[hist[f"{side}_id"].astype(str) == aid]
        for r in m.itertuples():
            won = getattr(r, f"{side}_win")
            lost = getattr(r, f"{other}_win")
            rows.append({"date": str(r.event_start)[:10], "opponent": getattr(r, f"{other}_name"),
                         "result": "W" if won is True or won == 1 else "L" if lost is True or lost == 1 else "D/NC",
                         "method": METHOD.get(r.result, r.result), "kind": method_kind(r.result), "round": int(r.period or 0)})
    df = pd.DataFrame(rows)
    if df.empty:
        return {"fights": 0, "last": [], "wins": {}, "losses": {}, "distance": None}
    df = df[pd.to_datetime(df["date"]) < before.tz_localize(None).normalize()].sort_values("date", ascending=False)
    count = lambda res: {k: int(v) for k, v in df[df["result"] == res]["kind"].value_counts().items()}
    return {"fights": int(len(df)), "last": df.head(n).drop(columns="kind").to_dict("records"),
            "wins": count("W"), "losses": count("L"),
            "distance": round(float((df["kind"] == "dec").mean()), 3) if len(df) else None}


def class_rates(hist: pd.DataFrame, weight_class: str, rounds: int) -> dict | None:
    """How fights in this weight class at this length end (UFC since 2021)."""
    if hist is None or hist.empty:
        return None
    m = hist[(hist["note"].map(_weight_class) == weight_class) & (hist["rounds"] == rounds)]
    if len(m) < 20:
        return None
    kinds = m["result"].map(method_kind)
    return {"n": int(len(m)), "distance": round(float((kinds == "dec").mean()), 3),
            "ko": round(float((kinds == "ko").mean()), 3), "sub": round(float((kinds == "sub").mean()), 3)}


def dk_props(f: pd.Series) -> dict | None:
    """DraftKings' method, distance and total rounds from ESPN as no-vig chances, or None without prices."""
    cells = {(s, m): f.get(f"{s}_{m}") for s in ("a", "b") for m in ("ko", "sub", "dec")}
    out = {}
    if all(pd.notna(v) for v in cells.values()):
        ip = {k: om.implied_prob(float(v)) for k, v in cells.items()}
        tot = sum(ip.values())
        out["method"] = {f"{s}_{m}": {"price": float(cells[(s, m)]), "p": round(ip[(s, m)] / tot, 4)} for s, m in ip}
        out["method_margin"] = round(tot - 1, 3)
    if pd.notna(f.get("distance_yes")) and pd.notna(f.get("distance_no")):
        p = om.no_vig_two_way(float(f["distance_yes"]), float(f["distance_no"]))[0]
        out["distance"] = {"yes": float(f["distance_yes"]), "no": float(f["distance_no"]), "p_yes": round(p, 4)}
    if pd.notna(f.get("total_line")) and pd.notna(f.get("over")) and pd.notna(f.get("under")):
        p = om.no_vig_two_way(float(f["over"]), float(f["under"]))[0]
        out["total"] = {"line": float(f["total_line"]), "over": float(f["over"]), "under": float(f["under"]), "p_over": round(p, 4)}
    if pd.notna(f.get("a_ml")) and pd.notna(f.get("b_ml")):
        out["ml"] = {"a": float(f["a_ml"]), "b": float(f["b_ml"]),
                     "p_a": round(om.no_vig_two_way(float(f["a_ml"]), float(f["b_ml"]))[0], 4)}
    return out or None


def books(ev: pd.DataFrame | None, a: str, b: str) -> list[dict]:
    """Each of Mike's books' moneyline for both fighters against the sharp no-vig chance (from the latest pull)."""
    if ev is None or ev.empty:
        return []
    out = []
    p_a, source = ufc._fair(ev, "h2h", a, b, "fanduel")
    if p_a is None:
        return []
    for side, other, p in ((a, b, p_a), (b, a, 1 - p_a)):
        row = {"label": f"{side} ML", "p_market": round(p, 4), "source": source}
        for bk in config.settings()["odds_api"]["target_books"]:
            tw = two_way(ev, "h2h", bk, side, other)
            if tw:
                pr = float(tw[0][1])
                row[bk] = {"price": pr, "ev": round(om.expected_value(p, pr), 4)}
        out.append(row)
    return out


def finish_timing(hist: pd.DataFrame) -> dict[int, list[float]]:
    """{scheduled rounds: seconds into the fight of every KO/TKO or submission since 2021}, for P(a finish comes
    before a total-rounds line)."""
    if hist is None or hist.empty:
        return {}
    fin = hist[hist["result"].map(method_kind).isin(["ko", "sub"]) & hist["seconds"].notna()]
    return {int(r): sorted(g["seconds"].astype(float)) for r, g in fin.groupby("rounds") if len(g) >= 50}


def sharp_total(ev: pd.DataFrame | None, dk: dict | None) -> tuple[float, float, str] | None:
    """(line, P(over), source) for total rounds: the sharp book's no-vig at its line from our pull, else DraftKings'."""
    if ev is not None and len(ev):
        for bk in config.settings()["odds_api"]["sharp_books"]:
            tw = two_way(ev, "totals", bk, "Over", "Under")
            if tw and pd.notna(tw[0][0]):
                return float(tw[0][0]), om.no_vig_two_way(float(tw[0][1]), float(tw[1][1]))[0], bk
    t = (dk or {}).get("total")
    return (t["line"], t["p_over"], "DraftKings") if t else None


def same_fight(fight: dict, timing: dict[int, list[float]], total: tuple | None) -> list[dict]:
    """Fair chances of same-fight parlays (Oct 23): a fighter to win with the fight's length. P(win) is the sharp
    moneyline (else DraftKings'); how each fighter wins (finish vs decision) is DraftKings' method market with its margin
    removed. Only a finish can come in under a rounds line, so P(a finish comes before L) is set to agree with the sharp
    total, P(under) / P(any finish) (capped at 1); without a total it is the share of every UFC finish since 2021 at
    this fight's length that came before L. So P(X wins inside L rounds) = P(X wins) x P(X's win is a finish) x that,
    and each fighter's under and over add up to their moneyline. `naive` is the two legs multiplied as if unrelated."""
    meth = (fight.get("dk") or {}).get("method")
    secs = timing.get(int(fight["rounds"]))
    if not meth or not secs:
        return []
    import bisect

    books_rows = fight.get("books") or []
    dk_ml = (fight.get("dk") or {}).get("ml") or {}
    def win_and_share(side, x):
        p_ko, p_sub, p_dec = (meth[f"{side}_{m}"]["p"] for m in ("ko", "sub", "dec"))
        row = next((r for r in books_rows if r["label"] == f"{x['name']} ML"), None)
        p_win = row["p_market"] if row else (dk_ml.get("p_a") if side == "a" else (1 - dk_ml["p_a"]) if dk_ml else None)
        if p_win is None or p_ko + p_sub + p_dec <= 0:
            return None
        return p_win, (p_ko + p_sub) / (p_ko + p_sub + p_dec)   # how much of X's winning DraftKings sees as finishes

    sides = {s: win_and_share(s, x) for s, x in (("a", fight["fighters"][0]), ("b", fight["fighters"][1]))}
    if total and all(sides.values()):
        p_finish = sum(w * sh for w, sh in sides.values())
        t = min(1.0, (1 - total[1]) / p_finish) if p_finish > 0 else 0.0
    elif total:
        t = bisect.bisect_left(secs, total[0] * 300) / len(secs)
    out = []
    for side, x in (("a", fight["fighters"][0]), ("b", fight["fighters"][1])):
        if sides[side] is None:
            continue
        p_win, share = sides[side]
        combos = [{"label": f"{x['name']} wins inside the distance", "p": p_win * share,
                   "dk_price": None},
                  {"label": f"{x['name']} wins by decision", "p": p_win * (1 - share), "dk_price": meth[f"{side}_dec"]["price"]}]
        if total:
            line, p_over, source = total
            under = p_win * share * t
            combos += [{"label": f"{x['name']} wins + under {line:g} rounds", "p": under, "naive": p_win * (1 - p_over)},
                       {"label": f"{x['name']} wins + over {line:g} rounds", "p": p_win - under, "naive": p_win * p_over}]
        for c in combos:
            c["p"] = round(c["p"], 4)
            c["fair_price"] = round(om.prob_to_american(c["p"])) if 0.005 < c["p"] < 0.995 else None
            if c.get("naive") is not None:
                c["naive"] = round(c["naive"], 4)
            if c.get("dk_price") is not None:
                c["dk_ev"] = round(om.expected_value(c["p"], float(c["dk_price"])), 4)
        out += combos
    return out


def _story(fight: dict) -> str:
    a, b = fight["fighters"]
    dk = fight.get("dk") or {}
    parts = []
    ml = dk.get("ml")
    if ml:
        fav, p = (a, ml["p_a"]) if ml["p_a"] >= 0.5 else (b, 1 - ml["p_a"])
        parts.append(f"DraftKings has it close to a coin flip ({fav['name']} {p:.0%})." if p < 0.53 else
                     f"DraftKings makes {fav['name']} the favorite at {p:.0%}.")
    meth = dk.get("method")
    if meth:
        top = max(meth.items(), key=lambda kv: kv[1]["p"])
        who = a if top[0].startswith("a_") else b
        word = {"ko": "by KO/TKO", "sub": "by submission", "dec": "on the scorecards"}[top[0][2:]]
        parts.append(f"The likeliest single result is {who['name']} {word} ({top[1]['p']:.0%} once the method market's "
                     f"{dk['method_margin']:.0%} margin is taken out).")
    dist, base = dk.get("distance"), fight.get("class_rates")
    if dist:
        line = f"It goes the distance {dist['p_yes']:.0%} of the time by DraftKings' price"
        if base:
            line += (f"; since 2021, {base['distance']:.0%} of {fight['weight_class'].lower()} {fight['rounds']}-rounders "
                     f"did ({base['n']} fights)")
        parts.append(line + ".")
    for x in (a, b):
        fm = x.get("form") or {}
        if fm.get("fights"):
            w = fm["wins"]
            parts.append(f"{x['name']}: {fm['fights']} UFC fights since 2021, wins {w.get('ko', 0)} by KO, {w.get('sub', 0)} by "
                         f"submission, {w.get('dec', 0)} on points.")
    return " ".join(parts)


def build(asof: pd.Timestamp, events: list[dict] | None = None, hist: pd.DataFrame | None = None,
          snap: pd.DataFrame | None = None) -> dict:
    """{"games": [one analysis per fight on the next UFC card]}. `events`: the Odds API's free event list (aligned to
    the card), `hist`: espn_ufc.history rows, `snap`: the latest UFC game-line snapshot."""
    fights = ufc.card_fights(asof, days=8)              # the next card, a week out
    if fights.empty:
        return {"games": []}
    fights = fights[pd.to_datetime(fights["start"], utc=True) > asof - pd.Timedelta(hours=8)]
    if events is None:
        from betlab.sources.odds_api import OddsApiClient
        events = OddsApiClient().events(config.settings()["leagues"]["ufc"]["sport_key"])   # free
    if hist is None:
        hist = src.history(range(2021, asof.year + 1))
    centers: dict[str, pd.DataFrame] = {}
    games, rows = [], []
    timing = finish_timing(hist)
    for e in ufc.align(events, fights):
        f = src.find(fights, e["home_team"], e["away_team"])
        eid = str(f.get("espn_event"))
        if eid not in centers:
            try:
                centers[eid] = src.fights(src.event(eid, refresh=True), eid)
            except Exception:                 # ESPN down: the page goes without DraftKings' props
                centers[eid] = pd.DataFrame()
        fc = centers[eid]
        row = fc[fc["fight_id"].astype(str) == str(f["fight_id"])]
        row = row.iloc[0] if len(row) else None
        a_name, b_name = (e["home_team"], e["away_team"]) if src._last(f["a_name"]) == src._last(e["home_team"]) else (e["away_team"], e["home_team"])
        start = pd.Timestamp(f["start"])
        wc = _weight_class(row["note"] if row is not None else "")
        fighters = []
        for side, name in (("a", a_name), ("b", b_name)):
            info = (row.get(f"{side}_info") if row is not None else None) or {}
            fighters.append({"name": name, **info,
                             "form": fighter_form(hist, row.get(f"{side}_id") if row is not None else None, start)})
        ev = snap[snap["event_id"].astype(str) == e["id"]] if snap is not None and len(snap) else None
        fight = {"event_id": e["id"], "game_ref": f"ufc:{eid}:{f['fight_id']}", "event": f.get("event"),
                 "matchup": f"{a_name} vs {b_name}", "commence_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "segment": SEGMENT.get(row["segment"], row["segment"]) if row is not None else None,
                 "weight_class": wc, "rounds": int(f["rounds"]),
                 "title": "title" in str(row["note"] if row is not None else "").lower(),
                 "fighters": fighters, "class_rates": class_rates(hist, wc, int(f["rounds"])),
                 "dk": dk_props(row) if row is not None else None, "books": books(ev, a_name, b_name)}
        if row is not None and fight["dk"] and src._last(row["a_name"]) != src._last(a_name):
            fight["dk"] = _swap(fight["dk"])               # ESPN's order 1 is our b
        fight["same_fight"] = same_fight(fight, timing, sharp_total(ev, fight["dk"]))
        fight["story"] = _story(fight)
        games.append(fight)
        if row is not None:
            rows.append({"fight_id": str(f["fight_id"]), "a_id": row["a_id"] if src._last(row["a_name"]) == src._last(a_name) else row["b_id"],
                         "b_id": row["b_id"] if src._last(row["a_name"]) == src._last(a_name) else row["a_id"],
                         "a_name": a_name, "b_name": b_name, "rounds": int(f["rounds"]), "note": row["note"]})
    try:                                   # our fight model's read: tracked, no weight (models/ufc.py)
        from betlab.models import ufc as model

        got = model.reads(hist, pd.DataFrame(rows))
    except Exception as exc:               # a read is a bonus; never block the pages
        print(f"UFC model read skipped ({type(exc).__name__}: {exc})")
        got = {}
    for g in games:
        r = got.get(g["game_ref"].rsplit(":", 1)[-1])
        if r:
            g["model"] = r
    return {"games": sorted(games, key=lambda g: g["commence_time"])}


def _swap(dk: dict) -> dict:
    out = dict(dk)
    if "method" in dk:
        out["method"] = {("b" if k[0] == "a" else "a") + k[1:]: v for k, v in dk["method"].items()}
    if "ml" in dk:
        out["ml"] = {"a": dk["ml"]["b"], "b": dk["ml"]["a"], "p_a": round(1 - dk["ml"]["p_a"], 4)}
    return out
