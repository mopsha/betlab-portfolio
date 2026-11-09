"""College football data from CollegeFootballData.com (free API key).

History is built once and committed as data/history/ncaaf_games.parquet
(about 70 API calls for 2014 onward); daily runs refresh only the current
season (6 calls). `games()` returns the same columns as the NFL games table,
so the shared football model works unchanged:

  spread_line  home favored by this many points (CFBD's own sign is flipped)
  *_odds       CFBD has lines but not prices, so spreads/totals assume -110
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import requests

from betlab import config

BASE = "https://apinext.collegefootballdata.com"
HISTORY = config.DATA_DIR / "history" / "ncaaf_games.parquet"
ET = "America/New_York"


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).replace(".", "_").lower()


def _get(path: str, **params) -> list[dict]:
    """GET a CFBD endpoint with the Bearer key; failures report the status, never the key."""
    key = config.secret("CFBD_API_KEY")
    if not key:
        raise RuntimeError("CFBD_API_KEY is not set (see .env.example)")
    r = requests.get(BASE + path, params=params, headers={"Authorization": f"Bearer {key}"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"CFBD {path} failed: HTTP {r.status_code} {r.text[:200]}")
    return r.json()


def _frame(rows: list[dict]) -> pd.DataFrame:
    """JSON rows -> DataFrame with snake_case columns."""
    df = pd.json_normalize(rows)
    df.columns = [_snake(c) for c in df.columns]
    return df


def _consensus_lines(rows: list[dict]) -> pd.DataFrame:
    """Median across providers of each game's closing and opening lines."""
    recs = [{"game_id": str(game["id"]), **{_snake(k): v for k, v in line.items()}}
            for game in rows for line in (game.get("lines") or [])]
    cols = ["spread", "spread_open", "over_under", "over_under_open", "home_moneyline", "away_moneyline"]
    if not recs:
        return pd.DataFrame(columns=["game_id"])
    df = pd.DataFrame(recs)
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df else np.nan
    # Moneylines are averaged as probabilities: the median of -110 and +100 as
    # prices would be -5, which isn't a price at all.
    for col in ("home_moneyline", "away_moneyline"):
        df[col] = df[col].where(df[col].abs() >= 100).map(_to_prob)
    agg = df.groupby("game_id")[cols].median().reset_index()
    return pd.DataFrame({
        "game_id": agg["game_id"],
        "spread_line": -agg["spread"], "spread_open": -agg["spread_open"],
        "total_line": agg["over_under"], "total_open": agg["over_under_open"],
        "home_moneyline": agg["home_moneyline"].map(_to_american),
        "away_moneyline": agg["away_moneyline"].map(_to_american),
    })


def _to_prob(american: float) -> float:
    if pd.isna(american):
        return np.nan
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def _to_american(p: float) -> float:
    if pd.isna(p) or not 0 < p < 1:
        return np.nan
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def _season(year: int) -> pd.DataFrame:
    """One season's games (regular + postseason) with consensus lines and each offense's PPA (6 calls)."""
    games, lines, ppa = [], [], []
    for season_type in ("regular", "postseason"):
        games += _get("/games", year=year, seasonType=season_type)
        lines += _get("/lines", year=year, seasonType=season_type)
        ppa += _get("/ppa/games", year=year, seasonType=season_type)
    g = _frame(games)
    out = pd.DataFrame({
        "game_id": g["id"].astype(str), "season": g["season"], "week": g["week"],
        "season_type": g["season_type"], "home_team": g["home_team"], "away_team": g["away_team"],
        "home_div": g.get("home_classification"), "away_div": g.get("away_classification"),
        "home_pts": g["home_points"], "away_pts": g["away_points"],
        "neutral": g["neutral_site"].fillna(False).astype(bool), "venue_id": g.get("venue_id"),
        "kickoff": pd.to_datetime(g["start_date"], utc=True, format="ISO8601").dt.tz_convert(ET),
    })
    out = out.merge(_consensus_lines(lines), on="game_id", how="left")
    if ppa:
        p = _frame(ppa)
        p = pd.DataFrame({"game_id": p["game_id"].astype(str), "team": p["team"], "epa": p["offense_overall"]})
        out = out.merge(p.rename(columns={"team": "home_team", "epa": "home_epa"}), on=["game_id", "home_team"], how="left")
        out = out.merge(p.rename(columns={"team": "away_team", "epa": "away_epa"}), on=["game_id", "away_team"], how="left")
    return out


SCHOOL_ALIASES = {  # sportsbook spelling -> CFBD school
    "Appalachian State": "App State",
    "UMass": "Massachusetts",
    "LIU": "Long Island University",
    "William and Mary": "William & Mary",
}
TEAMS = config.DATA_DIR / "history" / "ncaaf_teams.parquet"
VENUES = config.DATA_DIR / "history" / "ncaaf_venues.parquet"


def refresh_reference() -> None:
    """Teams (school + mascot, to match sportsbook names) and venues (state, for NY rules)."""
    TEAMS.parent.mkdir(parents=True, exist_ok=True)
    t = _frame(_get("/teams"))
    t[["school", "mascot"]].to_parquet(TEAMS, index=False)
    v = _frame(_get("/venues"))
    cols = ["id", "state", "name", "latitude", "longitude", "dome"]  # location and roof: kickoff weather
    v[[c for c in cols if c in v]].rename(columns={"id": "venue_id"}).to_parquet(VENUES, index=False)


def _plain(name: str) -> str:
    """Lowercase, accents and punctuation removed: 'San José State' -> 'sanjosestate'."""
    import unicodedata
    ascii_name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def team_names() -> dict[str, str]:
    """Map sportsbook names ('Alabama Crimson Tide') to CFBD schools ('Alabama').

    Exact 'school mascot' matches first; otherwise the longest school name the
    sportsbook name starts with. Built lazily per name via a dict subclass.
    """
    teams = pd.read_parquet(TEAMS)
    full = {_plain(f"{s} {m}"): s for s, m in zip(teams["school"], teams["mascot"]) if m}
    schools = sorted(((_plain(s), s) for s in teams["school"]), key=lambda x: -len(x[0]))
    # Where sportsbooks and CFBD spell a school differently
    schools = [(_plain(book), cfbd_name) for book, cfbd_name in SCHOOL_ALIASES.items()] + schools

    class Lookup(dict):
        def __missing__(self, name):
            key = _plain(name)
            school = full.get(key) or next((s for p, s in schools if p and key.startswith(p)), None)
            self[name] = school
            return school

        def get(self, name, default=None):
            return self[name] if self[name] is not None else default

    return Lookup()


def build_history(first: int = 2014, last: int | None = None) -> pd.DataFrame:
    """Download every season from first to last (6 calls each) and save the history file."""
    last = last or pd.Timestamp.now(tz=ET).year
    return _save(pd.concat([_season(y) for y in range(first, last + 1)], ignore_index=True))


def refresh_current() -> pd.DataFrame:
    """Replace this season's rows in the history file with a fresh download (6 calls)."""
    year = pd.Timestamp.now(tz=ET).year
    hist = pd.read_parquet(HISTORY)
    return _save(pd.concat([hist[hist["season"] != year], _season(year)], ignore_index=True))


ADVANCED = config.DATA_DIR / "history" / "ncaaf_advanced.parquet"


def _advanced_season(year: int) -> pd.DataFrame:
    """One season's per-game advanced stats for every offense (2 calls): plays, EPA (CFBD's
    PPA) and success rate overall and by pass/run, explosiveness, line yards, stuff rate.
    One row per (game, offense); the defense's numbers are the opponent's offense row."""
    rows = []
    for season_type in ("regular", "postseason"):
        rows += _get("/stats/game/advanced", year=year, seasonType=season_type)
    out = []
    for r in rows:
        o = r.get("offense") or {}
        rp, pp = o.get("rushingPlays") or {}, o.get("passingPlays") or {}
        n = lambda d: (d.get("totalPPA") / d["ppa"]) if d.get("ppa") not in (None, 0) and d.get("totalPPA") is not None else np.nan
        out.append({"game_id": str(r["gameId"]), "season": r["season"], "week": r["week"], "team": r["team"],
                    "opp": r["opponent"], "plays": o.get("plays"), "drives": o.get("drives"), "epa": o.get("ppa"),
                    "success": o.get("successRate"), "explosiveness": o.get("explosiveness"),
                    "stuff_rate": o.get("stuffRate"), "line_yards": o.get("lineYards"),
                    "rush_epa": rp.get("ppa"), "rush_success": rp.get("successRate"), "rushes": n(rp),
                    "pass_epa": pp.get("ppa"), "pass_success": pp.get("successRate"), "dropbacks": n(pp),
                    "pd_success": (o.get("passingDowns") or {}).get("successRate"),
                    "sd_success": (o.get("standardDowns") or {}).get("successRate")})
    return pd.DataFrame(out)


def build_advanced(first: int = 2014, last: int | None = None) -> pd.DataFrame:
    """Download every season's advanced game stats (2 calls each) and save them."""
    last = last or int(pd.Timestamp.now(tz=ET).year)
    df = pd.concat([_advanced_season(y) for y in range(first, last + 1)], ignore_index=True)
    ADVANCED.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ADVANCED, index=False)
    return df


def refresh_advanced_current() -> pd.DataFrame:
    """Replace this season's advanced stats with a fresh download (2 calls)."""
    year = int(pd.Timestamp.now(tz=ET).year)
    old = pd.read_parquet(ADVANCED) if ADVANCED.exists() else pd.DataFrame()
    new = _advanced_season(year)
    df = pd.concat([old[old["season"] != year] if len(old) else old, new], ignore_index=True)
    df.to_parquet(ADVANCED, index=False)
    return df


def advanced() -> pd.DataFrame:
    """The saved advanced game stats (see build_advanced)."""
    return pd.read_parquet(ADVANCED)


def _save(df: pd.DataFrame) -> pd.DataFrame:
    """Write the committed history file."""
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(HISTORY, index=False)
    return df


def games() -> pd.DataFrame:
    """The committed history as a model-ready games table: games involving an FBS team.

    Division II/III games have no lines and would only add hundreds of teams to
    the ratings. Bowl games get weeks 21+ so they never merge with week 1.
    """
    df = pd.read_parquet(HISTORY)
    df = df[(df["home_div"] == "fbs") | (df["away_div"] == "fbs")].copy()
    df["week"] = np.where(df["season_type"] == "postseason", df["week"] + 20, df["week"])
    # A real two-way market's implied probabilities add up to 98-120%; anything else is bad data.
    # (The history was rebuilt on 2026-09-25 with moneylines averaged as probabilities, which
    # left 2 such pairs of 4,447; the old price-median history had 51.)
    implied = df["home_moneyline"].map(_to_prob) + df["away_moneyline"].map(_to_prob)
    sane = implied.between(0.98, 1.20)
    df.loc[~sane, ["home_moneyline", "away_moneyline"]] = np.nan
    if VENUES.exists():
        states = pd.read_parquet(VENUES).set_index("venue_id")["state"]
        df["venue_state"] = df["venue_id"].map(states)
    df["date"] = df["kickoff"].dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    df["margin"] = df["home_pts"] - df["away_pts"]
    df["total"] = df["home_pts"] + df["away_pts"]
    for col, line in (("home_spread_odds", "spread_line"), ("away_spread_odds", "spread_line"),
                      ("over_odds", "total_line"), ("under_odds", "total_line")):
        df[col] = np.where(df[line].notna(), -110.0, np.nan)
    # days since each team's previous game, for the rest adjustment
    long = pd.concat([df[["game_id", "date", "home_team"]].rename(columns={"home_team": "team"}),
                      df[["game_id", "date", "away_team"]].rename(columns={"away_team": "team"})])
    long = long.sort_values("date")
    long["rest"] = long.groupby("team")["date"].diff().dt.days.clip(upper=14)
    rest = long.set_index(["game_id", "team"])["rest"]
    df["home_rest"] = rest.reindex(list(zip(df["game_id"], df["home_team"]))).to_numpy()
    df["away_rest"] = rest.reindex(list(zip(df["game_id"], df["away_team"]))).to_numpy()
    return df.sort_values(["date", "game_id"]).reset_index(drop=True)
