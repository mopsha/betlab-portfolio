"""Did a backtest's result change? (Nov 4, idea #78.) A weekly CI job (.github/workflows/backtests.yml) runs the fast free backtests and compares
them with config/backtest_baseline.json. Closed seasons should never move: if one does, a code change or a re-stated data file changed what the
models say, and someone should know why before the next decision rests on it. NFL's summary still takes in this season's games, so it
gets a wider allowance.

Run it in CI or a throwaway copy, never on the Mac's working files: some backtests save fitted settings as they go (`backtest nhl` rewrites
data/models/nhl.json, which is why the NHL's isn't here, and it takes 20 minutes).

    python scripts/backtest_drift.py            compare; exit 1 on drift
    python scripts/backtest_drift.py --update   write a new baseline, after reading why it moved
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "config" / "backtest_baseline.json"
CLOSED_THROUGH = 2025                  # soccer seasons by the year they start; 2026 is still being played
TIGHT, LOOSE = 0.0005, 0.005           # log loss: closed seasons are rounding only; NFL gets room for this season's games

SOCCER_ROW = re.compile(r"^\s*(\w+)\s+(\d{4})\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+[\d.]+\s+[\d.]+")
NFL_ROW = re.compile(r"^(sp|to|ml) (\{.*\})$")


def parse_soccer(text: str) -> dict[str, float]:
    out = {}
    for line in text.splitlines():
        m = SOCCER_ROW.match(line)
        if m and int(m[2]) <= CLOSED_THROUGH:
            out[f"soccer {m[1]} {m[2]} market"] = float(m[4])
            out[f"soccer {m[1]} {m[2]} model"] = float(m[5])
    return out


def parse_nfl(text: str) -> dict[str, float]:
    out = {}
    for line in text.splitlines():
        m = NFL_ROW.match(line.strip())
        if m:
            d = ast.literal_eval(m[2])
            out[f"nfl {m[1]} market"], out[f"nfl {m[1]} model"] = float(d["market"]), float(d["model"])
    return out


def compare(now: dict[str, float], base: dict[str, float]) -> list[str]:
    """What moved or went missing. A new number (a season that just closed) isn't drift."""
    lines = []
    for k, was in sorted(base.items()):
        if k not in now:
            lines.append(f"{k}: was {was}, now missing")
        elif abs(now[k] - was) > (LOOSE if k.startswith("nfl") else TIGHT):
            lines.append(f"{k}: {was} -> {now[k]}")
    return lines


def run(league: str) -> str:
    p = subprocess.run([sys.executable, "-m", "betlab.cli", "backtest", league], capture_output=True, text=True, cwd=ROOT, timeout=1200)
    if p.returncode:
        raise SystemExit(f"backtest {league} failed:\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}")
    return p.stdout


def main() -> int:
    now = {**parse_soccer(run("soccer")), **parse_nfl(run("nfl"))}
    if len(now) < 20:
        print(f"Only {len(now)} numbers read: the output's format changed, or a data source failed")
        return 1
    if "--update" in sys.argv:
        BASELINE.write_text(json.dumps(now, indent=0, sort_keys=True) + "\n")
        print(f"baseline written: {len(now)} numbers")
        return 0
    drift = compare(now, json.loads(BASELINE.read_text()))
    print(f"{len(now)} numbers read; {len(drift)} moved")
    for ln in drift:
        print(" ", ln)
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
