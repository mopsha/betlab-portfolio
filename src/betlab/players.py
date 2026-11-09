"""Matching sportsbook player names to nflverse player ids.

Books write "Michael Penix Jr.", "A.J. Brown" or "DJ Moore"; nflverse may write
"Michael Penix", "AJ Brown" or "D.J. Moore". We normalize both sides (case,
punctuation, suffixes) and match only within the two teams playing, so two
players with the same name on different teams can't be confused.
config/player_aliases.yaml holds the leftovers (book name -> nflverse name; "Chigoziem Okonkwo" is "Chig Okonkwo").
Unmatched names are returned, never guessed.
"""

from __future__ import annotations

import re
import unicodedata
from functools import cache

import pandas as pd
import yaml

from betlab import config

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize(name: str) -> str:
    """'Michael Penix Jr.' -> 'michael penix'; 'A.J. Brown' -> 'aj brown'; accents dropped."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"[.'’`]", "", s.lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    words = [w for w in s.split() if w not in SUFFIXES]
    return " ".join(words)


@cache
def aliases() -> dict[str, str]:
    path = config.CONFIG_DIR / "player_aliases.yaml"
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {normalize(k): normalize(v) for k, v in raw.items()}


def match(book_names, roster: pd.DataFrame) -> tuple[dict[str, str], list[str]]:
    """Map book names to gsis ids using a roster limited to the two teams.

    roster needs gsis_id, full_name and football_name (a nickname such as 'Hollywood').
    Returns ({book name: gsis_id}, [unmatched book names]). A name that fits two
    roster players is left unmatched.
    """
    keys: dict[str, set[str]] = {}
    for r in roster.itertuples():
        first_last = normalize(r.full_name)
        names = {first_last}
        if isinstance(r.football_name, str) and r.football_name:
            names.add(normalize(f"{r.football_name} {first_last.split(' ', 1)[-1]}"))
        for n in names:
            keys.setdefault(n, set()).add(r.gsis_id)
    found, missing = {}, []
    for name in book_names:
        n = normalize(name)
        n = aliases().get(n, n)
        ids = keys.get(n, set())
        if len(ids) == 1:
            found[name] = next(iter(ids))
        else:
            missing.append(name)
    return found, missing
