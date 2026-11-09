"""College football: the shared football evaluator on CollegeFootballData history.

New York rules are applied inside the evaluator: no games involving New York
colleges, none played in New York, and no player props at all.
"""

from __future__ import annotations

import pandas as pd

from betlab import config
from betlab.cards import football
from betlab.models.football import GameParams
from betlab.sources import cfbd

LEAGUE = football.FootballLeague(
    key="ncaaf",
    load_games=cfbd.games,
    team_names=cfbd.team_names,
    params_path=config.DATA_DIR / "models" / "ncaaf_params.json",
    first_season=2016,
    # tuned on 2016-2021, tested on 2022-2025: less shrinkage than the NFL (bigger talent gaps)
    base=GameParams(half_life_days=150, ridge_pts=1.0, ridge_epa=1.0, early_weeks=4),
)


def evaluate(snap: pd.DataFrame, asof: pd.Timestamp, book: str = "fanduel") -> pd.DataFrame:
    return football.evaluate(LEAGUE, snap, asof, book)


def load_model(games: pd.DataFrame):
    return football.load_model(LEAGUE, games)
