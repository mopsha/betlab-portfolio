"""NFL: the shared football evaluator on nflverse data."""

from __future__ import annotations

import pandas as pd

from betlab import config
from betlab.cards import football
from betlab.sources import nflverse

LEAGUE = football.FootballLeague(
    key="nfl",
    load_games=nflverse.games_with_epa,
    team_names=nflverse.team_abbr_by_name,
    params_path=config.DATA_DIR / "models" / "nfl_params.json",
    first_season=2009,
)


def evaluate(snap: pd.DataFrame, asof: pd.Timestamp, book: str = "fanduel") -> pd.DataFrame:
    return football.evaluate(LEAGUE, snap, asof, book)


def load_model(games: pd.DataFrame):
    return football.load_model(LEAGUE, games)
