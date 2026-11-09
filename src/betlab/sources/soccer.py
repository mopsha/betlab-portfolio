"""Soccer results, shots and closing odds from football-data.co.uk (free CSVs, no key).

One file per league and season: `https://www.football-data.co.uk/mmz4281/<2425>/<E0>.csv`
for the big five (MLS and other "extra" leagues come as one file per league:
`https://www.football-data.co.uk/new/USA.csv`). Each match row has the score, shots on
target (big five), and many books' odds, both earlier in the week and at the close:

- **Pinnacle** (`PSH/PSD/PSA` earlier in the week, `PSCH/PSCD/PSCA` at the close; over/under
  2.5 `P>2.5`, `PC>2.5`; Asian handicap `AHh`/`AHCh` with `PAHH`, `PCAHH`). Pinnacle stopped
  public odds in 2025, so its closing columns run through 2024-25 and part of 2025-26.
- **Betfair Exchange** closing (`BFECH/BFECD/BFECA`, from 2024-25) and the **average of the
  books** at the close (`AvgCH`...): the sharp reference after Pinnacle.

Files are cached under data/cache/soccer/ (not committed). Past seasons never change; the
current one is re-downloaded after CURRENT_HOURS (2: the files are ~40 KB and free; at 12, the 02:53 UTC grade's
copy from before the weekend's update was still "fresh" for the 9:55 AM daily on Oct 20, which graded no soccer line).
"""

from __future__ import annotations

import io
import time

import numpy as np
import pandas as pd
import requests

from betlab import config

BASE = "https://www.football-data.co.uk"
CACHE = config.DATA_DIR / "cache" / "soccer"
CURRENT_HOURS = 2.0
# BetLab league key -> football-data.co.uk division code (big five: one file per season)
DIVISIONS = {"epl": "E0", "la_liga": "SP1", "serie_a": "I1", "bundesliga": "D1", "ligue_1": "F1"}
EXTRA = {"mls": "USA"}  # one file for every season
NAMES = {"epl": "Premier League", "la_liga": "La Liga", "serie_a": "Serie A", "bundesliga": "Bundesliga",
         "ligue_1": "Ligue 1", "mls": "MLS"}


def season_code(season: int) -> str:
    """2025 (the season ending in 2025, i.e. 2024-25) -> '2425'."""
    return f"{(season - 1) % 100:02d}{season % 100:02d}"


def current_season(today: pd.Timestamp | None = None) -> int:
    """European seasons are named by the year they end (Jul 1 flips)."""
    today = today or pd.Timestamp.now(tz="America/New_York")
    return today.year + 1 if today.month >= 7 else today.year


def _get(url: str, name: str, max_age_hours: float) -> pd.DataFrame:
    path = CACHE / name
    if path.exists() and (time.time() - path.stat().st_mtime) / 3600 < max_age_hours:
        return pd.read_csv(path, encoding="latin-1")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return pd.read_csv(io.BytesIO(r.content), encoding="latin-1")


def _odds(df: pd.DataFrame, cols) -> np.ndarray:
    return np.column_stack([pd.to_numeric(df[c], errors="coerce") if c in df else np.full(len(df), np.nan) for c in cols])


def load(league: str, seasons) -> pd.DataFrame:
    """Matches for one league: date, season, home, away, hg, ag, hst, ast (shots on target;
    NaN where not recorded), and odds: pin_open_* / pin_close_* (1X2, decimal), bfx_close_*
    (Betfair Exchange), avg_close_*, pin_open_o25/u25, pin_close_o25/u25, ah_line_close
    (home handicap) with pin_close_ah_h/a. Sorted by date."""
    frames = []
    if league in EXTRA:
        raw = _get(f"{BASE}/new/{EXTRA[league]}.csv", f"{EXTRA[league]}.csv", CURRENT_HOURS)
        raw = raw[raw["Season"].astype(int).isin([int(s) for s in seasons])]
        raw = raw.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG"})
        raw["season"] = raw["Season"].astype(int)
        frames.append(raw)
    else:
        for s in seasons:
            code = season_code(s)
            age = CURRENT_HOURS if s >= current_season() else 24 * 365
            try:
                raw = _get(f"{BASE}/mmz4281/{code}/{DIVISIONS[league]}.csv", f"{DIVISIONS[league]}_{code}.csv", age)
            except requests.HTTPError:
                continue
            frames.append(raw.copy().assign(season=s))   # copy: one block, no fragmentation warning per season
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.lstrip("﻿").lstrip("ï»¿") for c in df.columns]
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    out = pd.DataFrame({
        "league": league, "season": df["season"].astype(int),
        "date": pd.to_datetime(df["Date"], format="mixed", dayfirst=True, errors="coerce"),
        "home": df["HomeTeam"].str.strip(), "away": df["AwayTeam"].str.strip(),
        "hg": df["FTHG"].astype(int), "ag": df["FTAG"].astype(int),
        "hst": pd.to_numeric(df.get("HST"), errors="coerce") if "HST" in df else np.nan,
        "ast": pd.to_numeric(df.get("AST"), errors="coerce") if "AST" in df else np.nan,
    })
    for prefix, cols in (("pin_open", ("PSH", "PSD", "PSA")), ("pin_close", ("PSCH", "PSCD", "PSCA")),
                         ("bfx_close", ("BFECH", "BFECD", "BFECA")), ("avg_close", ("AvgCH", "AvgCD", "AvgCA"))):
        o = _odds(df, cols)
        for i, side in enumerate(("h", "d", "a")):
            out[f"{prefix}_{side}"] = o[:, i]
    for name, cols in (("pin_open", ("P>2.5", "P<2.5")), ("pin_close", ("PC>2.5", "PC<2.5")),
                       ("avg_close", ("AvgC>2.5", "AvgC<2.5"))):
        o = _odds(df, cols)
        out[f"{name}_o25"], out[f"{name}_u25"] = o[:, 0], o[:, 1]
    o = _odds(df, ("AHCh", "PCAHH", "PCAHA"))
    out["ah_line_close"], out["pin_close_ah_h"], out["pin_close_ah_a"] = o[:, 0], o[:, 1], o[:, 2]
    return out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def no_vig(odds: np.ndarray) -> np.ndarray:
    """Decimal odds (n, k) -> no-vig probabilities, proportional (NaN rows stay NaN)."""
    inv = 1.0 / odds
    return inv / inv.sum(axis=1, keepdims=True)


def closing_1x2(m: pd.DataFrame) -> np.ndarray:
    """The sharp close for each match: Pinnacle, else Betfair Exchange, else the books' average."""
    out = np.full((len(m), 3), np.nan)
    for prefix in ("avg_close", "bfx_close", "pin_close"):   # later sources win
        o = m[[f"{prefix}_h", f"{prefix}_d", f"{prefix}_a"]].to_numpy(float)
        ok = np.isfinite(o).all(axis=1) & (o > 1).all(axis=1)
        out[ok] = no_vig(o[ok])
    return out


# ---------------------------------------------------------------- matching books' names to these files
_STOP = {"fc", "cf", "afc", "sc", "ac", "as", "ss", "club", "cd", "ud", "rc", "sd", "sv", "vfb", "vfl", "tsg",
         "fsv", "de", "the", "1", "calcio", "05", "04"}


def _clean(name: str) -> str:
    import re
    import unicodedata

    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(w for w in s.split() if w not in _STOP)


def similarity(a: str, b: str) -> float:
    """How alike two team names are ('Manchester City' vs 'Man City' ~0.8, same name ~1.45)."""
    import difflib

    a, b = _clean(a), _clean(b)
    r = difflib.SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    if ta & tb:
        r += 0.25 * len(ta & tb) / max(len(ta), len(tb))
    if a and b and (a.startswith(b) or b.startswith(a)):
        r += 0.2
    return r


# Sportsbook names the similarity score sends to the wrong club ("Paris Saint Germain" scored 0.70 for Paris FC
# and 0.68 for Paris SG, so PSG v Le Mans on Oct 10 found no result): mapped straight to football-data's name.
ALIASES = {"Paris Saint Germain": "Paris SG", "Paris Saint-Germain": "Paris SG"}


def find_match(fd: pd.DataFrame, home: str, away: str, kickoff) -> pd.Series | None:
    """The football-data row for a sportsbook fixture. Each name first resolves to its
    single best-matching club in the file (so 'Leeds United' is Leeds, never Man United),
    then the fixture must be those two clubs within a day of the kickoff. None otherwise,
    or if either name fits nothing well (similarity under 0.5)."""
    if fd.empty:
        return None
    kickoff = pd.Timestamp(kickoff)
    day = (kickoff.tz_convert("UTC") if kickoff.tzinfo else kickoff).tz_localize(None).normalize()
    clubs = sorted(set(fd["home"]) | set(fd["away"]))
    best = lambda name: max(clubs, key=lambda c: similarity(name, c))
    home, away = ALIASES.get(home, home), ALIASES.get(away, away)
    bh, ba = best(home), best(away)
    if similarity(home, bh) < 0.5 or similarity(away, ba) < 0.5 or bh == ba:
        return None
    cand = fd[(fd["home"] == bh) & (fd["away"] == ba) & ((fd["date"] - day).abs() <= pd.Timedelta(days=1))]
    return cand.iloc[0] if len(cand) else None


def postponed(league: str, home: str, away: str, kickoff) -> pd.Timestamp | None:
    """The date a fixture was actually played when it was moved 2-14 days after the kickoff the books listed
    (NY Red Bulls v St. Louis, listed Sep 26, played Oct 1), else None. Books void a postponed match's bets."""
    kickoff = pd.Timestamp(kickoff)
    season = kickoff.year if league in EXTRA else current_season(kickoff.tz_convert("America/New_York"))
    fd = load(league, [season])
    for days in range(2, 15):
        m = find_match(fd, home, away, kickoff + pd.Timedelta(days=days)) if len(fd) else None
        if m is not None:
            return pd.Timestamp(m["date"])
    return None


def closing_source(row: pd.Series) -> str | None:
    """Which sharp close closing_1x2 used for a row."""
    for prefix, label in (("pin_close", "Pinnacle"), ("bfx_close", "Betfair Exchange"), ("avg_close", "books' average")):
        o = [row.get(f"{prefix}_{s}") for s in "hda"]
        if all(pd.notna(x) and x > 1 for x in o):
            return label
    return None


def result(league: str, home: str, away: str, kickoff) -> dict | None:
    """Score and sharp closing 1X2 chances for a finished fixture, or None if the file
    doesn't have it yet (the current season's files update a few times a week)."""
    kickoff = pd.Timestamp(kickoff)
    season = kickoff.year if league in EXTRA else current_season(kickoff.tz_convert("America/New_York"))
    fd = load(league, [season])
    if fd.empty:
        return None
    m = find_match(fd, home, away, kickoff)
    if m is None:
        return None
    close = closing_1x2(m.to_frame().T)[0]
    return {"hg": int(m["hg"]), "ag": int(m["ag"]), "fd_home": m["home"], "fd_away": m["away"],
            "close": None if not np.isfinite(close).all() else tuple(float(x) for x in close),
            "close_source": closing_source(m)}
