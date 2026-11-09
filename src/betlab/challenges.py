"""Novig challenges: the best bet for each, and an alert when it's ripe (Mike, Oct 28).

Novig's Points > Challenges ("The Daily Drop": three a day, 50 points each and 100 more for all three) read like "Place a
straight trade on CFB (Min. $5)", "Place a parlay on Pro BB (M) (Min. 3 legs, 4.00x, $5)" or "Place a straight trade on
Hockey Player Goals (Min. $5)". They aren't in Novig's API, so each morning a screenshot goes in (More > Novig
challenges; the web's /api/challenges reads the lines into the `challenges` table, migration 0027). Mike: "i can submit
it in the morning and it alerts me when a pick is ripe". On every pre-game tick (free but for Novig's free catalog and
parlay pricer), for each of today's open challenges:

- **Straight:** every Novig price on the challenge's sport (and market) against the sharp no-vig chance: game lines
  against Pinnacle at the same number (the latest pull), NHL player goals against Pinnacle's anytime goal (both sides)
  or else Novig's own mid. The best EV wins. Only prices with at least the stake behind them ($5): it's a $5 trade.
- **Parlay:** legs from different games with no team twice (Novig's rule), each game line priced near fair or better at
  Novig; the combinations whose fair price reaches the minimum (Min. 4.00x) by a little, most likely first, then Novig's
  own price for the best few from its parlay pricer (`novig_parlays.price_all`). The most likely one Novig prices at the
  minimum or more wins.
- **Today's games only** (Mike, Oct 28: "from now on novig bets are only for day of events"): a bet on a later day
  can't be tracked on game day's card until then, and the news isn't in.
- **Ripe:** a bet is ripe when every game in it has its post-news pull (`ladders.ready_events`), starts 15+ minutes
  from now, and clears the hour's bar: before 5 PM a clearly good price (straights +1.5% EV, parlays
  -3%), until 10 PM a fair one (0%, -8%), after 10 PM the best there is. Also the best there is once every game that
  could still beat it is in (nothing better is coming). Then the pick is saved (`status` ready) and the owner's devices
  get an alert; until then the best so far shows as `best` ("watching").
- A saved pick whose game starts before it's placed is dropped ("missed: ..."), and the challenge is solved again.

Claude never places bets: Mike places it at Novig and taps "I placed it". New York rules hold: college player props
never, and no game a New York rule blocks (`ny_rules.allowed`).
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import pandas as pd

from betlab import config
from betlab import odds_math as om

LEAD = pd.Timedelta(minutes=15)
MIN_STAKE = 5.0
TODAY_BAR = {"straight": (0.015, 0.0, None), "parlay": (-0.03, -0.08, None)}     # before 5 PM, until 10 PM, after
SPORTS = [  # Novig's words -> ours (its sport chips: CFB, Pro FB, Pro BB (M), College BB (M), Hockey, Soccer, MMA)
    (r"\bcfb\b|college football|ncaaf", "ncaaf"), (r"pro fb|\bnfl\b", "nfl"),
    (r"pro bb \(w\)|\bwnba\b", "wnba"), (r"pro bb|\bnba\b", "nba"),
    (r"college bb|\bcbb\b|ncaab", "ncaab"), (r"hockey|\bnhl\b", "nhl"), (r"soccer", "soccer"),
    (r"\bmma\b|\bufc\b", "ufc"), (r"baseball|\bmlb\b", "mlb"),
]
MARKETS = [(r"player goals?", "player_goals"), (r"moneyline|\bwinner\b", "h2h"), (r"spread", "spreads"),
           (r"total", "totals")]
SPORT_KEY = {"ncaaf": "americanfootball_ncaaf", "nfl": "americanfootball_nfl", "nba": "basketball_nba",
             "ncaab": "basketball_ncaab", "nhl": "icehockey_nhl", "ufc": "mma_mixed_martial_arts"}


def parse(text: str) -> dict:
    """A challenge's rules from Novig's words; `sport` None when it names none BetLab prices."""
    t = text.lower()
    kind = "parlay" if "parlay" in t else "straight" if "straight" in t else "any"
    sport = next((s for pat, s in SPORTS if re.search(pat, t)), None)
    market = next((m for pat, m in MARKETS if re.search(pat, t)), None)
    legs = re.search(r"(\d+)\s*legs?", t)
    dec = re.search(r"(\d+(?:\.\d+)?)\s*x\b", t)
    stake = re.search(r"\$\s*(\d+(?:\.\d+)?)", t)
    return {"kind": kind, "sport": sport, "market": market,
            "min_legs": int(legs.group(1)) if legs else (2 if kind == "parlay" else 1),
            "min_dec": float(dec.group(1)) if dec else None,
            "min_stake": float(stake.group(1)) if stake else MIN_STAKE}


# ------------------------------------------------------------------ candidates
def _latest(sport_key: str, kind: str) -> pd.DataFrame:
    files = sorted((config.DATA_DIR / "odds" / sport_key).glob(f"*/*_{kind}.parquet"))
    return pd.read_parquet(files[-1]) if files else pd.DataFrame()


def _soccer_rows() -> pd.DataFrame:
    frames = [pd.read_parquet(sorted(d.glob("*/*_pick.parquet"))[-1])
              for d in (config.DATA_DIR / "odds").glob("soccer_*") if d.is_dir() and list(d.glob("*/*_pick.parquet"))]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _ny_ok(r, cache: dict) -> bool:
    """New York rules for one game (ny_rules.allowed): college football needs both schools and the venue's state known,
    as the college fun tickets do (cards/fun_ncaaf), or it's never offered; college basketball isn't offered here yet."""
    from betlab import ny_rules

    key = str(r["sport_key"])
    if key == "basketball_ncaab":
        return False
    if key != "americanfootball_ncaaf":
        return True
    if "games" not in cache:
        from betlab.sources import cfbd
        cache["games"], cache["names"] = cfbd.games(), cfbd.team_names()
    games, names = cache["games"], cache["names"]
    home, away = names.get(r["home_team"]), names.get(r["away_team"])
    if home is None or away is None:
        return False
    day = pd.Timestamp(r["commence_time"]).tz_convert("America/New_York").tz_localize(None).normalize()
    near = games[(games["date"] - day).abs() <= pd.Timedelta(days=1)]
    row = near[(near["home_team"] == home) & (near["away_team"] == away)]
    state = row["venue_state"].iloc[0] if len(row) and "venue_state" in row else None
    return isinstance(state, str) and bool(state) and ny_rules.allowed("ncaaf", home, away, venue_state=state)[0]


def _oid(link) -> str | None:
    m = re.search(r"novig\.com/events/([^/?#]+)", str(link or ""))
    return m.group(1) if m else None


def _label(r) -> str:
    if r["market"] == "h2h":
        return "Draw" if r["outcome"] == "Draw" else f"{r['outcome']} ML"
    if r["market"] == "spreads":
        return f"{r['outcome']} {float(r['point']):+g}"
    unit = "goals" if str(r["sport_key"]).startswith(("soccer", "icehockey")) else "total points"
    return f"{r['outcome']} {float(r['point']):g} {unit}"


def line_legs(df: pd.DataFrame, now: pd.Timestamp, markets: set[str] | None = None, stake: float = MIN_STAKE) -> list[dict]:
    """Every Novig game-line price (with at least the stake behind it) against Pinnacle's no-vig chance at the same
    number: {event_id, game, start, label, price, p, ev, oid, teams}."""
    if df.empty:
        return []
    ny_cache: dict = {}
    df = df[pd.to_datetime(df["commence_time"], utc=True, format="ISO8601") > now + LEAD]
    if markets:
        df = df[df["market"].isin(markets)]
    out = []
    df = df.assign(_pt=df["point"].abs().fillna(-1.0))
    for _, g in df.groupby(["event_id", "market", "_pt"], sort=False):
        pin, nv = g[g["bookmaker"] == "pinnacle"], g[g["bookmaker"] == "novig"]
        if nv.empty or len(pin) != 2 or g["market"].iloc[0] == "h2h" and len(g[g["bookmaker"] == "pinnacle"]) != 2:
            continue
        a, b = pin.iloc[0], pin.iloc[1]
        try:
            pa, _ = om.no_vig_two_way(float(a["price"]), float(b["price"]))
        except (ValueError, ZeroDivisionError):
            continue
        fair = {(a["outcome"], a["point"] if pd.notna(a["point"]) else None): pa,
                (b["outcome"], b["point"] if pd.notna(b["point"]) else None): 1 - pa}
        for _, r in nv.iterrows():
            p = fair.get((r["outcome"], r["point"] if pd.notna(r["point"]) else None))
            lim = r.get("bet_limit")
            if p is None or not _oid(r.get("link")) or (pd.notna(lim) and float(lim) < stake):
                continue
            if not _ny_ok(r, ny_cache):
                continue
            out.append({"event_id": str(r["event_id"]), "game": f"{r['away_team']} @ {r['home_team']}",
                        "start": r["commence_time"], "label": _label(r), "price": float(r["price"]), "p": float(p),
                        "ev": float(p) * om.american_to_decimal(float(r["price"])) - 1, "oid": _oid(r.get("link")),
                        "teams": {r["home_team"], r["away_team"]}})
    return out


def goal_legs(now: pd.Timestamp, stake: float = MIN_STAKE, idx=None) -> list[dict]:
    """NHL anytime goal (Novig: PLAYER_GOALS over 0.5) at Novig's live ask against Pinnacle's no-vig chance, else
    Novig's own mid (both bids)."""
    from betlab import novig_parlays as NP

    props, lines = _latest("icehockey_nhl", "props"), _latest("icehockey_nhl", "pick")
    if lines.empty:
        return []
    idx = idx or NP.Index(lines)
    pin = props[(props.get("market") == "player_goal_scorer_anytime") & (props.get("bookmaker") == "pinnacle")] \
        if not props.empty else pd.DataFrame()
    fair = {}
    for (eid, player), g in (pin.groupby(["event_id", "player"]) if len(pin) else []):
        y, n = g[g["outcome"] == "Yes"], g[g["outcome"] == "No"]
        if len(y) and len(n):
            try:
                fair[(str(eid), player)] = om.no_vig_two_way(float(y["price"].iloc[0]), float(n["price"].iloc[0]))[0]
            except (ValueError, ZeroDivisionError):
                pass
    out = []
    for eid, game in idx.games.items():
        if pd.Timestamp(game["start"]) <= now + LEAD:
            continue
        hit = idx.event(eid)
        if hit is None:
            continue
        for m in idx.markets(hit[1]["eventId"]):
            if m.get("marketType") != "PLAYER_GOALS" or abs(float(m.get("strike") or 0) - 0.5) > 1e-6:
                continue
            oc = m.get("outcomes") or []
            over = next((o for o in oc if str(o.get("name", "")).lower().startswith("over")), None)
            under = next((o for o in oc if o is not over), None)
            if over is None or under is None or not (under.get("bid") or {}).get("price"):
                continue
            ask = 1 - float(under["bid"]["price"])
            if float(under["bid"].get("qty") or 0) / 100 * ask < stake or not 0 < ask < 1:
                continue
            player = NP._player_of(m)
            p = next((v for (e, pl), v in fair.items() if e == eid and NP.same_player(pl, player)), None)
            if p is None and (over.get("bid") or {}).get("price"):
                p = (float(over["bid"]["price"]) + ask) / 2            # Novig's own mid
            if p is None:
                continue
            price = float(round(om.prob_to_american(ask)))
            out.append({"event_id": eid, "game": f"{game['away']} @ {game['home']}", "start": game["start"],
                        "label": f"{player} 1+ goals", "price": price, "p": p,
                        "ev": p * om.american_to_decimal(price) - 1, "oid": over["outcomeId"],
                        "teams": {game["home"], game["away"]}})
    return out


def today_only(legs: list[dict], now: pd.Timestamp) -> list[dict]:
    """Legs on games played today (Eastern): Novig bets are for day-of games only (Mike, Oct 28)."""
    day = now.tz_convert("America/New_York").date()
    return [l for l in legs if pd.Timestamp(l["start"]).tz_convert("America/New_York").date() == day]


def candidates(rules: dict, now: pd.Timestamp) -> list[dict]:
    """Every leg a challenge could use, on its sport and market, on today's games."""
    sport, market = rules.get("sport"), rules.get("market")
    if market == "player_goals":
        return today_only(goal_legs(now, rules.get("min_stake") or MIN_STAKE), now) if sport in (None, "nhl") else []
    df = _soccer_rows() if sport == "soccer" else _latest(SPORT_KEY[sport], "pick") if sport in SPORT_KEY else pd.DataFrame()
    stake = rules.get("min_stake") or MIN_STAKE
    return today_only(line_legs(df, now, {market} if market in ("h2h", "spreads", "totals") else None, stake), now)


def parlays(legs: list[dict], n: int, min_dec: float | None, price_all=None, keep: int = 14, ask: int = 8) -> list[dict]:
    """The most likely n-leg parlays from different games (no team twice) whose Novig price reaches min_dec, priced by
    Novig's parlay pricer; best first."""
    from betlab import novig_parlays as NP

    price_all = price_all or NP.price_all
    pool = sorted([l for l in legs if l["ev"] >= -0.01], key=lambda l: -l["ev"])[:keep]
    combos = []
    for c in itertools.combinations(pool, n):
        teams = [t for l in c for t in l["teams"]]
        if len(set(teams)) < len(teams):
            continue
        p = 1.0
        for l in c:
            p *= l["p"]
        if min_dec and 1 / p < min_dec * 1.03:                 # fair has to clear it: Novig's price runs a little under
            continue
        combos.append((p, c))
    combos.sort(key=lambda x: -x[0])
    combos = combos[:ask]
    quotes = price_all([[l["oid"] for l in c] for _, c in combos]) if combos else {}
    out = []
    for p, c in combos:
        q = quotes.get(",".join(l["oid"] for l in c))
        if not q or (min_dec and 1 / q["p"] < min_dec - 1e-9):
            continue
        dec = 1 / q["p"]
        out.append({"legs": [{k: l[k] for k in ("label", "game", "start", "price", "p", "event_id")} for l in c],
                    "label": " + ".join(l["label"] for l in c), "price": q["price"], "dec": round(dec, 3), "p": p,
                    "ev": p * dec - 1, "oids": [l["oid"] for l in c], "stake_max": q.get("stake_max"),
                    "start": min(l["start"] for l in c), "events": [l["event_id"] for l in c]})
    return sorted(out, key=lambda x: (-x["p"], -x["ev"]))


# ------------------------------------------------------------------ ripe
def bar(kind: str, now: pd.Timestamp) -> float | None:
    """The EV a bet needs to be ripe at this hour (Eastern): None after 10 PM (the best there is)."""
    h = now.tz_convert("America/New_York").hour
    early, evening, late = TODAY_BAR["parlay" if kind == "parlay" else "straight"]
    return early if h < 17 else evening if h < 22 else late


def _ready(bet: dict, ready: set[str], now: pd.Timestamp) -> bool:
    if any(str(eid) not in ready for eid in bet.get("events") or [bet["event_id"]]):
        return False
    return pd.Timestamp(bet["start"]) > now + LEAD


def decide(rules: dict, bets: list[dict], ready: set[str], now: pd.Timestamp) -> tuple[dict | None, dict | None]:
    """(the ripe pick or None, the best so far or None) among a challenge's ranked bets (best first)."""
    if not bets:
        return None, None
    best = bets[0]
    need = bar(rules.get("kind") or "straight", now)
    ripe = [b for b in bets if _ready(b, ready, now)]
    if not ripe:
        return None, best
    top = ripe[0]
    if need is None or top["ev"] >= need:
        return top, best
    unready = [b for b in bets if not _ready(b, ready, now) and pd.Timestamp(b["start"]) > now + LEAD]
    if not unready:                                   # nothing better is coming: the best there is
        return top, best
    return None, best


def live(bets: list[dict], stake: float, asks=None, n: int = 6) -> list[dict]:
    """The best few straights at Novig's price now (a pull can be hours old): each outcome's live ask from the catalog,
    with at least the stake behind it, its EV at the worse of that and the pulled price; a bet Novig no longer offers
    drops out. `asks`: {outcome id: (ask, dollars)}."""
    if asks is None:
        from betlab import links
        from betlab import novig_parlays as NP

        idx = NP.Index(pd.concat([links.book_rows(b) for b in ("fanduel", "draftkings", "novig")], ignore_index=True))
        asks = {}
        for eid in {b["event_id"] for b in bets[:n]}:
            hit = idx.event(eid)
            for m in idx.markets(hit[1]["eventId"]) if hit else []:
                for o in m.get("outcomes") or []:
                    other = [x for x in m.get("outcomes") or [] if x is not o]
                    bid = (other[0].get("bid") or {}) if len(other) == 1 else {}
                    if bid.get("price"):
                        a = 1 - float(bid["price"])
                        asks[o["outcomeId"]] = (a, float(bid.get("qty") or 0) / 100 * a)
    out = []
    for b in bets[:n]:
        a = asks.get(b["oid"])
        if a is None or a[1] < stake or not 0 < a[0] < 1:
            continue
        price = float(round(om.prob_to_american(a[0])))
        # the EV counts the worse of the pulled and the live price: the sharp chance is from the pull, and a live price
        # better than it often means the market moved since (Oct 28: Middle Tennessee -2.5 went -102 to +122 by
        # afternoon, a "+15%" against the morning's Pinnacle line)
        dec = min(om.american_to_decimal(price), om.american_to_decimal(b["price"]))
        out.append(b | {"price": price, "dec": om.american_to_decimal(price), "ev": b["p"] * dec - 1})
    return sorted(out, key=lambda b: -b["ev"]) + bets[n:]


def solve(rules: dict, now: pd.Timestamp, price_all=None, asks=None) -> list[dict]:
    """A challenge's bets, best first: straights by EV at Novig's live price, parlays by chance at Novig's own price."""
    legs = candidates(rules, now)
    if rules.get("kind") == "parlay":
        return parlays(legs, max(int(rules.get("min_legs") or 2), 2), rules.get("min_dec"), price_all)
    stake = max(float(rules.get("min_stake") or MIN_STAKE), MIN_STAKE)
    ranked = [l | {"oids": [l["oid"]], "dec": om.american_to_decimal(l["price"])} for l in sorted(legs, key=lambda l: -l["ev"])]
    return [b for b in live(ranked, stake, asks) if not rules.get("min_dec") or b["dec"] >= rules["min_dec"]]


def snapshot(b: dict, stake: float) -> dict:
    """What's saved on the challenge and shown in the apps."""
    from betlab import links
    from betlab.novig_parlays import LINK

    start = pd.Timestamp(b["start"]).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"label": b["label"], "legs": b.get("legs") or [{k: b[k] for k in ("label", "game", "start", "price", "p")}],
            "price": b["price"], "dec": round(float(b["dec"]), 3), "p": round(b["p"], 4), "ev": round(b["ev"], 4),
            "matchup": b.get("game") or " · ".join(l["game"] for l in b.get("legs") or []), "commence_time": start,
            "stake": stake, "link": links.book_link(LINK.format(ids=",".join(b["oids"]))),
            "stake_max": b.get("stake_max")}


def _when(iso: str) -> str:
    t = pd.Timestamp(iso).tz_convert("America/New_York")
    today = pd.Timestamp.now(tz="America/New_York").date()
    return (f"{t.hour % 12 or 12}:{t:%M %p}" if t.date() == today else f"{t:%a} {t.hour % 12 or 12}:{t:%M %p}")


def run(now: pd.Timestamp | None = None, send=None, db_url: str | None = None, private_key: str | None = None,
        price_all=None) -> str:
    """The worker's `challenges` step: parse, solve and decide today's open challenges, and alert when one is ripe."""
    from betlab import alerts, ladders

    now = now or pd.Timestamp.now(tz="UTC")
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    private_key = private_key or config.secret("VAPID_PRIVATE_KEY")
    send = send or alerts._send
    if not db_url:
        return "challenges: no app database (SUPABASE_DB_URL): skipped"
    import psycopg
    from psycopg.rows import dict_row

    day = now.tz_convert("America/New_York").date()
    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True, row_factory=dict_row) as c:
        rows = c.execute("select * from challenges where day = %s and status in ('open', 'ready')", [day]).fetchall()
        if not rows:
            return "challenges: none open today"
        ready = ladders.ready_events(now)
        solved, picked, alerted = 0, 0, 0
        for ch in rows:
            pick = ch.get("pick")
            if ch["status"] == "ready":
                if pick and pd.Timestamp(pick["commence_time"]) > now:
                    continue                                    # saved and alerted; waiting on Mike to place it
                c.execute("update challenges set status = 'open', pick = null, notice = %s where challenge_id = %s",
                          [f"missed: {pick['label']}" if pick else None, ch["challenge_id"]])
            rules = ch.get("rules") or {}
            if not rules.get("sport") and not rules.get("market"):
                rules = parse(ch["text"])
                c.execute("update challenges set rules = %s where challenge_id = %s", [json.dumps(rules), ch["challenge_id"]])
            if not rules.get("sport") and rules.get("market") != "player_goals":
                c.execute("update challenges set notice = %s where challenge_id = %s",
                          ["BetLab doesn't price this sport on Novig yet", ch["challenge_id"]])
                continue
            stake = max(float(rules.get("min_stake") or MIN_STAKE), MIN_STAKE)
            try:
                bets = solve(rules, now, price_all)
            except Exception as e:  # noqa: BLE001 - one challenge must not stop the rest
                print(f"challenges: {ch['text']}: not solved ({type(e).__name__}: {e})")
                continue
            solved += 1
            top, best = decide(rules, bets, ready, now)
            if top is None:
                c.execute("update challenges set best = %s, notice = %s where challenge_id = %s",
                          [json.dumps(snapshot(best, stake)) if best else None,
                           None if best else "No Novig price for this yet", ch["challenge_id"]])
                continue
            snap = snapshot(top, stake)
            c.execute("update challenges set status = 'ready', pick = %s, best = %s, picked_at = %s, notice = null "
                      "where challenge_id = %s", [json.dumps(snap), json.dumps(snap), now, ch["challenge_id"]])
            picked += 1
            novig_off = "Novig" in ((c.execute("select books_off from user_settings where user_id = %s", [str(ch["user_id"])])
                                     .fetchone() or [[]])[0] or [])        # Novig turned off (Nov 6, 0043): no alert
            if private_key and not novig_off:
                price = f"+{int(snap['price'])}" if snap["price"] > 0 else f"−{abs(int(snap['price']))}"
                alert = {"title": f"Novig challenge: {snap['label']} {price}",
                         "body": f"For \"{ch['text']}\": ${stake:g} at Novig ({_when(snap['commence_time'])}"
                                 f"{', ' + str(round(snap['p'] * 100)) + '% to hit' if rules.get('kind') == 'parlay' else ''}). "
                                 "Open it from More › Novig challenges.",
                         "url": "/more/challenges", "tag": f"challenge:{ch['challenge_id']}"}
                for sub in c.execute("select user_id, endpoint, p256dh, auth from push_subscriptions where user_id = %s",
                                     [str(ch["user_id"])]).fetchall():
                    status_ = send(sub, alert, private_key)
                    alerted += 200 <= status_ < 300
    return f"challenges: {len(rows)} open today, {solved} solved, {picked} ripe, {alerted} alert(s) delivered"
