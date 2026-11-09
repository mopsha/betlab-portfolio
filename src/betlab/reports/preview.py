"""The Games tab's document: game previews (exports/previews.json)."""

from __future__ import annotations

import json

from betlab import config


def write(doc: dict) -> None:
    """Write exports/previews.json (the page's app/previews document)."""
    (config.EXPORTS_DIR / "previews.json").write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
