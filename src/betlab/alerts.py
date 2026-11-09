"""Pick alerts (Mike, 2026-10-04: "I need notifications of when a pick is found").

`betlab alert` runs after each card in the worker's jobs. Every pick logged in the last
`WINDOW` that hasn't started and wasn't announced yet (the database's `alerts_sent`) goes to
every device that turned alerts on (`push_subscriptions`, Web Push from the home-screen app).
Picks only, never leans. Up to `MAX_SINGLE` new picks each get their own notification; more
than that arrive as one summary. A pick is marked announced even when nobody is subscribed,
so turning alerts on later never replays old picks. A device the push service no longer knows
(404 or 410) is removed.

Locked tickets (Mike, 2026-10-10: "when you lock the ticket a notification should be sent"): each
fun slice's SGP+ / TD tickets lock 15 minutes before its first kickoff (sgp_plus.keep_tickets); a
slice that locked with a ticket and hasn't started is announced once, keyed "lock:<slate>" in the
same `alerts_sent` table. A watched game's own slips are announced to its watchers when they lock, by the game ("slips:<event id>", Nov 7).

The native iPhone app's devices (endpoint 'apns:...', Oct 14) go through Apple instead (apns.py, its own keys).

Each account's settings (alert_prefs.py, Nov 2) choose picks, leans, locks, sports and a minimum EV. Leans are off by default,
keyed "lean:<id>" and only marked once some account wants them. An alert found in quiet hours waits in `alerts_held` until
`release` sends it (every pre-game tick), or is dropped once its game has started.

Keys: VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY (Mike made them and pasted them into Railway;
the web app reads the public one as NEXT_PUBLIC_VAPID_PUBLIC_KEY). Without them, or without
the database, the command says so and does nothing.
"""

from __future__ import annotations

import json
from typing import Callable

import pandas as pd

from betlab import alert_prefs, bans, books, config, ledger

WINDOW = pd.Timedelta(hours=6)
MAX_SINGLE = 3
CONTACT = "mailto:betlab-bot@users.noreply.github.com"   # the push services' contact for this sender
LEAGUE = {"nfl": "NFL", "ncaaf": "College football", "nba": "NBA", "ncaab": "College basketball", "nhl": "NHL",
          "epl": "Premier League", "la_liga": "La Liga", "serie_a": "Serie A", "bundesliga": "Bundesliga",
          "ligue_1": "Ligue 1", "mls": "MLS", "ucl": "Champions League", "uel": "Europa League",
          "uecl": "Conference League"}


def pending(picks: pd.DataFrame, sent: set[str], now: pd.Timestamp) -> pd.DataFrame:
    """New picks to announce: logged within WINDOW, not started, open, not announced yet."""
    if picks.empty:
        return picks
    made = pd.to_datetime(picks["created_at"], utc=True, format="ISO8601")
    start = pd.to_datetime(picks["commence_time"], utc=True, format="ISO8601")
    keep = (made > now - WINDOW) & (start > now) & (picks["status"] == "open") & ~picks["pick_id"].isin(sent)
    return picks[keep].sort_values("ev", ascending=False)


def slip_locks(slates: list[dict], sent: set[str], now: pd.Timestamp) -> dict[str, list[dict]]:
    """{event id: its own slips} for games whose slips just locked (sgp_plus.lock_slips: by the game's own start, never
    its slice, Mike Nov 7), not started and not announced yet ("slips:<event id>"). Each account hears of the games it
    watches; before Nov 7 a lone NFL game's and a Knicks game's slips alerted everyone with their slice."""
    out: dict[str, list[dict]] = {}
    for s in slates:
        for x in s.get("sgps") or []:
            eid = str(x.get("event_id"))
            if x.get("locked_at") and pd.Timestamp(x["commence_time"]) > now and f"slips:{eid}" not in sent:
                if x["sgp_id"] not in {y["sgp_id"] for y in out.get(eid, [])}:
                    out.setdefault(eid, []).append(x)
    return out


def slips_message(slips: list[dict], on: list[str] | None = None) -> dict:
    """'Locked: Knicks @ Cavaliers slips', how many, their fair prices and the start."""
    start = pd.Timestamp(slips[0]["commence_time"]).tz_convert("America/New_York")
    main = [x for x in slips if not x.get("longshot")]
    fair = sorted(int(x["fair_price"]) for x in main if x.get("fair_price") is not None)
    span = f", fair {_price(fair[0])} to {_price(fair[-1])}" if len(fair) > 1 else (f", fair {_price(fair[0])}" if fair else "")
    extra = " plus a long shot" if len(main) < len(slips) else ""
    single = len(main) == 1 and main[0].get("style") == "single"
    what = "best single" if single else f"{len(main)} slip{'s' if len(main) != 1 else ''}"
    nick = " @ ".join(t.split()[-1] for t in str(slips[0].get("matchup") or "").split(" @ "))
    sport = slips[0].get("sport")
    return {"title": f"Locked: {nick} {'pick' if single else 'slips'}",
            "body": f"{slips[0].get('matchup')}: {what}{span}{extra}. "
                    f"{'Tip-off' if sport in ('nba', 'ncaab') else 'Puck drop' if sport == 'nhl' else 'Start'} "
                    f"{start:%I:%M %p}".replace(" 0", " ") + " ET." + _open_at(on).replace(" it ", " one ", 1),
            "url": "/", "tag": f"slips-{slips[0].get('event_id')}"}


def watched_events(c) -> dict[str, frozenset]:
    """{user id: the Odds API event ids of the games it watches} from user_settings.watching (game ids, migration
    0045) through the games table. An app database without the column yet reads as nobody watching."""
    try:
        rows = c.execute("select s.user_id, g.odds_event_id from user_settings s "
                         "join games g on g.game_id = any(s.watching) where g.odds_event_id is not null").fetchall()
    except Exception as e:  # noqa: BLE001 - a missing column never stops the alerts
        print(f"alerts: watched games unavailable ({type(e).__name__})")
        return {}
    out: dict[str, set] = {}
    for user_id, eid in rows:
        out.setdefault(str(user_id), set()).add(str(eid))
    return {k: frozenset(v) for k, v in out.items()}


NEWS_NOTE = "The news changed after the early lock, so it was rebuilt (if you placed the earlier one, compare). "


def lock_key(s: dict) -> str:
    """The alerts_sent key of a slice's lock: "lock:<slate>", ":u<n>" for its n-th update on new news, and ":r" for a
    slice locked again after new slice hours (sgp_plus._resliced)."""
    return (f"lock:{s['slate']}" + (f":u{s['updated']}" if s.get("updated") else "")
            + (":r" if s.get("resliced") else ""))


def locked(slates: list[dict], sent: set[str], now: pd.Timestamp, games: list[dict] | None = None) -> list[dict]:
    """Slices that just locked (or locked again on new news) with a ticket; not started yet, not announced yet. A game's
    own slips lock and alert by their game (slip_locks)."""
    return [s for s in slates if s.get("locked_at") and (s.get("plus") or s.get("plus_short") or s.get("td"))
            and pd.Timestamp(s["kickoff"]) > now and lock_key(s) not in sent]


def _open_at(on: list[str] | None) -> str:
    """Where a locked slip opens, for an account's books on (Nov 6): FanDuel's link, or DraftKings' price."""
    on = on or ["FanDuel", "DraftKings"]
    ways = (["open it in FanDuel"] if "FanDuel" in on else []) + (["price it at DraftKings"] if "DraftKings" in on else []) \
        + (["price it at Novig"] if on == ["Novig"] else [])
    return " Open BetLab to " + " or ".join(ways) + "."


def lock_message(s: dict, games: list[dict] | None = None, on: list[str] | None = None) -> dict | None:
    """'Locked: College football noon games SGP+', what's on it and when the first game starts; `on`: the account's
    books (books.on_books), for where it opens. None when the slice has no ticket."""
    start = pd.Timestamp(s["kickoff"]).tz_convert("America/New_York")
    if not (s.get("plus") or s.get("plus_short") or s.get("td")):
        return None
    sport = (LEAGUE | {"soccer": "Soccer"}).get(s.get("sport", "nfl"), str(s.get("sport")))
    kinds, parts = [], []
    if s.get("plus"):
        t = s["plus"]
        kinds.append("SGP+")
        parts.append(f"{t['n_games']} games, {t['n_legs']} legs, fair {_price(t['fair_price'])}")
    if s.get("plus_short"):
        t = s["plus_short"]
        if not s.get("plus"):
            kinds.append("SGP+")
        parts.append(f"{t.get('cup') or 'likelier'}: {t['n_games']} games, {t['n_legs']} legs, fair {_price(t['fair_price'])}")
    if s.get("td"):
        kinds.append("TD ticket")
        parts.append(f"TD ticket: {len(s['td'].get('legs') or [])} scorers")
    title = s.get("title") or f"{sport} {s['slate']}"     # titles name the market ("Soccer midday matches")
    return {"title": f"{'Updated on new news' if s.get('updated') else 'Locked'}: {title} {' and '.join(kinds)}",
            "body": (NEWS_NOTE if s.get("updated") else "") + f"{'; '.join(parts)}. First game {start:%I:%M %p}".replace(" 0", " ")
                    + " ET." + _open_at(on),
            "url": "/", "tag": f"lock-{s['slate']}"}


def _price(p) -> str:
    p = float(p)
    return f"+{p:.0f}" if p > 0 else f"{p:.0f}"


def card_books() -> dict[str, dict]:
    """The card's picks and leans by pick id, with each book's own read (books.per_book): what an account with a book
    off is alerted from. Empty when there's no card file."""
    path = config.EXPORTS_DIR / "card.json"
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {r["pick_id"]: r for r in (card.get("picks") or []) + (card.get("leans") or []) if r.get("pick_id")}


def at_account_books(rows: pd.DataFrame, off, reads: dict[str, dict]) -> pd.DataFrame:
    """Picks or leans as an account with `off` books sees them (books.at_books, the apps' rule): at the best book it has
    on, the tier that book earns, or dropped. A pick the card no longer has keeps its own book, if that's on."""
    on = books.on_books(off)
    if rows.empty or len(on) == len(books.SHOWN):
        return rows
    keep = []
    for _, r in rows.iterrows():
        card = reads.get(r["pick_id"]) or {}
        offer = {**r.to_dict(), "book": books.name(r.get("book")), "books": card.get("books"),
                 "other_book": books.name(card["other_book"]) if card.get("other_book") else None,
                 **{k: card.get(k) for k in ("other_point", "other_price", "other_ev")}}
        got = books.at_books(offer, off)
        if got is not None:
            keep.append({**got, "book": {v: k for k, v in books.NAME.items()}.get(got["book"], got["book"]),
                         "other_book": {v: k for k, v in books.NAME.items()}.get(got.get("other_book"), got.get("other_book"))})
    return pd.DataFrame(keep, columns=list(rows.columns) + [c for c in ("other_book", "other_point", "other_price", "other_ev")
                                                             if c not in rows.columns]) if keep else rows.iloc[0:0]


def messages(rows: pd.DataFrame, word: str = "pick") -> list[dict]:
    """The notifications for these picks (or leans): one each, or one summary for more than MAX_SINGLE."""
    out = []
    if len(rows) > MAX_SINGLE:
        best = rows.iloc[0]
        out.append({"title": f"{len(rows)} new BetLab {word}s",
                    "body": f"Best: {best['label']} {_price(best['price'])} (EV {float(best['ev']):+.1%}). "
                            f"Open BetLab for the rest.",
                    "url": "/", "tag": f"{word}s-" + "-".join(rows["pick_id"].head(3))})
        return out
    from betlab.books import name as book_name

    for _, r in rows.iterrows():
        start = pd.Timestamp(r["commence_time"]).tz_convert("America/New_York")
        when = f"{start:%a} {start:%I:%M %p}".replace(" 0", " ")
        # both books' prices, the better first (Mike, Oct 12): "Bills +3.5 · DraftKings -105 · FanDuel -110"
        prices = f"{book_name(r.get('book'))} {_price(r['price'])}"
        if isinstance(r.get("other_book"), str) and r.get("other_book") and pd.notna(r.get("other_price")):
            pt = r.get("other_point")
            moved = "" if pd.isna(pt) or pt == r.get("point") else f" ({float(pt):+g})" if r.get("market") == "spreads" else f" ({float(pt):g})"
            prices += f" · {book_name(r['other_book'])}{moved} {_price(r['other_price'])}"
        out.append({"title": f"{LEAGUE.get(r['league'], str(r['league']).upper())} {word}: {r['label']} · {prices}",
                    "body": f"{r['matchup']} · {when} ET · EV {float(r['ev']):+.1%} · "
                            f"{float(r['units_tier']):g}u at {book_name(r.get('book'))}",
                    "url": "/", "tag": r["pick_id"]})
    return out


def _expiries(rows: pd.DataFrame, msgs: list[dict]) -> list[pd.Timestamp]:
    """When each of `messages(rows)` goes stale: its game's start, or the last start for a summary."""
    starts = pd.to_datetime(rows["commence_time"], utc=True, format="ISO8601")
    return list(starts) if len(msgs) == len(rows) else [starts.max()] * len(msgs)


def deliver(c, user_id, msg: dict, send, private_key: str) -> tuple[int, int, int]:
    """One notification to every device of an account: (delivered, devices, gone devices removed)."""
    subs = c.execute("select user_id, endpoint, p256dh, auth from push_subscriptions where user_id = %s", [user_id]).fetchall()
    ok = gone = 0
    for _, endpoint, p256dh, auth in subs:
        status = _safe(send, {"user_id": user_id, "endpoint": endpoint, "p256dh": p256dh, "auth": auth}, msg, private_key)
        if status in (404, 410):
            c.execute("delete from push_subscriptions where user_id = %s and endpoint = %s", [user_id, endpoint])
            gone += 1
        elif 200 <= status < 300:
            ok += 1
    return ok, len(subs), gone


def hold(c, user_id, msg: dict, until) -> None:
    """Keep an alert for the end of this account's quiet hours (`release`), no later than `until`."""
    c.execute("insert into alerts_held (user_id, msg, expires_at) values (%s, %s::jsonb, %s)",
              [user_id, json.dumps(msg), pd.Timestamp(until).isoformat()])


def without_banned(rows: pd.DataFrame, ban_list: list[dict]) -> pd.DataFrame:
    """The picks with none on a banned player or team (bans.py)."""
    if rows.empty or not ban_list:
        return rows
    keep = [not bans.banned(ban_list, str(r.get("label", "")), r.get("league"),
                            r.get("player") if isinstance(r.get("player"), str) and r.get("player") else None)
            for _, r in rows.iterrows()]
    return rows[keep]


def _send_webpush(sub: dict, payload: dict, private_key: str) -> int:
    """Send one push; returns the HTTP status (201 on success, 404/410 when the device is gone)."""
    from pywebpush import WebPushException, webpush

    try:
        r = webpush({"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                    data=json.dumps(payload), vapid_private_key=private_key,
                    vapid_claims={"sub": CONTACT}, ttl=3600, timeout=15)
        return r.status_code
    except WebPushException as e:
        return e.response.status_code if e.response is not None else 0
    except Exception:  # noqa: BLE001 - a timeout or a dropped connection (requests) is one device's failure, as in apns.post
        return 0


def _send(sub: dict, payload: dict, private_key: str) -> int:
    """One alert to one device: the iPhone app's rows through Apple (apns.py), the rest through Web Push. Never raises
    (Nov 9): one device's error used to end the loop before alerts_sent was written, so the next tick sent the same
    alerts again to the devices before it, and the ones after it got nothing."""
    from betlab import apns

    try:
        return apns.send(sub, payload) if apns.is_apns(sub.get("endpoint", "")) else _send_webpush(sub, payload, private_key)
    except Exception:  # noqa: BLE001
        return 0


def _safe(send: Callable[[dict, dict, str], int], sub: dict, msg: dict, private_key: str) -> int:
    """`send` for one device, 0 on any error: a sender passed in (tests, the leg alerts) gets the same guard."""
    try:
        return int(send(sub, msg, private_key) or 0)
    except Exception:  # noqa: BLE001
        return 0


def fun_slates() -> list[dict]:
    out = []
    for name in ("fun.json", "fun_nba.json"):
        path = config.EXPORTS_DIR / name
        out += json.loads(path.read_text(encoding="utf-8")).get("slates", []) if path.exists() else []
    return out


def fun_games() -> list[dict]:
    """The NFL games' slips (exports/fun.json), for a lone game's lock alert."""
    path = config.EXPORTS_DIR / "fun.json"
    return json.loads(path.read_text(encoding="utf-8")).get("games", []) if path.exists() else []


def run(now: pd.Timestamp | None = None, send: Callable[[dict, dict, str], int] = _send,
        db_url: str | None = None, private_key: str | None = None) -> str:
    now = now or pd.Timestamp.now(tz="UTC")
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    private_key = private_key or config.secret("VAPID_PRIVATE_KEY")
    if not db_url:
        return "alerts: no app database (SUPABASE_DB_URL): skipped"
    if not private_key:
        return "alerts: no VAPID_PRIVATE_KEY yet: skipped"
    import psycopg

    picks = ledger.load()
    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
        sent = {r[0] for r in c.execute("select pick_id from alerts_sent").fetchall()}
        new = pending(picks, sent, now)
        games = fun_games()
        slates = fun_slates()
        locks = locked(slates, sent, now, games)
        slipped = slip_locks(slates, sent, now)      # games whose own slips just locked (Nov 7: by the game)
        # each account's ban list (Oct 25) and alert settings (Nov 2)
        settings = c.execute("select user_id, bans, notify, books_off from user_settings").fetchall()
        watching = watched_events(c) if slipped else {}    # each account's watched games, as event ids (Nov 7, 0045)
        user_bans = {str(r[0]): bans.clean(r[1]) for r in settings}
        prefs = {str(r[0]): alert_prefs.clean(r[2]) for r in settings}
        user_off = {str(r[0]): list(r[3] or []) if len(r) > 3 else [] for r in settings}    # books turned off (Nov 6, 0043)
        reads = card_books()
        leans = pd.DataFrame()
        if any(p["leans"] for p in prefs.values()):   # never read or marked until an account asks for them
            leans = pending(ledger.load(ledger.LEANS), {k[5:] for k in sent if k.startswith("lean:")}, now)
        if new.empty and not locks and not slipped and leans.empty:
            return "alerts: no new picks or locked tickets"
        by_user: dict[str, list[tuple[dict, pd.Timestamp]]] = {}

        def rows_for(rows: pd.DataFrame, user_id, p: dict, tier: str) -> list[tuple[dict, pd.Timestamp]]:
            if rows.empty:
                return []
            mine = without_banned(rows, user_bans.get(user_id, []))
            mine = at_account_books(mine, user_off.get(user_id), reads)
            out = []
            for t in ("pick", "lean"):          # a pick at a book that's off can be a lean at one that's on
                part = mine[mine["tier"] == t] if not mine.empty else mine
                if part.empty or (t == "lean" and tier == "pick" and not p["leans"]):
                    continue
                part = part[[alert_prefs.wants(p, r.get("league"), r.get("ev"), t) for _, r in part.iterrows()]]
                if part.empty:
                    continue
                msgs = messages(part, t)
                out += list(zip(msgs, _expiries(part, msgs)))
            return out

        def msgs_for(user_id) -> list[tuple[dict, pd.Timestamp]]:
            if user_id not in by_user:
                p = prefs.get(user_id) or alert_prefs.clean(None)
                on = books.on_books(user_off.get(user_id))
                by_user[user_id] = (rows_for(new.assign(tier="pick") if not new.empty else new, user_id, p, "pick")
                                    + rows_for(leans.assign(tier="lean") if not leans.empty else leans, user_id, p, "lean")
                                    + [(m, pd.Timestamp(s["kickoff"])) for s in locks
                                       if alert_prefs.wants_lock(p, s.get("sport"))
                                       for m in [lock_message(s, games, on)] if m]
                                    + [(slips_message(x, on), pd.Timestamp(x[0]["commence_time"]))
                                       for eid, x in slipped.items() if eid in watching.get(user_id, frozenset())
                                       and alert_prefs.wants_lock(p, x[0].get("sport"))])
            return by_user[user_id]

        held: set[str] = set()
        subs = [dict(zip(("user_id", "endpoint", "p256dh", "auth"), r)) for r in
                c.execute("select user_id, endpoint, p256dh, auth from push_subscriptions").fetchall()]
        delivered, removed = 0, 0
        for sub in subs:
            ok = False
            user = str(sub["user_id"])
            if alert_prefs.in_quiet(prefs.get(user) or alert_prefs.clean(None), now):
                if user not in held:       # once per account, whatever its number of devices
                    held.add(user)
                    for msg, until in msgs_for(user):
                        hold(c, sub["user_id"], msg, until)
                continue
            for msg, _ in msgs_for(user):
                status = _safe(send, sub, msg, private_key)
                if status in (404, 410):
                    c.execute("delete from push_subscriptions where user_id = %s and endpoint = %s",
                              [sub["user_id"], sub["endpoint"]])
                    removed += 1
                    break
                ok = ok or 200 <= status < 300
            if ok:
                delivered += 1
                c.execute("update push_subscriptions set last_sent_at = now() where user_id = %s and endpoint = %s",
                          [sub["user_id"], sub["endpoint"]])
        for pid in ((list(new["pick_id"]) if not new.empty else []) + [lock_key(s) for s in locks]
                    + [f"slips:{eid}" for eid in slipped]
                    + ([f"lean:{i}" for i in leans["pick_id"]] if not leans.empty else [])):
            c.execute("insert into alerts_sent (pick_id, recipients) values (%s, %s) on conflict do nothing",
                      [pid, delivered])
    # games' slips lock for everyone; only their watchers hear (Nov 7): counted apart
    said = {m.get("tag") for msgs in by_user.values() for m, _ in msgs}
    heard = sum(1 for eid in slipped if f"slips-{eid}" in said)
    what = (f"{len(new)} new pick(s)" + (f" and {len(leans)} lean(s)" if not leans.empty else "")
            + (f" and {len(locks)} locked ticket(s)" if locks else "")
            + (f" and {heard} watched game(s)' slips ({len(slipped) - heard} unwatched)" if slipped else ""))
    return (f"alerts: {what} sent to {delivered} of {len(subs)} device(s)"
            + (f"; {removed} gone device(s) removed" if removed else "")
            + (f"; held for {len(held)} account(s) in quiet hours" if held else ""))


def release(now: pd.Timestamp | None = None, send: Callable[[dict, dict, str], int] = _send,
            db_url: str | None = None, private_key: str | None = None) -> str:
    """Send what quiet hours held once they've ended, and drop what has gone stale. Every pre-game tick, free."""
    now = now or pd.Timestamp.now(tz="UTC")
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    private_key = private_key or config.secret("VAPID_PRIVATE_KEY")
    if not (db_url and private_key):
        return "alerts: no app database or VAPID_PRIVATE_KEY yet: held alerts skipped"
    import psycopg

    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
        rows = c.execute("select h.id, h.user_id, h.msg, h.expires_at, s.notify from alerts_held h "
                         "left join user_settings s on s.user_id = h.user_id order by h.id").fetchall()
        sent = dropped = 0
        for id_, user_id, msg, expires, notify in rows:
            stale = pd.Timestamp(expires) <= now
            if not stale and alert_prefs.in_quiet(alert_prefs.clean(notify), now):
                continue
            if stale:
                dropped += 1
            else:
                deliver(c, user_id, json.loads(msg) if isinstance(msg, str) else msg, send, private_key)
                sent += 1
            c.execute("delete from alerts_held where id = %s", [id_])
    return f"alerts: {sent} held alert(s) sent, {dropped} dropped as stale"


def problem(kind: str, lines: list[str], now: pd.Timestamp | None = None,
            send: Callable[[dict, dict, str], int] = _send, db_url: str | None = None,
            private_key: str | None = None, owner: str | None = None) -> str:
    """A warning about the system itself (Oct 14: a grader left lines ungraded) to the owner's devices only,
    once a day for the same set of problems (`alerts_sent` key "problem:<kind>:<ET date>:<hash>")."""
    import hashlib

    now = now or pd.Timestamp.now(tz="UTC")
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    private_key = private_key or config.secret("VAPID_PRIVATE_KEY")
    owner = owner or config.owner_user_id()
    if not (db_url and private_key and owner):
        return "alerts: no app database, VAPID_PRIVATE_KEY or owner yet: problem alert skipped"
    what = sorted({ln.split(" (")[0].split(":")[0].strip() for ln in lines})   # "NHL prop lines not graded"
    day = now.tz_convert("America/New_York").strftime("%Y-%m-%d")
    key = f"problem:{kind}:{day}:" + hashlib.sha1("|".join(what).encode()).hexdigest()[:8]
    msg = {"title": f"BetLab: {kind} needs a look", "body": "; ".join(what)[:200], "url": "/bets?view=settled", "tag": key}
    import psycopg

    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
        if c.execute("select 1 from alerts_sent where pick_id = %s", [key]).fetchone():
            return f"alerts: {kind} problem already sent today"
        subs = c.execute("select endpoint, p256dh, auth from push_subscriptions where user_id = %s", [owner]).fetchall()
        ok = 0
        for endpoint, p256dh, auth in subs:
            status = _safe(send, {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}, msg, private_key)
            if status in (404, 410):
                c.execute("delete from push_subscriptions where user_id = %s and endpoint = %s", [owner, endpoint])
            elif 200 <= status < 300:
                ok += 1
        c.execute("insert into alerts_sent (pick_id, recipients) values (%s, %s) on conflict do nothing", [key, ok])
    return f"alerts: {kind} problem sent to {ok} of {len(subs)} owner device(s)"


TEST = {"title": "BetLab alerts are on", "body": "You'll get a notification like this whenever a new pick is found.",
        "url": "/more/settings", "tag": "test"}


def test(send: Callable[[dict, dict, str], int] = _send, db_url: str | None = None,
         private_key: str | None = None) -> str:
    """The confirmation a device gets right after turning alerts on (the app queues `test_alert`):
    sent to every device that hasn't had an alert yet."""
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    private_key = private_key or config.secret("VAPID_PRIVATE_KEY")
    if not (db_url and private_key):
        return "alerts: no app database or VAPID_PRIVATE_KEY yet: skipped"
    import psycopg

    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
        subs = c.execute("select user_id, endpoint, p256dh, auth from push_subscriptions where last_sent_at is null").fetchall()
        ok = 0
        for user_id, endpoint, p256dh, auth in subs:
            status = _safe(send, {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}, TEST, private_key)
            if status in (404, 410):
                c.execute("delete from push_subscriptions where user_id = %s and endpoint = %s", [user_id, endpoint])
            elif 200 <= status < 300:
                ok += 1
                c.execute("update push_subscriptions set last_sent_at = now() where user_id = %s and endpoint = %s",
                          [user_id, endpoint])
    return f"alerts: test sent to {ok} of {len(subs)} new device(s)"
