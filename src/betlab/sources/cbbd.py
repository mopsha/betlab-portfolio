"""College basketball from CollegeBasketballData (api.collegebasketballdata.com).

Same author and key as CollegeFootballData (`CFBD_API_KEY`). Seasons are named by the
year they end (2026 = 2025-26). The API returns at most 3,000 rows a call, so each
season is fetched in date windows. Everything is saved under data/history/ (committed,
like the college football history) so a season is downloaded once.

- **Games:** date, teams and conferences, neutral site, score, tournament, and CBBD's
  pregame Elo for both teams (a free baseline rating).
- **Team games:** per team per game: possessions, pace, offensive rating, the four
  factors (eFG%, turnover %, offensive rebound %, free-throw rate), points.
- **Venue:** city and state, so New York's rule (no college games played in New York,
  Madison Square Garden and Barclays included) can be checked from the schedule.
- **Teams:** school, mascot and display name ("Duke Blue Devils", the sportsbooks' style),
  for matching the odds feed's names (`team_names`).
- **Players and rosters** (the early-season roster shift, models/ncaab.roster_value):
  every player's season line (games, minutes, PORPAG: 1 call a season, `players`), CBBD's
  rosters for past seasons, and this season's from ESPN's free roster pages
  (`refresh_rosters`, every few days Oct–Dec). Player ids are ESPN's in both.
- **Live:** `refresh_recent` re-downloads the last 10 days and the coming week (about 3
  calls) into the saved files, so the season's ratings, venues and closing lines stay
  current without re-fetching the season.
- **Lines:** per game, the median across providers of the closing spread and total and the
  moneylines (averaged as probabilities), and the opening spread and total where a
  provider has one. Openers exist only from 2025-26 (Bovada, DraftKings); earlier seasons
  have closing lines only (ESPN BET, TeamRankings, a consensus).
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import requests

from betlab import config

BASE = "https://api.collegebasketballdata.com"
HISTORY = config.DATA_DIR / "history"
GAMES = HISTORY / "ncaab_games.parquet"
TEAM_GAMES = HISTORY / "ncaab_team_games.parquet"
TEAMS = HISTORY / "ncaab_teams.parquet"
ET = "America/New_York"


def current_season(today: pd.Timestamp | None = None) -> int:
    """Seasons are named by the year they end; August flips to the next one."""
    today = today or pd.Timestamp.now(tz=ET)
    return today.year + 1 if today.month >= 8 else today.year


def _get(path: str, **params) -> list[dict]:
    key = config.secret("CFBD_API_KEY")
    if not key:
        raise RuntimeError("CFBD_API_KEY is not set (the basketball API uses the same key)")
    for wait in (2, 5, 0):   # a 502 now and then (Nov 6 stopped the daily's refresh): ask again
        r = requests.get(BASE + path, params=params, headers={"Authorization": f"Bearer {key}"}, timeout=120)
        if r.status_code < 500 or not wait:
            break
        time.sleep(wait)
    r.raise_for_status()
    return r.json()


def _windows(season: int, days: int) -> list[tuple[str, str]]:
    """Date windows covering a season (Nov 1 to Apr 15). Each window ends where the next one
    starts: the API reads an end date as midnight UTC, so back-to-back windows lost the
    boundary day's games (found 2026-09-26). Rows seen twice are dropped in _fetch."""
    start, end = pd.Timestamp(f"{season - 1}-11-01"), pd.Timestamp(f"{season}-04-16")
    out = []
    while start < end:
        stop = min(start + pd.Timedelta(days=days), end)
        out.append((start.strftime("%Y-%m-%d"), stop.strftime("%Y-%m-%d")))
        start = stop
    return out


def _fetch(path: str, season: int, days: int, windows: list[tuple[str, str]] | None = None) -> list[dict]:
    rows, seen = [], set()
    for a, b in windows or _windows(season, days):
        batch = _get(path, season=season, startDateRange=a, endDateRange=b)
        if len(batch) >= 3000:
            raise RuntimeError(f"{path} {a}..{b} hit the 3,000-row cap; use shorter windows")
        for r in batch:
            k = (r.get("id") or r.get("gameId"), r.get("teamId"))
            if k not in seen:
                seen.add(k)
                rows.append(r)
    return rows


def _prob(american):
    if american is None or pd.isna(american) or abs(american) < 100:
        return np.nan
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def _american(p):
    if pd.isna(p) or not 0 < p < 1:
        return np.nan
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def season_games(season: int, windows=None) -> pd.DataFrame:
    g = pd.DataFrame(_fetch("/games", season, 31, windows))
    if g.empty:
        return g
    return pd.DataFrame({
        "game_id": g["id"].astype(str), "season": season, "season_type": g["seasonType"],
        "tournament": g["tournament"], "start": pd.to_datetime(g["startDate"], utc=True),
        "neutral": g["neutralSite"].fillna(False).astype(bool), "conference_game": g["conferenceGame"],
        "home_team": g["homeTeam"], "away_team": g["awayTeam"], "home_conf": g["homeConference"],
        "away_conf": g["awayConference"], "home_pts": g["homePoints"], "away_pts": g["awayPoints"],
        "home_elo": g["homeTeamEloStart"], "away_elo": g["awayTeamEloStart"], "status": g["status"],
        "venue": g.get("venue"), "city": g.get("city"), "state": g.get("state"),
    })


def season_lines(season: int, windows=None) -> pd.DataFrame:
    rows = []
    for game in _fetch("/lines", season, 31, windows):
        for ln in game.get("lines") or []:
            rows.append({"game_id": str(game["gameId"]), "provider": ln.get("provider"),
                         "spread": ln.get("spread"), "total": ln.get("overUnder"),
                         "spread_open": ln.get("spreadOpen"), "total_open": ln.get("overUnderOpen"),
                         "home_p": _prob(ln.get("homeMoneyline")), "away_p": _prob(ln.get("awayMoneyline"))})
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["game_id"])
    for c in ("spread", "total", "spread_open", "total_open"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    agg = df.groupby("game_id").agg(spread=("spread", "median"), total=("total", "median"),
                                    spread_open=("spread_open", "median"), total_open=("total_open", "median"),
                                    home_p=("home_p", "median"), away_p=("away_p", "median"),
                                    providers=("provider", lambda s: ",".join(sorted(set(map(str, s))))))
    return pd.DataFrame({"game_id": agg.index, "spread_line": -agg["spread"].to_numpy(),  # home expected margin
                         "total_line": agg["total"].to_numpy(), "spread_open": -agg["spread_open"].to_numpy(),
                         "total_open": agg["total_open"].to_numpy(),
                         "home_moneyline": [_american(p) for p in agg["home_p"]],
                         "away_moneyline": [_american(p) for p in agg["away_p"]],
                         "providers": agg["providers"].to_numpy()})


def season_team_games(season: int, windows=None) -> pd.DataFrame:
    rows = []
    for r in _fetch("/games/teams", season, 15, windows):
        t, o = r.get("teamStats") or {}, r.get("opponentStats") or {}
        ff, off = t.get("fourFactors") or {}, o.get("fourFactors") or {}
        rows.append({"game_id": str(r["gameId"]), "season": season, "team": r["team"], "opp": r["opponent"],
                     "is_home": r["isHome"], "neutral": r["neutralSite"], "minutes": r.get("gameMinutes"),
                     "pace": r.get("pace"), "poss": t.get("possessions"), "pts": (t.get("points") or {}).get("total"),
                     "opp_pts": (o.get("points") or {}).get("total"), "ortg": t.get("rating"), "drtg": o.get("rating"),
                     "efg": ff.get("effectiveFieldGoalPct"), "tov": ff.get("turnoverRatio"),
                     "orb": ff.get("offensiveReboundPct"), "ftr": ff.get("freeThrowRate"),
                     "opp_efg": off.get("effectiveFieldGoalPct"), "opp_tov": off.get("turnoverRatio"),
                     "opp_orb": off.get("offensiveReboundPct"), "opp_ftr": off.get("freeThrowRate"),
                     "start": r.get("startDate")})
    df = pd.DataFrame(rows)
    if len(df):
        df["start"] = pd.to_datetime(df["start"], utc=True, format="ISO8601")
    return df


def build_history(first: int = 2022, last: int = 2026) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download seasons first..last (about 25 calls each) and save both files."""
    games, teams = [], []
    for s in range(first, last + 1):
        g = season_games(s)
        games.append(g.merge(season_lines(s), on="game_id", how="left"))
        teams.append(season_team_games(s))
        print(f"  ncaab {s}: {len(g)} games", flush=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    gdf, tdf = pd.concat(games, ignore_index=True), pd.concat(teams, ignore_index=True)
    gdf.to_parquet(GAMES, index=False)
    tdf.to_parquet(TEAM_GAMES, index=False)
    return gdf, tdf


def refresh_recent(days_back: int = 10, days_ahead: int = 7, today: pd.Timestamp | None = None) -> int:
    """Re-download the last `days_back` days and the next `days_ahead` of the current season
    (games with venues, lines, team box scores: about 3 calls) and replace those games in
    the saved files. Returns the number of games refreshed."""
    today = (today or pd.Timestamp.now(tz=ET)).tz_localize(None).normalize() if (today or pd.Timestamp.now(tz=ET)).tzinfo \
        else (today or pd.Timestamp.now()).normalize()
    season = current_season(pd.Timestamp(today).tz_localize(ET))
    win = [((today - pd.Timedelta(days=days_back)).strftime("%Y-%m-%d"),
            (today + pd.Timedelta(days=days_ahead + 1)).strftime("%Y-%m-%d"))]
    g = season_games(season, win)
    if g.empty:
        return 0
    new = g.merge(season_lines(season, win), on="game_id", how="left")
    tg = season_team_games(season, win)
    old = pd.read_parquet(GAMES) if GAMES.exists() else pd.DataFrame()
    games_df = pd.concat([old[~old["game_id"].isin(new["game_id"])] if len(old) else old, new], ignore_index=True)
    games_df.to_parquet(GAMES, index=False)
    if len(tg):
        old_t = pd.read_parquet(TEAM_GAMES) if TEAM_GAMES.exists() else pd.DataFrame()
        pd.concat([old_t[~old_t["game_id"].isin(tg["game_id"])] if len(old_t) else old_t, tg],
                  ignore_index=True).to_parquet(TEAM_GAMES, index=False)
    return len(new)


# ---------------------------------------------------------------- players and rosters (early-season ratings)
PLAYERS = HISTORY / "ncaab_players.parquet"
ROSTERS = HISTORY / "ncaab_rosters.parquet"
RECRUITS = HISTORY / "ncaab_recruits.parquet"   # recruiting classes (247 composite rating), for freshmen
ESPN_ROSTER = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{}/roster"
ROSTER_COLUMNS = ["season", "team", "espn_team", "player_id", "name", "source", "fetched_at"]


def season_players(season: int) -> pd.DataFrame:
    """Every Division I player's season line (1 call): games, minutes and PORPAG (points over
    a replacement player per game). player_id is ESPN's athlete id, as in the rosters."""
    d = pd.DataFrame(_get("/stats/player/season", season=season))
    if d.empty:
        return d
    return pd.DataFrame({"season": season, "team": d["team"], "player_id": d["athleteSourceId"].astype(str),
                         "name": d["name"], "games": d["games"], "minutes": d["minutes"], "porpag": d["PORPAG"]})


def players(seasons=None) -> pd.DataFrame:
    """Saved player seasons; any season in `seasons` not saved yet is downloaded (1 call each)."""
    have = pd.read_parquet(PLAYERS) if PLAYERS.exists() else pd.DataFrame(columns=["season"])
    missing = [s for s in (seasons or []) if s not in set(have["season"])]
    if missing:
        have = pd.concat([x for x in [have] + [season_players(s) for s in missing] if len(x)], ignore_index=True)
        HISTORY.mkdir(parents=True, exist_ok=True)
        have.to_parquet(PLAYERS, index=False)
    return have


def season_roster(season: int) -> pd.DataFrame:
    """CBBD's rosters for a season (1 call; empty until CBBD fills it, weeks into the season)."""
    rows = [{"season": season, "team": t["team"], "espn_team": str(t.get("teamSourceId")), "player_id": str(p["sourceId"]),
             "name": p.get("name"), "source": "cbbd"}
            for t in _get("/teams/roster", season=season) for p in t.get("players") or []]
    return pd.DataFrame(rows, columns=ROSTER_COLUMNS)


def espn_roster(season: int, teams: pd.DataFrame, pause: float = 0.1) -> pd.DataFrame:
    """This season's rosters from ESPN (free, one request per team, preseason included).
    teams: (team, espn_team) pairs, from an earlier season's CBBD roster."""
    import time

    rows = []
    for t in teams.itertuples():
        try:
            r = requests.get(ESPN_ROSTER.format(t.espn_team), timeout=30)
            r.raise_for_status()
            d = r.json()
        except (requests.RequestException, ValueError):
            continue
        if (d.get("season") or {}).get("year") == season:
            rows += [{"season": season, "team": t.team, "espn_team": t.espn_team, "player_id": str(p["id"]),
                      "name": p.get("displayName"), "source": "espn"} for p in d.get("athletes") or []]
        time.sleep(pause)
    return pd.DataFrame(rows, columns=ROSTER_COLUMNS)


def rosters() -> pd.DataFrame:
    return pd.read_parquet(ROSTERS) if ROSTERS.exists() else pd.DataFrame(columns=ROSTER_COLUMNS)


def refresh_rosters(season: int | None = None, max_age_days: int = 3, now: pd.Timestamp | None = None) -> int:
    """Keep this season's rosters (ESPN, every few days: its preseason pages fill in through
    October) and last season's player lines saved, for the roster adjustment
    (models/ncaab.roster_value). Returns the teams with a roster."""
    now = now or pd.Timestamp.now(tz="UTC")
    season = season or current_season()
    players([season - 1])
    recruits([season - 1])                     # this season's freshmen (1 call, once)
    ro = rosters()
    cur = ro[ro["season"] == season]
    if len(cur) and (now - pd.Timestamp(cur["fetched_at"].iloc[0])).days < max_age_days:
        return int(cur["team"].nunique())
    earlier = ro[ro["season"] < season]
    if earlier.empty:
        return 0
    base = earlier[earlier["season"] == earlier["season"].max()].drop_duplicates("team")[["team", "espn_team"]]
    new = espn_roster(season, base)
    if new.empty:
        return int(cur["team"].nunique())
    new["fetched_at"] = now.isoformat(timespec="seconds")
    pd.concat([x for x in (ro[ro["season"] != season], new) if len(x)], ignore_index=True)[ROSTER_COLUMNS].to_parquet(
        ROSTERS, index=False)
    return int(new["team"].nunique())


def recruits(years=None, refresh: bool = False) -> pd.DataFrame:
    """Recruiting classes (CBBD /recruiting/players, 1 call a year, saved): year (the class enters season year + 1),
    name, team (committed school, CBBD's name), stars, rating (247 composite, 0-1), ranking. `years` are fetched
    when missing (or all of them with `refresh`); the saved file is returned."""
    old = pd.read_parquet(RECRUITS) if RECRUITS.exists() else pd.DataFrame(columns=["year"])
    todo = [y for y in (years or []) if refresh or y not in set(old["year"].astype(int))]
    if not todo:
        return old
    rows = [{"year": y, "name": r.get("name"), "team": (r.get("committedTo") or {}).get("name"), "stars": r.get("stars"),
             "rating": r.get("rating"), "ranking": r.get("ranking")} for y in todo for r in _get("/recruiting/players", year=y)]
    new = pd.concat([old[~old["year"].astype(int).isin(todo)], pd.DataFrame(rows)], ignore_index=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    new.to_parquet(RECRUITS, index=False)
    return new


def teams(season: int | None = None, refresh: bool = False) -> pd.DataFrame:
    """Division I teams: school, mascot, display name, conference (1 call, saved)."""
    if TEAMS.exists() and not refresh:
        return pd.read_parquet(TEAMS)
    t = pd.DataFrame(_get("/teams", season=season or current_season()))
    out = pd.DataFrame({"school": t["school"], "mascot": t["mascot"], "display": t["displayName"],
                        "conference": t["conference"]})
    HISTORY.mkdir(parents=True, exist_ok=True)
    out.to_parquet(TEAMS, index=False)
    return out


ALIASES = {  # the odds feed's spelling -> CBBD school, where abbreviations don't explain it
    "Arkansas-Little Rock Trojans": "Little Rock", "CSU Bakersfield Roadrunners": "Cal State Bakersfield",
    "CSU Fullerton Titans": "Cal State Fullerton", "CSU Northridge Matadors": "Cal State Northridge",
    "Florida Int'l Golden Panthers": "Florida International", "Gardner-Webb Bulldogs": "Gardner-Webb",
    "Grand Canyon Antelopes": "Grand Canyon", "IUPUI Jaguars": "IU Indianapolis",
    "Loyola (MD) Greyhounds": "Loyola Maryland", "Maryland-Eastern Shore Hawks": "Maryland Eastern Shore",
    "Prairie View Panthers": "Prairie View A&M", "SIU-Edwardsville Cougars": "SIU Edwardsville",
    "Seattle Redhawks": "Seattle U", "St. Thomas (MN) Tommies": "St. Thomas-Minnesota",
    "Tenn-Martin Skyhawks": "UT Martin", "Texas A&M-CC Islanders": "Texas A&M-Corpus Christi",
    "UMKC Kangaroos": "Kansas City", "UT-Arlington Mavericks": "UT Arlington", "Boston Univ. Terriers": "Boston University",
    "Appalachian St Mountaineers": "App State", "Mt. St. Mary's Mountaineers": "Mount St. Mary's",
    "N Colorado Bears": "Northern Colorado", "SE Missouri St Redhawks": "Southeast Missouri State",
    "Miss Valley St Delta Devils": "Mississippi Valley State", "St John's Red Storm": "St. John's",
    "LIU Sharks": "Long Island University", "Albany Great Danes": "UAlbany",
    "American Eagles": "American University", "Army Knights": "Army", "Cal Baptist Lancers": "California Baptist",
    "Grambling St Tigers": "Grambling", "Long Beach St 49ers": "Long Beach State", "Nicholls St Colonels": "Nicholls",
    "Sam Houston St Bearkats": "Sam Houston",
    # Nov 9 (week 1 review: unmatched all week, 6 and 38 times, so their games got no card or read)
    "Fort Wayne Mastodons": "Purdue Fort Wayne", "GW Revolutionaries": "George Washington",
}


def _norm(name: str) -> str:
    """Lowercase letters and digits; the feed's abbreviations expanded ('Florida St' ->
    'florida state', 'Int'l' -> 'international'); a leading 'St.' (St. John's) is left alone."""
    import re
    import unicodedata

    t = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    t = t.replace("int'l", "international").replace("univ.", "university")
    words = re.sub(r"[^a-z0-9& ]", " ", t).split()
    return " ".join("state" if w == "st" and i > 0 else w for i, w in enumerate(words))


def team_names(t: pd.DataFrame | None = None, feed_names=None) -> dict[str, str]:
    """Sportsbook name -> CBBD school. Exact on the display name ("Duke Blue Devils") or
    "school mascot" after expanding abbreviations, then ALIASES, then, for `feed_names`
    still unmatched, the single clearly-best display name (similarity 0.88+, 0.05 ahead of
    the next). Anything else stays unmatched and is logged, never guessed."""
    import difflib

    t = teams() if t is None else t
    exact = {}
    for r in t.itertuples():
        for n in (r.display, f"{r.school} {r.mascot}"):
            if isinstance(n, str):
                exact[_norm(n)] = r.school
    out = {}
    for r in t.itertuples():
        for n in (r.display, f"{r.school} {r.mascot}", r.school):
            if isinstance(n, str):
                out[n] = r.school
    out |= ALIASES
    for name in feed_names or []:
        if name in out:
            continue
        k = _norm(name)
        if k in exact:
            out[name] = exact[k]
            continue
        scored = sorted(((difflib.SequenceMatcher(None, k, d).ratio(), s_) for d, s_ in exact.items()), reverse=True)
        if scored and scored[0][0] >= 0.88 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.05):
            out[name] = scored[0][1]
    return out


def schedule() -> pd.DataFrame:
    """Every saved game, played or not: date (ET), teams, neutral site, venue state."""
    g = pd.read_parquet(GAMES).copy()
    g["date"] = g["start"].dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    if "state" not in g:
        g["state"] = None
    return g


def games() -> pd.DataFrame:
    """Finished games with lines and a date (ET), margin and total."""
    g = pd.read_parquet(GAMES)
    g = g[g["home_pts"].notna() & g["away_pts"].notna()].copy()
    g["date"] = g["start"].dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    g["margin"] = g["home_pts"] - g["away_pts"]
    g["total"] = g["home_pts"] + g["away_pts"]
    return g.sort_values("start").reset_index(drop=True)


def team_games() -> pd.DataFrame:
    return pd.read_parquet(TEAM_GAMES)
