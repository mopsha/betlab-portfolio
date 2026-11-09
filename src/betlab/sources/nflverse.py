"""NFL data from nflverse: schedules with closing lines, weekly team EPA."""

from __future__ import annotations

import io

import nflreadpy as nfl
import pandas as pd
import polars as pl
from nflreadpy.config import update_config
from nflreadpy.downloader import get_downloader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# GitHub's release downloads sometimes answer 500/502 for a minute (the Oct 6 daily died
# on one in grading). nflreadpy uses one shared session: retry server errors with backoff
# (about 1+2+4+8+16 s) before giving up.
_RETRY = Retry(total=5, backoff_factor=1, status_forcelist=(500, 502, 503, 504), allowed_methods=("GET",))
get_downloader().session.mount("https://", HTTPAdapter(max_retries=_RETRY))

# nflreadpy keeps every download in RAM by default (cache_mode "memory"). Each betlab command is
# its own process, so that cache never helps across steps, and it held three full-width seasons
# of play-by-play: `betlab preview` peaked at 1.3 GB and the Railway worker killed it (Oct 6).
update_config(cache_mode="off", verbose=False)
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"

RELOCATED = {"OAK": "LV", "SD": "LAC", "STL": "LA"}
ET = "America/New_York"


def load_games() -> pd.DataFrame:
    """All games with scores and nflverse's closing lines.

    spread_line is from the home team's side and positive when the home team
    is favored (spread_line = 3 means the home team is -3). result is the
    home margin.
    """
    g = nfl.load_schedules().to_pandas()
    for col in ("home_team", "away_team"):
        g[col] = g[col].replace(RELOCATED)
    g["date"] = pd.to_datetime(g["gameday"])
    g["kickoff"] = pd.to_datetime(g["gameday"] + " " + g["gametime"].fillna("13:00")).dt.tz_localize(ET)
    g["neutral"] = g["location"].eq("Neutral")
    g = g.rename(columns={"home_score": "home_pts", "away_score": "away_pts", "result": "margin"})
    return g.sort_values(["date", "game_id"]).reset_index(drop=True)


def load_team_epa(seasons) -> pd.DataFrame:
    """Offensive EPA per play for each team-game (dropbacks + rushes)."""
    t = nfl.load_team_stats(seasons=list(seasons)).to_pandas()
    plays = t["attempts"] + t["sacks_suffered"] + t["carries"]
    t["epa_pp"] = (t["passing_epa"].fillna(0) + t["rushing_epa"].fillna(0)) / plays.where(plays > 0)
    t["team"] = t["team"].replace(RELOCATED)
    return t[["game_id", "team", "epa_pp"]]


def team_abbr_by_name() -> dict[str, str]:
    """'Buffalo Bills' -> 'BUF', using the abbreviations the schedules use."""
    teams = nfl.load_teams().to_pandas()
    names = {name: RELOCATED.get(abbr, abbr) for abbr, name in zip(teams["team_abbr"], teams["team_name"])}
    names["Los Angeles Rams"] = "LA"
    return names


def games_with_epa(first_season: int = 2006) -> pd.DataFrame:
    """The NFL games table the model uses: load_games() plus each offense's EPA per play."""
    games = load_games()
    games = games[games["season"] >= first_season]
    epa = load_team_epa(range(first_season, int(games["season"].max()) + 1))
    home = epa.rename(columns={"team": "home_team", "epa_pp": "home_epa"})
    away = epa.rename(columns={"team": "away_team", "epa_pp": "away_epa"})
    games = games.merge(home, on=["game_id", "home_team"], how="left")
    games = games.merge(away, on=["game_id", "away_team"], how="left")
    return games


PLAYER_COLUMNS = [
    "player_id", "player_display_name", "position", "season", "week", "season_type", "game_id", "team",
    "opponent_team", "attempts", "completions", "passing_yards", "passing_tds", "carries", "rushing_yards",
    "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds",
]
# Every touchdown a player scores himself: what both books settle an anytime TD on (passing TDs don't count; kick,
# punt and defensive returns and fumble recoveries do). nflverse files them in separate, disjoint columns (2025: one
# defensive fumble return sits in two, which can't change "scored at least once"). Grading only: the TD read and the
# props models are fit on rushing + receiving.
TD_COLUMNS = ["rushing_tds", "receiving_tds", "special_teams_tds", "def_tds", "fumble_recovery_tds", "pt_return_tds"]


def anytime_tds(stats) -> float | pd.Series:
    """A player's own touchdowns (TD_COLUMNS) from a player-stats row or frame; a missing column counts 0."""
    if isinstance(stats, pd.DataFrame):
        return sum(pd.to_numeric(stats[c], errors="coerce").fillna(0) if c in stats else 0 for c in TD_COLUMNS)
    return float(sum(float(stats[c]) if c in stats and pd.notna(stats[c]) else 0.0 for c in TD_COLUMNS))


def load_snap_counts_all(seasons) -> pd.DataFrame:
    """Every player's snaps per game, linemen and defenders included (PFR names and
    positions; load_snap_counts keeps only players with a gsis id). For injuries_nfl."""
    sc = nfl.load_snap_counts(seasons=list(seasons)).to_pandas()
    sc["team"] = sc["team"].replace(RELOCATED)
    return sc[["game_id", "season", "week", "player", "position", "team", "offense_pct", "defense_pct"]]


def load_player_stats_all(seasons) -> pd.DataFrame:
    """Weekly player stats with the defensive columns (sacks, QB hits). For injuries_nfl, and the Notebook's opponent
    patterns (cards/notebook_nfl.py: opponent_team, catches and yards)."""
    ps = nfl.load_player_stats(seasons=list(seasons)).to_pandas()
    ps["team"] = ps["team"].replace(RELOCATED)
    return ps[["game_id", "season", "week", "player_id", "player_display_name", "position", "team", "opponent_team",
               "targets", "carries", "receptions", "receiving_yards", "rushing_yards", "def_sacks", "def_qb_hits"]]


def load_player_stats(seasons) -> pd.DataFrame:
    """Weekly player stats (regular season and playoffs), the columns the props models use.

    nflverse leaves out players who played but recorded no stats; snap counts fill
    that gap for backtests (docs/MODELS.md).
    """
    ps = nfl.load_player_stats(seasons=list(seasons)).to_pandas()
    ps["team"] = ps["team"].replace(RELOCATED)
    ps["opponent_team"] = ps["opponent_team"].replace(RELOCATED)
    return ps[PLAYER_COLUMNS + [c for c in TD_COLUMNS if c in ps and c not in PLAYER_COLUMNS]]


def load_rosters_weekly(seasons) -> pd.DataFrame:
    """Weekly rosters: gsis_id (= player_id in player stats), name, team, position, status (ACT, INA, RES...)."""
    r = nfl.load_rosters_weekly(seasons=list(seasons)).to_pandas()
    r["team"] = r["team"].replace(RELOCATED)
    return r[["season", "week", "team", "position", "status", "full_name", "football_name", "last_name",
              "gsis_id", "pfr_id"]]


SNAP_POSITIONS = {"HB": "RB", "FB": "RB"}


def load_snap_counts(seasons) -> pd.DataFrame:
    """Offensive snaps per player-game, keyed by gsis_id (the player-stats id).

    Snap counts come from Pro Football Reference with PFR ids; load_ff_playerids maps
    them to gsis ids. Players without a mapping are dropped (rare for skill players).
    Snap counts are what reveal players who played but recorded no stats.
    """
    sc = nfl.load_snap_counts(seasons=list(seasons)).to_pandas()
    ids = nfl.load_ff_playerids().to_pandas()[["gsis_id", "pfr_id"]].dropna().drop_duplicates("pfr_id")
    sc = sc.merge(ids, left_on="pfr_player_id", right_on="pfr_id", how="inner")
    sc["team"] = sc["team"].replace(RELOCATED)
    sc["position"] = sc["position"].replace(SNAP_POSITIONS)
    return sc[["game_id", "season", "week", "gsis_id", "player", "position", "team",
               "offense_snaps", "offense_pct", "defense_snaps", "defense_pct"]].rename(columns={"gsis_id": "player_id"})


def load_injuries(seasons) -> pd.DataFrame:
    """Official weekly injury reports: gsis_id, team, week, report_status (Out, Doubtful,
    Questionable, or empty when the player is only on the practice report)."""
    inj = nfl.load_injuries(seasons=list(seasons)).to_pandas()
    inj["team"] = inj["team"].replace(RELOCATED)
    return inj[["season", "week", "team", "gsis_id", "full_name", "position", "report_status",
                "report_primary_injury", "practice_status"]]


def load_qb_depth(season: int) -> pd.DataFrame:
    """Each team's quarterbacks in order on its latest ESPN depth chart (nflverse updates
    it about twice a day): team, player_id (gsis), name, rank, as_of."""
    d = nfl.load_depth_charts(seasons=[season]).to_pandas()
    d = d[d["pos_abb"] == "QB"].copy()
    d["team"] = d["team"].replace(RELOCATED)
    d = d[d["dt"] == d.groupby("team")["dt"].transform("max")]
    d = d.rename(columns={"gsis_id": "player_id", "player_name": "name", "pos_rank": "rank", "dt": "as_of"})
    return d[["team", "player_id", "name", "rank", "as_of"]].sort_values(["team", "rank"]).reset_index(drop=True)


PRECIP_WORDS = "rain|snow|shower|drizzle|sleet"


def load_weather(seasons) -> pd.DataFrame:
    """Kickoff weather for past games: game_id, indoor (dome or closed roof), temp, wind
    (0 indoors), precip (the play-by-play weather text mentions rain, snow, showers,
    drizzle or sleet) and cold (32 F or colder, outdoors)."""
    seasons = [int(s) for s in seasons]
    g = load_games()
    g = g[g["season"].isin(seasons)][["game_id", "roof", "temp", "wind"]]
    text = load_pbp(seasons, columns=["game_id", "weather"]).drop_duplicates("game_id")
    g = g.merge(text, on="game_id", how="left")
    g["indoor"] = g["roof"].isin(["dome", "closed"])
    g["wind"] = g["wind"].where(~g["indoor"], 0.0)
    g["precip"] = ~g["indoor"] & g["weather"].fillna("").str.contains(PRECIP_WORDS, case=False)
    g["cold"] = ~g["indoor"] & (g["temp"] <= 32)
    return g[["game_id", "roof", "indoor", "temp", "wind", "precip", "cold"]]


def load_pbp(seasons, columns=None) -> pd.DataFrame:
    """Play-by-play for the seasons (only the columns asked for: the full table is ~370 wide)."""
    from betlab.models.game_nfl import PBP_COLUMNS

    cols = list(columns or PBP_COLUMNS)
    return pl.concat([_pbp_season(int(s), cols) for s in seasons], how="diagonal_relaxed").to_pandas()


def _pbp_season(season: int, columns: list[str]) -> pl.DataFrame:
    """One season's play-by-play, reading only the columns asked for from the parquet file (the
    full ~370-column table is never built). Uses nflreadpy's session, so the retries apply."""
    r = get_downloader().session.get(PBP_URL.format(season=season), timeout=120)
    r.raise_for_status()
    return pl.read_parquet(io.BytesIO(r.content), columns=columns)

