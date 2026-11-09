"""One text shape for start times in every ledger (Oct 14).

The odds feed writes `2026-10-10T23:10:00Z`, ESPN `2026-10-01T02:00Z`, some writers `+00:00`. A ledger
holding two shapes broke pandas' format inference (`to_datetime` without `format="ISO8601"` takes the
first row's shape): the Oct 13-14 dailies graded no NHL prop lines. Every ledger save passes through
`utc_starts`, which rewrites each start column as `YYYY-MM-DDTHH:MM:SSZ` (UTC). Same instant, one shape.
"""

from __future__ import annotations

import pandas as pd

START_COLUMNS = ("commence_time", "start", "kickoff", "tipoff")
SHAPE = "%Y-%m-%dT%H:%M:%SZ"


def utc_text(values: pd.Series) -> pd.Series:
    """Each value as SHAPE in UTC; blanks stay blank and anything unparseable is kept as it was."""
    t = pd.to_datetime(values, utc=True, format="ISO8601", errors="coerce")
    return t.dt.strftime(SHAPE).where(t.notna(), values)


def utc_starts(df: pd.DataFrame) -> pd.DataFrame:
    """The frame with its start columns (START_COLUMNS) in SHAPE, ready to save."""
    cols = [c for c in START_COLUMNS if c in df.columns]
    return df.assign(**{c: utc_text(df[c]) for c in cols}) if cols and len(df) else df
