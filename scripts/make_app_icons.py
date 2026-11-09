#!/usr/bin/env python3
"""The iPhone's custom app icons (Mike's W12, Nov 2): ESPN's team colors and our season looks -> ios/BetLab/app_icons.json, which
Settings > App icon lists and scripts/make_app_icons.swift draws into the asset catalog. Run by hand:
.venv/bin/python scripts/make_app_icons.py && swift scripts/make_app_icons.swift. No team logos, only colors and abbreviations."""

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PATHS = {"nfl": ("NFL", "football/nfl"), "nba": ("NBA", "basketball/nba"), "nhl": ("NHL", "hockey/nhl")}
LOOKS = [("gold", "Gold", "0b0a08", "e2b84a", "BetLab"), ("pink", "Pink", "0c0a0c", "ff5fa8", "BetLab"), ("purple", "Purple", "0d0b12", "b18cff", "BetLab"),
         ("neon", "Neon", "050505", "39ff14", "BetLab"), ("mint", "Mint", "0f9d78", "ffffff", "BetLab")]
SEASONS = [("football", "Football season", "5a3a1e", "ffffff", "FB"), ("basketball", "Basketball season", "d9661f", "ffffff", "BB"),
           ("hockey", "Hockey season", "0b3d91", "ffffff", "NHL"), ("soccer", "Soccer season", "0e8a3c", "ffffff", "FC"),
           ("fight", "Fight night", "b00020", "ffffff", "UFC"), ("playoffs", "Playoffs", "111111", "e2b84a", "WIN")]


def lum(h: str) -> float:
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def teams(path: str) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams?limit=64"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return [t["team"] for t in r.json()["sports"][0]["leagues"][0]["teams"]]


icons = [{"id": f"Icon-look-{i}", "title": t, "group": "Looks", "bg": b, "fg": f, "tag": ""} for i, t, b, f, _ in LOOKS]
icons += [{"id": f"Icon-season-{i}", "title": t, "group": "Seasons", "bg": b, "fg": f, "tag": a} for i, t, b, f, a in SEASONS]
for league, (group, path) in PATHS.items():
    for t in sorted(teams(path), key=lambda t: t["displayName"]):
        bg = (t.get("color") or "222222").lower()
        alt = (t.get("alternateColor") or "ffffff").lower()
        fg = "111111" if lum(bg) > 0.6 else "ffffff"
        icons.append({"id": f"Icon-{league}-{t['abbreviation']}", "title": t["displayName"], "group": group, "bg": bg, "fg": fg,
                      "tag": t["abbreviation"], "stripe": alt if abs(lum(alt) - lum(bg)) > 0.12 else None})
(ROOT / "ios/BetLab/app_icons.json").write_text(json.dumps(icons, indent=0) + "\n", encoding="utf-8")
print(len(icons), "icons")
