"""Leg push alerts (Mike's #23, Oct 24: FanDuel-style notifications as each leg of a real bet hits or misses).

The worker runs `run` every minute. Every open real bet (My bets, `my_bets`) placed in the last 3 days is judged leg by
leg from ESPN (live_legs.py, the web tracker's logic), and its owner's devices get one notification per event:

- a leg hit (a parlay's leg won outright: an over reached, a spread or moneyline won at the final);
- one leg left (every other leg won and the last one still going);
- a leg lost (the parlay is dead: no more alerts for it);
- the bet won (every leg won), which replaces that minute's leg hit.

A single bet only gets won or lost. Each event is sent once, ever: keyed in `alerts_sent` ("leg:<bet>:<i>:won",
"bet:<bet>:won", ...). A bet's first look records what has already happened without sending it (a bet entered after
its first leg hit doesn't replay it). A user can turn these off with user_settings.notify {"legs": false}, and during an
account's quiet hours (alert_prefs.py, Nov 2) events are recorded unsent. An account
on the Pink theme (user_settings.theme, Oct 25: Mike, "it's for my girlfriend call her diva") gets the same facts in
diva words: gentler when a leg loses, louder when it hits.
The iPhone app's devices go through Apple, others through Web Push (alerts._send).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Callable

from betlab import alert_prefs, live_activity, live_legs

OPEN_SQL = """
select b.bet_id::text, b.user_id::text, b.kind, b.sgp_id, b.price, b.label, b.matchup, b.legs, coalesce(b.games, cp.games), b.league,
       b.sport, ft.body, us.theme, coalesce(us.notify ->> 'legs', 'true') <> 'false', b.book, b.stake, b.boost, us.notify, b.protect,
       b.placed_at, b.pick_commence_time, b.ticket_commence_time
from my_bets b left join fun_tickets ft on ft.sgp_id = b.sgp_id
left join user_settings us on us.user_id = b.user_id
left join custom_parlays cp on cp.user_id = b.user_id and cp.sgp_id = b.sgp_id and b.kind = 'custom'
where b.mode = 'real' and b.cashout is null and b.placed_at > now() - interval '3 days'
  and coalesce(b.pick_status, 'open') = 'open' and coalesce(b.ticket_status, 'open') = 'open'
"""
# A Build slip marked before Nov 1 has no games of its own: its saved slip (custom_parlays) has them.
SEEN = "seen:{}"          # a bet's first look (its already-settled legs recorded, not sent)


def bet_name(bet: dict, n: int, by_count: bool = False) -> str:
    """A bet's name in an alert: a parlay by who is in it ("Fagnano, Lawrence and 2 more (+940)"), or by its count where a
    sentence needs the word ("is on your 4-leg parlay (+940)": `by_count`); a single by its leg."""
    price = bet.get("price")
    p = "" if price is None else f" ({'+' if float(price) > 0 else ''}{float(price):g})"
    if n > 1 and by_count:
        return f"{n}-leg parlay{p}"
    return f"{parlay_name(bet.get('legs') or [], n)}{p}" if n > 1 else f"{(bet.get('legs') or [bet.get('label') or 'Bet'])[0]}{p}"


# Where a leg's name stops: a number, a side or a market word ("125+", "-9.5", "over", "ML", "anytime", "to win").
_STOP = re.compile(r"^([+\-.]?\d|o\d|u\d)|^(over|under|ml|anytime|to|yes|no|draw|first|last|alt|both|total|btts)$", re.I)
_SUFFIX = re.compile(r"^(jr\.?|sr\.?|ii|iii|iv)$", re.I)
_TEAM_REST = re.compile(r"^(ml|[+\-]\d+(\.\d+)?|draw)$", re.I)


def leg_name(leg: str, full: bool = False) -> str | None:
    """Who a leg is about: a team by its full name, a player without his first name; None for a leg with no name
    ("Over 47.5"). The apps' rule (web lib/gameday.ts legName, iPhone Stats.legName)."""
    w = leg.split()
    i = next((k for k, x in enumerate(w) if _STOP.search(x)), len(w))
    who, rest = w[:i], w[i:]
    if not who:
        return None
    team = (not rest or (len(rest) == 1 and _TEAM_REST.match(rest[0]))
            or (rest[0].lower() == "to" and len(rest) > 1 and rest[1].lower() == "win"))
    if team or len(who) < 2 or (len(who) == 2 and _SUFFIX.match(who[1])):
        return " ".join(who)
    return " ".join(who if full else who[1:])


def parlay_name(legs: list[str], n: int) -> str:
    """A parlay by who is in it (overhaul, Nov 6): two names, then "and N more" for the other names and the legs with no
    name; one name on every leg is "Rashod Bateman, 2 legs"; no name at all, "4-leg parlay" (tests/fixtures/bet_names.json)."""
    if len(legs) != n:
        return f"{n}-leg parlay"
    names: list[str] = []
    bare = 0
    for leg in legs:
        name = leg_name(leg)
        if name is None:
            bare += 1
        elif name not in names:
            names.append(name)
    if not names:
        return f"{n}-leg parlay"
    if len(names) == 1 and not bare:
        return f"{leg_name(legs[0], full=True)}, {n} legs"
    more = len(names) - min(2, len(names)) + bare
    shown = ", ".join(names[:2])
    return f"{shown} and {more} more" if more else shown


def leg_detail(leg: dict, games: dict) -> str:
    """What happened on a leg, briefly: a prop's count, or the game's score."""
    if leg.get("unit") and leg["unit"] != "total" and leg.get("current") is not None:
        return f"{live_legs._fmt(leg['current'])} {leg['unit']}"
    g = games.get(leg.get("game"))
    if g and g["home"].get("score") is not None and g["sport"] != "ufc":
        a, h = g["away"], g["home"]
        score = f"{a['abbr'] or a['name']} {live_legs._fmt(a['score'] or 0)}-{live_legs._fmt(h['score'] or 0)} {h['abbr'] or h['name']}"
        return score + ("" if g["state"] == "post" else f", {g['detail']}")
    return leg.get("text") or ""


def events(bet_id: str, live: dict, sent: set[str]) -> list[tuple[str, str]]:
    """(key, kind) of this bet's new events, kinds: leg_won, leg_lost, one_left, won, lost (singles: won, lost)."""
    legs, out = live["legs"], []
    if any(k.startswith(f"leg:{bet_id}:") and k.endswith(":lost") for k in sent) or f"bet:{bet_id}:won" in sent:
        return []                                            # already over
    single = len(legs) == 1
    for i, leg in enumerate(legs):
        if leg["status"] in ("won", "lost"):
            key = f"leg:{bet_id}:{i}:{leg['status']}"
            if key not in sent:
                out.append((key, ("won" if leg["status"] == "won" else "lost") if single else f"leg_{leg['status']}"))
    if live["status"] == "won" and not single and f"bet:{bet_id}:won" not in sent:
        out.append((f"bet:{bet_id}:won", "won"))
    # one leg left: every other leg won or off the slip (a pushed or voided leg is out of it, Nov 9), the last still going
    left = [l for l in legs if l["status"] not in ("won", "void")]
    if (not single and live["status"] != "lost" and len(left) == 1
            and f"bet:{bet_id}:one_left" not in sent
            and left[0]["status"] in ("live", "winning", "losing", "tied", "pending")):
        out.append((f"bet:{bet_id}:one_left", "one_left"))
    return out


def message(bet: dict, live: dict, evs: list[tuple[str, str]]) -> dict | None:
    """One notification for a bet's events this minute."""
    kinds = {k for _, k in evs}
    legs, games = live["legs"], {g["key"]: g for g in live["games"]}
    name = bet_name(bet, len(legs))
    by_key = {key: kind for key, kind in evs}

    def leg_of(kind):
        for key, k in by_key.items():
            if k == kind and key.startswith("leg:"):
                return legs[int(key.split(":")[2])]
        return None

    diva = bet.get("theme") == "pink"
    if "lost" in kinds or "leg_lost" in kinds:
        leg = leg_of("lost") or leg_of("leg_lost")
        if diva:
            title = "Oh no, diva 💔" if "lost" in kinds else "Not this one, diva 💔"
            body = (f"{leg['label']} didn't come through ({leg_detail(leg, games)}). "
                    + ("You'll get the next one, queen 👑" if "lost" in kinds else f"{name} is done, but you're still iconic ✨"))
        else:
            title = "Bet lost" if "lost" in kinds else "Leg lost"
            body = f"{leg['label']}: {leg_detail(leg, games)}." + ("" if "lost" in kinds else f" {name} is done.")
    elif "won" in kinds:
        title = "DIVA, YOU WON 💅💸" if diva else "Winner"
        body = f"{name}: every leg hit." if len(legs) > 1 else f"{name}: {leg_detail(leg_of('won') or legs[0], games)}."
        body += " Obviously. 👑" if diva else ""
    elif "leg_won" in kinds or "one_left" in kinds:
        hit = [legs[int(key.split(':')[2])] for key, k in evs if k == "leg_won"]
        left = [l for l in legs if l["status"] not in ("won", "void")]
        title = ("One more, diva ✨" if "one_left" in kinds else "Yes, diva! 💖") if diva \
            else "One leg left" if "one_left" in kinds else "Leg hit"
        parts = [f"{l['label']} ({leg_detail(l, games)})" for l in hit]
        body = ("; ".join(parts) + ". " if parts else "") + f"{live['hit']} of {len(legs)} in"
        if "one_left" in kinds and left:
            body += f"; needs {left[0]['label']}" + (f": {left[0]['text']}" if left[0].get("text") else "")
        body += f" ({name})."
    else:
        return None
    return {"title": title, "body": body[:240], "url": "/bets", "tag": evs[0][0][:64]}


def _row(r) -> tuple[dict, dict | None]:
    keys = ("bet_id", "user_id", "kind", "sgp_id", "price", "label", "matchup", "legs", "games", "league", "sport")
    bet = dict(zip(keys, r[:11]))
    for k in ("legs", "games"):
        if isinstance(bet[k], str):
            bet[k] = json.loads(bet[k])
    body = r[11]
    bet["theme"] = r[12] if len(r) > 12 else None
    bet["alerts"] = r[13] if len(r) > 13 else True        # user_settings.notify.legs; Live Activities go either way
    bet["book"] = r[14] if len(r) > 14 else None
    bet["stake"] = r[15] if len(r) > 15 else None
    bet["boost"] = r[16] if len(r) > 16 else None
    bet["notify"] = r[17] if len(r) > 17 else None
    bet["protect"] = r[18] if len(r) > 18 else None
    for i, k in enumerate(("placed_at", "pick_commence_time", "ticket_commence_time"), 19):   # where to look for its games
        v = r[i] if len(r) > i else None
        bet[k] = v.isoformat() if isinstance(v, datetime) else v
    return bet, (json.loads(body) if isinstance(body, str) else body)


def game_starts(c, bets: list[tuple[dict, dict | None]]) -> None:
    """Each custom bet's games' kickoffs from the games table, by id, for refs that carry no time (bet["game_starts"],
    read by live_legs.groups): an open bet is looked for on its own game's day (Nov 9)."""
    ids = sorted({gid for b, _ in bets for g in (b.get("games") or []) if isinstance(g, dict)
                  and not live_legs.ref_time(g.get("game_ref")) and (gid := live_legs.ref_game_id(g.get("game_ref")))})
    if not ids:
        return
    starts = {gid: t.isoformat() if isinstance(t, datetime) else t for gid, t in
              c.execute("select game_id, commence_time from games where game_id = any(%s) and commence_time is not null",
                        [ids]).fetchall()}
    for b, _ in bets:
        b["game_starts"] = starts


def check(bets: list[tuple[dict, dict | None]], sent: set[str], now: datetime | None = None,
          get=live_legs.espn, lives: dict | None = None) -> list[tuple[dict, list[str], dict | None]]:
    """(bet, event keys to record, message or None when it's only a first look) for every bet with something new.
    `lives` collects every bet's judging ({bet_id: (bet, live)}) for the Live Activities."""
    now = now or datetime.now(live_legs.ET)
    boards: dict = {}
    boxes: dict = {}

    def board(sport, league, days):           # each bet's own game days (live_legs.search_days)
        k = (sport, league, tuple(days))
        if k not in boards:
            boards[k] = live_legs.scoreboard(sport, league, days, get)
        return boards[k]

    def box(game, league):
        if game["key"] not in boxes:
            boxes[game["key"]] = live_legs.boxscore(game, league, get)
        return boxes[game["key"]]

    out = []
    for bet, ticket in bets:
        live = live_legs.live_bet(bet, ticket, board, box, now)
        if lives is not None:
            lives[bet["bet_id"]] = (bet, live)
        if not bet.get("alerts", True):
            continue
        evs = events(bet["bet_id"], live, sent)
        first = SEEN.format(bet["bet_id"]) not in sent
        if first:
            out.append((bet, [SEEN.format(bet["bet_id"])] + [k for k, _ in evs], None))
        elif evs:
            quiet = alert_prefs.in_quiet(alert_prefs.clean(bet.get("notify")), now)
            out.append((bet, [k for k, _ in evs], None if quiet else message(bet, live, evs)))
    return out


def run(send: Callable | None = None, db_url: str | None = None, now: datetime | None = None, get=live_legs.espn) -> str:
    """One minute's check; returns a line for the runs log ("" when nothing happened)."""
    from betlab import alerts, config

    send = send or alerts._send
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    if not db_url:
        return ""
    private_key = config.secret("VAPID_PRIVATE_KEY") or ""
    import psycopg

    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
        bets = [_row(r) for r in c.execute(OPEN_SQL).fetchall()]
        try:
            game_starts(c, bets)
        except Exception as e:  # noqa: BLE001 - without the starts, a bet is looked for around when it was placed
            print(f"leg alerts: game starts unavailable ({type(e).__name__}: {e})")
        ids = [b["bet_id"] for b, _ in bets]
        like = [f"leg:{i}:%" for i in ids] + [f"bet:{i}:%" for i in ids] + [SEEN.format(i) for i in ids]
        sent = {r[0] for r in c.execute("select pick_id from alerts_sent where pick_id like any(%s)", [like]).fetchall()} \
            if bets else set()
        lives: dict = {}
        found = check(bets, sent, now, get, lives)
        lines, notes = [], {}
        for bet, keys, msg in found:
            delivered = 0
            if msg:
                subs = c.execute("select user_id, endpoint, p256dh, auth from push_subscriptions where user_id = %s",
                                 [bet["user_id"]]).fetchall()
                for user_id, endpoint, p256dh, auth in subs:
                    status = send({"user_id": user_id, "endpoint": endpoint, "p256dh": p256dh, "auth": auth}, msg, private_key)
                    if status in (404, 410):
                        c.execute("delete from push_subscriptions where user_id = %s and endpoint = %s", [user_id, endpoint])
                    elif 200 <= status < 300:
                        delivered += 1
                lines.append(f"{msg['title']}: {msg['body']} -> {delivered} of {len(subs)} device(s)")
                notes[bet["bet_id"]] = msg
            for k in keys:
                c.execute("insert into alerts_sent (pick_id, recipients) values (%s, %s) on conflict do nothing", [k, delivered])
        try:                                           # Live Activities never stop the alerts
            line = live_activity.tick(c, lives, notes, now)
        except Exception as e:
            line = f"live activities: failed ({type(e).__name__}: {e})"
        if line:
            lines.append(line)
    return "\n".join(lines)
