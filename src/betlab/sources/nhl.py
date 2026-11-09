"""NHL data from free public sources (no key, no odds credits).

- **NHL stats API** (api.nhle.com/stats/rest): one row per team per game (goals, shots,
  5-on-5 shot attempts, empty-net goals, overtime and shootout results) and per goalie per
  game (started, shots against, saves). Seasons are named by the year they end (2026 =
  2025-26), like the NBA source; the API's own id is "20252026".
- **NHL web API** (api-web.nhle.com): the schedule with start times.
- **ESPN** (site.api.espn.com): DraftKings' moneyline, puck line and total for upcoming
  games, the probable starting goalies with their status (Confirmed / Probable), and for
  past games the opening and closing lines (2025-26 onward; older seasons carry one line
  from another book, or none).

Files are cached under data/cache/nhl/ (not committed); the current season is refreshed
when older than `max_age_hours`. The lines history (`data/history/nhl_lines.parquet`) is
committed, because it takes one ESPN call per game to rebuild.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from betlab import config

STATS = "https://api.nhle.com/stats/rest/en"
WEB = "https://api-web.nhle.com/v1"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
CACHE = config.DATA_DIR / "cache" / "nhl"
LINES = config.DATA_DIR / "history" / "nhl_lines.parquet"
TIMEOUT = 60

# ESPN's abbreviations where they differ from the NHL's.
ESPN_TO_NHL = {"LA": "LAK", "NJ": "NJD", "SJ": "SJS", "TB": "TBL", "UTAH": "UTA"}


def current_season(today: pd.Timestamp | None = None) -> int:
    """The season in progress or next up, named by the year it ends (Aug 1 flips the year)."""
    today = today or pd.Timestamp.now(tz="America/New_York")
    return today.year + 1 if today.month >= 8 else today.year


def season_id(season: int) -> str:
    return f"{season - 1}{season}"


def _cached(name: str, season: int, fetch, max_age_hours: float | None = None) -> pd.DataFrame:
    path = CACHE / f"{name}_{season}.parquet"
    if max_age_hours is None:
        max_age_hours = 6.0 if season >= current_season() else 24 * 365
    if path.exists() and (time.time() - path.stat().st_mtime) / 3600 < max_age_hours:
        return pd.read_parquet(path)
    df = fetch()
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def _report(kind: str, report: str, season: int, game_type: int = 2) -> pd.DataFrame:
    """One stats-API report, every game of a season (regular season = game type 2)."""
    exp = f"seasonId={season_id(season)} and gameTypeId={game_type}"
    r = requests.get(f"{STATS}/{kind}/{report}", timeout=TIMEOUT,
                     params={"isAggregate": "false", "isGame": "true", "start": 0, "limit": -1, "cayenneExp": exp})
    r.raise_for_status()
    return pd.DataFrame(r.json()["data"])


def _team_games_raw(season: int) -> pd.DataFrame:
    summ = _report("team", "summary", season)
    if summ.empty:
        return summ
    shoot = _report("team", "summaryshooting", season)[["gameId", "teamId", "satFor", "satAgainst", "usatFor", "usatAgainst"]]
    real = _report("team", "realtime", season)[["gameId", "teamId", "emptyNetGoals", "totalShotAttempts"]]
    df = summ.merge(shoot, on=["gameId", "teamId"], how="left").merge(real, on=["gameId", "teamId"], how="left")
    keep = ["gameId", "gameDate", "teamId", "teamFullName", "homeRoad", "opponentTeamAbbrev", "goalsFor", "goalsAgainst",
            "shotsForPerGame", "shotsAgainstPerGame", "wins", "losses", "otLosses", "winsInShootout", "winsInRegulation",
            "regulationAndOtWins", "powerPlayPct", "penaltyKillPct", "satFor", "satAgainst", "usatFor", "usatAgainst",
            "emptyNetGoals", "totalShotAttempts"]
    return df[keep]


def load_team_games(seasons, max_age_hours: float | None = None) -> pd.DataFrame:
    """One row per (game, team), regular season: goals (the shootout goal removed), shots,
    5-on-5 shot attempts (sat = all, usat = unblocked), empty-net goals, overtime/shootout."""
    frames = []
    for s in seasons:
        df = _cached("team_games", s, lambda s=s: _team_games_raw(s), max_age_hours)
        if not df.empty:
            frames.append(df.assign(season=s))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    # A team's own abbreviation is its opponent's opponentTeamAbbrev in the same game.
    opp = df[["gameId", "teamId", "opponentTeamAbbrev"]].rename(columns={"teamId": "oppId", "opponentTeamAbbrev": "team"})
    df = df.merge(opp, on="gameId")
    df = df[df["oppId"] != df["teamId"]].drop(columns="oppId")
    out = pd.DataFrame({
        "game_id": df["gameId"].astype(int), "season": df["season"].astype(int),
        "date": pd.to_datetime(df["gameDate"]), "team": df["team"], "opp": df["opponentTeamAbbrev"],
        "home": (df["homeRoad"] == "H").astype(int),
        "gf": df["goalsFor"].astype(float), "ga": df["goalsAgainst"].astype(float),
        "sf": df["shotsForPerGame"].astype(float), "sa": df["shotsAgainstPerGame"].astype(float),
        "cf": df["satFor"].astype(float), "ca": df["satAgainst"].astype(float),
        "ff": df["usatFor"].astype(float), "fa": df["usatAgainst"].astype(float),
        "en_goals": df["emptyNetGoals"].fillna(0).astype(float),
        "win": df["wins"].astype(int), "so_win": df["winsInShootout"].fillna(0).astype(int),
        "reg_win": df["winsInRegulation"].fillna(0).astype(int),
    })
    # Overtime or shootout: nobody won in regulation.
    reg = out.groupby("game_id")["reg_win"].transform("sum")
    out["extra"] = (reg == 0).astype(int)
    so = out.groupby("game_id")["so_win"].transform("sum")
    out["shootout"] = (so > 0).astype(int)
    # Nov 4: the NHL's report leaves a shootout's score tied. Books credit the winner one goal (moneylines, puck lines
    # and totals all settle on it), so gf and ga carry it, and gf_play and ga_play take it out so goals are goals.
    tied = out["shootout"].astype(bool) & (out["gf"] == out["ga"])
    out["gf_play"], out["ga_play"] = out["gf"], out["ga"]
    out.loc[tied, "gf"] += out.loc[tied, "so_win"]
    out.loc[tied, "ga"] += 1 - out.loc[tied, "so_win"]
    return out.sort_values(["date", "game_id", "home"]).reset_index(drop=True)


def _goalie_games_raw(season: int) -> pd.DataFrame:
    df = _report("goalie", "summary", season)
    if df.empty:
        return df
    return df[["gameId", "gameDate", "playerId", "goalieFullName", "teamAbbrev", "opponentTeamAbbrev", "homeRoad",
               "gamesStarted", "shotsAgainst", "saves", "goalsAgainst", "timeOnIce"]]


def load_goalie_games(seasons, max_age_hours: float | None = None) -> pd.DataFrame:
    """One row per (game, goalie who played): started, shots against, saves, time on ice."""
    frames = []
    for s in seasons:
        df = _cached("goalie_games", s, lambda s=s: _goalie_games_raw(s), max_age_hours)
        if not df.empty:
            frames.append(df.assign(season=s))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return pd.DataFrame({
        "game_id": df["gameId"].astype(int), "season": df["season"].astype(int), "date": pd.to_datetime(df["gameDate"]),
        "goalie_id": df["playerId"].astype(int), "goalie": df["goalieFullName"], "team": df["teamAbbrev"],
        "opp": df["opponentTeamAbbrev"], "started": df["gamesStarted"].fillna(0).astype(int),
        "shots_against": df["shotsAgainst"].fillna(0).astype(float), "saves": df["saves"].fillna(0).astype(float),
        "toi": df["timeOnIce"].fillna(0).astype(float),
    }).sort_values(["date", "game_id"]).reset_index(drop=True)


def schedule(date: str) -> pd.DataFrame:
    """The NHL's schedule for the week starting at `date` (YYYY-MM-DD): game id, start, teams."""
    r = requests.get(f"{WEB}/schedule/{date}", timeout=TIMEOUT)
    r.raise_for_status()
    rows = []
    for day in r.json().get("gameWeek", []):
        for g in day["games"]:
            rows.append({"game_id": int(g["id"]), "game_type": g.get("gameType"), "start": g["startTimeUTC"],
                         "home": g["homeTeam"]["abbrev"], "away": g["awayTeam"]["abbrev"],
                         "state": g.get("gameState"), "neutral": bool(g.get("neutralSite", False))})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- ESPN: lines and goalies
def _am(x) -> float | None:
    """American odds from ESPN's '+105', '-118', 'EVEN' or a number; None if missing."""
    if x is None:
        return None
    s = str(x).strip().upper()
    if s in ("", "OFF", "NONE", "NAN"):
        return None
    if s in ("EVEN", "EV"):
        return 100.0
    try:
        v = float(s.replace("+", ""))
    except ValueError:
        return None
    return v if abs(v) >= 100 else None


def _line(x) -> float | None:
    """A line like 'o6.5', 'u5.5', '+1.5', '-1.5' as a number (the sign kept for puck lines)."""
    if x is None:
        return None
    s = str(x).strip().lower().lstrip("ou")
    try:
        return float(s)
    except ValueError:
        return None


def _abbr(team: dict) -> str:
    a = team.get("abbreviation", "")
    return ESPN_TO_NHL.get(a, a)


def _dig(d, *keys):
    for k in keys:
        d = (d or {}).get(k)
    return d


def _odds_row(o: dict) -> dict:
    """ESPN's odds block (scoreboard or summary pickcenter) as flat open/close fields."""
    ml, pl, tot = o.get("moneyline") or {}, o.get("pointSpread") or {}, o.get("total") or {}
    row = {"book": (o.get("provider") or {}).get("name"),
           "ml_home_open": _am(_dig(ml, "home", "open", "odds")), "ml_away_open": _am(_dig(ml, "away", "open", "odds")),
           "ml_home_close": _am(_dig(ml, "home", "close", "odds")), "ml_away_close": _am(_dig(ml, "away", "close", "odds")),
           "total_open": _line(_dig(tot, "over", "open", "line")), "over_open": _am(_dig(tot, "over", "open", "odds")),
           "under_open": _am(_dig(tot, "under", "open", "odds")),
           "total_close": _line(_dig(tot, "over", "close", "line")), "over_close": _am(_dig(tot, "over", "close", "odds")),
           "under_close": _am(_dig(tot, "under", "close", "odds")),
           "pl_home_close": _line(_dig(pl, "home", "close", "line")), "pl_home_close_price": _am(_dig(pl, "home", "close", "odds")),
           "pl_away_close_price": _am(_dig(pl, "away", "close", "odds"))}
    # The flat fields are the current (or, after the game, the last) numbers.
    cur_home, cur_away = _am((o.get("homeTeamOdds") or {}).get("moneyLine")), _am((o.get("awayTeamOdds") or {}).get("moneyLine"))
    if row["ml_home_close"] is None and cur_home is not None:
        row["ml_home_close"], row["ml_away_close"] = cur_home, cur_away
    if row["total_close"] is None and o.get("overUnder") is not None:
        row["total_close"], row["over_close"], row["under_close"] = float(o["overUnder"]), _am(o.get("overOdds")), _am(o.get("underOdds"))
    return row


def scoreboard(date: str | None = None) -> pd.DataFrame:
    """ESPN's NHL games for a date (YYYYMMDD; default today): start, teams, DraftKings'
    current lines, and the probable starting goalies with their status."""
    params = {"dates": date} if date else {}
    r = requests.get(f"{ESPN}/scoreboard", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    rows = []
    for e in r.json().get("events", []):
        c = e["competitions"][0]
        teams = {t["homeAway"]: t for t in c["competitors"]}
        home, away = _abbr(teams["home"]["team"]), _abbr(teams["away"]["team"])
        row = {"espn_id": e["id"], "start": e["date"], "home": home, "away": away,
               "home_name": teams["home"]["team"].get("displayName"), "away_name": teams["away"]["team"].get("displayName"),
               "state": e.get("status", {}).get("type", {}).get("state"),
               "season_type": (e.get("season") or {}).get("type")}
        for side in ("home", "away"):
            prob = next((p for p in teams[side].get("probables", []) if p.get("name") == "probableStartingGoalie"), None)
            row[f"{side}_goalie"] = (prob or {}).get("athlete", {}).get("displayName")
            row[f"{side}_goalie_status"] = ((prob or {}).get("status") or {}).get("type")
        odds = c.get("odds") or []
        if odds:
            row.update(_odds_row(odds[0]))
        rows.append(row)
    return pd.DataFrame(rows)


def _summary_lines(espn_id: str) -> dict | None:
    try:
        r = requests.get(f"{ESPN}/summary", params={"event": espn_id}, timeout=TIMEOUT)
        r.raise_for_status()
        pc = r.json().get("pickcenter") or []
    except (requests.RequestException, ValueError):
        return None
    return _odds_row(pc[0]) if pc else {}


def backfill_lines(season: int, workers: int = 8) -> pd.DataFrame:
    """Every regular-season game's ESPN lines for one season (one call per date plus one per
    game), merged into the committed history. Returns the season's rows."""
    sched = load_team_games([season])
    dates = sorted(sched["date"].dt.strftime("%Y%m%d").unique())
    games = []
    for d in dates:
        try:
            sb = scoreboard(d)
        except requests.RequestException:
            continue
        if len(sb):
            games.append(sb[["espn_id", "start", "home", "away", "season_type"]])
    games = pd.concat(games, ignore_index=True)
    games = games[games["season_type"] == 2].drop_duplicates("espn_id")
    with ThreadPoolExecutor(workers) as ex:
        lines = list(ex.map(_summary_lines, games["espn_id"]))
    rows = [{**g, **(ln or {})} for g, ln in zip(games.to_dict("records"), lines)]
    df = pd.DataFrame(rows).assign(season=season)
    # Attach the NHL game id by date and teams.
    tg = sched[sched["home"] == 1][["game_id", "date", "team", "opp"]].rename(columns={"team": "home", "opp": "away"})
    df["date"] = pd.to_datetime(df["start"], utc=True, format="ISO8601").dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    df = df.merge(tg, on=["date", "home", "away"], how="left")
    old = pd.read_parquet(LINES) if LINES.exists() else pd.DataFrame()
    if len(old):
        old = old[old["season"] != season]
    LINES.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([old, df], ignore_index=True).to_parquet(LINES, index=False)
    return df


def load_lines() -> pd.DataFrame:
    return pd.read_parquet(LINES) if LINES.exists() else pd.DataFrame()


def skater_shots(game_id) -> pd.DataFrame:
    """Every skater's shots on goal in one game (plain names for matching feeds)."""
    r = requests.get(f"{STATS}/skater/summary", timeout=TIMEOUT,
                     params={"isAggregate": "false", "isGame": "true", "start": 0, "limit": -1,
                             "cayenneExp": f"gameId={int(game_id)}"})
    r.raise_for_status()
    df = pd.DataFrame(r.json()["data"])
    if df.empty:
        return pd.DataFrame(columns=["player", "plain", "team", "shots"])
    return pd.DataFrame({"player": df["skaterFullName"], "plain": df["skaterFullName"].map(_plain),
                         "team": df["teamAbbrev"], "shots": df["shots"].astype(float)})


def skater_box(game_id) -> pd.DataFrame:
    """Every skater's shots, goals, assists and points in one game (plain names for matching)."""
    r = requests.get(f"{STATS}/skater/summary", timeout=TIMEOUT,
                     params={"isAggregate": "false", "isGame": "true", "start": 0, "limit": -1,
                             "cayenneExp": f"gameId={int(game_id)}"})
    r.raise_for_status()
    df = pd.DataFrame(r.json()["data"])
    if df.empty:
        return pd.DataFrame(columns=["player", "plain", "team", "shots", "goals", "assists", "points"])
    return pd.DataFrame({"player": df["skaterFullName"], "plain": df["skaterFullName"].map(_plain), "team": df["teamAbbrev"],
                         **{c: df[c].astype(float) for c in ("shots", "goals", "assists", "points")}})


def goalie_box(game_id) -> pd.DataFrame:
    """Every goalie's saves and shots against in one game."""
    r = requests.get(f"{STATS}/goalie/summary", timeout=TIMEOUT,
                     params={"isAggregate": "false", "isGame": "true", "start": 0, "limit": -1,
                             "cayenneExp": f"gameId={int(game_id)}"})
    r.raise_for_status()
    df = pd.DataFrame(r.json()["data"])
    if df.empty:
        return pd.DataFrame(columns=["player", "plain", "team", "saves", "shots_against"])
    return pd.DataFrame({"player": df["goalieFullName"], "plain": df["goalieFullName"].map(_plain), "team": df["teamAbbrev"],
                         "saves": df["saves"].astype(float), "shots_against": df["shotsAgainst"].astype(float)})


# ---------------------------------------------------------------- team names
def _plain(name: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace(".", "").replace("-", " ").split())


def team_codes() -> dict[str, str]:
    """{plain full name: NHL abbreviation} for every current and recent franchise name
    (both of Utah's), cached for a week; used to read the Odds API's team names."""
    path = CACHE / "teams.json"
    if path.exists() and (time.time() - path.stat().st_mtime) < 7 * 86400:
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    r = requests.get(f"{STATS}/team", timeout=TIMEOUT)
    r.raise_for_status()
    out = {_plain(t["fullName"]): t["triCode"] for t in r.json()["data"]}
    import json
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out), encoding="utf-8")
    return out


def code_for(name: str, codes: dict[str, str] | None = None) -> str | None:
    """A feed's team name ("St Louis Blues", "Montreal Canadiens") as the NHL's abbreviation;
    falls back to the nickname, which is unique in the league."""
    codes = codes if codes is not None else team_codes()
    plain = _plain(name)
    if plain in codes:
        return codes[plain]
    nick = plain.split()[-1] if plain else ""
    hits = {c for full, c in codes.items() if full.split()[-1] == nick}
    return hits.pop() if len(hits) == 1 else None


# ---------------------------------------------------------------- players, special teams, injuries
def _months(season: int) -> list[tuple[str, str]]:
    """Month ranges covering a regular season (late September to mid-April)."""
    starts = pd.date_range(f"{season - 1}-09-01", f"{season}-05-01", freq="MS")
    return [(a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")) for a, b in zip(starts[:-1], starts[1:])]


def _report_paged(kind: str, report: str, season: int) -> pd.DataFrame:
    """A per-game report too big for one call (the API caps a call at 10,000 rows): month by month."""
    frames = []
    for a, b in _months(season):
        exp = f'seasonId={season_id(season)} and gameTypeId=2 and gameDate>="{a}" and gameDate<"{b}"'
        r = requests.get(f"{STATS}/{kind}/{report}", timeout=TIMEOUT,
                         params={"isAggregate": "false", "isGame": "true", "start": 0, "limit": -1, "cayenneExp": exp})
        r.raise_for_status()
        frames.append(pd.DataFrame(r.json()["data"]))
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _skater_games_raw(season: int) -> pd.DataFrame:
    summ = _report_paged("skater", "summary", season)
    if summ.empty:
        return summ
    toi = _report_paged("skater", "timeonice", season)[["gameId", "playerId", "timeOnIce", "evTimeOnIce", "ppTimeOnIce",
                                                        "shTimeOnIce", "shifts"]]
    keep = ["gameId", "gameDate", "playerId", "skaterFullName", "positionCode", "teamAbbrev", "opponentTeamAbbrev",
            "homeRoad", "goals", "assists", "points", "shots", "ppGoals", "ppPoints", "evPoints"]
    return summ[keep].merge(toi, on=["gameId", "playerId"], how="left")


def load_skater_games(seasons, max_age_hours: float | None = None) -> pd.DataFrame:
    """One row per (game, skater): time on ice (all, even strength, power play, shorthanded,
    seconds), shots on goal, goals, assists, points, power-play points."""
    frames = []
    for s in seasons:
        df = _cached("skater_games", s, lambda s=s: _skater_games_raw(s), max_age_hours)
        if not df.empty:
            frames.append(df.assign(season=s))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return pd.DataFrame({
        "game_id": df["gameId"].astype(int), "season": df["season"].astype(int), "date": pd.to_datetime(df["gameDate"]),
        "player_id": df["playerId"].astype(int), "player": df["skaterFullName"], "pos": df["positionCode"],
        "team": df["teamAbbrev"], "opp": df["opponentTeamAbbrev"], "home": (df["homeRoad"] == "H").astype(int),
        "toi": df["timeOnIce"].fillna(0).astype(float), "ev_toi": df["evTimeOnIce"].fillna(0).astype(float),
        "pp_toi": df["ppTimeOnIce"].fillna(0).astype(float), "sh_toi": df["shTimeOnIce"].fillna(0).astype(float),
        "shots": df["shots"].fillna(0).astype(float), "goals": df["goals"].fillna(0).astype(float),
        "assists": df["assists"].fillna(0).astype(float), "points": df["points"].fillna(0).astype(float),
        "pp_points": df["ppPoints"].fillna(0).astype(float),
    }).sort_values(["date", "game_id", "team"]).reset_index(drop=True)


def _special_raw(season: int) -> pd.DataFrame:
    pp = _report("team", "powerplay", season)
    if pp.empty:
        return pp
    pk = _report("team", "penaltykill", season)[["gameId", "teamId", "timesShorthanded", "ppGoalsAgainst"]]
    return pp[["gameId", "teamId", "opponentTeamAbbrev", "ppOpportunities", "powerPlayGoalsFor"]].merge(
        pk, on=["gameId", "teamId"], how="left")


def load_special_teams(seasons, max_age_hours: float | None = None) -> pd.DataFrame:
    """One row per (game, team): power-play chances and goals, times shorthanded and
    power-play goals allowed. Joined to team games by (game_id, opp)."""
    frames = []
    for s in seasons:
        df = _cached("special_teams", s, lambda s=s: _special_raw(s), max_age_hours)
        if not df.empty:
            frames.append(df.assign(season=s))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return pd.DataFrame({"game_id": df["gameId"].astype(int), "opp": df["opponentTeamAbbrev"],
                         "pp_opp": df["ppOpportunities"].fillna(0).astype(float),
                         "pp_goals": df["powerPlayGoalsFor"].fillna(0).astype(float),
                         "times_sh": df["timesShorthanded"].fillna(0).astype(float),
                         "pp_goals_against": df["ppGoalsAgainst"].fillna(0).astype(float)})


def injuries_now() -> pd.DataFrame:
    """ESPN's NHL injury report: team, player, position, status (Day-To-Day, Injured Reserve,
    Out, Suspension...)."""
    r = requests.get(f"{ESPN}/injuries", timeout=TIMEOUT)
    r.raise_for_status()
    rows = []
    for team in r.json().get("injuries", []):
        for i in team.get("injuries", []):
            a = i.get("athlete", {})
            code = _abbr(a.get("team", {})) if a.get("team") else None
            rows.append({"team_name": team.get("displayName"), "team": code, "player": a.get("displayName"),
                         "plain": _plain(a.get("displayName", "")), "pos": (a.get("position") or {}).get("abbreviation"),
                         "status": i.get("status"), "detail": (i.get("details") or {}).get("type") or i.get("shortComment")})
    return pd.DataFrame(rows)
