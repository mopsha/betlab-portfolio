"""The Fun tab's document: suggested same-game parlays per game (exports/fun.json)."""

from __future__ import annotations

import json

from betlab import config


def markdown(doc: dict) -> str:
    """The parlays as readable Markdown, for the terminal and exports/fun.md."""
    lines = [f"# Fun parlays ({doc['status']}), {doc.get('generated_at', '')}", "", doc["note"]]
    for g in doc["games"]:
        lines += ["", f"## {g['matchup']}", ""]
        for n in g.get("notes", []):
            lines.append(f"- {n}")
        for i in g.get("injuries", []):
            lines.append(f"- Injury report: {i['player']} {i['status']} ({i['injury']})")
        if g.get("unmatched"):
            lines.append(f"- Unmatched names: {', '.join(g['unmatched'])}")
        for s in g["sgps"]:
            lines.append(f"- **{s['theme']}**: fair {s['fair_price']:+d} (FanDuel legs multiply to "
                         f"{s['naive_price']:+d})")
            for leg in s["legs"]:
                flag = f" [Questionable: {leg['questionable']}]" if leg.get("questionable") else ""
                lines.append(f"  - {leg['label']} {leg['price']:+d} (fair {leg['fair_price']:+d}){flag}")
            lines.append(f"  {s['why']}")
        if not g["sgps"]:
            lines.append("No parlays in the band.")
    return "\n".join(lines) + "\n"


def write(doc: dict, day: str) -> None:
    """Write exports/fun.json, exports/fun/<day>.json and exports/fun.md."""
    out = config.EXPORTS_DIR
    (out / "fun").mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2, default=str)
    (out / "fun.json").write_text(text, encoding="utf-8")
    (out / "fun" / f"{day}.json").write_text(text, encoding="utf-8")
    (out / "fun.md").write_text(markdown(doc), encoding="utf-8")
