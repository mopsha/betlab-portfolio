"""NBA preseason live test: how early are nba.com lineups Confirmed, and does FanDuel post
preseason props in the Odds API feed?

The NBA run prices each game 15-75 minutes before tip, with the `lineup` settings only when
both lineups are Confirmed (`props_nba.confirmed_lineups`). Last season's archived lineup
files can't say when that happens: their timestamps are the final update, about 2.5 hours
after tip. So this watches one evening live:

- every 5 minutes it reads nba.com's lineup file and ESPN's scoreboard, and records when
  each team's starters were first listed Expected and first listed Confirmed, in minutes
  before tip;
- about 60 minutes before the first tip it asks the Odds API for the preseason event list
  (free) and one game's FanDuel props (about 8 credits), and counts what comes back.

It stops 15 minutes after the last tip (or after --hours) and writes
data/lineup_watch/<day>.json, which the workflow commits. Paper-free: nothing is priced or
logged to any ledger.

Usage: python scripts/lineup_watch.py [--day YYYYMMDD] [--hours 5.5] [--every 300]
"""

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo("America/New_York")
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
LINEUPS = "https://stats.nba.com/js/data/leaders/00_daily_lineups_{day}.json"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com/"}
ESPN_TO_NBA = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}
PRESEASON_KEY = "basketball_nba_preseason"


def tips(day: str) -> dict[str, datetime]:
    """{NBA team abbreviation: tip-off (UTC)} from ESPN's scoreboard."""
    events = requests.get(SCOREBOARD, params={"dates": day}, timeout=30).json().get("events", [])
    out = {}
    for e in events:
        t = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        for c in e["competitions"][0]["competitors"]:
            a = c["team"]["abbreviation"]
            out[ESPN_TO_NBA.get(a, a)] = t
    return out


def starter_status(day: str) -> dict[str, str]:
    """{team: 'Confirmed' | 'Expected' | 'mixed'} for teams whose starters are listed."""
    try:
        r = requests.get(LINEUPS.format(day=day), headers=HEADERS, timeout=20)
        games = r.json().get("games", []) if r.status_code == 200 else []
    except Exception:
        return {}
    out = {}
    for g in games:
        for side in ("homeTeam", "awayTeam"):
            team = g.get(side) or {}
            statuses = {p.get("lineupStatus") for p in team.get("players", []) if p.get("position")}
            if statuses:
                out[team["teamAbbreviation"]] = statuses.pop() if len(statuses) == 1 else "mixed"
    return out


def props_probe() -> dict:
    """Preseason events (free) and one game's FanDuel props (about 8 credits)."""
    from betlab.sources import odds_api
    if not odds_api.any_key():
        return {"error": "no Odds API key"}
    try:
        client = odds_api.OddsApiClient()
        client.sync_balance()
        events = client.events(PRESEASON_KEY)
        out = {"preseason_events": len(events)}
        now = datetime.now(timezone.utc)
        upcoming = sorted((e for e in events if datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) > now),
                          key=lambda e: e["commence_time"])
        if upcoming:
            e = upcoming[0]
            df = odds_api.flatten(client.event_odds(PRESEASON_KEY, e["id"], odds_api.NBA_PROP_MARKETS),
                                  PRESEASON_KEY, now.isoformat())
            fd = df[df["bookmaker"] == "fanduel"] if "bookmaker" in df else df.iloc[0:0]
            out.update({"game": f"{e['away_team']} @ {e['home_team']}", "prices": len(df),
                        "books": sorted(df["bookmaker"].unique().tolist()) if "bookmaker" in df else [],
                        "fanduel_prices": len(fd),
                        "fanduel_markets": sorted(fd["market"].unique().tolist()) if len(fd) else [],
                        "credits": client.balance_note()})
        return out
    except Exception as exc:  # never print the request (it has the key)
        return {"error": type(exc).__name__}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=datetime.now(ET).strftime("%Y%m%d"))
    ap.add_argument("--hours", type=float, default=5.5)
    ap.add_argument("--every", type=int, default=300)
    ap.add_argument("--no-probe", action="store_true")
    a = ap.parse_args()

    tip = tips(a.day)
    if not tip:
        print(f"no NBA games on {a.day}: nothing to watch")
        return
    first_seen: dict[str, dict[str, float]] = {t: {} for t in tip}
    probe, polls = None, 0
    stop = min(max(tip.values()) + timedelta(minutes=15),
               datetime.now(timezone.utc) + timedelta(hours=a.hours))
    print(f"watching {len(tip)} teams on {a.day} until {stop:%H:%M} UTC")
    while True:
        now = datetime.now(timezone.utc)
        polls += 1
        for team, status in starter_status(a.day).items():
            if team in first_seen and status not in first_seen[team]:
                mins = round((tip[team] - now).total_seconds() / 60, 1)
                first_seen[team][status] = mins
                print(f"{now:%H:%M} UTC  {team}: starters {status}, {mins} min before tip")
        if probe is None and not a.no_probe and min(tip.values()) - now <= timedelta(minutes=60):
            probe = props_probe()
            print("props probe:", probe)
        if now >= stop:
            break
        time.sleep(a.every)

    teams = [{"team": t, "tip_utc": tip[t].isoformat(), **{f"{k.lower()}_min_before": v for k, v in s.items()}}
             for t, s in sorted(first_seen.items())]
    conf = [t["confirmed_min_before"] for t in teams if "confirmed_min_before" in t]
    summary = {
        "day": a.day, "polls": polls, "every_s": a.every, "teams": teams, "props_probe": probe,
        "confirmed": len(conf), "of": len(teams),
        "confirmed_by_75": sum(m >= 75 for m in conf), "confirmed_by_30": sum(m >= 30 for m in conf),
        "confirmed_by_15": sum(m >= 15 for m in conf),
    }
    path = Path("data/lineup_watch") / f"{a.day}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "teams"}, indent=1))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
