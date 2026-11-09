# src/betlab/reports/: what gets written to `exports/`

| File | What it is |
|---|---|
| `card.py` | `build(evaluated, generated_at, credits, notes)` assembles the card dict (picks, leans, check-the-news, sorted by EV; fields in `FIELDS`). `markdown(card)` renders it for humans. `write(card, day)` writes `exports/card.json`, `exports/cards/<day>.json` and `exports/card.md` |
| `review.py` | `summarize(df)` gives record, units, ROI, ROI noise (≈1/√n), CLV count, average CLV and beat-close rate. `build()` returns overall, per-market (`"<league> <market>"`) and taken-only summaries from the ledger. `write()` produces `exports/results.json` |

The weekly narrative review isn't generated here. A Claude session writes it into
the page's `reviews` collection, using `results.json` and the ledger.

Output schemas: `exports/README.md`.

`preview.py` writes `exports/previews.json` (the page's `app/previews` document).

`fun.py` writes the fun parlays: `exports/fun.json` (the page's `app/fun` document), `exports/fun/<ET date>.json` and `exports/fun.md`.
