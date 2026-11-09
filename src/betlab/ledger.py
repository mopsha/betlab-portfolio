"""The paper (and later real) bet ledger: one CSV row per pick, committed to git.

A pick is recorded the first time it qualifies, at the price available then.
Later runs never overwrite it, so the git history proves when each pick was
made and at what price.

Leans (edges below the pick bar, never bet) go to a second file in the same format,
`leans.csv`, logged and graded the same way. They measure whether the same signal
(FanDuel lagging the sharp books) beats the close, with more samples than picks alone.
"""

from __future__ import annotations

import hashlib

import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

LEDGER = config.DATA_DIR / "ledger" / "picks.csv"
LEANS = config.DATA_DIR / "ledger" / "leans.csv"
COLUMNS = [
    "pick_id", "created_at", "league", "event_id", "game_ref", "commence_time", "matchup",
    "market", "side", "player", "label", "point", "price", "book", "kind",
    "p_model", "p_market", "p_final", "p_push", "ev", "market_source",
    "units_flat", "units_tier", "units_kelly", "why",
    # filled by grading (clv_raw: props only, CLV against the close before the over-lean
    # correction; the go-live checklist judges props on it, see golive.py)
    "status", "profit_flat", "close_point", "close_price", "p_close", "close_push", "clv", "clv_raw", "graded_at",
    # props (Oct 19): where the close came from, "sharp:<book>" at the bet's line, or "soft" / "none" (no CLV)
    "close_source",
    # filled when you place it for real (taken_book: where, FanDuel or DraftKings, Oct 12; `book` is where it was logged;
    # taken_bonus: placed with a book's bonus credit, Oct 19: a win pays the profit only, a loss costs nothing)
    "taken", "taken_price", "taken_stake", "taken_book", "taken_bonus",
]


def pick_id(r) -> str:
    """Stable 12-character id per league/event/market/side/player, so re-qualifying picks aren't duplicated."""
    key = f"{r['league']}|{r['event_id']}|{r['market']}|{r['side']}|{r['player'] or ''}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


# Text columns stay text even when every value is still empty: pandas 3 reads an all-empty
# column as numbers and then refuses to write a string into it (grading crashed on
# "graded_at" on Sep 25, the first day a prop pick could be graded).
TEXT = ["pick_id", "created_at", "league", "event_id", "game_ref", "commence_time", "matchup", "market", "side",
        "player", "label", "book", "kind", "market_source", "why", "status", "graded_at", "taken", "taken_book", "taken_bonus",
        "close_source"]


def load(path=None) -> pd.DataFrame:
    """The ledger (empty, with the right columns, if it doesn't exist yet). path: LEANS for the leans file."""
    path = path or LEDGER
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype={c: "object" for c in TEXT})
    df = df.reindex(columns=COLUMNS + [c for c in df.columns if c not in COLUMNS])  # files from before a new column
    for c in TEXT:   # a column new to the file arrives as empty floats, which refuse text (close_source, Oct 19)
        df[c] = df[c].astype(object)
    return df


def save(df: pd.DataFrame, path=None) -> None:
    """Write the ledger back in COLUMNS order."""
    path = path or LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(path, index=False)


def apply_taken(taken: list[dict]) -> int:
    """Mark the picks and leans a user took (taken, taken_price, taken_stake, taken_book, taken_bonus), from the page's
    taken list or the app's bets (publish.page_lists). Rows not in the list are unmarked."""
    by_id = {t["pick_id"]: t for t in taken if t.get("pick_id")}
    n = 0
    for path in (LEDGER, LEANS):
        if not path.exists():
            continue
        df = load(path)
        marked = df["pick_id"].isin(by_id)
        df["taken"] = marked
        df["taken_price"] = [by_id[i].get("price") if i in by_id else None for i in df["pick_id"]]
        df["taken_stake"] = [by_id[i].get("stake") if i in by_id else None for i in df["pick_id"]]
        df["taken_book"] = [(by_id[i].get("book") or "FanDuel") if i in by_id else None for i in df["pick_id"]]
        df["taken_bonus"] = [str(bool(by_id[i].get("bonus"))) if i in by_id else None for i in df["pick_id"]]
        save(df, path)
        n += int(marked.sum())
    return n


def bet_key(r) -> str:
    """A pick id's parts with the player normalized (players.normalize: accents, "Jr.", periods), so one bet spelled
    differently by two books (FanDuel "A.J. Brown", DraftKings "AJ Brown") is still one bet (Oct 12)."""
    from betlab import players

    p = r["player"]
    p = "" if p is None or (isinstance(p, float) and pd.isna(p)) else str(p)
    return f"{r['league']}|{r['event_id']}|{r['market']}|{r['side']}|{players.normalize(p)}"


def add_picks(picks: pd.DataFrame, created_at: str, path=None) -> pd.DataFrame:
    """Append picks not already in the ledger (by pick id, or by the same bet under another spelling: bet_key);
    returns the newly added rows."""
    ledger = load(path)
    new = picks.copy()
    if len(new) and "commence_time" in new:
        # never at or after the start (Oct 13: three NHL leans logged 27-47 seconds after puck drop by the on-the-hour
        # tick, and Monday night's leans at 8:15:31 after the feed moved its start to 8:18): a bet logged then may be
        # at in-game prices
        start = pd.to_datetime(new["commence_time"], utc=True, format="ISO8601", errors="coerce")
        if created_at:                                # the card's own time (generated_at), when the bet is logged
            new = new[start.isna() | (start > pd.Timestamp(created_at))]
    new["pick_id"] = [pick_id(r) for _, r in new.iterrows()]
    new = new[~new["pick_id"].isin(ledger["pick_id"])]
    if len(new) and len(ledger):
        seen = {bet_key(r) for _, r in ledger.iterrows()}
        new = new[[bet_key(r) not in seen for _, r in new.iterrows()]]
    if new.empty:
        return new
    new["created_at"] = created_at
    new["status"] = "open"
    for col in COLUMNS:
        if col not in new:
            new[col] = None
    save(pd.concat([ledger, new[COLUMNS]], ignore_index=True) if len(ledger) else new[COLUMNS], path)
    return new
