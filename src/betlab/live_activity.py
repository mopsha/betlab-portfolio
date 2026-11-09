"""Live Activities: a real bet live on the iPhone's lock screen and in the Dynamic Island (Mike's #3, Oct 27).

Runs each minute inside the leg alerts (leg_alerts.run), from the same judging of every open real bet (live_legs.py):

- start: a bet's first game is in progress -> a push-to-start to each of its owner's iPhones (`live_activity_tokens`
  kind 'start'), at most MAX_ACTIVE live at once per account;
- update: what it shows changed (a score, a leg's count, a leg settled), or it hasn't been refreshed in HEARTBEAT, ->
  an update to that activity's own token (kind 'update', which the app saves once Apple starts it). A leg hitting or
  dying goes at high priority, the rest at low (Apple budgets the high ones);
- end: the bet won or lost, every game is over, or it left the open bets (graded, cashed out) -> an end that stays on
  the lock screen for LINGER.

`live_activity_state` remembers what was started and last sent. The JSON keys of `content` are the app's
BetActivityAttributes.ContentState (ios/Shared/BetActivity.swift): **change both together.**
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime

from betlab import apns, live_legs

TOPIC = apns.TOPIC + ".push-type.liveactivity"
MAX_ACTIVE = 3                 # live at once per account
MAX_LEGS = 6                   # legs sent (the lock screen has room for about that many)
MAX_GAMES = 3
HEARTBEAT = 20 * 60            # resend at least this often while live, so it never looks stale
STALE = 30 * 60
LINGER = 60 * 60               # an ended activity stays on the lock screen this long
RETRY = 3 * 60                 # a start no iPhone confirmed (no update token back) goes again after this
MAX_STARTS = 2                 # ...this many starts at most, so a phone that missed one never stacks duplicates;
                               # a confirmed start resets the count, so a card the phone lost (an app update ends
                               # them; the app then drops its token) is started again
SHOW_UNIT = {"3PM": "3s"}       # the tracker's unit -> what the lock screen says
ORDER = {"lost": 0, "losing": 1, "tied": 1, "winning": 1, "live": 1, "pending": 2, "unknown": 3, "won": 4, "void": 5}


def _short(s: str, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def leg_view(leg: dict) -> dict:
    """{label, status, value, progress}: a prop's count against its target ("62/75 yds"), a side's lead ("+3")."""
    cur, target, unit = leg.get("current"), leg.get("target"), leg.get("unit") or ""
    unit = SHOW_UNIT.get(unit, unit)
    value, progress = None, None
    if cur is not None and target is not None:
        value = f"{live_legs._fmt(cur)}/{live_legs._fmt(target)}" + (f" {unit}" if unit and unit != "total" else "")
        if float(target) > 0 and leg["status"] != "pending":     # a leg not under way yet has no bar
            progress = round(max(0.0, min(float(cur) / float(target), 1.0)), 3)
    elif cur is not None:
        value = ("+" if float(cur) > 0 else "") + live_legs._fmt(cur)
    elif leg.get("text") and len(leg["text"]) <= 18 and leg["status"] not in ("pending", "unknown"):
        value = leg["text"]
    return {"label": _short(leg.get("label"), 40), "status": leg["status"], "value": value, "progress": progress}


def game_view(g: dict) -> dict:
    def score(side):
        return None if g["sport"] == "ufc" or side.get("score") is None else live_legs._fmt(side["score"])

    a, h = g["away"], g["home"]
    pre = g["state"] == "pre"
    detail = g.get("detail") or ""
    if pre:                                            # ESPN's "10/27 - 8:00 PM EDT" -> "8:00 PM"
        t = re.search(r"\d{1,2}:\d{2}\s*[AP]M", detail)
        detail = t.group(0) if t else detail
    return {"away": _short(a.get("abbr") or a.get("name"), 14), "home": _short(h.get("abbr") or h.get("name"), 14),
            "awayScore": None if pre else score(a), "homeScore": None if pre else score(h), "state": g["state"],
            "detail": _short(detail, 24), "awayColor": a.get("color"), "homeColor": h.get("color"),
            "awayLogo": a.get("logo"), "homeLogo": h.get("logo")}


def content(live: dict, note: str | None = None) -> dict:
    """The activity's state from a bet's live judging (leg_alerts / live_legs.live_bet)."""
    legs = live["legs"]
    shown = sorted(range(len(legs)), key=lambda i: (ORDER.get(legs[i]["status"], 3), i))[:MAX_LEGS]
    games = live["games"]
    status = live["status"]
    if status in ("live", "pending") and games and all(g["state"] == "post" for g in games):
        status = "final"                                  # every game over; the grader still to come
    keys = [g.get("key") for g in games[:MAX_GAMES]]
    return {"status": status, "hit": live["hit"], "total": live["total"],
            "games": [game_view(g) for g in games[:MAX_GAMES]],
            "legs": [leg_view(legs[i]) | {"game": keys.index(legs[i].get("game")) if legs[i].get("game") in keys else None}
                     for i in sorted(shown)],
            "more": max(0, len(legs) - MAX_LEGS),
            "note": _short(note, 80) if note else None}


def _done(c: dict) -> int:
    """Legs settled (a leg hitting or dying goes at high priority; a score or a count at low)."""
    return c.get("hit", 0) * 100 + sum(l["status"] in ("won", "lost", "void") for l in c.get("legs", []))


def is_on(live: dict) -> bool:
    return any(g["state"] == "in" for g in live["games"])


def is_over(c: dict) -> bool:
    return c.get("status") in ("won", "lost", "final")


def push(event: str, c: dict, now: float, attributes: dict | None = None, alert: dict | None = None) -> dict:
    aps = {"timestamp": int(now), "event": event, "content-state": c}
    if event == "end":
        aps["dismissal-date"] = int(now + LINGER)
    else:
        aps["stale-date"] = int(now + STALE)
    if attributes is not None:                         # push-to-start
        aps["attributes-type"] = "BetActivityAttributes"
        aps["attributes"] = attributes
        aps["input-push-token"] = 1
    if alert:
        aps["alert"] = alert
    return {"aps": aps}


def headers(priority: int) -> dict:
    return {"apns-topic": TOPIC, "apns-push-type": "liveactivity", "apns-priority": str(priority),
            "apns-expiration": str(int(time.time()) + 600)}


def plan(lives: dict, state: dict, tokens: dict, notes: dict, now: float) -> list[dict]:
    """What to send this minute, pure. `lives`: {bet_id: (bet, live)} for open real bets; `state`: {bet_id: row} of
    live_activity_state ({user_id, content, sent_at (epoch), ended, starts}); `tokens`: {user_id: {"start": [...], bet_id:
    [...], "since": {token: epoch created}}} of (env, token); `notes`: {bet_id: the alert sent this minute}. Each action: {bet_id, user_id, event, body,
    priority, to: [(env, token)], content}."""
    out = []
    active: dict[str, int] = {}
    for bet_id, row in state.items():
        if not row["ended"]:
            active[row["user_id"]] = active.get(row["user_id"], 0) + 1
    for bet_id, (bet, live) in lives.items():
        user, row = bet["user_id"], state.get(bet_id)
        mine = tokens.get(user, {})
        note = notes.get(bet_id)
        note_text = f"{note['title']}: {note['body']}" if note else None
        if row is None:
            if not is_on(live) or live["status"] in ("won", "lost") or active.get(user, 0) >= MAX_ACTIVE:
                continue
            if not mine.get("start"):
                continue
            c = content(live, note_text)
            body = _start(bet_id, bet, live, c, now)
            out.append({"bet_id": bet_id, "user_id": user, "event": "start", "body": body, "priority": 10,
                        "to": mine["start"], "content": c})
            active[user] = active.get(user, 0) + 1
            continue
        if row["ended"]:
            continue
        c = content(live, note_text or row["content"].get("note"))
        since = mine.get("since", {})
        late = [t for t in mine.get("start", []) if since.get(t[1], 0) > row["sent_at"]]
        retry = row.get("starts", 1) < MAX_STARTS and now - row["sent_at"] >= RETRY
        if not mine.get(bet_id) and (late or retry) and mine.get("start") and is_on(live) and not is_over(c):
            # never confirmed: an iPhone registered after the start (Oct 27: the first start went to a simulator, the
            # phone came 8 minutes later), or the start was lost; start it again; sent_at and starts keep it from looping
            out.append({"bet_id": bet_id, "user_id": user, "event": "start", "body": _start(bet_id, bet, live, c, now),
                        "priority": 10, "to": late or mine["start"], "content": c})
            continue
        changed = c != row["content"]
        if not changed and now - row["sent_at"] < HEARTBEAT:
            continue
        settled = _done(c) != _done(row["content"]) or c["status"] != row["content"].get("status")
        event = "end" if is_over(c) else "update"
        out.append({"bet_id": bet_id, "user_id": user, "event": event, "body": push(event, c, now),
                    "priority": 10 if settled or event == "end" else 5, "to": mine.get(bet_id, []), "content": c})
    for bet_id, row in state.items():                  # started, no longer open: graded, cashed out or too old
        if row["ended"] or bet_id in lives:
            continue
        c = dict(row["content"])
        if not is_over(c):
            c["status"] = "final"
        out.append({"bet_id": bet_id, "user_id": row["user_id"], "event": "end", "body": push("end", c, now),
                    "priority": 10, "to": tokens.get(row["user_id"], {}).get(bet_id, []), "content": c})
    return out


def _start(bet_id: str, bet: dict, live: dict, c: dict, now: float) -> dict:
    """A push-to-start, always with its alert, as Apple's start payload has (the Oct 27 resend had none and never showed)."""
    name = _name(bet, live)
    first = live["games"][0] if live["games"] else None
    return push("start", c, now, {"betId": bet_id, "name": name, "book": bet.get("book"), "toWin": to_win(bet)},
                {"title": name, "body": "Game on" + (f": {game_view(first)['away']} @ {game_view(first)['home']}"
                                                    if first else "")})


def to_win(bet: dict) -> str | None:
    """What a win pays in units, boost included ("10.48u"), as My bets shows it."""
    try:
        price, stake = float(bet["price"]), float(bet.get("stake") or 1)
    except (KeyError, TypeError, ValueError):
        return None
    profit = stake * (price / 100 if price > 0 else 100 / -price) * (1 + max(float(bet.get("boost") or 0), 0) / 100)
    return f"{profit:.2f}u"


def _name(bet: dict, live: dict) -> str:
    from betlab import leg_alerts

    return leg_alerts.bet_name(bet, len(live["legs"]))


def tick(c, lives: dict, notes: dict, now: datetime | None = None, post=None) -> str:
    """One minute's Live Activity pushes on an open connection; returns a log line ("" when nothing was sent)."""
    post = post or apns.post
    ts = (now or datetime.now(live_legs.ET)).timestamp()
    state = {r[0]: {"user_id": str(r[1]), "content": r[2] if isinstance(r[2], dict) else json.loads(r[2]),
                    "sent_at": r[3].timestamp(), "ended": r[4] is not None, "starts": r[5] if len(r) > 5 else 1}
             for r in c.execute("select bet_id, user_id, content, sent_at, ended_at, starts from live_activity_state "
                                "where ended_at is null or bet_id = any(%s)", [list(lives)]).fetchall()}
    users = {b["user_id"] for b, _ in lives.values()} | {r["user_id"] for r in state.values()}
    if not users:
        return ""
    tokens: dict = {}
    for user_id, token, env, kind, bet_id, *made in c.execute(
            "select user_id::text, token, env, kind, bet_id, created_at from live_activity_tokens "
            "where user_id::text = any(%s)", [list(users)]).fetchall():
        mine = tokens.setdefault(user_id, {})
        mine.setdefault("start" if kind == "start" else bet_id, []).append((env, token))
        if made and made[0] is not None:
            mine.setdefault("since", {})[token] = made[0].timestamp()
    for bet_id, row in state.items():                  # confirmed (its update token is in): the start count resets
        if not row["ended"] and row["starts"] and tokens.get(row["user_id"], {}).get(bet_id):
            c.execute("update live_activity_state set starts = 0 where bet_id = %s", [bet_id])
            row["starts"] = 0
    sent = []
    for a in plan(lives, state, tokens, notes, ts):
        if a["event"] == "update" and not a["to"]:
            continue                                   # its token isn't saved yet: try again next minute
        ok = 0
        for env, token in a["to"]:
            status = post(env, token, headers(a["priority"]), a["body"])
            if status == 200:
                ok += 1
            elif status == 410:
                c.execute("delete from live_activity_tokens where token = %s", [token])
        payload = json.dumps(a["content"])
        if a["event"] == "start":
            if not ok:
                continue
            c.execute("insert into live_activity_state (bet_id, user_id, content) values (%s, %s, %s) "
                      "on conflict (bet_id) do update set content = excluded.content, sent_at = now(), ended_at = null, "
                      "starts = live_activity_state.starts + 1",
                      [a["bet_id"], a["user_id"], payload])
        else:
            c.execute("update live_activity_state set content = %s, sent_at = now()"
                      + (", ended_at = now()" if a["event"] == "end" else "") + " where bet_id = %s", [payload, a["bet_id"]])
            if a["event"] == "end":
                c.execute("delete from live_activity_tokens where kind = 'update' and bet_id = %s", [a["bet_id"]])
        sent.append(f"{a['event']} {a['bet_id'][:8]} -> {ok} of {len(a['to'])}")
    return ("live activities: " + ", ".join(sent)) if sent else ""
