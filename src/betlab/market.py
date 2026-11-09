"""Reading prices out of a flattened odds snapshot (see sources.odds_api.flatten)."""

from __future__ import annotations

import pandas as pd

from betlab import config


def two_way(ev: pd.DataFrame, market: str, book: str, outcome_a: str, outcome_b: str,
            player: str | None = None):
    """((point_a, price_a), (point_b, price_b)) for one book, or None if either side is missing."""
    rows = ev[(ev["market"] == market) & (ev["bookmaker"] == book)]
    if player is not None:
        rows = rows[rows["player"] == player]
    a = rows[rows["outcome"] == outcome_a]
    b = rows[rows["outcome"] == outcome_b]
    if a.empty or b.empty:
        return None
    return (a["point"].iloc[0], a["price"].iloc[0]), (b["point"].iloc[0], b["price"].iloc[0])


def reference_books(ev: pd.DataFrame, market: str, sharp_books: list[str], target_book: str) -> tuple[list[str], str]:
    """Books to read the fair market from: the sharpest available, else every other book.

    Returns (books, label) where label names the source for the why-notes.
    """
    books = list(ev.loc[ev["market"] == market, "bookmaker"].unique())
    for sharp in sharp_books:
        if sharp in books:
            return [sharp], sharp
    mine = set((config.settings()["odds_api"].get("target_books") or [])) | {target_book}
    others = [b for b in books if b not in mine]      # neither of Mike's books is ever the other's market (Oct 12)
    return others, f"consensus of {len(others)} books"
