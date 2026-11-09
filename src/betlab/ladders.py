"""Ladder challenges: the worker locks each ladder's next step (Mike, Oct 26).

A ladder (the app's `ladders` table, migrations 0020-0021) rolls the whole stack into one bet at a time toward a target.
Mike: "If I start a ladder at the beginning of the day I can signify a game or not but it gives me best pick from that
day and waits until it has the info it needs, like I don't need a pick on demand." So on every pre-game tick (free:
it reads the database and the day's pregame state, no odds calls), for each active ladder waiting on a step:

- **No game chosen:** the day's best step is the strongest +EV pick (then lean) priced -250 to +150 that starts later
  today (ET) and at least 15 minutes from now, not turned down, not on the owner's ban list. It locks once that game's
  news is in (its post-news pull: `pregame.load_state` "pulled"); until then it is only held, and may change as the day's
  pulls re-price the card.
- **A game chosen:** once that game's news is in, its best step locks; with none, the ladder gets a notice
  ("none:<game_id>") and the owner an alert, and it waits for him to choose (Mike chose "tell me, I'll decide").
- **Locked:** the step is saved on the ladder (`locked`) with its stake (the whole stack) and the owner's devices get an
  alert. He places it himself and taps "I placed it" (Claude never places bets). A locked step whose game starts before
  it is placed is cleared with a "missed:<label>" notice, and the next one can lock.

The ladder math is web/lib/ladder.ts and ios/BetLab/Ladder.swift ported; all three answer tests/fixtures/ladder.json.
"""

from __future__ import annotations

import json
import math

import pandas as pd

from betlab import bans, config

STEP_MIN, STEP_MAX = -250.0, 150.0      # a step's price: near even money
LEAD = pd.Timedelta(minutes=15)         # a step starts at least this long after it's suggested
DUST = 1e-6
TIER = {"pick": 0, "lean": 1}
SETTLED = ("won", "lost", "push", "void", "cashout")


def _dec(price: float) -> float:
    return 1 + price / 100 if price > 0 else 1 + 100 / -price


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def status(b: dict) -> str:
    """A bet's status as My bets reads it: a cash-out settles it whatever its legs do."""
    if _num(b.get("cashout")) is not None:
        return "cashout"
    return str(b.get("pick_status") or b.get("ticket_status") or "open").lower()


def profit(b: dict) -> float | None:
    """Profit in units at the price taken (web lib/bets.ts profit): bonus, boost, cash-out and voided legs included,
    less Bet Protect+'s 3% fee unless the bet is void."""
    p = _profit_before_fee(b)
    fee = 0.03 * (_num(b.get("stake")) or 1.0) if b.get("protect") is True and status(b) != "void" else 0.0
    return None if p is None else p - fee


def _profit_before_fee(b: dict) -> float | None:
    s, st = status(b), _num(b.get("stake")) or 1.0
    bonus = b.get("bonus") is True
    if s == "cashout":
        return _num(b["cashout"]) - (0 if bonus else st)
    if s == "won":
        boost = 1 + max(_num(b.get("boost")) or 0, 0) / 100
        price = _num(b.get("price"))
        if price is not None:
            void = 1.0
            for leg in b.get("leg_results") or []:
                if leg.get("result") in ("void", "push") and _num(leg.get("p")) is not None:
                    void *= _num(leg["p"])
            return st * (max(_dec(price) * void, 1) - 1) * boost
        per = _num(b.get("profit_flat")) if _num(b.get("profit_flat")) is not None else _num(b.get("profit_1u"))
        return None if per is None else st * per
    if s == "lost":
        return 0.0 if bonus else -st
    if s in ("push", "void"):
        return 0.0
    return None


def state(ladder: dict, bets: list[dict]) -> dict:
    """phase (climbed, busted, stopped, in play, next step), stack, won, open step, next stake (web ladderState)."""
    steps = sorted((b for b in bets if b.get("ladder_id") == ladder["ladder_id"]), key=lambda b: str(b.get("placed_at")))
    start, target = float(ladder["start_units"]), float(ladder["target_units"])
    stack = start + sum(profit(b) or 0 for b in steps if status(b) in SETTLED)
    open_ = next((b for b in steps if status(b) not in SETTLED), None)
    won = sum(status(b) == "won" for b in steps)
    phase = ("climbed" if stack >= target - DUST else "busted" if stack <= DUST and open_ is None
             else "stopped" if ladder.get("status") == "stopped" else "in play" if open_ else "next step")
    to_win = None
    if open_ is not None and _num(open_.get("price")) is not None:
        to_win = (_num(open_.get("stake")) or 1.0) * (_dec(_num(open_["price"])) - 1) * (1 + max(_num(open_.get("boost")) or 0, 0) / 100)
    return {"phase": phase, "stack": stack, "won": won, "open": open_, "steps": steps, "to_win": to_win,
            "next_stake": stack if phase == "next step" else None}


def at_book(o: dict, book: str | None) -> dict | None:
    """An offer as it stands at one book (web atBook): itself when priced there, else the other book's price and EV when
    that book posts the same line (same number); None when it doesn't. A ladder stays at one book (Mike, Oct 26)."""
    if not book or (o.get("book") or "FanDuel") == book:
        return o
    same = o.get("other_point") is None or _num(o.get("other_point")) == _num(o.get("point"))
    if o.get("other_book") == book and _num(o.get("other_price")) is not None and same:
        return {**o, "book": book, "price": _num(o["other_price"]), "ev": _num(o.get("other_ev"))}
    return None


def options(offers: list[dict], now: pd.Timestamp, before: pd.Timestamp | None = None, book: str | None = None) -> list[dict]:
    """Every offer that could be a step, best first: +EV picks then leans, -250 to +150, 15+ minutes out (and, given
    `before`, starting before it: today's games; given `book`, at that book's own price)."""
    offers = [x for x in (at_book(o, book) for o in offers) if x is not None]
    def ok(o):
        t = pd.Timestamp(o["commence_time"]) if o.get("commence_time") else None
        return (o.get("tier") in TIER and (_num(o.get("ev")) or 0) > 0 and STEP_MIN <= float(o["price"]) <= STEP_MAX
                and t is not None and t - now >= LEAD and (before is None or t < before))
    return sorted((o for o in offers if ok(o)), key=lambda o: (TIER[o["tier"]], -(_num(o.get("ev")) or 0)))


def suggest(offers: list[dict], now: pd.Timestamp, skipped=(), game: str | None = None,
            before: pd.Timestamp | None = None, book: str | None = None) -> dict | None:
    """The best step not turned down, from one game when `game` is given, at one book when `book` is (web suggestStep)."""
    return next((o for o in options(offers, now, before, book) if o["offer_id"] not in skipped
                 and (game is None or o.get("game_id") == game)), None)


def steps_to_target(stack: float, target: float, price: float) -> int:
    return 0 if stack >= target else math.ceil(math.log(target / stack) / math.log(_dec(price)))


def end_of_day(now: pd.Timestamp) -> pd.Timestamp:
    """Midnight Eastern after `now`: a ladder's "today"."""
    et = now.tz_convert("America/New_York")
    return (et.normalize() + pd.Timedelta(days=1)).tz_convert("UTC")


def ready_events(now: pd.Timestamp) -> set[str]:
    """Odds events whose post-news pull is in today, in every league (pregame.load_state)."""
    from betlab import pregame

    out: set[str] = set()
    for lg in (config.settings().get("leagues") or {}).values():
        try:
            out |= set(pregame.load_state(lg["sport_key"], now)["pulled"])
        except Exception:  # noqa: BLE001 - one league's state file must not stop the rest
            continue
    return out


def _fmt_price(p: float) -> str:
    return f"+{int(p)}" if p > 0 else f"−{abs(int(p))}"


def _units(u: float) -> str:
    return f"{u:.2f}".rstrip("0").rstrip(".") + "u"


def decide(ladder: dict, st: dict, offers: list[dict], ready: set[str], games: dict[str, str], ban_list: list[dict],
           now: pd.Timestamp) -> dict | None:
    """What this tick changes on a ladder: {"locked": ..., "notice": ..., "alert": {...}} or None (nothing).
    `games`: {game_id: odds_event_id}; an offer's game is ready when its odds event's news pull is in."""
    locked = ladder.get("locked")
    if isinstance(locked, str):
        locked = json.loads(locked)
    if st["phase"] != "next step":
        return {"locked": None, "notice": None} if locked else None      # placed (or over): nothing to hold
    if locked:
        if pd.Timestamp(locked["commence_time"]) <= now:                  # it started before it was placed
            return {"locked": None, "notice": f"missed:{locked['label']}"}
        return None
    skipped = ladder.get("skipped") or []
    if isinstance(skipped, str):
        skipped = json.loads(skipped)
    mine = [o for o in offers if not bans.banned(ban_list, o.get("label") or "", o.get("league"), o.get("player"))]
    game = ladder.get("game_id")
    best = suggest(mine, now, skipped, game, end_of_day(now), ladder.get("book"))   # the column defaults to FanDuel
    is_ready = lambda gid: games.get(gid) in ready if gid else False
    n = len(st["steps"]) + 1
    if game:
        if not is_ready(game):
            return None
        if best is None:
            note = f"none:{game}"
            if ladder.get("notice") == note:
                return None
            return {"locked": None, "notice": note,
                    "alert": {"title": f"Ladder step {n}: no step in your game", "url": "/bets?view=ladder",
                              "body": f"Its news is in and BetLab has no +EV pick or lean there at {ladder.get('book') or 'FanDuel'}. Choose another game or any game.",
                              "tag": f"ladder:{ladder['ladder_id']}:{note}"}}
    if best is None or not is_ready(best.get("game_id")):
        return None                                                       # held, not ready yet
    stake = st["stack"]
    # fd_url: the betslip link at the step's own book (offers.fd_url, FanDuel's or DraftKings'), so the apps can open the bet
    # at the book from the locked step (Nov 6: "Place 2.08u at FanDuel" came with no way to get there)
    snap = {k: best.get(k) for k in ("offer_id", "tier", "label", "book", "matchup", "game_id", "league", "player", "fd_url")}
    snap |= {"price": float(best["price"]), "ev": _num(best.get("ev")), "stake": round(stake, 2), "step": n,
             "commence_time": pd.Timestamp(best["commence_time"]).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")}
    t = pd.Timestamp(best["commence_time"]).tz_convert("America/New_York")
    when = f"{t.hour % 12 or 12}:{t:%M %p}"                     # "7:30 PM" ("%-I" is Linux-only)
    return {"locked": snap, "notice": None,
            "alert": {"title": f"Ladder step {n}: {best['label']} {_fmt_price(float(best['price']))}",
                      "body": f"Place {_units(stake)} at {best.get('book') or 'FanDuel'} ({best.get('matchup')}, {when}), "
                              "then tap I placed it in My bets › Ladder.",
                      "url": "/bets?view=ladder", "tag": f"ladder:{ladder['ladder_id']}:{best['offer_id']}"}}


def run(now: pd.Timestamp | None = None, send=None, db_url: str | None = None, private_key: str | None = None) -> str:
    """The worker's `ladders` step: decide every active ladder and alert its owner's devices."""
    from betlab import alerts

    now = now or pd.Timestamp.now(tz="UTC")
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    private_key = private_key or config.secret("VAPID_PRIVATE_KEY")
    send = send or alerts._send
    if not db_url:
        return "ladders: no app database (SUPABASE_DB_URL): skipped"
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True, row_factory=dict_row) as c:
        ladders = c.execute("select * from ladders where status = 'active'").fetchall()
        if not ladders:
            return "ladders: none active"
        offers = c.execute("select * from offers where active and tier in ('pick', 'lean') and commence_time > now()").fetchall()
        games = {r["game_id"]: r["odds_event_id"] for r in c.execute(
            "select game_id, odds_event_id from games where commence_time > now() - interval '1 day'").fetchall()}
        for o in offers:                                   # an offer's odds event, when its game row has none
            games.setdefault(o["game_id"], o.get("odds_event_id"))
        ready = ready_events(now)
        changed, alerted, closed = 0, 0, 0
        for lad in ladders:
            uid = str(lad["user_id"])
            bets = c.execute("select * from my_bets where user_id = %s and ladder_id = %s", [uid, lad["ladder_id"]]).fetchall()
            st = state({**lad, "ladder_id": str(lad["ladder_id"])}, [{**b, "ladder_id": str(b["ladder_id"])} for b in bets])
            # a ladder its steps ended (busted or climbed) is over: close it, or it stays "active" and blocks starting
            # another (Nov 6, Mike: "I can't start another ladder even though the old ones busted"). It still reads as
            # busted or climbed: the apps work that out from its bets before its status.
            if st["phase"] in ("busted", "climbed"):
                c.execute("update ladders set status = 'stopped', ended_at = %s, locked = null, locked_at = null where ladder_id = %s",
                          [now, lad["ladder_id"]])
                closed += 1
                continue
            row = c.execute("select bans from user_settings where user_id = %s", [uid]).fetchone()
            ban_list = bans.clean((row or {}).get("bans"))
            d = decide({**lad, "ladder_id": str(lad["ladder_id"])}, st, offers, ready, games, ban_list, now)
            if d is None:
                continue
            c.execute("update ladders set locked = %s, locked_at = %s, notice = %s where ladder_id = %s",
                      [json.dumps(d["locked"], default=str) if d["locked"] else None, now if d["locked"] else None,
                       d["notice"], lad["ladder_id"]])
            changed += 1
            if d.get("alert") and private_key:
                for sub in c.execute("select user_id, endpoint, p256dh, auth from push_subscriptions where user_id = %s", [uid]).fetchall():
                    status_ = send(sub, d["alert"], private_key)
                    alerted += 200 <= status_ < 300
    return f"ladders: {len(ladders)} active, {changed} changed, {closed} closed (busted or climbed), {alerted} alert(s) delivered"
