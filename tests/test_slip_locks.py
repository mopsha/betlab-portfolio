"""A watched game's own slips lock by their game (sgp_plus.lock_slips), and that alone makes a tick rebuild (Nov 9)."""

import pandas as pd

from betlab.sgp_plus import keep_tickets, lock_due, slips_due


def _slate(locked=None, sgps=()):
    kick = "2026-11-08T20:30:00Z"
    return {"slate": "2026-11-08-ncaab-afternoon", "sport": "ncaab", "kickoff": kick, "packs": [], "overs": [],
            "locked_at": locked, "plus": {"sgp_id": "T", "games": [{"commence_time": kick}]}, "sgps": list(sgps)}


SLIP = {"sgp_id": "w1", "event_id": "late", "commence_time": "2026-11-08T22:00:00Z", "legs": []}


def test_a_watched_games_slips_make_their_slate_due_without_its_slice():
    """A game later than its slice's first kickoff (a 5 PM tip in a slice locked at 3:15) locked its own slips only at
    the next tick with a pull, often after the start, and its watchers heard nothing (Nov 8: Richmond @ Temple, Real
    Betis @ Elche). The slips' own lock time makes the slate due, so the tick rebuilds (keep_tickets -> lock_slips),
    publishes and alerts on time."""
    slate = _slate("2026-11-08T20:15:00+00:00", [SLIP])
    assert lock_due([slate], pd.Timestamp("2026-11-08T21:30:00Z")) == []            # 30 minutes out: a preview
    now = pd.Timestamp("2026-11-08T21:45:00Z")                                     # 15 minutes out: its lock
    assert slips_due(slate, now) == ["late"]
    assert lock_due([slate], now) == ["2026-11-08-ncaab-afternoon"]
    assert lock_due([slate | {"sgps": []}], now) == []                             # the slice itself locked long ago
    built = keep_tickets([_slate(sgps=[SLIP])], [slate], now)
    assert built[0]["sgps"][0]["locked_at"] == now.isoformat(timespec="seconds")
    assert lock_due(built, now) == []                                              # locked: not due again
    assert lock_due([slate], pd.Timestamp("2026-11-08T22:01:00Z")) == []           # started: too late to lock


def test_an_unlocked_slice_is_still_due_by_its_own_time():
    slate = _slate(sgps=[SLIP])
    assert lock_due([slate], pd.Timestamp("2026-11-08T20:16:00Z")) == ["2026-11-08-ncaab-afternoon"]
    assert slips_due(slate, pd.Timestamp("2026-11-08T20:16:00Z")) == []
