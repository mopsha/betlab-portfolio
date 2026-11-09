"""Do NFL closing totals already price the wind, and does the referee matter? (Nov 4, ideas #12 and #13.)

Free: nflverse's schedule has each game's closing total, wind, roof and referee. For each question the number is points against
the close, so a real effect means the market left it on the table. Rule, as for every feature here (docs/MODELS.md): 2+ standard
errors with the same sign in both halves of the years, and enough to matter after -110 (52.4% to break even).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from betlab.sources import nflverse

BREAK_EVEN = 0.5238


def games() -> pd.DataFrame:
    g = nflverse.load_games()
    g = g[g["game_type"].isin(["REG", "WC", "DIV", "CON", "SB"]) & g["total"].notna() & g["total_line"].notna()].copy()
    g["miss"] = g["total"] - g["total_line"]           # actual total minus the close: above 0 went over
    return g[g["miss"] != 0].assign(push=False)


def line(name: str, d: pd.DataFrame) -> str:
    if d.empty:
        return f"{name:34} none"
    m, se = d["miss"].mean(), d["miss"].std(ddof=1) / np.sqrt(len(d))
    under = (d["miss"] < 0).mean()
    ci = 1.96 * np.sqrt(under * (1 - under) / len(d))
    return f"{name:34} {len(d):5}  miss {m:+.2f} (SE {se:.2f})  under {under:6.1%} +/- {ci:4.1%}"


def wind(g: pd.DataFrame) -> None:
    out = g[g["roof"].isin(["outdoors", "open"]) & g["wind"].notna()].copy()
    print(f"\nWIND, outdoor games {out['season'].min()}-{out['season'].max()}: points against the closing total")
    for name, lo, hi in [("under 10 mph", 0, 10), ("10-14", 10, 15), ("15-19", 15, 20), ("20+", 20, 99)]:
        print(line(name, out[(out["wind"] >= lo) & (out["wind"] < hi)]))
    mid = int(out["season"].median())
    for name, d in [(f"15+ mph, to {mid}", out[(out["wind"] >= 15) & (out["season"] <= mid)]), (f"15+ mph, after {mid}", out[(out["wind"] >= 15) & (out["season"] > mid)]),
                    ("15+ mph, since 2018", out[(out["wind"] >= 15) & (out["season"] >= 2018)]), ("20+ mph, since 2018", out[(out["wind"] >= 20) & (out["season"] >= 2018)])]:
        print(line(name, d))


def wind_check(g: pd.DataFrame, reps: int = 4000) -> None:
    """Harder tests of 15+ mph: whole seasons resampled (games in a season share rule changes and scoring), the season-by-season
    sign, the favorite's total size, and whether it beats -110 at all."""
    out = g[g["roof"].isin(["outdoors", "open"]) & g["wind"].notna()]
    d = out[out["wind"] >= 15].copy()
    d["under"] = d["miss"] < 0
    rng = np.random.default_rng(7)
    seasons = d["season"].unique()
    by = {s: d[d["season"] == s]["under"].to_numpy() for s in seasons}
    rates = [np.concatenate([by[s] for s in rng.choice(seasons, len(seasons))]).mean() for _ in range(reps)]
    lo, hi = np.percentile(rates, [2.5, 97.5])
    print(f"\nWIND 15+ mph, season-block bootstrap: under {d['under'].mean():.1%}, 95% interval {lo:.1%} to {hi:.1%}; share of resamples under break-even {np.mean(np.array(rates) < BREAK_EVEN):.1%}")
    t = d.groupby("season")["under"].agg(["size", "mean"])
    t = t[t["size"] >= 8]
    print(f"Seasons with 8+ such games: {len(t)}; under above 52.4% in {(t['mean'] > BREAK_EVEN).sum()}. Last 8 seasons:", " ".join(f"{s}:{m:.0%}({n})" for s, n, m in t.tail(8).itertuples()))
    for name, x in [("total 45+", d[d["total_line"] >= 45]), ("total under 45", d[d["total_line"] < 45]),
                    ("Nov-Jan", d[d["gameday"].astype(str).str[5:7].isin(["11", "12", "01"])]), ("Sep-Oct", d[d["gameday"].astype(str).str[5:7].isin(["09", "10"])])]:
        print(line(name, x))
    calm = out[out["wind"] < 10]
    print(f"Baseline, under 10 mph: under {(calm['miss'] < 0).mean():.1%}; the wind effect is the gap, in the same years.")


def wind_forecast(g: pd.DataFrame, first: int = 2021, last: int = 2025) -> None:
    """The wind you could have known: Open-Meteo's archive of its forecast models at each outdoor stadium, at kickoff (free), instead of
    the game-day reading nflverse records. Not the forecast from days before: the models' near-term runs, so about what the close
    could see. This is the test that decides whether there's anything to bet."""
    import requests

    from betlab.sources import weather

    d = g[(g["season"] >= first) & (g["season"] <= last) & g["stadium_id"].notna()].copy()
    v = weather.venues()
    d = d[d["stadium_id"].map(lambda i: (v.get(i) or {}).get("roof") == "outdoors")]
    d["kick"] = pd.to_datetime(d["gameday"].astype(str) + " " + d["gametime"].astype(str)).dt.tz_localize("America/New_York", ambiguous=True, nonexistent="shift_forward").dt.tz_convert("UTC").dt.floor("h")
    s = requests.Session()
    rows = []
    for (stadium, season), x in d.groupby(["stadium_id", "season"]):
        r = s.get("https://historical-forecast-api.open-meteo.com/v1/forecast", timeout=60, params={
            "latitude": v[stadium]["lat"], "longitude": v[stadium]["lon"], "hourly": "wind_speed_10m", "wind_speed_unit": "mph", "timezone": "UTC",
            "start_date": x["kick"].min().strftime("%Y-%m-%d"), "end_date": x["kick"].max().strftime("%Y-%m-%d")})
        if not r.ok:
            continue
        h = r.json().get("hourly") or {}
        at = dict(zip(pd.to_datetime(h.get("time", []), utc=True), h.get("wind_speed_10m", [])))
        rows += [{"game_id": i, "forecast": at.get(k)} for i, k in zip(x["game_id"], x["kick"])]
    f = d.merge(pd.DataFrame(rows), on="game_id").dropna(subset=["forecast"])
    print(f"\nFORECAST WIND at kickoff, outdoor games {first}-{last}: {len(f)} games. Correlation with nflverse's reading: {f['forecast'].corr(f['wind']):.2f}")
    for name, lo, hi in [("forecast under 8", 0, 8), ("8-12", 8, 12), ("12-15", 12, 15), ("15-20", 15, 20), ("15+", 15, 99), ("20+", 20, 99)]:
        print(line(name, f[(f["forecast"] >= lo) & (f["forecast"] < hi)]))
    m = f["gameday"].astype(str).str[5:7]
    print(line("15+, Nov-Jan", f[(f["forecast"] >= 15) & m.isin(["11", "12", "01"])]))
    print(line("15+, Sep-Oct", f[(f["forecast"] >= 15) & m.isin(["09", "10"])]))
    for y, x in f[f["forecast"] >= 15].groupby("season"):
        print(f"  {y}: {len(x)} games, under {(x['miss'] < 0).mean():.0%}")


def referees(g: pd.DataFrame, least: int = 60) -> None:
    d = g[g["referee"].notna()].copy()
    print(f"\nREFEREES, {d['season'].min()}-{d['season'].max()}: a ref's points against the close, split by even and odd seasons")
    rows = []
    for ref, x in d.groupby("referee"):
        a, b = x[x["season"] % 2 == 0], x[x["season"] % 2 == 1]
        if len(a) >= least / 2 and len(b) >= least / 2:
            rows.append({"ref": ref, "n": len(x), "miss": x["miss"].mean(), "se": x["miss"].std(ddof=1) / np.sqrt(len(x)),
                         "even": a["miss"].mean(), "odd": b["miss"].mean(), "under": (x["miss"] < 0).mean()})
    r = pd.DataFrame(rows).sort_values("miss")
    print(f"{len(r)} refs with {least}+ games. Share beyond 2 SE: {(np.abs(r['miss'] / r['se']) >= 2).mean():.0%} (5% by luck alone)")
    print(f"Even-season vs odd-season miss across refs: correlation {r['even'].corr(r['odd']):+.2f} (near 0: nothing persists)")
    print(r.head(4).round(2).to_string(index=False))
    print(r.tail(4).round(2).to_string(index=False))
    # the test that matters: pick each ref's side from the seasons before, bet it next season
    bets = []
    for season in sorted(d["season"].unique()):
        past = d[d["season"] < season].groupby("referee")["miss"].agg(["mean", "std", "count"])
        past = past[past["count"] >= least]
        now = d[d["season"] == season]
        for ref, row in past.iterrows():
            if abs(row["mean"]) / (row["std"] / np.sqrt(row["count"])) < 2:
                continue
            x = now[now["referee"] == ref]
            bets += [{"season": season, "win": (m > 0) == (row["mean"] > 0)} for m in x["miss"]]
    b = pd.DataFrame(bets)
    if len(b):
        p, se = b["win"].mean(), np.sqrt(b["win"].mean() * (1 - b["win"].mean()) / len(b))
        print(f"Walk-forward: bet the side of any ref 2+ SE off in the seasons before: {len(b)} bets, won {p:.1%} (SE {se:.1%}), break-even {BREAK_EVEN:.1%}")


if __name__ == "__main__":
    g = games()
    wind(g)
    wind_check(g)
    wind_forecast(g)
    referees(g)
