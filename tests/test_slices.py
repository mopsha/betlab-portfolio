"""Kickoff slices: the worker's slice_of against the fixture the apps read too (web lib/slices.ts, iPhone Slices)."""

import json
from pathlib import Path

import pytest

from betlab import sgp_plus

FIX = json.loads((Path(__file__).parent / "fixtures" / "slices.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", FIX["cases"], ids=lambda c: f"{c[0]} {c[1]}")
def test_slice_of_matches_the_apps(case):
    sport, kickoff, day, name = case
    assert sgp_plus.slice_of(kickoff, sport) == (day, name)
