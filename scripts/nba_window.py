"""Is an NBA game tipping off 15-75 minutes from now? (Standard library only, no key.)

The hourly NBA tick starts nba.yml; this check runs before anything is installed, so a
tick with no game in the window costs seconds. It reads ESPN's public scoreboard for
today's Eastern date and writes `soon=true|false` to $GITHUB_OUTPUT. `betlab pull-props
--league nba` checks the window again with the Odds API's free event list.

Usage: python scripts/nba_window.py [MIN MAX]
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={day}"


def tipoffs(day: str) -> list[datetime]:
    with urllib.request.urlopen(URL.format(day=day), timeout=30) as r:
        events = json.load(r).get("events", [])
    return [datetime.fromisoformat(e["date"].replace("Z", "+00:00")) for e in events]


def main() -> None:
    lo, hi = (float(a) for a in sys.argv[1:3]) if len(sys.argv) >= 3 else (15.0, 75.0)
    now = datetime.now(timezone.utc)
    day = now.astimezone(ZoneInfo("America/New_York")).strftime("%Y%m%d")
    try:
        soon = [t for t in tipoffs(day) if now + timedelta(minutes=lo) <= t <= now + timedelta(minutes=hi)]
        found = bool(soon)
        print(f"{len(soon)} NBA tip-off(s) {lo:g}-{hi:g} minutes from now" if found
              else f"no NBA tip-off {lo:g}-{hi:g} minutes from now: nothing to do")
    except Exception as exc:  # ESPN down: let the Odds API check decide
        found = True
        print(f"scoreboard check failed ({type(exc).__name__}); continuing to the Odds API check")
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"soon={'true' if found else 'false'}\n")


if __name__ == "__main__":
    main()
