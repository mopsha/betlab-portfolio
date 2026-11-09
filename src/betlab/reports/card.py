"""The daily card: picks, leans and flags, written for the page (JSON) and for humans (Markdown)."""

from __future__ import annotations

import json

import pandas as pd

from betlab import config

FIELDS = ["pick_id", "league", "matchup", "commence_time", "market", "label", "price", "p_model", "p_market",
          "p_final", "p_push", "ev", "market_source", "tier", "units_flat", "units_tier",
          "units_kelly", "why", "context", "kind", "event_id", "side", "player", "point",
          # the book it's priced at and the other book's price (DraftKings, Oct 12: left out until the evening, so the
          # app showed every bet as FanDuel's and its link was matched at FanDuel)
          "book", "other_book", "other_point", "other_price", "other_ev", "lean_only",
          "bet_limit",     # an exchange price's dollars available (Novig, Oct 22)
          "books"]         # every book's own read of the bet, for accounts that turn books off (Nov 6, books.per_book)


def _records(df: pd.DataFrame) -> list[dict]:
    """The card's fields for each row, JSON-safe."""
    cols = [c for c in FIELDS if c in df]
    return json.loads(df[cols].to_json(orient="records"))


def build(evaluated: pd.DataFrame, generated_at: str, credits: int | None, notes: list[str]) -> dict:
    """Assemble the card: picks, leans and check-the-news lists, each sorted by EV."""
    by_ev = evaluated.sort_values("ev", ascending=False)
    return {
        "generated_at": generated_at,
        "credits_remaining": credits,
        "notes": notes,
        "picks": _records(by_ev[by_ev["tier"] == "pick"]),
        "leans": _records(by_ev[by_ev["tier"] == "lean"]),
        "check_news": _records(by_ev[by_ev["tier"] == "check_news"]),
        "offers_evaluated": int(len(evaluated)),
    }


def markdown(card: dict) -> str:
    """The card as readable Markdown (exports/card.md)."""
    lines = [f"# BetLab card, {card['generated_at']}", ""]
    lines += [f"- {n}" for n in card["notes"]]
    for title, key in (("Picks", "picks"), ("Leans (not bets)", "leans"), ("Check the news", "check_news")):
        lines += ["", f"## {title}", ""]
        if not card[key]:
            lines.append("None.")
        for r in card[key]:
            units = f" | {r['units_flat']:g}u" if key == "picks" else ""
            lines.append(f"- **{r['matchup']}**: {r['label']} ({r['price']:+.0f}), EV {r['ev']:+.1%}{units}")
            if r.get("context"):
                lines.append(f"  {r['context']}")
            lines.append(f"  {r['why']}")
    return "\n".join(lines) + "\n"


def write(card: dict, day: str) -> None:
    """Write exports/card.json, exports/cards/<day>.json and exports/card.md."""
    out = config.EXPORTS_DIR
    (out / "cards").mkdir(parents=True, exist_ok=True)
    text = json.dumps(card, indent=2)
    (out / "card.json").write_text(text, encoding="utf-8")
    (out / "cards" / f"{day}.json").write_text(text, encoding="utf-8")
    (out / "card.md").write_text(markdown(card), encoding="utf-8")
