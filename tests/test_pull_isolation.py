"""`betlab pull` (cli.cmd_pull): each league on its own (Nov 9). One league's Odds API error used to end the step, and
in the 9:55 daily, where it is a hard step, the morning card, publish and alerts of every league with it."""

import argparse

import pandas as pd
import pytest

from betlab import alerts, cli
from betlab.sources import odds_api


class Client:
    def __init__(self, bad):
        self.bad, self.asked = bad, []

    def sync_balance(self):
        pass

    def balance_note(self):
        return "n/a"

    def odds(self, sport_key, markets=()):
        self.asked.append(sport_key)
        if sport_key in self.bad:
            raise odds_api.OddsApiError(f"/sports/{sport_key}/odds failed on every key: HTTP 429")
        return [sport_key]


@pytest.fixture
def pull(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    problems = []
    monkeypatch.setattr(odds_api, "any_key", lambda: True)
    monkeypatch.setattr(odds_api, "flatten", lambda data, key, ts: pd.DataFrame({"event_id": ["e1"], "sport": [key]}))
    monkeypatch.setattr(odds_api, "save_snapshot", lambda df, key, ts, kind: tmp_path / f"{key}.parquet")
    monkeypatch.setattr(alerts, "problem", lambda kind, lines: problems.append((kind, lines)) or "alerts: (test)")

    def run(bad, leagues=("nfl", "nhl", "nba")):
        sport = lambda lg: cli.config.settings()["leagues"][lg]["sport_key"]
        client = Client({sport(lg) for lg in bad})
        monkeypatch.setattr(odds_api, "OddsApiClient", lambda: client)
        args = argparse.Namespace(prime_time=False, leagues=list(leagues), auto=False, again=None)
        code = 0
        try:
            cli.cmd_pull(args)
        except SystemExit as e:
            code = e.code
        return code, client, out.read_text(), problems
    return run


def test_one_leagues_error_leaves_the_others_pulled(pull, capsys):
    code, client, out, problems = pull({"nhl"})
    assert code == cli.WARN_EXIT                          # the worker records it and the daily goes on
    assert len(client.asked) == 3 and "pulled=true" in out
    assert "nhl: not pulled (" in capsys.readouterr().out
    assert problems == [("the odds pull", ["odds pull failed (nhl)"])]


def test_every_league_failing_fails_the_step(pull):
    code, _, out, problems = pull({"nfl", "nhl"}, leagues=("nfl", "nhl"))
    assert code == 1 and "pulled" not in out and problems == []   # the worker's failed-step alert says it


def test_no_error_no_exit(pull):
    code, _, out, problems = pull(set())
    assert code == 0 and "pulled=true" in out and problems == []
