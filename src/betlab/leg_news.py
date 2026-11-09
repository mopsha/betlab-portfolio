"""News on your legs (Mike's #49, Nov 2): a player on an open real bet goes out, and the bet's owner hears it with the book's rule.

Every pre-game tick (free): ESPN's injury report for the NFL, NBA and NHL, plus nba.com's inactives, against each open bet's
player legs in games that haven't started. A player must be on one of the game's two teams, so a namesake elsewhere never
counts. Only "out" statuses alert; questionable and day-to-day don't. Each player alerts once per bet ("news:<bet>:<name>" in
`alerts_sent`), and an account can turn it off (notify.news) or hold it through quiet hours (alert_prefs.py). Soccer has no
injury feed here and college props are banned, so neither is covered. The rules are in docs/DRAFTKINGS_PLAN.md (House rules).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

import pandas as pd

from betlab import alert_prefs, leg_alerts, live_legs, news

LEAGUES = ("nfl", "nba", "nhl")
OUT = {"out", "injured reserve", "ir", "suspended", "suspension", "inactive", "physically unable to perform", "pup"}


def is_out(status: str) -> bool:
    return str(status or "").strip().lower() in OUT


def read_outs(league: str, now: datetime) -> dict[str, dict[str, str]]:
    """{team key: {plain name: status}} of who's out, for one league. A source that fails is left out."""
    out: dict[str, dict[str, str]] = {}

    def add(entries: dict[str, list[str]]) -> None:
        for team, rows in entries.items():
            for row in rows:
                name, _, status = row.rpartition(":")
                if name and is_out(status):
                    out.setdefault(team, {})[live_legs.norm_name(name)] = status.strip().title()

    add(news._injuries(league))
    if league == "nba":
        try:
            add(news._nba_lineups(now.astimezone(alert_prefs.ET).strftime("%Y%m%d")))
        except Exception as exc:     # the injury report still counts
            print(f"leg news: nba lineups unavailable ({type(exc).__name__})")
    return out


def _status(outs: dict[str, str], player: str) -> tuple[str, str] | None:
    """(name as listed, status) for a slip's player: the full name, or "J. Allen" when just one out player fits."""
    name = live_legs.norm_name(player)
    if name in outs:
        return name, outs[name]
    parts = name.split()
    if len(parts) == 2 and len(parts[0]) == 1:
        hits = [k for k in outs if k.split()[0][:1] == parts[0] and k.split()[-1] == parts[1]]
        if len(hits) == 1:
            return hits[0], outs[hits[0]]
    return None


def scan(bet: dict, ticket: dict | None, outs: dict[str, dict[str, dict[str, str]]], board) -> list[dict]:
    """This bet's player legs on out players in games not yet started."""
    found = []
    for grp in live_legs.groups(bet, ticket):
        tries = [grp["sport"]] if grp["sport"] else list(LEAGUES)
        for sport in tries:
            if sport not in outs:
                continue
            game = live_legs.find_game(board(sport, None), grp["matchup"])
            if not game:
                continue
            if game["state"] == "pre":
                teams = [news.team_key(game[s]["name"]) for s in ("home", "away")]
                listed = {k: v for t in teams for k, v in outs[sport].get(t, {}).items()}
                for label in grp["legs"]:
                    leg = live_legs.parse_leg(label) or {}
                    hit = _status(listed, leg["player"]) if leg.get("player") else None
                    if hit:
                        found.append({"key": hit[0], "player": leg["player"], "status": hit[1], "label": label, "start": game.get("start")})
            break
    return found


def rule(book, n_legs: int, protect=False) -> str:
    """What the bet's book does when a player doesn't play (docs/DRAFTKINGS_PLAN.md, House rules)."""
    b = str(book or "").lower()
    if "novig" in b:
        return "Novig's own rules decide this one, so check the bet in its app."
    name = "DraftKings" if "draftkings" in b else "FanDuel" if "fanduel" in b else "Your book"
    if n_legs <= 1:
        return f"{name} voids a prop when the player doesn't play, so your stake should come back."
    if protect:
        return "With Bet Protect+, a leg on a player who doesn't play counts as won. Check the slip."
    return f"{name} takes that leg off and reprices, so the rest of the parlay stays alive at a shorter price. Check the slip."


def message(bet: dict, hit: dict, n_legs: int) -> dict:
    name = leg_alerts.bet_name(bet, n_legs, by_count=True)
    return {"title": f"{hit['player']} is out",
            "body": f"ESPN lists {hit['player']} as {hit['status']}. {hit['label']} is on your {name}. "
                    f"{rule(bet.get('book'), n_legs, bet.get('protect'))}"[:240],
            "url": "/bets", "tag": f"news-{bet['bet_id']}"[:64]}


def run(send: Callable | None = None, db_url: str | None = None, now: datetime | None = None,
        get=live_legs.espn, read: Callable = read_outs) -> str:
    from betlab import alerts, config

    send = send or alerts._send
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    if not db_url:
        return "leg news: no app database (SUPABASE_DB_URL): skipped"
    private_key = config.secret("VAPID_PRIVATE_KEY") or ""
    now = now or datetime.now(live_legs.ET)
    import psycopg

    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
        bets = [leg_alerts._row(r) for r in c.execute(leg_alerts.OPEN_SQL).fetchall()]
        bets = [(b, t) for b, t in bets if alert_prefs.clean(b.get("notify"))["news"]]
        checked = sum(1 for b, t in bets for g in live_legs.groups(b, t) for l in g["legs"]
                      if (live_legs.parse_leg(l) or {}).get("player"))
        if not checked:
            return "leg news: no open player legs"
        outs: dict = {}
        for league in LEAGUES:
            try:
                outs[league] = read(league, now)
            except Exception as exc:   # an outage must never look like news, or stop the tick
                print(f"leg news: {league} injuries unavailable ({type(exc).__name__})")
        days = [live_legs.ymd(now - timedelta(days=1)), live_legs.ymd(now), live_legs.ymd(now + timedelta(days=1))]
        boards: dict = {}

        def board(sport, league):
            if sport not in boards:
                boards[sport] = live_legs.scoreboard(sport, league, days, get)
            return boards[sport]

        sent = {r[0] for r in c.execute("select pick_id from alerts_sent where pick_id like 'news:%'").fetchall()}
        alerted = 0
        for bet, ticket in bets:
            n = sum(len(g["legs"]) for g in live_legs.groups(bet, ticket))
            for hit in scan(bet, ticket, outs, board):
                key = f"news:{bet['bet_id']}:{hit['key']}"
                if key in sent:
                    continue
                sent.add(key)
                msg = message(bet, hit, n)
                if alert_prefs.in_quiet(alert_prefs.clean(bet.get("notify")), now):
                    alerts.hold(c, bet["user_id"], msg, hit["start"] or pd.Timestamp(now) + pd.Timedelta(hours=12))
                    delivered = 0
                else:
                    delivered = alerts.deliver(c, bet["user_id"], msg, send, private_key)[0]
                c.execute("insert into alerts_sent (pick_id, recipients) values (%s, %s) on conflict do nothing", [key, delivered])
                alerted += 1
    return f"leg news: {checked} player leg(s) checked, {alerted} out alert(s)"
