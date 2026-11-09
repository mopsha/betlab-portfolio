"""NBA data from sportsdataverse (ESPN and stats.nba.com mirrors on GitHub releases; free, no key).

stats.nba.com blocks cloud IPs, so the cloud runs read sportsdataverse's copies instead:
`https://github.com/sportsdataverse/sportsdataverse-data/releases/download/<tag>/<file>`.
Seasons are named by the year they end (2025 = 2024-25; the season that opens Oct 20,
2026 is 2027). Files are cached under data/cache/nba/ (not committed) and re-downloaded
when older than `max_age_hours`: past seasons never change, the current one updates daily.

- `load_schedules(seasons)`: games, date and tip time, home/away, scores, neutral site.
- `load_team_box(seasons)`: team box scores (FG, 3P, FT, rebounds, turnovers...).
- `load_player_box(seasons)`: player box scores with minutes, starter, did-not-play reason.

The current season's files lag: on Oct 19, 2026 the 2027 player and team box files didn't exist yet (404)
and the schedule had no scores. So for the current season, finished games the files don't have yet come
from ESPN's free API (`_with_espn_finals`, `_espn_box`: the scoreboard and each game's summary, the source
sportsdataverse copies), cached for good once final. Grading and the trackers never wait on the mirror.
- `load_injuries()`: ESPN's injury report, one snapshot a day (the history).
- `injuries_now()`: ESPN's live injury report (site.api.espn.com, free, no key), falling
  back to the latest daily snapshot; this is what tonight's pricing uses.
- `rosters_now()`: every team's current roster (ESPN, free), so offseason and deadline
  moves count on the night they happen.

All-Star games (ESPN labels them regular season, with teams like "EAST", "SHQ" or
"STARS") and other exhibitions are dropped: only games between the 30 franchises
(`NBA_TEAMS`, ESPN's abbreviations) are kept. Update the set if a team relocates or the
league expands.

There are no historical betting lines here (ESPN's game files have empty odds for past
games); docs/NBA_PLAN.md covers where lines come from.
"""

from __future__ import annotations

import io
import json
import re
import time

import pandas as pd
import requests

from betlab import config

BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
CACHE = config.DATA_DIR / "cache" / "nba"
FILES = {"schedules": ("espn_nba_schedules", "nba_schedule_{season}.parquet"),
         "team_box": ("espn_nba_team_boxscores", "team_box_{season}.parquet"),
         "player_box": ("espn_nba_player_boxscores", "player_box_{season}.parquet"),
         "injuries": ("espn_nba_injuries", "injuries_{season}.parquet")}


NBA_TEAMS = frozenset({"ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS", "HOU", "IND", "LAC",
                       "LAL", "MEM", "MIA", "MIL", "MIN", "NO", "NY", "OKC", "ORL", "PHI", "PHX", "POR", "SA",
                       "SAC", "TOR", "UTAH", "WSH"})


def _league_games(df: pd.DataFrame) -> pd.DataFrame:
    """Rows of games in which every team is one of the 30 franchises (drops All-Star games)."""
    odd = df.loc[~df["team_abbreviation"].isin(NBA_TEAMS), "game_id"]
    return df[~df["game_id"].isin(odd)].reset_index(drop=True)


def current_season(today: pd.Timestamp | None = None) -> int:
    """The season in progress or next up, named by the year it ends (Aug 1 flips the year)."""
    today = today or pd.Timestamp.now(tz="America/New_York")
    return today.year + 1 if today.month >= 8 else today.year


def _get(kind: str, season: int, max_age_hours: float | None = None, session=None) -> pd.DataFrame:
    tag, pattern = FILES[kind]
    name = pattern.format(season=season)
    path = CACHE / name
    if max_age_hours is None:  # past seasons never change; the current one does
        max_age_hours = 12.0 if season >= current_season() else 24 * 365
    if path.exists() and (time.time() - path.stat().st_mtime) / 3600 < max_age_hours:
        return pd.read_parquet(path)
    r = (session or requests).get(f"{BASE}/{tag}/{name}", timeout=180)
    r.raise_for_status()
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return pd.read_parquet(io.BytesIO(r.content))


# ESPN's display names where the odds feed (and so our matchups, game ids and slips) say it another way. Nov 9: ESPN's
# "LA Clippers" never matched our "Los Angeles Clippers", so no Clippers game line, NBA read or Clippers-home game id
# graded or resolved for three weeks. Renamed once here, in the schedule and the box, so every reader matches.
ESPN_NAMES = {"LA Clippers": "Los Angeles Clippers"}
NAME_COLS = ("home_display_name", "away_display_name", "team_display_name", "opponent_team_display_name")


def our_names(df: pd.DataFrame) -> pd.DataFrame:
    """The frame with ESPN's team display names read as ours (ESPN_NAMES)."""
    cols = [c for c in NAME_COLS if c in df]
    if not cols:
        return df
    return df.assign(**{c: df[c].replace(ESPN_NAMES) for c in cols})


def load_schedules(seasons, max_age_hours: float | None = None) -> pd.DataFrame:
    """Games with scores; `max_age_hours` re-downloads a fresher copy (grading wants last night's). Team names as
    ours (ESPN_NAMES)."""
    cols = ["game_id", "season", "season_type", "date", "start_date", "neutral_site", "home_id", "home_abbreviation",
            "home_display_name", "home_score", "away_id", "away_abbreviation", "away_display_name", "away_score",
            "status_type_completed", "venue_full_name", "status_period"]
    frames = [_get("schedules", s, max_age_hours) for s in seasons]
    df = our_names(pd.concat([f[[c for c in cols if c in f]] for f in frames], ignore_index=True))
    df["tipoff"] = pd.to_datetime(df["start_date"], utc=True, format="ISO8601")
    df = df.rename(columns={"status_period": "periods"})  # 5+ means overtime
    df = df[df["home_abbreviation"].isin(NBA_TEAMS) & df["away_abbreviation"].isin(NBA_TEAMS)]
    if any(s >= current_season() for s in seasons):
        df = _with_espn_finals(df)
    return df.sort_values("tipoff").reset_index(drop=True)


def load_team_box(seasons) -> pd.DataFrame:
    return _league_games(pd.concat([_get("team_box", s) for s in seasons], ignore_index=True))


def load_player_box(seasons, max_age_hours: float | None = None) -> pd.DataFrame:
    """`max_age_hours` re-downloads a fresher copy (grading wants last night's games). For the current season,
    finished games the file doesn't have yet (or the whole season, before the file exists) come from ESPN."""
    frames = []
    for s in seasons:
        if s < current_season():
            frames.append(_get("player_box", s, max_age_hours))
            continue
        try:
            got = _get("player_box", s, max_age_hours)
        except requests.HTTPError:
            got = pd.DataFrame()                       # not published yet (404)
        sched = load_schedules([s], max_age_hours=max_age_hours)
        have = set(pd.to_numeric(got["game_id"]).astype(int)) if len(got) else set()
        final = sched[sched["status_type_completed"].fillna(False).astype(bool) & ~sched["game_id"].astype(int).isin(have)]
        frames += [got] if len(got) else []
        frames += [b for g in final.itertuples() if len(b := _espn_box(int(g.game_id), g))]
    if not frames:
        raise FileNotFoundError(f"no NBA player box scores for {list(seasons)} yet (no file, no finished game)")
    df = our_names(_league_games(pd.concat(frames, ignore_index=True)))
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce")
    return df


ESPN_CACHE = CACHE / "espn"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
ESPN_FINAL_HOURS = 2.0          # a game this long after tip may be final; ESPN's status says whether it is


def _espn_finals(day: str, session=None) -> dict[int, dict]:
    """{game id: {home_score, away_score, periods}} for a day's finished games on ESPN's scoreboard (day:
    YYYYMMDD). A day whose games are all final is cached for good."""
    path = ESPN_CACHE / f"finals_{day}.json"
    if path.exists():
        return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
    events = (session or requests).get(f"{ESPN_API}/scoreboard", params={"dates": day}, timeout=30).json().get("events", [])
    out, all_final = {}, bool(events)
    for e in events:
        c = e["competitions"][0]
        status = c.get("status") or e.get("status") or {}
        if not status.get("type", {}).get("completed"):
            all_final = False
            continue
        side = {t["homeAway"]: t for t in c.get("competitors", [])}
        if "home" in side and "away" in side:
            out[int(e["id"])] = {"home_score": float(side["home"]["score"]), "away_score": float(side["away"]["score"]),
                                 "periods": int(status.get("period") or 0)}
    if all_final:
        ESPN_CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out), encoding="utf-8")
    return out


def _with_espn_finals(df: pd.DataFrame, now: pd.Timestamp | None = None, finals=None) -> pd.DataFrame:
    """The schedule with ESPN's final scores filled into games the file still shows unfinished, for tips more
    than ESPN_FINAL_HOURS ago (the current season's file lags; on Oct 19, 2026 it had no scores)."""
    now = now or pd.Timestamp.now(tz="UTC")
    finals = finals or _espn_finals
    done = df["status_type_completed"].fillna(False).astype(bool)
    late = df[~done & (df["tipoff"] < now - pd.Timedelta(hours=ESPN_FINAL_HOURS))]
    if late.empty:
        return df
    df = df.copy()
    got: dict[int, dict] = {}
    for d in sorted(set(late["tipoff"].dt.tz_convert("America/New_York").dt.strftime("%Y%m%d"))):
        try:
            got |= finals(d)
        except (requests.RequestException, ValueError, KeyError):
            continue                                   # an ESPN hiccup: those games stay open for the next run
    for i in late.index:
        f = got.get(int(df.at[i, "game_id"]))
        if f:
            df.loc[i, ["home_score", "away_score", "periods"]] = [f["home_score"], f["away_score"], f["periods"]]
            df.at[i, "status_type_completed"] = True
    return df


_STATS = {"minutes": "minutes", "points": "points", "rebounds": "rebounds", "assists": "assists",
          "turnovers": "turnovers", "steals": "steals", "blocks": "blocks", "offensiveRebounds": "offensive_rebounds",
          "defensiveRebounds": "defensive_rebounds", "fouls": "fouls"}
_PAIRS = {"fieldGoalsMade-fieldGoalsAttempted": ("field_goals_made", "field_goals_attempted"),
          "threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("three_point_field_goals_made",
                                                                     "three_point_field_goals_attempted"),
          "freeThrowsMade-freeThrowsAttempted": ("free_throws_made", "free_throws_attempted")}


def _num(v) -> float | None:
    try:
        return float(str(v).lstrip("+"))
    except ValueError:
        return None


def espn_box_rows(summary: dict, game) -> pd.DataFrame:
    """One game's player box from ESPN's summary JSON, in sportsdataverse's columns; `game` is its schedule row."""
    teams = summary.get("boxscore", {}).get("players", [])
    tip = pd.Timestamp(game.tipoff).tz_convert("America/New_York")
    score = {"home": game.home_score, "away": game.away_score}
    rows = []
    for t in teams:
        team = t["team"]
        ha = "home" if int(team["id"]) == int(game.home_id) else "away"
        opp = next((o["team"] for o in teams if o is not t), {})
        for block in t.get("statistics", [])[:1]:
            keys = block.get("keys", [])
            for a in block.get("athletes", []):
                ath, vals = a.get("athlete", {}), dict(zip(keys, a.get("stats") or []))
                r = {"game_id": int(game.game_id), "season": int(game.season), "season_type": int(game.season_type),
                     "game_date": tip.strftime("%Y-%m-%d"), "game_date_time": tip,
                     "athlete_id": float(ath["id"]), "athlete_display_name": ath.get("displayName"),
                     "athlete_short_name": ath.get("shortName"), "athlete_jersey": ath.get("jersey"),
                     "athlete_position_abbreviation": (ath.get("position") or {}).get("abbreviation"),
                     "team_id": int(team["id"]), "team_name": team.get("name"), "team_location": team.get("location"),
                     "team_short_display_name": team.get("shortDisplayName"), "team_display_name": team.get("displayName"),
                     "team_abbreviation": team.get("abbreviation"), "home_away": ha,
                     "opponent_team_id": int(opp["id"]) if opp else None,
                     "opponent_team_abbreviation": opp.get("abbreviation"), "opponent_team_display_name": opp.get("displayName"),
                     "team_score": score[ha], "opponent_team_score": score["away" if ha == "home" else "home"],
                     "starter": bool(a.get("starter")), "did_not_play": bool(a.get("didNotPlay")),
                     "ejected": bool(a.get("ejected")), "active": bool(a.get("active")), "reason": a.get("reason"),
                     "plus_minus": str(vals["plusMinus"]) if "plusMinus" in vals else None}
                for k, col in _STATS.items():
                    r[col] = _num(vals[k]) if k in vals else None
                for k, (made, att) in _PAIRS.items():
                    m, _, n = str(vals.get(k, "")).partition("-")
                    r[made], r[att] = _num(m), _num(n)
                rows.append(r)
    return pd.DataFrame(rows)


def _espn_box(game_id: int, game, session=None) -> pd.DataFrame:
    """A finished game's player box from ESPN (cached for good); empty on an ESPN hiccup (retried next run)."""
    path = ESPN_CACHE / f"box_{game_id}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    try:
        df = espn_box_rows((session or requests).get(SUMMARY, params={"event": game_id}, timeout=30).json(), game)
    except (requests.RequestException, ValueError, KeyError):
        return pd.DataFrame()
    if len(df):
        ESPN_CACHE.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
    return df


def load_injuries(season: int | None = None) -> pd.DataFrame:
    return _get("injuries", season or current_season(), max_age_hours=6.0)


ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
LIVE_INJURIES = f"{ESPN_API}/injuries"


def rosters_now(abbreviations=None, session=None) -> pd.DataFrame:
    """Current rosters: athlete_id, athlete_display_name, team_id, team_abbreviation,
    athlete_position_abbreviation (the columns live_nba.rosters returns)."""
    http = session or requests
    teams = http.get(f"{ESPN_API}/teams", timeout=30).json()["sports"][0]["leagues"][0]["teams"]
    rows = []
    for t in teams:
        t = t["team"]
        if abbreviations is not None and t["abbreviation"] not in abbreviations:
            continue
        for a in http.get(f"{ESPN_API}/teams/{t['id']}/roster", timeout=30).json().get("athletes", []):
            rows.append({"athlete_id": int(a["id"]), "athlete_display_name": a.get("displayName"),
                         "team_id": int(t["id"]), "team_abbreviation": t["abbreviation"],
                         "athlete_position_abbreviation": (a.get("position") or {}).get("abbreviation")})
    return pd.DataFrame(rows)


def national_tv(day: str, session=None) -> dict[tuple[str, str], list[str]]:
    """{(home abbreviation, away abbreviation): [networks]} for a day's games on national TV
    (ESPN's free scoreboard lists each broadcast's market: home, away or national). day: YYYYMMDD."""
    http = session or requests
    events = http.get(f"{ESPN_API}/scoreboard", params={"dates": day}, timeout=30).json().get("events", [])
    out = {}
    for e in events:
        c = e["competitions"][0]
        teams = {t["homeAway"]: t["team"]["abbreviation"] for t in c.get("competitors", [])}
        nets = [n for b in c.get("broadcasts", []) if b.get("market") == "national" for n in b.get("names", [])]
        if nets and "home" in teams and "away" in teams:
            out[(teams["home"], teams["away"])] = nets
    return out



def scoreboard_teams(day: str, session=None) -> list[dict]:
    """A day's games on ESPN's free scoreboard: each side's display name and abbreviation, and the
    national TV networks. day: YYYYMMDD. For the morning NBA listing (reports/nba.schedule)."""
    http = session or requests
    events = http.get(f"{ESPN_API}/scoreboard", params={"dates": day}, timeout=30).json().get("events", [])
    out = []
    for e in events:
        c = e["competitions"][0]
        side = {t["homeAway"]: t["team"] for t in c.get("competitors", [])}
        if "home" not in side or "away" not in side:
            continue
        out.append({"home_name": side["home"].get("displayName"), "home": side["home"].get("abbreviation"),
                    "away_name": side["away"].get("displayName"), "away": side["away"].get("abbreviation"),
                    "national_tv": [n for b in c.get("broadcasts", []) if b.get("market") == "national" for n in b.get("names", [])]})
    return out

LINEUPS = "https://stats.nba.com/js/data/leaders/00_daily_lineups_{day}.json"
NBA_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com/"}


def lineups(day: str, session=None) -> pd.DataFrame:
    """nba.com's "Today's Lineups" for a day (YYYYMMDD): one row per listed player with
    team (NBA abbreviation, e.g. NYK), player, starter (a position is filled in only for the
    five starters), lineup_status ("Confirmed" or "Expected"), roster_status ("Active" or
    "Inactive") and timestamp. A static file on nba.com's CDN (Akamai), not the stats API that
    blocks cloud servers. Empty when the file isn't there."""
    cols = ["nba_game_id", "team", "player", "starter", "lineup_status", "roster_status", "timestamp"]
    try:
        r = (session or requests).get(LINEUPS.format(day=day), headers=NBA_HEADERS, timeout=20)
        games = r.json().get("games", []) if r.status_code == 200 else []
    except Exception:
        games = []
    rows = [{"nba_game_id": g.get("gameId"), "team": g[side]["teamAbbreviation"], "player": p.get("playerName"),
             "starter": bool(p.get("position")), "lineup_status": p.get("lineupStatus"),
             "roster_status": p.get("rosterStatus"), "timestamp": p.get("timestamp")}
            for g in games for side in ("homeTeam", "awayTeam") if g.get(side) for p in g[side].get("players", [])]
    return pd.DataFrame(rows, columns=cols)


RULED_OUT = re.compile(r"\b(?:ruled out|will not play|won't play|will miss|is out)\b", re.I)


def injuries_now(session=None) -> pd.DataFrame:
    """Who is out or day-to-day right now: athlete_id, name, team, status, date, comment, sits.

    `sits` is True for "Out"; for "Day-To-Day" players whose latest note (under 36 hours
    old) says they were ruled out (ESPN often leaves game-day scratches as day-to-day); and
    for anyone whose expected return is more than 3 days away (long injuries listed as
    day-to-day in the offseason). A heuristic: check it against box scores in October."""
    try:
        d = (session or requests).get(LIVE_INJURIES, timeout=30).json()
        rows = []
        for team in d.get("injuries", []):
            for i in team.get("injuries", []):
                a = i.get("athlete", {})
                ids = [m.group(1) for link in a.get("links", []) if (m := re.search(r"/id/(\d+)", link.get("href", "")))]
                if ids:
                    rows.append({"athlete_id": int(ids[0]), "athlete_display_name": a.get("displayName"),
                                 "team": team.get("displayName"), "status": i.get("status"),
                                 "date": i.get("date"), "comment": i.get("shortComment") or "",
                                 "return_date": (i.get("details") or {}).get("returnDate")})
        df = pd.DataFrame(rows)
        if df.empty:
            raise ValueError("empty live report")
    except Exception:  # the daily snapshot is a day behind but better than nothing
        inj = load_injuries()
        inj = inj[inj["as_of_date"] == inj["as_of_date"].max()]
        df = pd.DataFrame({"athlete_id": inj["athlete_id"].astype(int), "athlete_display_name": inj["athlete_display_name"],
                           "team": inj["team_display_name"], "status": inj["status"], "date": inj["injury_date"],
                           "comment": inj["short_comment"].fillna(""), "return_date": inj["detail_return_date"]})
    fresh = pd.Timestamp.now(tz="UTC") - pd.to_datetime(df["date"], utc=True, errors="coerce") < pd.Timedelta(hours=36)
    far = pd.to_datetime(df["return_date"], utc=True, errors="coerce") > pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=3)
    df["sits"] = (df["status"] == "Out") | (fresh & df["comment"].str.contains(RULED_OUT)) | far
    return df.reset_index(drop=True)
