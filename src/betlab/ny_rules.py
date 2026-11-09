"""New York betting restrictions, applied before anything reaches the card.

Name matching is by prefix ("Syracuse" matches "Syracuse Orange"), which can
also exclude an out-of-state school whose name starts the same way. That
errs on the side of skipping a legal game, never of betting an illegal one.
"""

from __future__ import annotations

import re

from betlab import config

COLLEGE_LEAGUES = {"ncaaf", "ncaab"}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def is_ny_college(team: str) -> bool:
    team_n = _norm(team)
    return any(team_n.startswith(_norm(school)) for school in config.ny_restrictions()["ny_college_teams"])


def allowed(league: str, home: str, away: str, player: str | None = None,
            venue_state: str | None = None) -> tuple[bool, str]:
    """(allowed, reason) for a bet under New York rules."""
    if league not in COLLEGE_LEAGUES:
        return True, ""
    rules = config.ny_restrictions()
    if player and not rules["college_player_props"]:
        return False, "New York bans college player props"
    if is_ny_college(home) or is_ny_college(away):
        return False, "New York bans bets on games involving New York colleges"
    if venue_state == "NY" and not rules["college_games_in_ny_state"]:
        return False, "New York bans bets on college games played in New York"
    return True, ""
