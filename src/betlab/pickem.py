"""FanDuel's College Football Pick'em: track the entry and pick it from the stale lines (Mike, Nov 7).

The contest (Rewards Hub › College Football Pick'em, free): 10 spread picks a week on FanDuel's own college slate.
The lines freeze on Wednesday morning and the entry locks Saturday at 12 PM ET; the contest settles on the frozen
numbers, not the book's live spread. The top score of the week shares $500K in bonus bets; beating the FanDuel
partners' score pays a 25% profit boost (any sport, 7 days). Graded Sunday morning.

That freeze is the edge: by Saturday the sharp market has moved, and whichever side of a stale number the market now
favors covers more often than not. So each pick is the side with the higher cover chance at the frozen line, priced
like the card's spreads (`cards.football._center`: Pinnacle's spread and no-vig price into the college margin model,
`KeyNumberDist.over_push_under` at the frozen number). Maximizing expected correct picks is the whole strategy: the
jackpot needs 10 of 10 among everyone, so a contrarian card isn't worth its cost; the partners' score is beaten by
the same picks.

Mike screenshots the Questions screens (web `/api/pickem` reads them with Claude into `pickem`, one row per game,
migration 0044; the iPhone app sends them to the same route). The order on the screen lists the away team first;
the worker matches the pair to the week's Odds API event and swaps when FanDuel listed them the other way. Then on
every pre-game tick (free: the latest ncaaf snapshot) each game not yet started is priced again, and once it's final
it's graded from ESPN's scoreboard. Saturday from 10 AM until the lock, the owner gets one alert naming the picks to
flip (52%+ our way) and the games still unpicked. The apps show the week: your pick, our pick and its chance, the
result, the score, and what BetLab's card would have scored.

New York rules: a game involving a New York college gets no pick from BetLab (`ours` null, a notice); the pick'em
isn't a bet, but the rule is never weakened here. Claude never enters picks: Mike edits them in FanDuel.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from betlab import config, ny_rules
from betlab.live_legs import game_match, plain, scoreboard, side_of

SPORT_KEY = "americanfootball_ncaaf"
LOCK_HOUR = 12           # Saturday noon ET
ALERT_HOUR = 10          # the first alert, from 10 AM Saturday: only when there's something to change
LAST_CALL = (11, 45)     # the 11:45 tick, the last before the lock: always, "submit your picks" (Mike, Nov 7)
MIN_FLIP = 0.52          # a flip worth an alert: our side's cover chance at the frozen line
ET = "America/New_York"


def week_of(now: pd.Timestamp) -> date:
    """The entry's week is its lock day: the coming Saturday in Eastern time (today, on a Saturday)."""
    d = now.tz_convert(ET).date()
    return d + timedelta(days=(5 - d.weekday()) % 7)


# ------------------------------------------------------------------------------------------------- matching

def _fit(short: str, full: str) -> int | None:
    """How FanDuel's short name ("Ole Miss", "Miami", "Texas") fits an Odds API name ("Ole Miss Rebels", "Miami
    Hurricanes", "Texas Tech Red Raiders"): the words left over after it, fewer is better; None when it doesn't start
    the name. A rank ("#19 Iowa") is dropped first."""
    s, f = plain(short).split(), plain(full).split()
    if s and s[0].startswith("#") or (s and s[0].isdigit()):
        s = s[1:]
    if not s or f[:len(s)] != s:
        return None
    return len(f) - len(s)


def clean(name: str) -> str:
    """"#19 Iowa" -> "Iowa"."""
    return " ".join(w for w in str(name or "").split() if not (w.startswith("#") or w.isdigit())).strip()


def events(snap: pd.DataFrame | None) -> list[dict]:
    """The snapshot's games, one each: {event_id, home, away, start}."""
    if snap is None or snap.empty:
        return []
    cols = ["event_id", "home_team", "away_team", "commence_time"]
    out = snap[cols].drop_duplicates("event_id")
    return [{"event_id": r.event_id, "home": r.home_team, "away": r.away_team, "start": str(r.commence_time)}
            for r in out.itertuples()]


def match_event(evs: list[dict], first: str, second: str) -> tuple[dict, bool] | None:
    """The event a screenshot's pair names, and whether FanDuel listed it the other way round (first = home). Both
    names must fit the same event; the closer fit wins ("Texas" fits "Texas Longhorns" before "Texas Tech")."""
    first, second = clean(first), clean(second)
    best = None
    for ev in evs:
        for swapped, (h, a) in ((False, (second, first)), (True, (first, second))):
            fh, fa = _fit(h, ev["home"]), _fit(a, ev["away"])
            if fh is None or fa is None:
                continue
            score = fh + fa
            if best is None or score < best[0]:
                best = (score, ev, swapped)
    return (best[1], best[2]) if best else None


# ------------------------------------------------------------------------------------------------- pricing

def price(ev_rows: pd.DataFrame, home: str, away: str, home_line: float, md, sd: float, sharp_books: list[str]) -> dict | None:
    """The home team's cover chance at the frozen line from the sharp market now: {p_home, fair_line, source}, or
    None when no book prices the game. `fair_line` is the market's home spread (the model's center, negated)."""
    from betlab.cards.football import _center
    from betlab.market import reference_books

    books, src = reference_books(ev_rows, "spreads", sharp_books, "fanduel")
    if not books:
        return None
    center = _center(ev_rows, "spreads", books, home, away, md, sd)
    if center is None or pd.isna(center):
        return None
    over, push, under = md.over_push_under(center, sd, -float(home_line))
    if over + under <= 0:
        return None
    return {"p_home": round(float(over / (over + under)), 4), "fair_line": round(-float(center), 1), "source": src}


def our_side(p_home: float | None, home: str, away: str) -> tuple[str | None, str | None]:
    """(our side, notice): the likelier side, or none under New York rules."""
    ok, why = ny_rules.allowed("ncaaf", home, away)
    if not ok:
        return None, f"New York rules ({why}): your call"
    if p_home is None:
        return None, "No sharp line for this game yet"
    return ("home" if p_home >= 0.5 else "away"), None


# ------------------------------------------------------------------------------------------------- grading

def settle(home_line: float, home_pts: int, away_pts: int) -> str:
    """Which side covered the frozen home line: home when the margin beats it, push at the number."""
    m = home_pts - away_pts + float(home_line)
    return "push" if m == 0 else "home" if m > 0 else "away"


def final_score(boards: list[dict], home: str, away: str) -> tuple[int, int] | None:
    """(home points, away points) from ESPN's board once the game is final, else None."""
    hits = sorted(((game_match(g, away, home), g) for g in boards), key=lambda h: -h[0])
    if not hits or hits[0][0] <= 0:
        return None
    g = hits[0][1]
    if g.get("state") != "post":
        return None
    hs = side_of(home, g)
    if hs is None:
        return None
    h, a = (g["home"], g["away"]) if hs == "home" else (g["away"], g["home"])
    try:
        return int(h["score"]), int(a["score"])
    except (TypeError, ValueError):
        return None


def team_logos(boards: list[dict], home: str, away: str) -> tuple[str | None, str | None]:
    """(home logo, away logo) from ESPN's board for the game, when it lists one."""
    hits = sorted(((game_match(g, away, home), g) for g in boards), key=lambda h: -h[0])
    if not hits or hits[0][0] <= 0:
        return None, None
    g = hits[0][1]
    hs = side_of(home, g)
    if hs is None:
        return None, None
    h, a = (g["home"], g["away"]) if hs == "home" else (g["away"], g["home"])
    return h.get("logo"), a.get("logo")


def score(rows: list[dict]) -> dict:
    """The week's tally: {graded, yours, ours, picked, games}."""
    done = [r for r in rows if r.get("result") in ("home", "away", "push")]
    return {"games": len(rows), "picked": sum(1 for r in rows if r.get("pick")), "graded": len(done),
            "yours": sum(1 for r in done if r.get("pick") and r["result"] in (r["pick"], "push")),
            "ours": sum(1 for r in done if r.get("ours") and r["result"] in (r["ours"], "push"))}


def flips(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(picks to flip, games not picked yet): a flip is a pick against our side with our side at MIN_FLIP or better."""
    to_flip, unpicked = [], []
    for r in rows:
        ours = r.get("ours")
        p = r.get("p_home")
        if not r.get("pick"):
            unpicked.append(r)
        elif ours and p is not None and r["pick"] != ours and max(float(p), 1 - float(p)) >= MIN_FLIP:
            to_flip.append(r)
    return to_flip, unpicked


def side_label(r: dict, side: str) -> str:
    """"Iowa +2.5": the side's team as FanDuel names it and its frozen line."""
    team = r["home"] if side == "home" else r["away"]
    line = float(r["home_line"]) if side == "home" else -float(r["home_line"])
    return f"{team} {line:+g}"


# ------------------------------------------------------------------------------------------------- the worker step

def run(now: pd.Timestamp | None = None, send=None, db_url: str | None = None, private_key: str | None = None,
        snap: pd.DataFrame | None = None, boards=None) -> str:
    """The worker's `pickem` step: match, price and grade this week's entries; one alert Saturday morning."""
    from betlab import alerts

    now = now or pd.Timestamp.now(tz="UTC")
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    private_key = private_key or config.secret("VAPID_PRIVATE_KEY")
    send = send or alerts._send
    if not db_url:
        return "pickem: no app database (SUPABASE_DB_URL): skipped"
    import psycopg
    from psycopg.rows import dict_row

    week = week_of(now)
    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True, row_factory=dict_row) as c:
        rows = c.execute("select * from pickem where week = %s order by n", [week]).fetchall()
        if not rows:
            return f"pickem {week}: no entry"
        if snap is None:
            from betlab.cli import latest_snapshot
            snap = latest_snapshot(SPORT_KEY)
        evs = events(snap)
        model = None
        sharp = config.settings()["odds_api"]["sharp_books"]
        matched = priced = graded = 0
        for r in rows:
            try:
                if r.get("result"):
                    continue
                if not r.get("event_id"):
                    hit = match_event(evs, r["away"], r["home"])
                    if not hit:
                        c.execute("update pickem set notice = %s where pick_id = %s",
                                  [f"No game found for {clean(r['away'])} and {clean(r['home'])} this week", r["pick_id"]])
                        continue
                    ev, swapped = hit
                    if swapped:
                        r["home_line"] = -float(r["home_line"])
                        r["pick"] = {"home": "away", "away": "home"}.get(r.get("pick") or "", None)
                    if swapped:
                        r["home"], r["away"] = r["away"], r["home"]
                    r.update(event_id=ev["event_id"], home_name=ev["home"], away_name=ev["away"], start=ev["start"], notice=None)
                    if boards is None:
                        boards = scoreboard("ncaaf", None, [f"{pd.Timestamp(ev['start']).tz_convert(ET):%Y%m%d}"])
                    logos = team_logos(boards, ev["home"], ev["away"])
                    r.update(home_logo=logos[0], away_logo=logos[1])
                    c.execute("update pickem set event_id = %s, home = %s, away = %s, home_name = %s, away_name = %s, start = %s, "
                              "home_line = %s, pick = %s, home_logo = %s, away_logo = %s, notice = null where pick_id = %s",
                              [ev["event_id"], r["home"], r["away"], ev["home"], ev["away"], ev["start"], r["home_line"], r["pick"],
                               logos[0], logos[1], r["pick_id"]])
                    matched += 1
                start = pd.Timestamp(r["start"])
                if start > now:
                    if model is None:
                        from betlab.cards import ncaaf
                        p, md, _ = ncaaf.load_model(ncaaf.LEAGUE.load_games())
                        model = (md, p.market_margin_sd)
                    ev_rows = snap[snap["event_id"] == r["event_id"]] if snap is not None else pd.DataFrame()
                    px = price(ev_rows, r["home_name"], r["away_name"], float(r["home_line"]), *model, sharp) if len(ev_rows) else None
                    ours, notice = our_side(px["p_home"] if px else None, r["home_name"], r["away_name"])
                    r.update(ours=ours, p_home=px["p_home"] if px else None, notice=notice)
                    c.execute("update pickem set p_home = %s, fair_line = %s, ours = %s, priced_at = %s, notice = %s "
                              "where pick_id = %s",
                              [px["p_home"] if px else None, px["fair_line"] if px else None, ours, now, notice, r["pick_id"]])
                    priced += px is not None
                else:
                    if boards is None:
                        boards = scoreboard("ncaaf", None, [f"{start.tz_convert(ET):%Y%m%d}"])
                    fs = final_score(boards, r["home_name"], r["away_name"])
                    if fs:
                        res = settle(float(r["home_line"]), *fs)
                        c.execute("update pickem set home_pts = %s, away_pts = %s, result = %s where pick_id = %s",
                                  [fs[0], fs[1], res, r["pick_id"]])
                        graded += 1
            except Exception as e:  # noqa: BLE001 - one game must not stop the rest
                print(f"pickem: {r.get('away')} @ {r.get('home')}: skipped ({type(e).__name__}: {e})")
        alerted = _alert(c, rows, week, now, send, private_key)
    return f"pickem {week}: {len(rows)} games, {matched} matched, {priced} priced, {graded} graded, {alerted} alert(s)"


def _alert(c, rows: list[dict], week: date, now: pd.Timestamp, send, private_key: str | None) -> int:
    """Saturday, once per account each: from 10 AM, the picks to flip and the games still unpicked (only when there are
    any); at the 11:45 tick, the last before the noon lock, a last call to submit the picks either way."""
    t = now.tz_convert(ET)
    if not private_key or t.date() != week or not ALERT_HOUR <= t.hour < LOCK_HOUR:
        return 0
    last_call = (t.hour, t.minute) >= LAST_CALL
    sent = 0
    for user_id in {str(r["user_id"]) for r in rows}:
        mine = [r for r in rows if str(r["user_id"]) == user_id]
        to_flip, unpicked = flips(mine)
        if not last_call and not to_flip and not unpicked:
            continue
        key = f"pickem:{week}:{user_id}" + (":last" if last_call else "")
        if not c.execute("insert into alerts_sent (pick_id, recipients) values (%s, 0) on conflict do nothing returning pick_id",
                         [key]).fetchone():
            continue
        parts = []
        if to_flip:
            parts.append("Flip to " + ", ".join(
                f"{side_label(r, r['ours'])} ({round(max(float(r['p_home']), 1 - float(r['p_home'])) * 100)}%)" for r in to_flip))
        if unpicked:
            parts.append(f"{len(unpicked)} game{'s' if len(unpicked) != 1 else ''} not picked yet")
        if not parts:
            parts.append("Your picks match BetLab's")
        title = ("Pick'em locks in 15 minutes: submit your picks" if last_call
                 else f"Pick'em locks at noon: {len(to_flip)} to flip" if to_flip else "Pick'em locks at noon")
        alert = {"title": title, "body": ". ".join(parts) + ". Edit in FanDuel; the picks are in Me › CFB Pick'em.",
                 "url": "/more/pickem", "tag": key}
        n = 0
        for sub in c.execute("select user_id, endpoint, p256dh, auth from push_subscriptions where user_id = %s", [user_id]).fetchall():
            n += 200 <= send(sub, alert, private_key) < 300
        c.execute("update alerts_sent set recipients = %s where pick_id = %s", [n, key])
        sent += n
    return sent
