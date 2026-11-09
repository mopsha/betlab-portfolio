"""The page export keeps every database document under 256 KiB: the Fun document splits per
game, a month of the ledger splits into chunks (the Fun document passed the limit on 2026-09-26)."""

import json

import pandas as pd

from betlab import cli, config, ledger


def big_fun(games=16, slips=6):
    leg = {"label": "Some Player 60+ receiving yds", "note": "x" * 400, "price": -150, "p_fair": 0.55}
    return {"generated_at": "2026-09-27T14:00:00+00:00", "slates": [{"slate": "s", "plus": None}],
            "games": [{"event_id": f"e{i}", "matchup": f"A{i} @ B{i}", "commence_time": "2026-09-27T17:00:00Z",
                       "primetime": i == 0, "game_ref": f"2026_04_A{i}_B{i}",
                       "sgps": [{"sgp_id": f"s{i}{j}", "legs": [leg] * 5, "why": "y" * 800} for j in range(slips)],
                       "reads": [{"player": "P", "p_model": 0.5}] * 40} for i in range(games)]}


def test_split_fun_keeps_an_index_and_one_document_per_game():
    body, games = cli.split_fun(big_fun())
    assert len(games) == 16 and body["games_split"] and body["slates"]
    assert body["games"][0] == {"event_id": "e0", "matchup": "A0 @ B0", "commence_time": "2026-09-27T17:00:00Z",
                                "primetime": True, "game_ref": "2026_04_A0_B0", "n_sgps": 6, "has_pack": False}
    assert games[3][0] == "e3" and len(games[3][1]["sgps"]) == 6


def test_split_card_moves_leans_into_listed_chunks():
    card = {"generated_at": "t", "picks": [{"pick_id": "p"}], "leans": [{"pick_id": str(i), "context": "c" * 1500} for i in range(300)]}
    body, chunks = cli.split_card(card)
    assert body["leans"] == [] and body["picks"] == card["picks"] and body["leans_docs"] == [c for c, _ in chunks]
    assert len(chunks) > 1 and sum(len(c["rows"]) for _, c in chunks) == 300
    assert all(c["generated_at"] == "t" and len(json.dumps(c)) < 256 * 1024 for _, c in chunks)


def test_chunk_rows_stays_under_the_limit():
    rows = [{"pick_id": str(i), "why": "z" * 900} for i in range(600)]
    parts = cli.chunk_rows(rows, limit=200_000)
    assert len(parts) > 1 and sum(len(p) for p in parts) == 600
    assert all(len(json.dumps(p)) < 256 * 1024 for p in parts)


def test_export_writes_every_document_under_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path)
    (tmp_path / "fun.json").write_text(json.dumps(big_fun()), encoding="utf-8")
    leans = [{"pick_id": str(i), "context": "c" * 1500} for i in range(177)]
    (tmp_path / "card.json").write_text(json.dumps({"generated_at": "t", "picks": [], "leans": leans}), encoding="utf-8")
    rows = pd.DataFrame([{c: None for c in ledger.COLUMNS} | {"pick_id": str(i), "commence_time": "2026-11-05T00:00:00Z",
                                                                 "matchup": "m" * 700, "why": ""} for i in range(500)])
    monkeypatch.setattr(ledger, "load", lambda path=None: rows)
    cli.cmd_export_page(None)
    manifest = json.loads((tmp_path / "page_sync" / "manifest.json").read_text())
    names = [(m["collection"], m["doc_id"]) for m in manifest]
    assert ("app", "fun") in names and ("fun_games", "e0") in names and ("ledger", "2026-11-2") in names
    assert ("app", "card") in names and ("card_leans", "1") in names
    for m in manifest:
        assert len((tmp_path / "page_sync" / m["file"].split("/")[-1]).read_bytes()) < 256 * 1024, m


def test_export_writes_nan_as_null(tmp_path, monkeypatch):
    """Oct 1: the NHL view carried NaN in "book" and the page sync refused the document."""
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path)
    (tmp_path / "nhl.json").write_text('{"games": [{"book": NaN, "line": {"total": Infinity, "over": -110}}]}',
                                       encoding="utf-8")
    monkeypatch.setattr(ledger, "load", lambda path=None: pd.DataFrame(columns=ledger.COLUMNS))
    cli.cmd_export_page(None)
    text = (tmp_path / "page_sync" / "app__nhl.json").read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    assert json.loads(text)["games"][0] == {"book": None, "line": {"total": None, "over": -110}}
