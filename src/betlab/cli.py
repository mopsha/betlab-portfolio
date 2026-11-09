"""betlab command line.

  betlab credits                 show the Odds API balance (free call)
  betlab pull --auto             odds for leagues with games in the next 36 h, once a day
  betlab pull --auto --again 3   ...or again, if today's last pull is 3+ hours old (the midday re-price)
  betlab pull --prime-time       evening check: NFL odds only if a kickoff is 30-110 min away
  betlab pull nfl [ncaaf ...]    save a FanDuel + sharp-book odds snapshot now
  betlab pull-props [--event ID] NFL player props, alt ladders and anytime TD (~9 credits a game)
  betlab pull-props --league nba NBA props for games tipping in 15-75 minutes (~8 credits a game)
  betlab card [--dry-run]        price today's offers, write the card, log paper picks
  betlab fun [--dry-run]         fun same-game parlays from the latest props snapshot
  betlab preview                 game previews: how each NFL game should go (next 7 days)
  betlab refresh                 update this season's college data (CFBD)
  betlab grade                   settle finished picks, compute CLV, write results
  betlab export-page             bundle card/results/ledger as page documents for the sync
  betlab import-taken FILE       merge the picks you marked on the page into the ledger
  betlab backtest nfl            walk-forward backtest against closing lines
  betlab backtest props          walk-forward backtest of the NFL props models (2023-2025)
  betlab backtest script         does the game script add to the 2025 prop market?
  betlab backtest game           QB ratings, weather and non-QB absences in the game-flow engine
  betlab backtest cfb            college: the efficiency read vs opening and closing lines; refits the early read
  betlab backtest nba            NBA team and player models vs naive baselines (2025-26); saves their settings
  betlab backtest sgp            fun-parlay simulator: do legs move together as in real games? (2023-25, 2025 lines)
  betlab backtest soccer         soccer ratings vs Pinnacle's close and earlier line, big five + MLS (2019-26)
  betlab backtest ncaab          college basketball ratings vs the close and the opener (2023-26)
  betlab backtest lag            do FanDuel's morning prop prices lag? morning +EV sides vs the sharp close (2026 snapshots)
  betlab backfill props --season 2025 --weeks 3-18   historical prop lines (paid key, ~40 credits a game)
  betlab backfill nba-lines --season 2026            NBA 2025-26 spreads/totals near tip (paid key, ~4,620 credits)

Each command is one step of the daily pipeline (docs/ARCHITECTURE.md). The full
reference, with every flag, is in src/betlab/README.md.
"""

from __future__ import annotations

import argparse
import importlib
from datetime import datetime, timezone

import pandas as pd

from betlab import config, ledger, picks
from betlab.reports import card as card_report
from betlab.sources import odds_api

EVALUATORS = {"nfl": "betlab.cards.nfl", "ncaaf": "betlab.cards.ncaaf", "ncaab": "betlab.cards.ncaab",
              "nhl": "betlab.cards.nhl",   # market-only: FanDuel vs the sharp book (cards/nhl.py)
              "nba": "betlab.cards.nba",   # market-only game lines from opening night (cards/nba.py)
              "ufc": "betlab.cards.ufc",   # market-only moneyline and total rounds, UFC fights only (cards/ufc.py)
              # soccer: FanDuel's 3-way result vs the sharp price (market-only; cards/soccer.py)
              # (the leagues and, from Oct 13, the European cups: cards/soccer.LEAGUES)
              **{lg: "betlab.cards.soccer" for lg in ("epl", "la_liga", "serie_a", "bundesliga", "ligue_1", "mls",
                                                      "ucl", "uel", "uecl")}}


def ready(league: str) -> tuple[bool, str]:
    """Whether a league's model has the data it needs (so we never pay for odds we can't price)."""
    if league == "ncaaf":
        from betlab.sources import cfbd
        if not (cfbd.HISTORY.exists() and cfbd.TEAMS.exists()):
            return False, "college football history not built yet (needs the CFBD key)"
    if league == "ncaab":
        from betlab.sources import cbbd
        if not (cbbd.GAMES.exists() and cbbd.TEAM_GAMES.exists()):
            return False, "college basketball history not built yet (cbbd.build_history)"
    return True, ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def latest_snapshot(sport_key: str, kind: str = "pick") -> pd.DataFrame | None:
    """The newest odds snapshot for a sport (files sort by ET date, then time), or None."""
    files = sorted((config.DATA_DIR / "odds" / sport_key).glob(f"*/*_{kind}.parquet"))
    return pd.read_parquet(files[-1]) if files else None


def cmd_credits(args) -> None:
    """Print the Odds API balance (a free call)."""
    client = odds_api.OddsApiClient()
    client.sync_balance()
    for label, _, guard in client.keys:
        print(f"{label}: {guard.balance()} credits left (resets {guard.next_reset():%b %d})")


def _pulled_today(sport_key: str, day: str) -> bool:
    """Whether a snapshot already exists in today's (ET) folder for this sport."""
    return any((config.DATA_DIR / "odds" / sport_key / day).glob("*_pick.parquet"))


def _hours_since_pull(sport_key: str, day: str, now: pd.Timestamp) -> float | None:
    """Hours since today's latest whole-league game-line pull for this sport (None if none today)."""
    from betlab import pregame

    # Nov 1-2: one early game's pre-game pull read as "already pulled", and the 9:55 skipped every other college game
    own = pregame.pregame_files(sport_key, now)
    files = [f for f in sorted((config.DATA_DIR / "odds" / sport_key / day).glob("*_pick.parquet")) if f.name not in own]
    if not files:
        return None
    ts = pd.Timestamp(f"{day} {files[-1].name[:6]}", tz=config.settings()["timezone"])
    return (now - ts).total_seconds() / 3600


PRIME_TIME_WINDOW = (30, 110)  # minutes before kickoff: after inactives (T-90), with room for cron delays


def prime_time_events(events: list[dict], now: pd.Timestamp, window=PRIME_TIME_WINDOW) -> list[dict]:
    """Events kicking off between window[0] and window[1] minutes from now."""
    lo, hi = now + pd.Timedelta(minutes=window[0]), now + pd.Timedelta(minutes=window[1])
    return [e for e in events if lo <= pd.Timestamp(e["commence_time"]) <= hi]


def _set_output(name: str, value: str) -> None:
    """Tell a GitHub Actions workflow what happened (no-op elsewhere)."""
    import os

    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


PRE_KICKOFF_LEAGUES = ("nfl", "ncaaf")


def _pull_prime_time(client: odds_api.OddsApiClient, now: pd.Timestamp) -> None:
    """Pre-kickoff check (evening, Sunday and Saturday ticks): re-pull a league's odds only
    when one of its games kicks off 30-110 minutes from now (free /events check first). The
    pull is the near-closing price that picks' CLV and prop CLV are measured against, and
    the card is re-priced after inactives."""
    day = now.tz_convert(config.settings()["timezone"]).strftime("%Y-%m-%d")
    pulled = []
    for league in PRE_KICKOFF_LEAGUES:
        lg = config.settings()["leagues"][league]
        if str(lg["start"]) > day:
            continue
        soon = prime_time_events(client.events(lg["sport_key"]), now)  # free call
        if not soon:
            print(f"{league}: no kickoff 30-110 minutes from now: skipping (0 credits)")
            continue
        ts = _now()
        df = odds_api.flatten(client.odds(lg["sport_key"]), lg["sport_key"], ts)
        odds_api.save_snapshot(df, lg["sport_key"], ts, "pick")
        pulled.append(league)
        shown = ", ".join(f"{e['away_team']} @ {e['home_team']}" for e in soon[:6])
        print(f"{league}: pre-kickoff pull for {len(soon)} game(s): {shown}{' ...' if len(soon) > 6 else ''}")
    if pulled:
        print(f"credits remaining: {client.balance_note()}")
        _set_output("pulled", "true")


# An extra early-week look for college: on Tuesdays (ET) the auto pull covers games in the
# next 5 days, so the Games tab's early read sees near-opening numbers (the read beat the
# opener, not the close; `betlab backtest cfb`). One pull, about 3 credits.
EARLY_WINDOW = {"ncaaf": (1, 120)}  # league: (weekday, Monday=0; hours ahead)


def cmd_pull(args) -> None:
    """Pull odds for the named leagues, or with --auto for every league that
    has a model, has started its season, and has games in the next 36 hours
    (checked with the free /events endpoint), at most once per day."""
    if not odds_api.any_key():
        print("no Odds API key is set: skipping the odds pull (add it to .env or the repo secrets)")
        return
    client = odds_api.OddsApiClient()
    client.sync_balance()
    now = pd.Timestamp.now(tz="UTC")
    if args.prime_time:
        _pull_prime_time(client, now)
        return
    day = now.tz_convert(config.settings()["timezone"]).strftime("%Y-%m-%d")
    leagues = args.leagues or [lg for lg in EVALUATORS
                               if str(config.settings()["leagues"][lg]["start"]) <= day]
    ts = _now()
    pulled_any, called, failed = False, 0, []
    for league in leagues:
        # each league on its own (Nov 9): one league's error (a 429 or 502 past the client's retries) used to end the
        # step, and in the 9:55 daily (a hard step) it cost the morning card, publish and alerts of every league
        try:
            got = _pull_league(args, client, league, day, now, ts)
        except odds_api.OddsApiError as exc:
            failed.append(league)
            called += 1
            print(f"{league}: not pulled ({exc})")
            continue
        called += got is not None
        pulled_any |= bool(got)
    print(f"credits remaining: {client.balance_note()}")
    if pulled_any:
        _set_output("pulled", "true")
    if failed and len(failed) == called:
        raise SystemExit(1)       # every league that asked the API failed: the step fails (the worker alerts the owner)
    if failed:                    # the job goes on with the leagues that answered (WARN_EXIT: recorded, not stopped)
        try:
            from betlab import alerts
            print(alerts.problem("the odds pull", [f"odds pull failed ({', '.join(failed)})"]))
        except Exception as exc:  # an alert must never stop the pull's report
            print(f"pull problem alert failed ({type(exc).__name__})")
        raise SystemExit(WARN_EXIT)


def _pull_league(args, client, league: str, day: str, now: pd.Timestamp, ts) -> bool | None:
    """One league's part of `pull`: True when it saved a snapshot, False when the API (or ESPN) had nothing to pull,
    None when it was skipped without asking (not ready, already pulled today). Raises odds_api.OddsApiError."""
    sport_key = config.settings()["leagues"][league]["sport_key"]
    paid_from = config.settings()["leagues"][league].get("paid_odds_from")
    if args.auto and paid_from and day < str(paid_from):
        return _pull_free(league, sport_key, now)
    if args.auto:
        ok, why = ready(league)
        if not ok:
            print(f"{league}: skipping, {why}")
            return None
        since = _hours_since_pull(sport_key, day, now)
        if since is not None and (args.again is None or since < args.again):
            print(f"{league}: already pulled today" + (f" ({since:.1f} h ago)" if since is not None else ""))
            return None
        weekday, early_hours = EARLY_WINDOW.get(league, (None, 36))
        local = now.tz_convert(config.settings()["timezone"])
        hours = early_hours if local.weekday() == weekday else 36
        soon = [e for e in client.events(sport_key)
                if now < pd.Timestamp(e["commence_time"]) < now + pd.Timedelta(hours=hours)]
        if not soon:
            print(f"{league}: no games in the next {hours}h, skipping (0 credits)")
            return False
    markets = tuple(config.settings()["leagues"][league].get("markets") or odds_api.GAME_MARKETS)
    df = odds_api.flatten(client.odds(sport_key, markets=markets), sport_key, ts)
    if config.settings()["leagues"][league].get("family") == "soccer":   # Novig's soccer, free (sources/novig.py)
        from betlab.sources import novig
        df = novig.add_rows(df, sport_key, ts)
    path = odds_api.save_snapshot(df, sport_key, ts, "pick")
    print(f"{league}: {df['event_id'].nunique()} events, {len(df)} prices -> {path.name}")
    return True


def _pull_free(league: str, sport_key: str, now: pd.Timestamp) -> bool:
    """ESPN's free DraftKings lines for games in the next 36 hours, saved as a snapshot
    (0 credits). Used for college basketball until `paid_odds_from` (reads only: no FanDuel
    or sharp price, so no picks)."""
    from betlab.sources import espn_odds

    ok, why = ready(league)
    if not ok:
        print(f"{league}: skipping, {why}")
        return False
    local = now.tz_convert(config.settings()["timezone"])
    dates = [(local + pd.Timedelta(days=d)).strftime("%Y%m%d") for d in (0, 1)]
    try:
        df = espn_odds.snapshot(sport_key, dates, _now())
    except Exception as exc:           # ESPN down must not block the paid pulls
        print(f"{league}: free lines not pulled ({type(exc).__name__}: {exc})")
        return False
    if len(df):
        start = pd.to_datetime(df["commence_time"], utc=True, format="ISO8601")
        df = df[(start > now) & (start < now + pd.Timedelta(hours=36))]
    if df.empty:
        print(f"{league}: no games with lines in the next 36h (free ESPN lines)")
        return False
    path = odds_api.save_snapshot(df, sport_key, df["snapshot_ts"].iloc[0], "pick")
    print(f"{league}: {df['event_id'].nunique()} games from ESPN's free DraftKings lines -> {path.name} (0 credits)")
    return True


NBA_TIP_WINDOW = (15, 75)  # minutes before tip-off; the NBA tick runs hourly, so each game lands in one run


def open_prop_markets(league: str) -> dict[str, list[str]]:
    """{event_id: [markets]} of open prop picks and leans in a league (what a closing pull needs)."""
    out: dict[str, set] = {}
    for path in (None, ledger.LEANS):
        df = ledger.load(path)
        if df.empty or "kind" not in df:
            continue
        df = df[(df["league"] == league) & (df["status"] == "open") & (df["kind"] == "prop")]
        for eid, market in zip(df["event_id"], df["market"]):
            out.setdefault(str(eid), set()).add(market)
    return {k: sorted(v) for k, v in out.items()}


def _pull_props_nba(args, client: odds_api.OddsApiClient, now: pd.Timestamp) -> None:
    """NBA props for games tipping 15-75 minutes from now (lineups are close, injury news is
    in), plus the night's game lines (their spreads feed the blowout feature). A game with
    open NBA prop picks or leans that tips before the window gets just those markets pulled
    again: the close their CLV is measured against."""
    lg = config.settings()["leagues"]["nba"]
    sport_key = lg["sport_key"]
    day = now.tz_convert(config.settings()["timezone"]).strftime("%Y-%m-%d")
    if str(lg["start"]) > day and not args.event:
        print(f"nba: the season starts {lg['start']}: skipping (0 credits)")
        return
    events = client.events(sport_key)  # free call
    lo, hi = args.tip_window or NBA_TIP_WINDOW
    chosen = [e for e in events if e["id"] == args.event] if args.event else prime_time_events(events, now, (lo, hi))
    ids = {e["id"] for e in chosen}
    started = {e["id"] for e in events if pd.Timestamp(e["commence_time"]) <= now}
    closing = {eid: m for eid, m in open_prop_markets("nba").items()
               if eid not in ids and eid not in started and eid in {e["id"] for e in events}}
    if not chosen and not closing:
        print(f"nba: no tip-off {lo}-{hi} minutes from now: skipping (0 credits)")
        return
    ts = _now()
    frames = []
    for e in chosen:
        markets = odds_api.NBA_PROP_MARKETS + odds_api.NBA_ALT_MARKETS  # alt ladders feed the fun tickets
        frames.append(odds_api.flatten(client.event_odds(sport_key, e["id"], markets), sport_key, ts))
        print(f"{e['away_team']} @ {e['home_team']}: {len(frames[-1])} prices")
    for eid, markets in closing.items():
        frames.append(odds_api.flatten(client.event_odds(sport_key, eid, markets, priority="closing"), sport_key, ts))
        print(f"closing prices for open picks in event {eid}: {', '.join(markets)}")
    df = pd.concat(frames, ignore_index=True)
    path = odds_api.save_snapshot(df, sport_key, ts, "props")
    if chosen:
        lines = odds_api.flatten(client.odds(sport_key), sport_key, ts)
        odds_api.save_snapshot(lines, sport_key, ts, "pick")
    print(f"nba props: {len(chosen)} games priced, {len(closing)} closing pulls, {len(df)} prices -> {path.name} "
          f"| credits remaining: {client.balance_note()}")
    _set_output("pulled", "true")


def cmd_pull_props(args) -> None:
    """Pull NFL player props (main lines, alt ladders, anytime TD) for one event, the
    prime-time game, or every game in the next --within hours. One event-odds call
    per game, each costing about one credit per market that comes back (about 9).
    With --league nba: NBA props for games tipping 15-75 minutes from now."""
    if not odds_api.any_key():
        print("no Odds API key is set: skipping the props pull (add it to .env or the repo secrets)")
        return
    if args.league == "nba":
        client = odds_api.OddsApiClient()
        client.sync_balance()
        _pull_props_nba(args, client, pd.Timestamp.now(tz="UTC"))
        return
    if args.league == "nhl":
        _pull_props_nhl(args)
        return
    sport_key = config.settings()["leagues"]["nfl"]["sport_key"]
    now = pd.Timestamp.now(tz="UTC")
    day = now.tz_convert(config.settings()["timezone"]).strftime("%Y-%m-%d")
    if args.once_daily and any((config.DATA_DIR / "odds" / sport_key / day).glob("*_props.parquet")):
        print("props already pulled today: skipping (0 credits)")
        return
    if args.morning_data and any((config.DATA_DIR / "odds" / sport_key / day).glob("*_props_am.parquet")):
        print("morning props (data only) already pulled today: skipping (0 credits)")
        return
    client = odds_api.OddsApiClient()
    client.sync_balance()
    events = client.events(sport_key)  # free call
    if args.event:
        chosen = [e for e in events if e["id"] == args.event]
    elif args.prime_time:
        chosen = prime_time_events(events, now)
    else:
        chosen = [e for e in events
                  if now < pd.Timestamp(e["commence_time"]) < now + pd.Timedelta(hours=args.within)]
    if not chosen:
        print("no matching NFL events: skipping (0 credits)")
        return
    markets = odds_api.NFL_PROP_MARKETS + odds_api.NFL_ALT_MARKETS + odds_api.NFL_TD_MARKETS
    ts = _now()
    frames = []
    for e in chosen:
        payload = client.event_odds(sport_key, e["id"], markets)
        frames.append(odds_api.flatten(payload, sport_key, ts))
        print(f"{e['away_team']} @ {e['home_team']}: {len(frames[-1])} prices")
    df = pd.concat(frames, ignore_index=True)
    # --morning-data (the new schedule, Oct 4): the props lag study's morning look only. Saved as
    # `props_am`, which the card, fun slips and previews never read (they take `props`).
    path = odds_api.save_snapshot(df, sport_key, ts, "props_am" if args.morning_data else "props")
    print(f"props: {len(chosen)} events, {len(df)} prices -> {path.name} | credits remaining: {client.balance_note()}")
    if not args.morning_data:
        _set_output("pulled", "true")


def _pull_props_nhl(args) -> None:
    """NHL props (shots on goal, points, goalie saves) for games in the next --within hours: once
    a day (about 3 credits a game), plus with --afternoon one more look after 3 PM ET."""
    from betlab.cards.props_nhl import MARKETS

    sport_key = config.settings()["leagues"]["nhl"]["sport_key"]
    now = pd.Timestamp.now(tz="UTC")
    local = now.tz_convert(config.settings()["timezone"])
    day = local.strftime("%Y-%m-%d")
    if args.afternoon:                     # one more look near the start: the "close" for prop CLV
        if local.hour < 15:
            print("NHL props: the afternoon pull waits until 3 PM ET (0 credits)")
            return
        if any(f.stem[:2] >= "15" for f in (config.DATA_DIR / "odds" / sport_key / day).glob("*_props.parquet")):
            print("NHL props: already pulled this afternoon (0 credits)")
            return
    if str(config.settings()["leagues"]["nhl"]["start"]) > day:
        print("NHL props: before the season start in settings (0 credits)")
        return
    if args.once_daily and any((config.DATA_DIR / "odds" / sport_key / day).glob("*_props.parquet")):
        print("NHL props already pulled today: skipping (0 credits)")
        return
    client = odds_api.OddsApiClient()
    client.sync_balance()
    chosen = [e for e in client.events(sport_key)
              if now < pd.Timestamp(e["commence_time"]) < now + pd.Timedelta(hours=args.within)]
    if not chosen:
        print("no NHL games in the window: skipping (0 credits)")
        return
    ts = _now()
    frames = [odds_api.flatten(client.event_odds(sport_key, e["id"], tuple(MARKETS)), sport_key, ts) for e in chosen]
    df = pd.concat(frames, ignore_index=True)
    path = odds_api.save_snapshot(df, sport_key, ts, "props")
    print(f"NHL props: {len(chosen)} games, {len(df)} prices -> {path.name} | credits remaining: {client.balance_note()}")


def cmd_pregame(args) -> None:
    """The worker's pre-game pulls (pregame.py): each game once, after its sport's news, every 15 minutes."""
    if not odds_api.any_key():
        print("no Odds API key is set: skipping the pre-game pulls")
        return
    from betlab import pregame

    client = odds_api.OddsApiClient()
    client.sync_balance()
    failed = []
    try:
        done = pregame.run(client)
    except pregame.PregameError as exc:
        done, failed = exc.done, exc.failed
    for line in done:
        print(line)
    if done:
        print(f"credits remaining: {client.balance_note()}")
        _set_output("pulled", "true")
    else:
        print("pregame: no game in its window (0 credits)")
    if failed:
        raise SystemExit("pregame: skipped " + "; ".join(failed))


def _lines_by_book(offers: pd.DataFrame, sides: int = 2) -> str:
    """'120 FanDuel and 131 DraftKings lines' (offers have one row per side, `sides` a line)."""
    from betlab import books
    counts = offers.groupby(offers["book"].fillna("fanduel")).size() // sides if "book" in offers else {}
    parts = [f"{int(counts[b])} {books.name(b)}" for b in books.targets() if b in counts and counts[b]]
    return (" and ".join(parts) or "0") + " lines"


STARTING_MINUTES = 2      # the card skips games starting within this many minutes (cmd_card)


def not_starting(offers: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Offers for games more than STARTING_MINUTES from their start. The on-the-hour tick priced games starting that
    minute (Oct 8-10: three NHL leans 27-47 seconds after puck drop), and NHL prop offers are reused for up to 6
    hours. A bet this close is never logged (ledger.add_picks), so it shouldn't show or alert either."""
    if not len(offers) or "commence_time" not in offers:
        return offers
    start = pd.to_datetime(offers["commence_time"], utc=True, format="ISO8601", errors="coerce")
    return offers[start.isna() | (start > asof + pd.Timedelta(minutes=STARTING_MINUTES))]


def cmd_card(args) -> None:
    """Price each league's latest snapshot, classify and stake the offers, write the card
    to exports/ and log new picks (nothing is written with --dry-run). A league that
    fails only adds a note to the card."""
    asof = pd.Timestamp(args.asof, tz="UTC") if args.asof else pd.Timestamp.now(tz="UTC")
    notes, frames, ncaab_read_rows = [], [], []
    for league, module in EVALUATORS.items():
        sport_key = config.settings()["leagues"][league]["sport_key"]
        snap = pd.read_parquet(args.snapshot) if args.snapshot else latest_snapshot(sport_key)
        if snap is None:
            if league in ("nfl", "ncaaf"):  # soccer leagues just wait for their first matchday pull
                notes.append(f"{league.upper()}: no odds snapshot yet")
            continue
        snap = snap[pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof]
        ok, why = ready(league)
        if not ok:
            notes.append(f"{league.upper()}: {why}")
            continue
        try:
            if league == "ncaab":  # the card's offers plus the model's reads (cards/ncaab.py)
                from betlab.cards import ncaab as ncaab_card
                offers, ncaab_read_rows, ncaab_notes = ncaab_card.price(snap, asof)
                notes += ncaab_notes
            else:
                from betlab import books           # every book Mike bets at (Oct 12: FanDuel, DraftKings)
                offers = books.price_all(importlib.import_module(module).evaluate, snap, asof)
        except Exception as exc:  # one league failing must not sink the whole card
            notes.append(f"{league.upper()}: pricing failed ({type(exc).__name__}: {exc})")
            continue
        notes.append(f"{league.upper()}: {offers['event_id'].nunique() if len(offers) else 0} games priced "
                     f"from the {snap['snapshot_ts'].max() if len(snap) else 'n/a'} snapshot")
        frames.append(offers)
    # NFL player props (paper), priced only from a fresh props snapshot.
    props_snap = None if args.snapshot else latest_snapshot(config.settings()["leagues"]["nfl"]["sport_key"], "props")
    if props_snap is not None:
        from betlab.cards import props_nfl
        try:
            offers = props_nfl.evaluate(props_snap, asof)
            if len(offers):
                notes.append(f"NFL PROPS: {_lines_by_book(offers)} priced from the "
                             f"{props_snap['snapshot_ts'].max()} snapshot (paper only)")
                frames.append(offers)
        except Exception as exc:
            notes.append(f"NFL PROPS: pricing failed ({type(exc).__name__}: {exc})")
    # NBA player props (paper; the market prices them, the model is only tracked), from a
    # props snapshot under 2 hours old. Every line also goes to the NBA tracker.
    nba_rows = []
    nba_key = config.settings()["leagues"]["nba"]["sport_key"]
    nba_snap = None if args.snapshot else latest_snapshot(nba_key, "props")
    if nba_snap is not None:
        from betlab.cards import props_nba
        try:
            offers, nba_rows = props_nba.price(nba_snap, asof, pick_snap=latest_snapshot(nba_key))
            if len(offers):
                games_known = {r["event_id"] for r in nba_rows if r.get("lineup_known")}
                notes.append(f"NBA PROPS: {_lines_by_book(offers)} priced from the "
                             f"{nba_snap['snapshot_ts'].max()} snapshot (paper only); confirmed lineups for "
                             f"{len(games_known)} of {len({r['event_id'] for r in nba_rows})} games")
                frames.append(offers)
        except Exception as exc:
            notes.append(f"NBA PROPS: pricing failed ({type(exc).__name__}: {exc})")
    # Soccer anytime scorers (paper, market-first): FanDuel vs Pinnacle's two-way price, from props pulls
    # under 6 hours old (cards/props_soccer.scorer_offers).
    if not args.snapshot:
        from betlab.cards import props_soccer
        from betlab.cards.soccer import LEAGUES as SOCCER_LEAGUES

        n_scorer = n_goals = 0
        for lg in SOCCER_LEAGUES:
            snap_p = latest_snapshot(config.settings()["leagues"][lg]["sport_key"], "props")
            if snap_p is None or snap_p.empty or asof - pd.to_datetime(snap_p["snapshot_ts"], utc=True).max() > pd.Timedelta(hours=6):
                continue
            try:
                from betlab import books
                offers = books.price_all(props_soccer.scorer_offers, snap_p, lg, asof, kind="props")
            except Exception as exc:
                notes.append(f"SOCCER SCORERS ({lg}): pricing failed ({type(exc).__name__}: {exc})")
                continue
            if len(offers):
                frames.append(offers)
                n_scorer += len(offers)
            try:                                  # goals and both teams to score from the same pull (Oct 12)
                from betlab.cards import soccer_goals
                from betlab import books
                goals = books.price_all(soccer_goals.evaluate, snap_p, lg, asof)
            except Exception as exc:
                notes.append(f"SOCCER GOALS ({lg}): pricing failed ({type(exc).__name__}: {exc})")
                continue
            if len(goals):
                frames.append(goals)
                n_goals += len(goals)
        if n_scorer:
            notes.append(f"SOCCER SCORERS: {n_scorer} FanDuel and DraftKings anytime-scorer prices against Pinnacle's no-vig (paper only)")
        if n_goals:
            notes.append(f"SOCCER GOALS: {n_goals} FanDuel and DraftKings goals and both-teams-to-score prices against the sharp no-vig (paper only)")
    # NHL player props (paper, market-first): priced by `betlab nhl` (cards/props_nhl.py), used if fresh.
    nhl_offers = config.EXPORTS_DIR / "cards" / "nhl_prop_offers.json"
    if nhl_offers.exists() and not args.snapshot:
        import json

        body = json.loads(nhl_offers.read_text(encoding="utf-8"))
        if body.get("offers") and asof - pd.Timestamp(body["generated_at"]) < pd.Timedelta(hours=6):
            frames.append(pd.DataFrame(body["offers"]))
            notes.append(f"NHL PROPS: {_lines_by_book(pd.DataFrame(body['offers']))} priced (paper only)")
    from betlab import books                   # one offer per bet: the better book, the other's price attached
    offers = not_starting(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), asof)
    evaluated = picks.classify(books.select(offers), asof) if len(offers) else pd.DataFrame()
    if len(evaluated):
        evaluated = picks.stake(evaluated)
        # each book's own read, for accounts that turn a book off (books.per_book; the card is the same for everyone)
        evaluated["books"] = books.per_book(offers, evaluated, lambda d: picks.stake(picks.classify(d, asof)))
        evaluated["why"] = [picks.why_note(r) for _, r in evaluated.iterrows()]
        evaluated["pick_id"] = [ledger.pick_id(r) for _, r in evaluated.iterrows()]
        shown = evaluated[evaluated["tier"] != ""]
    else:
        shown = evaluated
    card = card_report.build(shown, _now(), None, notes) if len(shown) else \
        {"generated_at": _now(), "credits_remaining": None, "notes": notes, "picks": [], "leans": [],
         "check_news": [], "offers_evaluated": int(len(evaluated))}
    if args.dry_run:
        print(card_report.markdown(card))
        return
    card_report.write(card, asof.tz_convert(config.settings()["timezone"]).strftime("%Y-%m-%d"))
    added = ledger.add_picks(shown[shown["tier"] == "pick"], card["generated_at"]) if len(shown) else []
    if len(shown):  # leans: same signal, smaller edges; graded for CLV like picks (ledger.LEANS)
        ledger.add_picks(shown[shown["tier"] == "lean"], card["generated_at"], ledger.LEANS)
    if ncaab_read_rows:
        from betlab import ncaab_reads
        print(f"college basketball reads logged: {ncaab_reads.record(ncaab_read_rows, asof)}")
    if nba_rows:
        from betlab import tracking_nba
        print(f"NBA prop lines tracked: {tracking_nba.record(nba_rows, asof)}")
        fd_rows = [r for r in nba_rows if r.get("book", "fanduel") == "fanduel"]   # fun tickets: FanDuel until day 4
        _nba_page(fd_rows, nba_snap, latest_snapshot(nba_key), asof)
    if not args.snapshot and not args.dry_run:
        _nba_schedule(latest_snapshot(nba_key), asof)
    if len(evaluated):
        from betlab import tracking_soccer
        from betlab.cards import soccer

        soc = evaluated[evaluated["league"].isin(soccer.LEAGUES)]
        if len(soc):
            try:            # a tracker must never stop the card (Oct 13: it failed every card from 5:15 PM)
                print(f"soccer lines tracked: {tracking_soccer.record(soc, asof)}")
            except Exception as exc:  # noqa: BLE001
                print(f"soccer lines skipped ({type(exc).__name__}: {exc})")
    if not args.snapshot:
        try:                # college moneyline dogs at 20-40% (cfb_dogs.py, Oct 26): tracked from the latest pull
            from betlab import cfb_dogs
            snap_c = latest_snapshot(config.settings()["leagues"]["ncaaf"]["sport_key"])
            print(f"college dogs tracked: {cfb_dogs.record(snap_c, asof)}")
        except Exception as exc:  # noqa: BLE001 - a tracker must never stop the card
            print(f"college dogs skipped ({type(exc).__name__}: {exc})")
    try:
        print(f"soccer prop rungs tracked: {_soccer_props(asof)}")
    except Exception as exc:  # the props tracker must never block the card
        print(f"soccer props skipped ({type(exc).__name__}: {exc})")
    print(f"card written: {len(card['picks'])} picks ({len(added)} new in ledger), "
          f"{len(card['leans'])} leans, {len(card['check_news'])} check-news")


def _soccer_analysis(asof: pd.Timestamp) -> int:
    """Each soccer match's analysis for its game page (cards/analysis_soccer.py)."""
    from betlab import tracking_soccer, tracking_soccer_props
    from betlab.cards import analysis_soccer
    from betlab.cards.soccer import LEAGUES

    picks = {lg: latest_snapshot(config.settings()["leagues"][lg]["sport_key"]) for lg in LEAGUES}
    docs = analysis_soccer.build(tracking_soccer.view(now=asof, days=2)["games"], asof, picks, tracking_soccer_props.load())
    analysis_soccer.write(docs)
    from betlab import soccer_goal_reads   # the lineup goals read, logged once the lineup is confirmed (Oct 12)
    rows = [{"event_id": eid, "league": d.get("league"), "commence_time": d.get("commence_time"),
             "home": d["teams"][0]["team"], "away": d["teams"][1]["team"],
             "matchup": f"{d['teams'][0]['team']} vs {d['teams'][1]['team']}", **d["goals_read"]}
            for eid, d in docs.items() if d.get("goals_read") and d.get("lineup") == "confirmed" and len(d.get("teams", [])) == 2]
    if rows:
        print(f"soccer goals reads logged: {soccer_goal_reads.record(rows, asof)}")
    return len(docs)


def _soccer_props(asof: pd.Timestamp) -> int:
    """Every FanDuel soccer prop rung in today's props pulls (pregame, after lineups), with the other
    books' ladder fits and ESPN's lineup, into tracking_soccer_props. Free: the pulls are done."""
    from betlab import tracking_soccer_props
    from betlab.cards.soccer import LEAGUES
    from betlab.sources import espn_soccer as E

    from betlab.cards import props_soccer

    matches = []
    for lg in LEAGUES:
        key = config.settings()["leagues"][lg]["sport_key"]
        snap = latest_snapshot(key, "props")
        if snap is None or snap.empty:
            continue
        snap = snap[pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof]
        pick = latest_snapshot(key)
        for eid, g in snap.groupby("event_id"):
            home, away, kick = g["home_team"].iloc[0], g["away_team"].iloc[0], g["commence_time"].iloc[0]
            espn_id, squad, xg = None, None, None
            try:
                espn_id = E.find_event(lg, home, away, kick)
                squad = E.lineup(E.SLUGS[lg], espn_id) if espn_id else None
                xg = props_soccer.market_xg(pick[pick["event_id"] == eid] if pick is not None else None, home, away)
            except Exception:  # noqa: BLE001 - no lineup: rows still logged
                pass
            matches.append((lg, eid, g, espn_id, squad, xg, {"event_id": eid, "espn_id": espn_id, "commence_time": kick,
                                                              "matchup": f"{away} @ {home}"}))
    model = props_soccer.fitted()
    try:
        mus = props_soccer.means([(sq, lg, xg) for lg, _, _, _, sq, xg, _ in matches if sq is not None and len(sq)])
    except Exception as exc:  # the model must never block the logging
        print(f"soccer props model skipped ({type(exc).__name__}: {exc})")
        mus = {}
    rows = []
    for lg, eid, g, espn_id, squad, xg, info in matches:
        rows += tracking_soccer_props.rows(g, lg, info, squad, mus.get(str(espn_id)) if espn_id else None,
                                           model.dispersion if model is not None else None)
    return tracking_soccer_props.record(rows, asof) if rows else 0


def _nba_schedule(pick_snap, asof: pd.Timestamp) -> None:
    """The night's NBA games on the app from the morning's game-line pull (reports/nba.schedule), before
    any is priced; never blocks the card."""
    if pick_snap is None or pick_snap.empty or asof.date() < pd.Timestamp(str(config.settings()["leagues"]["nba"]["start"])).date() - pd.Timedelta(days=1):
        return
    from betlab.reports import nba as nba_report
    from betlab.sources import nba

    try:
        day = asof.tz_convert(config.settings()["timezone"]).strftime("%Y%m%d")
        try:
            espn = nba.scoreboard_teams(day)
        except Exception:  # ESPN down: no abbreviations or TV tags
            espn = []
        from betlab import nba_reads

        def read(entries):            # the team model's read on each game, logged once (nba_reads)
            try:
                proj = nba_reads.project(entries, asof)
            except Exception as exc:  # the read is a bonus: the games still list without it
                print(f"NBA read skipped ({type(exc).__name__}: {exc})")
                return
            try:                      # who's out tonight: the read doesn't adjust for them yet, so say so
                outs = nba_reads.absences(entries, asof)
            except Exception as exc:
                print(f"NBA absences skipped ({type(exc).__name__}: {exc})")
                outs = {}
            for e in entries:
                if e["event_id"] in proj:
                    e["model"] = proj[e["event_id"]] | ({"out": outs[e["event_id"]], "key_out": outs[e["event_id"]]["key_out"]}
                                                        if e["event_id"] in outs else {})
            print(f"NBA reads logged: {nba_reads.record(nba_reads.rows(entries, asof), asof)}")

        n = nba_report.schedule(pick_snap, espn, asof, enrich=read)
        if n:
            print(f"NBA games listed for the app: {n}")
    except Exception as exc:
        print(f"NBA listing skipped ({type(exc).__name__}: {exc})")


def _nba_page(rows: list[dict], props_snap, pick_snap, asof: pd.Timestamp) -> None:
    """The page's NBA view and this window's NBA fun slate (reports/nba.py); never blocks the card."""
    from betlab import tracking_nba
    from betlab.cards import fun_nba
    from betlab.reports import nba as nba_report
    from betlab.sources import nba

    try:
        day = asof.tz_convert(config.settings()["timezone"]).strftime("%Y%m%d")
        try:
            national = nba.national_tv(day)
        except Exception:  # ESPN down: no national-TV tags tonight
            national = {}
        centers = {}
        for r in rows:
            if r["event_id"] not in centers:
                centers[r["event_id"]] = fun_nba._center(pick_snap, r["home_name"], r["away_name"])
        import json

        from betlab import sgp_plus

        from betlab import pregame

        tips = pregame.load_state(config.settings()["leagues"]["nba"]["sport_key"], asof)["start"].values()
        from betlab import bans

        ban_list = bans.use(bans.owner_bans())   # the ban list (Oct 25)
        slates = fun_nba.build(rows, pick_snap, config.settings()["fun"], national, props_snap, day_tips=tips)
        bans.scrub({"slates": slates}, ban_list)
        path = config.EXPORTS_DIR / "fun_nba.json"   # earlier windows tonight: re-pulls merge in, locks hold
        old = json.loads(path.read_text(encoding="utf-8")).get("slates", []) if path.exists() else []
        slates = fun_nba.merge(slates, old, config.settings()["fun"])
        same = {s["slate"] for s in slates}
        slates = sgp_plus.keep_tickets(slates, [o for o in old if o["slate"] in same], asof, ("nba",))
        nba_report.write(rows, slates, centers, national, asof, tracking_nba.summary())
        print(f"NBA page: {len({r['event_id'] for r in rows})} games, {len(slates)} fun slate(s)")
    except Exception as exc:
        print(f"NBA page skipped ({type(exc).__name__}: {exc})")


def cmd_ufc(args) -> None:
    """The UFC fight pages for the next card (cards/analysis_ufc.py) -> exports/ufc.json (free: ESPN and the
    Odds API's event list)."""
    import json

    from betlab.cards import analysis_ufc

    asof = pd.Timestamp.now(tz="UTC")
    doc = {"generated_at": _now(), **analysis_ufc.build(asof, snap=latest_snapshot(
        config.settings()["leagues"]["ufc"]["sport_key"]))}
    path = config.EXPORTS_DIR / "ufc.json"
    path.write_text(json.dumps(finite(doc), indent=1, allow_nan=False), encoding="utf-8")
    print(f"UFC fight pages: {len(doc['games'])} fights -> {path}")
    from betlab import tracking_ufc                    # DraftKings' props and our read, every card (the tracker)

    try:
        print(f"UFC tracker: {tracking_ufc.record(doc['games'], asof)} fights updated, {tracking_ufc.grade(asof)} graded")
    except Exception as exc:  # the tracker must never stop the pages
        print(f"UFC tracker not updated ({type(exc).__name__}: {exc})")


def cmd_fun(args) -> None:
    """Build the fun same-game parlays from the latest props snapshot (exports/fun.json)."""
    from betlab import sgp_plus
    from betlab.cards import fun_nfl
    from betlab.reports import fun as fun_report

    from betlab import bans

    ban_list = bans.use(bans.owner_bans())      # the owner's ban list (Oct 25): no tickets on banned players/teams
    sport_key = config.settings()["leagues"]["nfl"]["sport_key"]
    snap = latest_snapshot(sport_key, kind="props")
    asof = pd.Timestamp.now(tz="UTC")
    if snap is None:
        print("no NFL props snapshot yet: only college tickets (run betlab pull-props for NFL slips)")
        doc = {"generated_at": _now(), **fun_nfl.build(snap.iloc[:0] if snap is not None else pd.DataFrame(
            columns=["commence_time"]), asof, args.event)}
    else:
        doc = {"generated_at": _now(), **fun_nfl.build(snap, asof, args.event)}
    td_rows = doc.pop("_td_rows", [])   # the anytime TD reads, for the tracker (not the page)
    college = config.settings()["fun"].get("college")
    if college and not args.event:  # one lines-only college ticket per kickoff slice (never mixed with the NFL)
        from betlab.cards import fun_ncaaf
        try:
            pick = latest_snapshot(config.settings()["leagues"]["ncaaf"]["sport_key"])
            doc["slates"] = sorted(doc.get("slates", []) + fun_ncaaf.build(pick, asof, college),
                                   key=lambda s: pd.Timestamp(s["kickoff"]))
        except Exception as exc:  # the college ticket is a bonus; never block the NFL build
            print(f"college ticket skipped ({type(exc).__name__}: {exc})")
    ncaab_cfg = config.settings()["fun"].get("ncaab")
    if ncaab_cfg and not args.event:  # one lines-only college basketball ticket per tip slice (never mixed with others)
        from betlab.cards import fun_ncaab
        try:
            nkey = config.settings()["leagues"]["ncaab"]["sport_key"]
            doc["slates"] = sorted(doc.get("slates", []) + fun_ncaab.build(latest_snapshot(nkey), asof, ncaab_cfg),
                                   key=lambda s: pd.Timestamp(s["kickoff"]))
        except Exception as exc:  # a bonus; never block the NFL build
            print(f"college basketball ticket skipped ({type(exc).__name__}: {exc})")
    soccer_cfg = config.settings()["fun"].get("soccer")
    snaps: dict = {}
    if soccer_cfg and not args.event:  # one soccer ticket per kickoff slice across the leagues (never mixed with others)
        from betlab.cards import fun_soccer
        from betlab.cards.soccer import LEAGUES

        try:
            snaps = {lg: latest_snapshot(config.settings()["leagues"][lg]["sport_key"]) for lg in LEAGUES}
            from betlab import tracking_soccer_props   # shot legs and overs from the props tracker
            doc["slates"] = sorted(doc.get("slates", []) + fun_soccer.build(snaps, asof, soccer_cfg,
                                                                          tracking_soccer_props.load()),
                                   key=lambda s: pd.Timestamp(s["kickoff"]))
        except Exception as exc:  # the soccer ticket is a bonus; never block the NFL build
            print(f"soccer ticket skipped ({type(exc).__name__}: {exc})")
    nhl_cfg = config.settings()["fun"].get("nhl")
    if nhl_cfg and not args.event:  # one NHL ticket per night plus shots overs (never mixed with other sports)
        from betlab.cards import fun_nhl

        try:
            key = config.settings()["leagues"]["nhl"]["sport_key"]
            doc["slates"] = sorted(doc.get("slates", []) + fun_nhl.build(latest_snapshot(key), latest_snapshot(key, "props"),
                                                                         asof, nhl_cfg),
                                   key=lambda s: pd.Timestamp(s["kickoff"]))
        except Exception as exc:  # the NHL ticket is a bonus; never block the NFL build
            print(f"NHL ticket skipped ({type(exc).__name__}: {exc})")
    ufc_cfg = config.settings()["fun"].get("ufc")
    if ufc_cfg and not args.event:  # one UFC parlay per card segment (never mixed with other sports)
        from betlab.cards import fun_ufc

        try:
            key = config.settings()["leagues"]["ufc"]["sport_key"]
            doc["slates"] = sorted(doc.get("slates", []) + fun_ufc.build(latest_snapshot(key), asof, ufc_cfg),
                                   key=lambda s: pd.Timestamp(s["kickoff"]))
        except Exception as exc:  # a bonus; never block the NFL build
            print(f"UFC ticket skipped ({type(exc).__name__}: {exc})")
    import json

    prev = config.EXPORTS_DIR / "fun.json"   # the last build: each slice's tickets lock 15 minutes before it starts
    try:
        old = json.loads(prev.read_text(encoding="utf-8")).get("slates", []) if prev.exists() and not args.event else []
    except ValueError as exc:   # Oct 18: the full disk cut fun.json off; build afresh rather than fail every tick
        print(f"fun.json unreadable, building without the last build ({exc})")
        old = []
    reopen = set()
    if not args.event:
        try:
            from betlab import pregame
            reopen = pregame.reopened_slates({o["slate"]: o["locked_at"] for o in old if o.get("locked_at")}, asof)
            # only slices before their usual lock can reopen (keep_tickets); past it the lock is final, so don't
            # say "new news" for them (Oct 12: the log said so for an NHL slice after puck drop, though nothing changed)
            reopen = {o["slate"] for o in old if o["slate"] in reopen and asof < sgp_plus.lock_time(o)}
        except Exception as exc:  # a failed check keeps the locks as they are
            print(f"reopen check skipped ({type(exc).__name__}: {exc})")
        if reopen:
            print(f"new news after an early lock: {', '.join(sorted(reopen))}")
    if n := bans.scrub(doc, ban_list):
        print(f"ban list: {n} ticket(s), slip(s) or over(s) left out")
    doc["slates"] = sgp_plus.keep_tickets(doc.get("slates", []), old, asof, early=_settled(asof) if not args.event else set(),
                                          reopen=reopen)
    nba_path = config.EXPORTS_DIR / "fun_nba.json"   # NBA slates are built by the card; lock the due ones here
    if nba_path.exists() and not args.dry_run:
        nba = json.loads(nba_path.read_text(encoding="utf-8"))
        locked = sgp_plus.keep_tickets(nba.get("slates", []), nba.get("slates", []), asof, ("nba",))
        if locked != nba.get("slates", []):
            nba_path.write_text(json.dumps(nba | {"slates": locked}, indent=2, default=str), encoding="utf-8")
    if args.dry_run:
        print(fun_report.markdown(doc))
        return
    try:                                      # after keep_tickets: only the tickets that stay get pulled
        _soccer_goals_lines([s for s in doc["slates"] if s.get("sport") == "soccer"], snaps, asof)
    except Exception as exc:  # links only: the ticket still shows without them
        print(f"soccer goals lines skipped ({type(exc).__name__}: {exc})")
    try:                                      # FanDuel's likely quote on every slip and ticket (fun_ledger.quote_model)
        from betlab import fun_ledger
        qm = fun_ledger.quote_model(fun_ledger.load())
        if qm:
            for d in [s for g in doc.get("games", []) for s in g.get("sgps") or []] + \
                     [sl[k] for sl in doc.get("slates", []) for k in ("plus", "plus_short") if sl.get(k)]:
                d["likely_price"] = fun_ledger.likely_price(qm, d.get("fair_price"), d.get("naive_price"), d.get("n_legs"),
                                                            str(d.get("sgp_id", "")).startswith("plus-"))
    except Exception as exc:  # a note on the slips only
        print(f"likely FanDuel quotes skipped ({type(exc).__name__}: {exc})")
    fun_report.write(doc, asof.tz_convert(config.settings()["timezone"]).strftime("%Y-%m-%d"))
    from betlab import fun_offers, td_reads
    print(f"anytime TD reads tracked: {td_reads.record(td_rows, asof)}")
    print(f"offered slips logged (value vs one story): {fun_offers.record(doc['games'], asof)}")
    n = sum(len(g["sgps"]) for g in doc["games"])
    print(f"fun parlays written: {n} across {len(doc['games'])} games")


def _soccer_goals_lines(slates: list[dict], snaps: dict, now: pd.Timestamp) -> None:
    """FanDuel's goals ladder and both-teams-to-score lines for the soccer tickets' matches, so every
    leg gets its betslip link and the ticket opens in FanDuel in one tap (Mike, 2026-10-10). The bulk
    feed has only FanDuel's 3-way; the event endpoint has the rest, at 2 credits a match. Each match
    is pulled once (kept in the league's `_goals` snapshot until kickoff), so the pre-game rebuilds
    of the ticket cost nothing."""
    from betlab.cards import fun_soccer
    from betlab.pregame import merge_latest

    want = {str(g["event_id"]) for sl in slates for g in (sl.get("plus") or {}).get("games") or []}
    if not want or not odds_api.any_key():
        return
    client = None
    for lg, snap in snaps.items():
        if snap is None or snap.empty:
            continue
        key = config.settings()["leagues"][lg]["sport_key"]
        prev = latest_snapshot(key, "goals")
        have = set(prev["event_id"].astype(str)) if prev is not None else set()
        props = latest_snapshot(key, "props")     # the pre-game pull takes goals and BTTS too (Oct 12)
        if props is not None and len(props):
            have |= set(props.loc[props["market"].isin(fun_soccer.GOALS_MARKETS), "event_id"].astype(str))
        ids = sorted((want & set(snap["event_id"].astype(str))) - have)
        if not ids:
            continue
        client = client or odds_api.OddsApiClient()
        ts = _now()
        new = pd.concat([odds_api.flatten(client.event_odds(key, e, fun_soccer.GOALS_MARKETS), key, ts) for e in ids],
                        ignore_index=True)
        path = odds_api.save_snapshot(merge_latest(new, prev, now), key, ts, "goals")
        print(f"soccer goals lines ({lg}): {len(ids)} matches -> {path.name} | credits remaining: {client.balance_note()}")


def _settled(now: pd.Timestamp) -> set[str]:
    """Slices whose news is in for every game, which lock early (pregame.settled_slates); never blocks a build."""
    from betlab import pregame

    try:
        early = pregame.settled_slates(now)
    except Exception as exc:
        print(f"early locks skipped ({type(exc).__name__}: {exc})")
        return set()
    if early:
        print(f"news in for every game: {', '.join(sorted(early))}")
    return early


def cmd_lock_due(args) -> None:
    """Does a fun slice reach its lock time (15 minutes before its first kickoff) now? Free; the worker's
    pre-game tick rebuilds, publishes and alerts when one is due (sgp_plus.lock_due)."""
    import json

    from betlab import sgp_plus

    slates = []
    for name in ("fun.json", "fun_nba.json"):
        path = config.EXPORTS_DIR / name
        try:
            slates += json.loads(path.read_text(encoding="utf-8")).get("slates", []) if path.exists() else []
        except ValueError as exc:   # Oct 18: the full disk cut fun.json off mid-write; the next `fun` rewrites it
            print(f"{name} unreadable, skipped ({exc})")
    now = pd.Timestamp.now(tz="UTC")
    early = _settled(now)
    due = sgp_plus.lock_due(slates, now, early=early)
    # a game's own slips lock by their game (Nov 9): a slate due only for them is said apart, so the watchdog's
    # "slices to lock" count stays the slices'
    slices = sgp_plus.lock_due([s | {"sgps": []} for s in slates], now, early=early)
    print(f"slices to lock: {', '.join(slices)}" if slices else "no slice to lock")
    if games := [e for s in slates if s["slate"] in due for e in sgp_plus.slips_due(s, now)]:
        print(f"games' own slips to lock: {', '.join(games)}")
    if due:
        _set_output("lock_due", "true")


def cmd_preview(args) -> None:
    """Build the Game Previews for NFL games in the next week (exports/previews.json)."""
    from betlab.cards import preview_nfl
    from betlab.reports import preview

    import json

    from betlab import cfb_reads, tracking
    from betlab.cards import preview_ncaaf

    import time

    now = pd.Timestamp.now(tz="UTC")
    t0 = time.monotonic()    # timings in the log: the worker once ran this past its 25-minute limit
    body, rows = preview_nfl.build(now)
    n = tracking.record(rows, now)
    doc = {"generated_at": _now(), **body, "track_record": tracking.summary()}
    preview.write(doc)
    print(f"previews written: {len(doc['games'])} games; {n} prop lines tracked ({time.monotonic() - t0:.0f}s)", flush=True)
    try:  # the college view is separate so a college problem never blocks the NFL previews
        t0 = time.monotonic()
        cbody, crows = preview_ncaaf.build(now)
        m = cfb_reads.record(crows, now)
        cdoc = {"generated_at": _now(), **cbody, "track_record": cfb_reads.summary()}
        (config.EXPORTS_DIR / "previews_ncaaf.json").write_text(json.dumps(cdoc, indent=2, default=str), encoding="utf-8")
        print(f"college previews: {len(cdoc['games'])} games; {m} early reads tracked ({time.monotonic() - t0:.0f}s)")
    except Exception as exc:
        print(f"college previews failed: {type(exc).__name__}: {exc}")
    try:  # the soccer game pages' analysis (cards/analysis_soccer.py); never blocks the rest
        t0 = time.monotonic()
        n_soc = _soccer_analysis(now)
        print(f"soccer analysis: {n_soc} games ({time.monotonic() - t0:.0f}s)")
    except Exception as exc:
        print(f"soccer analysis failed: {type(exc).__name__}: {exc}")


def cmd_archive(args) -> None:
    """Every saved odds pull boiled down to one row per bet, for studies (archive.py, Nov 4). Free; writes data/cache."""
    from betlab import archive

    print(archive.run())


def cmd_wind_watch(args) -> None:
    """Windy NFL games logged against the close: tracked, never bet (wind_watch.py, Nov 4). Free."""
    from betlab import wind_watch

    print(wind_watch.run())


def cmd_dfs(args) -> None:
    """Today's DraftKings classic lineups from the market's props, or what past ones scored (dfs.py, Nov 5). Free."""
    from betlab import dfs

    print(dfs.grade() if args.grade else dfs.run())


def cmd_calendar(args) -> None:
    """ESPN's next 10 weeks of games for the calendar, once a day (calendar_sync.py, Nov 4). Free."""
    from betlab import calendar_sync

    print(calendar_sync.run())


def cmd_backup(args) -> None:
    """The app database's backup, once a day (backup.py, Nov 4). Free."""
    from betlab import backup

    print(backup.run())


def cmd_health(args) -> None:
    """A slice past kickoff without its lock, or a src/ push not on the worker (health.py, Nov 4). Free."""
    from betlab import health

    health.run(alert=not args.no_alert)


def cmd_watchdog(args) -> None:
    """Yesterday's runs (ET) checked for features that quietly reported zero or swallowed an error (watchdog.py, Oct 30);
    the 9:55 daily. Findings go to the owner's phone once a day and exit WARN_EXIT."""
    from datetime import date

    from betlab import watchdog

    lines, result = watchdog.run(date.fromisoformat(args.day) if args.day else None, alert=not args.no_alert)
    for ln in lines:
        print(f"watchdog: {ln}")
    print(result)
    if lines:
        raise SystemExit(WARN_EXIT)


def cmd_challenges(args) -> None:
    """Today's Novig challenges: the best bet for each, saved and alerted once it's ripe (challenges.py); every
    pre-game tick."""
    from betlab import challenges

    print(challenges.run())


def cmd_pickem(args) -> None:
    """This week's FanDuel College Football Pick'em entries: matched to their games, priced at the frozen lines against
    the sharp market, graded when final, one alert Saturday morning (pickem.py); every pre-game tick."""
    from betlab import pickem

    print(pickem.run())


def cmd_ladders(args) -> None:
    """Lock each ladder's next step once its game's news is in, and alert its owner (ladders.py); every pre-game tick."""
    from betlab import ladders

    print(ladders.run())


def cmd_resets(args) -> None:
    """A lost bet with a bet reset puts its stake in the wallet as a bonus bet (resets.py); every pre-game tick."""
    from betlab import resets

    print(resets.run())


def cmd_alert(args) -> None:
    """Push new picks to the phones that turned alerts on (alerts.py); the worker runs it after each card."""
    from betlab import alerts

    print(alerts.test() if args.test else alerts.release() if args.held else alerts.run())


def cmd_leg_news(args) -> None:
    """A player on an open real bet goes out: an alert with the book's rule (leg_news.py); every pre-game tick, free."""
    from betlab import leg_news

    print(leg_news.run())


def cmd_rotation(args) -> None:
    """Keys due for rotation get a to-do and one alert (rotation.py); the 9:55 daily. Names only, never a value."""
    from betlab import rotation

    print(rotation.run())


def cmd_nhl(args) -> None:
    """The NHL view (free data, 0 credits): today's and tomorrow's games with DraftKings'
    lines from ESPN, the starting goalies and our model; every game is tracked
    (data/ledger/nhl_lines.csv) and the page document written to exports/nhl.json."""
    from betlab import tracking_nhl
    from betlab.cards import preview_nhl

    import json

    from betlab import tracking_nhl_props

    now = pd.Timestamp.now(tz="UTC")
    doc, rows = preview_nhl.build(now)
    n = tracking_nhl.record(rows, now)
    doc["tracker"] = tracking_nhl.summary()
    offers, track = doc.pop("_prop_offers", []), doc.pop("_prop_track", [])
    if track:
        print(f"NHL prop lines tracked: {tracking_nhl_props.record(track, now)}")
        doc["props_tracker"] = tracking_nhl_props.summary()
    # the card (betlab card) prices these with the other leagues' offers
    (config.EXPORTS_DIR / "cards").mkdir(parents=True, exist_ok=True)
    (config.EXPORTS_DIR / "cards" / "nhl_prop_offers.json").write_text(
        json.dumps({"generated_at": now.isoformat(), "offers": offers}, default=str), encoding="utf-8")
    preview_nhl.write(doc)
    reads = sum(1 for g in doc["games"] if g.get("read"))
    fd = sum(1 for g in doc["games"] if g.get("book") == "FanDuel")
    print(f"NHL: {len(doc['games'])} games ({fd} on FanDuel vs Pinnacle, the rest DraftKings via ESPN), {reads} reads; {n} tracked")
    if doc["games"]:
        _set_output("built", "true")


def cmd_refresh(args) -> None:
    """Refresh data that isn't read live: this season's college games, lines and PPA (6 CFBD
    calls) and advanced game stats for the college previews (2 calls); soccer's player history
    from ESPN (free) for the shots model."""
    from betlab.cards.soccer import DOMESTIC
    from betlab.sources import cfbd, espn_soccer

    for lg in DOMESTIC:          # not the cups: cup games in the history would change the model's inputs untested
        try:
            espn_soccer.update_history(lg)
        except Exception as exc:  # ESPN down must not block the college refresh
            print(f"soccer history not updated for {lg} ({type(exc).__name__}: {exc})")

    if not config.secret("CFBD_API_KEY"):
        print("CFBD_API_KEY is not set: skipping the college refresh")
        return
    df = cfbd.refresh_current()
    print(f"college history refreshed: {len(df)} games")
    adv = cfbd.refresh_advanced_current()
    print(f"college advanced stats refreshed: {len(adv)} team-games")
    start = pd.Timestamp(str(config.settings()["leagues"]["ncaab"]["start"]))
    today = pd.Timestamp.now(tz="America/New_York").tz_localize(None).normalize()
    if today >= start - pd.Timedelta(days=5) and today.month not in (5, 6, 7, 8, 9):
        from betlab.sources import cbbd
        try:
            print(f"college basketball refreshed: {cbbd.refresh_recent()} games (last 10 days and the next week)")
        except Exception as exc:          # the API down must not block the rosters; the card reads yesterday's file
            print(f"college basketball not refreshed ({type(exc).__name__}: {exc})")
    if today.month in (10, 11, 12):   # rosters for the early-season roster adjustment (ESPN, at most weekly)
        from betlab.sources import cbbd
        try:
            print(f"college basketball rosters: {cbbd.refresh_rosters()} teams")
        except Exception as exc:          # ESPN down must not block the rest; the card notes a missing roster
            print(f"college basketball rosters not refreshed ({type(exc).__name__}: {exc})")


GRADE_PROBLEM = "not graded", "unavailable"   # a grader's line that left something ungraded
WARN_EXIT = 3                                  # the worker records it and the job goes on (worker.WARN)


class _Tee:
    """Writes to several streams: the grade output still prints while it's read for problem lines."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text: str) -> int:
        for s in self.streams:
            s.write(text)
        return len(text)

    def flush(self) -> None:
        for s in self.streams:
            s.flush()


def cmd_grade(args) -> None:
    """Grade everything (_grade_everything). Any grader that left lines ungraded ("not graded",
    "unavailable") is listed, alerted to the owner's devices once a day, and the command exits WARN_EXIT:
    on Oct 13-14 two dailies graded no NHL prop or soccer lines while the step reported success.
    --no-alert (the worker's 3 AM grade): still exits WARN_EXIT, but the phone alert waits for the 9:55 daily's grade."""
    import contextlib
    import io
    import sys

    buf = io.StringIO()
    with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
        _grade_everything()
    problems = [ln.strip() for ln in buf.getvalue().splitlines() if any(k in ln for k in GRADE_PROBLEM)]
    if problems:
        print(f"grade warnings: {len(problems)} line(s) left something ungraded")
        if getattr(args, "no_alert", False):
            print("grade warning alert left to the morning grade (--no-alert)")
            raise SystemExit(WARN_EXIT)
        try:
            from betlab import alerts
            print(alerts.problem("grade", problems))
        except Exception as exc:  # noqa: BLE001 - the warning exit must not depend on the alert
            print(f"grade warning alert not sent ({type(exc).__name__})")
        raise SystemExit(WARN_EXIT)


def _grade_everything() -> None:
    """Settle finished picks (result, profit, CLV) and write exports/results.json."""
    from betlab import grading
    from betlab.reports import review

    from betlab import tracking

    from betlab import fun_ledger

    settled = grading.grade_all()
    print(f"leans graded: {grading.grade_all(ledger.LEANS)}")
    try:
        print(f"prop lines graded for the Games tab's track record: {tracking.grade()}")
    except Exception as exc:              # Nov 9: GitHub's 504s on nflverse here stopped every grader below
        print(f"prop lines not graded ({type(exc).__name__}: {exc})")
    from betlab import tracking_nhl, tracking_nhl_props
    try:
        print(f"NHL games graded: {tracking_nhl.grade()}")
    except Exception as exc:              # the NHL's or ESPN's API down must not block the rest
        print(f"NHL games not graded ({type(exc).__name__}: {exc})")
    try:
        print(f"NHL prop lines graded: {tracking_nhl_props.grade()}")
    except Exception as exc:              # nor the games' grader stop the props (Oct 13-14: one try hid both)
        print(f"NHL prop lines not graded ({type(exc).__name__}: {exc})")
    from betlab import tracking_nba, tracking_soccer

    from betlab import ncaab_reads

    try:
        from betlab import td_reads
        print(f"anytime TD reads graded: {td_reads.grade()}")
    except Exception as exc:
        print(f"anytime TD reads not graded ({type(exc).__name__}: {exc})")
    try:
        from betlab import nba_reads
        print(f"NBA game reads graded: {nba_reads.grade()}")
    except Exception as exc:  # the schedule file must not block the rest
        print(f"NBA game reads not graded ({type(exc).__name__}: {exc})")
    try:
        print(f"college basketball reads graded: {ncaab_reads.grade()}")
    except Exception as exc:
        print(f"college basketball reads not graded ({type(exc).__name__}: {exc})")
    try:
        from betlab import soccer_goal_reads
        print(f"soccer goals reads graded: {soccer_goal_reads.grade()}")
    except Exception as exc:
        print(f"soccer goals reads not graded ({type(exc).__name__}: {exc})")
    try:
        from betlab import tracking_soccer_props
        print(f"soccer prop rungs graded: {tracking_soccer_props.grade()}")
    except Exception as exc:  # ESPN down must not block the rest
        print(f"soccer prop rungs not graded ({type(exc).__name__}: {exc})")
    try:
        print(f"soccer lines graded: {tracking_soccer.grade()}")
    except Exception as exc:  # football-data.co.uk down must not block the rest
        print(f"soccer lines not graded ({type(exc).__name__}: {exc})")
    try:
        print(f"NBA prop lines graded: {tracking_nba.grade()}")
    except Exception as exc:  # the NBA box-score file must not block the football grading
        print(f"NBA prop lines not graded ({type(exc).__name__}: {exc})")
    try:
        print(f"fun parlays graded: {fun_ledger.grade()}")
    except Exception as exc:              # Nov 9: an nflverse 504 here skipped every step below
        print(f"fun parlays not graded ({type(exc).__name__}: {exc})")
    try:
        from betlab import fun_offers
        print(f"offered slips graded: {fun_offers.grade()}")
        s = fun_offers.summary()
        for r in s.itertuples():
            print(f"  {r.group}: {r.hits}/{r.slips} hit (expected {r.expected}), 1u at naive price {r.profit_1u:+.2f}")
    except Exception as exc:  # nflverse down must not block the rest
        print(f"offered slips not graded ({type(exc).__name__}: {exc})")
    try:
        from betlab import cfb_reads
        print(f"college early reads graded: {cfb_reads.grade()}")
    except Exception as exc:  # noqa: BLE001 - CFBD down must not block the rest
        print(f"college early reads not graded ({type(exc).__name__}: {exc})")
    try:                    # college moneyline dogs at 20-40% (cfb_dogs.py, Oct 26): tracked, never a pick
        from betlab import cfb_dogs
        print(f"college dogs graded: {cfb_dogs.grade()}")
    except Exception as exc:  # noqa: BLE001 - CFBD down must not block the rest
        print(f"college dogs not graded ({type(exc).__name__}: {exc})")
    try:
        fun_ledger.write_results()
    except Exception as exc:  # noqa: BLE001 - the review and scorecard below still write
        print(f"fun results not written ({type(exc).__name__}: {exc}): not graded")
    results = review.build()
    review.write(results)
    from betlab import golive

    g = golive.write()
    print("go-live: " + "; ".join(f"{m['market']} {m['picks']['with_clv']}/{golive.MIN_PICKS} {m['status']}"
                                  for m in g["markets"]))
    o = results["overall"]
    print(f"graded {settled} picks | overall {o['record']}, {o['units']:+}u, "
          f"avg CLV {o['avg_clv'] if o['avg_clv'] is not None else 'n/a'}")


DOC_LIMIT = 250_000   # the page's database takes at most 256 KiB of compact JSON per document


def split_fun(body: dict) -> tuple[dict, list[tuple[str, dict]]]:
    """app/fun without each game's block (slips, reads, injuries), plus one fun_games document
    per game: the whole Fun document passed 256 KiB on Sep 26, and the page sync writes all
    documents in one all-or-nothing batch."""
    keep = ("event_id", "matchup", "commence_time", "primetime", "game_ref")
    games = [(str(g["event_id"]), g) for g in body.get("games", []) if g.get("event_id")]
    index = [{k: g.get(k) for k in keep} | {"n_sgps": len(g.get("sgps") or []), "has_pack": bool(g.get("pack"))}
             for _, g in games]
    return body | {"games": index, "games_split": True}, games


def split_packs(games: list[tuple[str, dict]], sport: str) -> list[tuple[str, dict]]:
    """Each game's parlay-builder pack (sgp.leg_pack) as its own fun_legs document, taken out of
    the game's block: a pack is 50-150 KB, and a game block plus its pack could pass 256 KiB."""
    out = []
    for event_id, g in games:
        pack = g.pop("pack", None)
        if pack:
            out += pack_docs({"event_id": event_id, "matchup": g.get("matchup"), "commence_time": g.get("commence_time"),
                              "game_ref": g.get("game_ref"), "sport": sport, **pack})
    return out


def pack_docs(pack: dict, limit: int = 200_000) -> list[tuple[str, dict]]:
    """A builder pack as one or more fun_legs documents under the size limit: <event_id>, then
    <event_id>-2, ... (the page merges them by event_id). A leg that points at its complement
    ("not") stays in the same part as that leg."""
    import json

    head = {k: v for k, v in pack.items() if k != "legs"}
    parts, cur, size = [], [], 0
    for leg in pack["legs"]:
        n = len(json.dumps(leg, separators=(",", ":"))) + 1
        if cur and size + n > limit and "not" not in leg:
            parts.append(cur)
            cur, size = [], 0
        cur.append(leg)
        size += n
    parts.append(cur)
    eid = str(pack["event_id"])
    return [(eid if i == 0 else f"{eid}-{i + 1}", head | {"part": i + 1, "parts": len(parts), "legs": p})
            for i, p in enumerate(parts)]


def split_card(body: dict) -> tuple[dict, list[tuple[str, dict]]]:
    """app/card without its leans, plus the leans in card_leans chunks: 177 leans with their
    context passed 256 KiB on Sep 27 once props joined the card. app/card lists the chunks
    (leans_docs) so the page ignores a chunk left over from a longer day."""
    parts = chunk_rows(body.get("leans") or [])
    chunks = [(str(i), {"generated_at": body.get("generated_at"), "rows": p}) for i, p in enumerate(parts)]
    return body | {"leans": [], "leans_split": True, "leans_docs": [i for i, _ in chunks]}, chunks


def chunk_rows(rows: list[dict], limit: int = 200_000) -> list[list[dict]]:
    """Ledger rows in chunks that each stay under the document limit."""
    import json

    out, cur, size = [], [], 0
    for r in rows:
        n = len(json.dumps(r, default=str)) + 1
        if cur and size + n > limit:
            out.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += n
    return out + ([cur] if cur else [])


PAGE_SOURCES = (("card.json", "card"), ("results.json", "results"), ("fun.json", "fun"),
                ("previews.json", "previews"), ("fun_results.json", "fun_results"),
                ("previews_ncaaf.json", "previews_ncaaf"), ("golive.json", "golive"),
                ("fun_nba.json", "fun_nba"), ("nba.json", "nba"), ("nhl.json", "nhl"), ("ufc.json", "ufc"))


def finite(o):
    """NaN/inf become null: Python writes them as bare NaN, which JSON readers refuse."""
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {k: finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [finite(v) for v in o]
    return o


def page_products(novig: bool = False) -> dict:
    """Everything the page and the app show, whole: each exports/*.json with its FanDuel links
    attached, the current-rule paper picks, the coverage table and the credit balances. `novig`: Novig's side of every
    parlay too (novig_parlays.py; publish only, since the apps read it and it asks Novig's catalog and pricer).

    export-page splits these into page documents (page_docs); publish writes them to the
    database whole (publish.py). Builder packs stay on the Fun slates here.
    """
    import json

    from betlab import links
    from betlab.golive import current_rule

    from betlab import books

    matchers = {b: links.Matcher(links.book_rows(b)) for b in books.targets()}   # each book's betslip links (links.py)
    matcher = matchers["fanduel"]                          # parlay legs' FanDuel links; DraftKings' side below
    from betlab import fun_ledger
    try:                                   # DraftKings' likely quote: its own model from ~40 typed quotes, else FanDuel's
        fl = fun_ledger.load()
        dk_model = fun_ledger.quote_model(fl, book="draftkings")
        dk_stand_in = dk_model is None
        dk_model = dk_model or fun_ledger.quote_model(fl)
    except Exception:  # noqa: BLE001 - no quote yet: DraftKings' side shows its legs only
        dk_model, dk_stand_in = None, True
    nv_index = None
    if novig and (config.settings()["odds_api"].get("novig") or {}).get("parlays"):
        from betlab import novig_parlays                   # Novig's exact parlay price (Oct 28)
        nv_index = novig_parlays.Index(pd.concat([links.book_rows(b) for b in matchers], ignore_index=True))
        nv_watched = novig_parlays.watched_events()      # own slips priced only for watched games (Nov 7)
    out: dict = {}
    for name, doc_id in PAGE_SOURCES:
        path = config.EXPORTS_DIR / name
        if not path.exists():
            continue
        body = json.loads(path.read_text(encoding="utf-8"))
        if doc_id == "card":
            links.attach_card(body, matchers)
        if doc_id in ("fun", "fun_nba"):
            links.attach_fun(body, matcher)
            if "draftkings" in matchers:          # DraftKings' side of every slip (docs/DRAFTKINGS_PLAN.md, day 4)
                links.attach_dk(body, matchers["draftkings"], dk_model, dk_stand_in)
            if nv_index is not None:              # Novig's side: never stops the publish
                try:
                    print("novig parlays ({}): {} of {} priced".format(doc_id, *novig_parlays.attach(body, nv_index, watched=nv_watched)))
                except Exception as e:  # noqa: BLE001
                    print(f"novig parlays ({doc_id}): not priced ({type(e).__name__}: {e})")
        out[doc_id] = body
    out["picks"] = current_rule(ledger.load())   # the page shows current-rule picks only (DECISIONS 2026-09-30)
    out["coverage"] = coverage_doc()
    from betlab import tracking_soccer
    out["soccer"] = tracking_soccer.view()      # every soccer match, not only those with a bet
    from betlab.cards import analysis_soccer
    extra = analysis_soccer.load()               # the game page's analysis, built by `preview`
    for g in out["soccer"].get("games", []):
        if str(g["event_id"]) in extra:
            g["analysis"] = extra[str(g["event_id"])]
    if nv_index is not None:                      # Novig in the game pages' price tables (Oct 28): never stops the publish
        try:
            print(f"novig tables: {novig_parlays.attach_tables(out, nv_index)} rows priced")
        except Exception as e:  # noqa: BLE001
            print(f"novig tables: not priced ({type(e).__name__}: {e})")
    from betlab import pregame
    out["schedule"] = pregame.schedule()
    balances = {k["label"]: odds_api.CreditGuard(odds_api.usage_log(k["label"]), k["monthly_credits"],
                                                 k["reserve"], k["reset_day"]).remaining
                for k in config.settings()["odds_api"]["keys"]}
    known = [v for v in balances.values() if v is not None]
    out["meta"] = {"synced_at": _now(), "credits_remaining": sum(known) if known else None,
                   "credits_by_key": balances}
    return out


def page_docs(products: dict):
    """(collection, doc_id, body) for every claude.ai page document, each under the database's
    256 KiB limit: the Fun document is split per game (fun_games) with builder packs in fun_legs,
    the card's leans into chunks (card_leans) and a month of the ledger into chunks."""
    import copy

    products = copy.deepcopy({k: v for k, v in products.items() if k != "picks"}) | {"picks": products.get("picks")}
    for _, doc_id in PAGE_SOURCES:
        if doc_id not in products:
            continue
        body = products[doc_id]
        if doc_id == "fun":
            for slate in body.get("slates", []):    # college, NHL and soccer builder packs ride on their slates
                for pack in slate.pop("packs", []):
                    for doc_key, part in pack_docs(pack):
                        yield "fun_legs", doc_key, part
            body, games = split_fun(body)
            for event_id, pack in split_packs(games, "nfl"):
                yield "fun_legs", event_id, pack
            for event_id, game in games:
                yield "fun_games", event_id, game
        if doc_id == "fun_nba":   # each window's slate carries its games' builder packs
            for slate in body.get("slates", []):
                slate.pop("games", None)         # kept in exports/fun_nba.json for re-pulls only (fun_nba.merge)
                for pack in slate.pop("packs", []):
                    for doc_key, part in pack_docs(pack):
                        yield "fun_legs", doc_key, part
        if doc_id == "card":
            body, chunks = split_card(body)
            for chunk_id, chunk in chunks:
                yield "card_leans", chunk_id, chunk
        yield "app", doc_id, body
    picks_df = products.get("picks")
    if picks_df is not None and len(picks_df):
        rows = picks_df.drop(columns=["why"]).astype(object).where(picks_df.drop(columns=["why"]).notna(), None)
        rows["month"] = rows["commence_time"].astype(str).str[:7]
        for month, g in rows.groupby("month"):
            for i, part in enumerate(chunk_rows(g.drop(columns=["month"]).to_dict(orient="records"))):
                yield "ledger", month if i == 0 else f"{month}-{i + 1}", {"rows": part}
    if products.get("coverage"):
        yield "app", "coverage", products["coverage"]
    yield "app", "meta", products["meta"]


def cmd_export_page(args) -> None:
    """Write exports/page_sync/: one JSON file per page document, plus a manifest.

    Whoever syncs the page (the cloud routine, or Claude in a session) uploads
    each file with ArtifactData 'set' and never needs to interpret the data.
    """
    import json

    out = config.EXPORTS_DIR / "page_sync"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    manifest = []
    for collection, doc_id, body in page_docs(page_products()):
        name = f"{collection}__{doc_id}.json"
        text = json.dumps(finite(body), default=str, separators=(",", ":"), allow_nan=False)
        if len(text.encode("utf-8")) > DOC_LIMIT:
            print(f"WARNING: {collection}/{doc_id} is {len(text) // 1024} KB, over the page database's limit")
        (out / name).write_text(text, encoding="utf-8")
        manifest.append({"collection": collection, "doc_id": doc_id, "file": f"exports/page_sync/{name}"})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"{len(manifest)} page documents -> {out}")


def coverage_doc(path=None) -> dict | None:
    """docs/COVERAGE.md as the page's Markets tab: the table's columns and rows, the
    last-updated date and the key's bullet lines (the markdown stays the one source)."""
    import re

    # The worker's image has no docs/ (Dockerfile.worker copies src only): read the data repo's copy, which each job
    # pulls from main (Oct 14: the app's Markets table had sat on the Oct 4 version since the worker cutover).
    if path is None:
        found = [p for p in (config.DATA_DIR.parent / "docs" / "COVERAGE.md", config.ROOT / "docs" / "COVERAGE.md") if p.exists()]
        if not found:
            print("export-page: docs/COVERAGE.md not found; the Markets table keeps its last published copy")
            return None
        path = found[0]
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    table = [l for l in lines if l.startswith("|")]
    if len(table) < 3:
        return None
    cells = lambda l: [c.strip() for c in l.strip().strip("|").split("|")]
    updated = next((m.group(1) for l in lines if (m := re.match(r"Last updated:\s*([^,\s]+)", l))), None)
    plain = lambda t: re.sub(r"\*\*(.+?)\*\*", r"\1", t).replace("\\*", "*").replace("`", "")
    key, notes, cur = [], [], None        # bullets and closing notes, wrapped lines joined
    after = lines[lines.index(table[-1]) + 1:]
    for l in after:
        if l.startswith("- "):
            key.append(l[2:].strip())
            cur = key
        elif l.startswith("**") and not l.startswith("**Key"):
            notes.append(l.strip())
            cur = notes
        elif l.strip() and cur is not None and not l.startswith("**"):
            cur[-1] += " " + l.strip()
        elif not l.strip():
            cur = None if cur is notes else cur
    key, notes = [plain(k) for k in key], [plain(n) for n in notes]
    return {"updated": updated, "columns": cells(table[0]), "rows": [[plain(c) for c in cells(l)] for l in table[2:]],
            "key": key, "notes": notes}


def cmd_import_taken(args) -> None:
    """Merge the page's 'taken' documents (a JSON list saved by the sync) into the ledger."""
    import json

    taken = json.loads(open(args.file, encoding="utf-8").read())
    print(f"{ledger.apply_taken(taken)} picks marked as yours")


def cmd_publish(args) -> None:
    """Write the app's database from the page products (docs/APP_PLAN.md). Skips quietly
    when SUPABASE_DB_URL isn't set, so the workflows can run it before the database exists."""
    url = config.secret("SUPABASE_DB_URL")
    if not url:
        print("publish: SUPABASE_DB_URL not set, skipping")
        return
    import psycopg

    from betlab import fun_ledger, publish
    from betlab.golive import current_rule

    products = page_products(novig=True)
    packs = [(doc_id, body) for coll, doc_id, body in page_docs(products) if coll == "fun_legs"]
    picks, leans = ledger.load(), ledger.load(ledger.LEANS)
    current = set(current_rule(picks)["pick_id"]) | set(current_rule(leans, picks=False)["pick_id"])
    try:
        from betlab.sources import nflverse

        abbr = nflverse.team_abbr_by_name()
    except Exception as e:   # noqa: BLE001 - names still match by start time and spelling
        print(f"publish: no NFL team names ({type(e).__name__}); matching by spelling only")
        abbr = {}
    rows = publish.build_rows(products, picks, leans, fun_ledger.load(), packs, current, abbr)
    owner = config.owner_user_id()
    with psycopg.connect(url, prepare_threshold=None) as conn:   # no prepared statements: Supabase's pooler
        counts = publish.publish(conn, rows)
        try:                                     # live CLV on open bets (Oct 28): its own transaction, never stops the publish
            from betlab import clv_now
            with conn.transaction():
                print(clv_now.run(conn, products, [b for _, b in packs]))
        except Exception as e:  # noqa: BLE001
            print(f"live CLV: not written ({type(e).__name__}: {e})")
        fun_df = fun_ledger.load()
        counts["custom_graded"] = sum(publish.grade_customs(conn, uid, fun_df)       # every account's saved parlays
                                      for uid in set(publish.app_users(conn)) | ({owner} if owner else set()))
        publish.pulse(conn)                      # last: open apps read everything above at once (Nov 4)
    print("published: " + ", ".join(f"{k} {v}" for k, v in counts.items()))


def cmd_import_page_taps(args) -> None:
    """Copy the old page's marks and typed prices (the page sync's JSON lists) into the app's
    database for the owner. Insert-only, so the daily run repeats it while both apps are in use."""
    import json
    from pathlib import Path

    url, owner = config.secret("SUPABASE_DB_URL"), config.owner_user_id()
    if not url or not owner:
        print("import-page-taps: SUPABASE_DB_URL or the owner id not set, skipping")
        return
    import psycopg

    from betlab import publish

    read = lambda f: json.loads(Path(f).read_text(encoding="utf-8")) if f and Path(f).exists() else []
    picks, leans = ledger.load(), ledger.load(ledger.LEANS)
    rows = publish.page_tap_rows(read(args.taken), read(args.fun_taken), read(args.quotes),
                                 set(leans["pick_id"]), set(picks["pick_id"]))
    with psycopg.connect(url, prepare_threshold=None) as conn:
        counts = publish.import_page_taps(conn, owner, rows)
    print("page taps -> app: " + ", ".join(f"{k} {v} new of {len(rows[k])}" for k, v in counts.items()))


def cmd_db_migrate(args) -> None:
    """Apply new supabase/migrations to the app's database (docs/APP_PLAN.md). --already NAME marks a
    file applied by hand (0001_init.sql ran in Supabase's SQL editor)."""
    url = config.secret("SUPABASE_DB_URL")
    if not url:
        print("db-migrate: SUPABASE_DB_URL not set")
        return
    import psycopg

    from betlab import publish

    with psycopg.connect(url, prepare_threshold=None, autocommit=True) as conn:
        ran = publish.migrate(conn, already=set(args.already or []))
    print("db-migrate: " + (", ".join(ran) if ran else "already up to date"))


def cmd_novig_sync(args) -> None:
    """Mike's Novig bets into My bets from his own account (read-only key in NOVIG_KEY_ID / NOVIG_PRIVATE_KEY)."""
    from betlab import novig_sync

    print(novig_sync.run())


def cmd_sync_personal(args) -> None:
    """Bring the owner's bets, typed prices and saved parlays from the app's database into the
    CSV ledgers (replaces the page's claude/page-sync round trip). --to-json DIR writes the
    three lists instead (taken.json, fun_quotes.json, fun_taken.json), for a rollback."""
    import json
    from pathlib import Path

    url, owner = config.secret("SUPABASE_DB_URL"), config.owner_user_id()
    if not url or not owner:
        print("sync-personal: SUPABASE_DB_URL or OWNER_USER_ID not set, skipping")
        return
    import psycopg

    from betlab import fun_ledger, publish

    with psycopg.connect(url, prepare_threshold=None) as conn:   # no prepared statements: Supabase's pooler
        taken, quotes, fun_taken = publish.page_lists(*publish.fetch_personal(conn, owner))
        # other accounts (Oct 10): their slips are graded and their prices counted, never their stakes
        others = []
        for uid in publish.app_users(conn):
            if uid != owner:
                _, q, ft = publish.page_lists(*publish.fetch_personal(conn, uid))
                others += publish.others_as_quotes(q, ft)
        quotes = others + quotes            # the owner's row wins on a slip both priced
    if args.to_json:
        out = Path(args.to_json)
        out.mkdir(parents=True, exist_ok=True)
        for name, rows in (("taken", taken), ("fun_quotes", quotes), ("fun_taken", fun_taken)):
            (out / f"{name}.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
        print(f"wrote {len(taken)} taken, {len(quotes)} quotes, {len(fun_taken)} fun taken -> {out}")
        return
    n = ledger.apply_taken(taken)
    slips = fun_ledger.sync(quotes, fun_taken)
    print(f"sync-personal: {n} picks marked, {len(quotes)} quoted ({len(others)} from other accounts), "
          f"{len(fun_taken)} parlays marked -> {slips} slips")


def cmd_import_fun(args) -> None:
    """Merge the page's fun_quotes and fun_taken documents (JSON lists saved by the sync)
    into the fun ledger (data/ledger/fun.csv)."""
    import json
    from pathlib import Path

    from betlab import fun_ledger

    read = lambda f: json.loads(Path(f).read_text(encoding="utf-8")) if f and Path(f).exists() else []
    quotes, taken = read(args.quotes), read(args.taken)
    n = fun_ledger.sync(quotes, taken)
    print(f"fun ledger: {len(quotes)} quoted, {len(taken)} marked -> {n} slips")


def cmd_backfill(args) -> None:
    """Pull historical odds (paid key): NFL prop lines (about 40 credits a game) for the props
    backtest, or NBA game lines (20 credits a snapshot, ~4,620 a season) for the team model."""
    if args.what == "nhl-lines":             # free: ESPN, one call per game
        from betlab.sources import nhl

        df = nhl.backfill_lines(args.season)
        print(f"{len(df)} NHL games, {int(df.get('ml_home_close', pd.Series(dtype=float)).notna().sum())} with lines -> {nhl.LINES}")
        return
    if args.what == "nba-lines":
        from betlab import backfill_nba_lines as B

        df = B.run(args.season, max_credits=args.max_credits, limit=args.limit)
        print(f"{df['event_id'].nunique() if len(df) else 0} games saved -> {B.path(args.season)}")
        return
    from betlab import backfill_props

    first, _, last = args.weeks.partition("-")
    weeks = range(int(first), int(last or first) + 1)
    df = backfill_props.run(args.season, weeks, limit=args.limit)
    print(f"{df['game_id'].nunique() if len(df) else 0} games saved -> {backfill_props.path(args.season)}")


def cmd_backtest(args) -> None:
    """Run a league's walk-forward backtest and print log loss and pick results
    (`props`: the NFL props models, 2023-2025, about 5 minutes per model version;
    `script`: does the game script add to the 2025 prop market, about 10 minutes)."""
    if args.league == "nba":
        from betlab import backtest_nba

        from betlab import backfill_nba_lines

        tg, pg, sch = backtest_nba.load([2024, 2025, 2026])
        print("team model:", backtest_nba.team_eval(tg, 2025, [2026]))
        if backfill_nba_lines.path(2026).exists():
            rep = backtest_nba.market_report(backtest_nba.market_eval(tg, backfill_nba_lines.closing_lines(2026), sch))
            print("team model vs the 2025-26 closing lines (blend weight: 0 = market only; SE in brackets):")
            print(rep["fit"].to_string())
            print("betting FanDuel's line when the model disagrees by the gap:")
            print(rep["fanduel"].to_string(index=False))
        table, saved = backtest_nba.player_eval(pg, tg, 2025, 2026)
        print("log loss at a typical line (lower is better), fit on 2024-25, tested on 2025-26:")
        print(table.to_string(index=False))
        print("usage betas:", {k: round(v, 3) for k, v in saved["v3"]["usage_beta"].items()})
        print("saved data/models/nba_team.json and data/models/nba_player.json (pre_lineup, lineup)")
        return
    if args.league == "cfb":
        from betlab import backtest_cfb

        t = backtest_cfb.table()
        print(f"{len(t)} FBS games with lines, {int(t['open'].notna().sum())} with opening lines")
        print(backtest_cfb.evaluate(t).to_string(index=False))
        fit = backtest_cfb.fit_early(t)
        print(f"early read refit on {fit['n']} games ({fit['seasons'][0]}-{fit['seasons'][-1]}) -> data/models/ncaaf_early.json")
        return
    if args.league == "game":
        from betlab import backtest_game
        from betlab.sources import nflverse

        tg, qg = backtest_game.load(2010, 2025)
        print(backtest_game.qb_report(backtest_game.qb_eval(tg, qg, range(2016, 2026))).to_string(index=False))
        rep = backtest_game.weather_eval(tg, nflverse.load_weather(range(2012, 2026)), range(2012, 2026))
        print(f"weather: {rep['n']} team-games, {rep['windy']} with 15+ mph wind, {rep['precip']} rain/snow, "
              f"{rep['cold']} freezing")
        print(rep["fits"].to_string(index=False))
        print(rep["pass_epa_by_wind"].to_string())
        from betlab import injuries_nfl

        seasons = range(2015, 2026)
        ab = injuries_nfl.absences(nflverse.load_snap_counts_all(seasons), nflverse.load_player_stats_all(seasons))
        inj = backtest_game.injury_eval(tg, qg, ab, range(2016, 2026))
        print(f"non-QB absences: {inj['n']} team-games; how often each is missing: {inj['rates']}")
        print(inj["fits"].to_string(index=False))
        return
    if args.league == "td":
        from betlab import backtest_td

        rep = backtest_td.run()
        print("anytime TD read, trained 2023-24, tested 2025 (log loss gain vs usage + team points, game bootstrap):")
        print(rep["table"].to_string(index=False))
        print(rep["calibration"].to_string())
        print("refit on 2023-25 and saved to data/models/td_params.json")
        return
    if args.league == "lag":
        from betlab import props_lag

        p = props_lag.pairs(props_lag.load())
        print(f"FanDuel main prop sides, morning price vs the sharp close: {len(p)} sides, "
              f"{p['event_id'].nunique() if len(p) else 0} games (CLV on the plain sharp close, game-bootstrap SE)")
        if len(p):
            print(props_lag.report(p).to_string(index=False))
        return
    if args.league == "nfl-props-ml":
        from betlab import backtest_props_nfl_ml as BN

        out = BN.run()
        print(out["logloss"].to_string(index=False))
        print(out["bets"].to_string(index=False))
        return
    if args.league == "soccer-props":
        from betlab import backtest_props_soccer as BS

        df = BS.prepare()
        r = BS.evaluate(df)
        print(r.pivot_table(index=["league", "target", "line"], columns="model", values="log_loss",
                            aggfunc="mean").round(4).to_string())
        BS.train_final(df)
        print(f"model saved -> {BS.MODEL_PATH}")
        return
    if args.league == "ufc":                       # the fight model vs Elo, the base rate and DraftKings (Oct 23)
        from betlab.models import ufc as UM
        from betlab.sources import espn_ufc

        from betlab import tracking_ufc

        for line in UM.report(espn_ufc.history(range(2021, pd.Timestamp.now().year + 1))) + tracking_ufc.summary():
            print(line)
        return
    if args.league == "nhl-props":
        from betlab import backtest_props_nhl as BP

        df = BP.prepare()
        print(BP.evaluate(df).round(4).to_string(index=False))
        BP.train_final(df, max(BP.SEASONS))
        print(f"model saved -> {BP.MODEL_PATH}")
        return
    if args.league == "nhl":
        from betlab import backtest_nhl

        out = backtest_nhl.report()
        print("settings:", out["params"])
        print("measured on 2022-24:", out["calibration"])
        if out["tuning"] is not None:
            print(out["tuning"].head(8).to_string(index=False))
        print("held out (2025-26):", out["test"])
        for k, v in out["market"].items():
            print(k, v)
        backtest_nhl.save_params(out["params"], {"test": out["test"]})
        print("settings saved -> data/models/nhl.json")
        return
    if args.league == "ncaab":
        from betlab import backtest_ncaab
        from betlab.sources import cbbd

        g, tg = cbbd.games(), cbbd.team_games()
        pred = backtest_ncaab.predict(g, tg, [2024, 2025, 2026], roster=(cbbd.players(), cbbd.rosters()))
        print("margin and total error vs the close (settings tuned on 2023-24; roster shift fit on 2022-24):")
        print(backtest_ncaab.vs_close(pred).to_string(index=False))
        print("does the line move toward the model after the opener (2024-25, 2025-26)?")
        print(backtest_ncaab.line_moves(pred[pred["season"] >= 2025]).to_string(index=False))
        print("the same without the roster shift:")
        print(backtest_ncaab.line_moves(pred[pred["season"] >= 2025].assign(m_margin=pred["m_margin_base"])).to_string(index=False))
        return
    if args.league == "soccer":
        from betlab import backtest_soccer
        from betlab.models import soccer as soccer_model

        pred = backtest_soccer.run(p=soccer_model.Params(sot_weight=0.5))
        for against, label in (("c", "the close"), ("o", "Pinnacle earlier in the week")):
            print(f"1X2 log loss vs {label} (blend weight from earlier seasons only):")
            print(backtest_soccer.evaluate(pred, against).round(4).to_string(index=False))
        print("does the model predict line moves (earlier -> close)?")
        print(backtest_soccer.line_moves(pred).round(4).to_string(index=False))
        return
    if args.league == "sgp":
        from betlab import backfill_props, backtest_props, backtest_sgp

        hist = backtest_props.load(2021, 2025)
        rep = backtest_sgp.report(backtest_sgp.run((2023, 2024, 2025), hist=hist))
        print("pairs of 70% legs, 2023-25 (together = rank correlation; lift = both hit vs independent legs):")
        print(rep["pairs"].to_string(index=False))
        print(rep["slips"].to_string(index=False))
        print("anytime TD by position:"); print(rep["td_pos"].to_string())
        print("anytime TD by simulated chance:"); print(rep["td_bins"].to_string())
        print("team TDs:", rep["teams"])
        mp = backtest_sgp.market_pairs(pd.read_parquet(backfill_props.path(2025)), hist=hist)
        print("2025 FanDuel lines, market chances per leg: the simulator's joint vs independent legs")
        print(backtest_sgp.market_report(mp).to_string(index=False))
        return
    if args.league == "script":
        from betlab import backfill_props, backtest_props

        m = backtest_props.market_eval(pd.read_parquet(backfill_props.path(2025)))
        for label, ww in (("team ratings only", False), ("with who starts at QB and the weather", True)):
            rep = backtest_props.script_eval(m, who_and_weather=ww)
            print(f"--- {label}")
            print(rep["fits"].to_string(index=False))
            print("pass game, game bootstrap:", {k: round(v, 3) for k, v in rep["bootstrap"].items()})
            print(rep["halves"].to_string(index=False))
            print("side the matchup favors (|edge| >= 1 SD):", rep["strong_matchups"])
        return
    if args.league == "props":
        from betlab import backtest_props

        res = backtest_props.run()
        rep = backtest_props.report(res)
        print(rep["summary"].to_string())
        print(rep["rungs"].to_string(index=False))
        return
    from betlab import backtest

    report, _, _ = getattr(backtest, args.league)()
    for key, v in report["log_loss"].items():
        print(key, v)
    print(pd.DataFrame(report["picks"]).to_string(index=False))


def _owner_conn():
    url, owner = config.secret("SUPABASE_DB_URL"), config.owner_user_id()
    if not url or not owner:
        raise SystemExit("SUPABASE_DB_URL or the owner id isn't set")
    import psycopg
    return psycopg.connect(url, prepare_threshold=None), owner


def cmd_import_page_db(args) -> None:
    """Copy the page's to-dos and reviews (ArtifactData out_dir files: DIR/todos/*.json,
    DIR/reviews/*.json) into the app's database for the owner. Insert-only."""
    import json
    from pathlib import Path

    from betlab import plan

    def docs(sub):
        return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted((Path(args.dir) / sub).glob("*.json"))}
    conn, owner = _owner_conn()
    with conn:
        counts = plan.import_page(conn, owner, docs("todos"), docs("reviews"))
    print("import-page-db: " + ", ".join(f"{k} {v} new" for k, v in counts.items()))


def cmd_todo(args) -> None:
    """The shared to-do list in the app's database (More > Plan): list, add, done, reopen, set."""
    from betlab import plan

    conn, owner = _owner_conn()
    with conn:
        if args.action == "list":
            for t in plan.list_todos(conn, owner, None if args.all else "open"):
                due = f" (due {t['due']})" if t["due"] else ""
                mark = "x" if t["status"] == "done" else " "
                print(f"[{mark}] {t['owner']:6} {t['id']}: {t['title']}{due}")
                if args.verbose and t["detail"]:
                    print(" " * 9 + t["detail"])
        elif args.action == "add":
            if not args.owner or not args.title:
                raise SystemExit("add needs --owner and --title")
            print(plan.add_todo(conn, owner, args.owner, args.title, args.detail or "", args.due, args.id))
        elif args.action in ("done", "reopen", "set"):
            if not args.id:
                raise SystemExit("--id is required")
            n = plan.update_todo(conn, owner, args.id, done={"done": True, "reopen": False}.get(args.action),
                                 title=args.title, detail=args.detail, due=args.due,
                                 owner=args.owner if args.action == "set" else None)
            print(f"{n} updated")


def cmd_review(args) -> None:
    """Post a weekly review to More > Reviews (body from a Markdown-ish text file)."""
    from pathlib import Path

    from betlab import plan

    conn, owner = _owner_conn()
    with conn:
        print(plan.add_review(conn, owner, args.title, Path(args.body_file).read_text(encoding="utf-8"), args.id))


def main(argv=None) -> None:
    """Entry point for the `betlab` command (see the module docstring)."""
    parser = argparse.ArgumentParser(prog="betlab")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("credits").set_defaults(fn=cmd_credits)
    p = sub.add_parser("pull")
    p.add_argument("leagues", nargs="*")
    p.add_argument("--auto", action="store_true", help="only leagues with games in the next 36h, once a day")
    p.add_argument("--again", type=float, default=None,
                   help="with --auto: pull again if today's last pull is at least this many hours old")
    p.add_argument("--prime-time", action="store_true",
                   help="evening check: NFL odds only if a game kicks off in 30-110 minutes")
    p.set_defaults(fn=cmd_pull)
    p = sub.add_parser("pull-props")
    p.add_argument("--event", help="one Odds API event id")
    p.add_argument("--prime-time", action="store_true", help="only a game kicking off in 30-110 minutes")
    p.add_argument("--within", type=float, default=36, help="hours ahead to include (default 36)")
    p.add_argument("--once-daily", action="store_true", help="skip if props were already pulled today (ET)")
    p.add_argument("--morning-data", action="store_true",
                   help="nfl: the morning look for the props lag study only (data only: never picks), once a day")
    p.add_argument("--league", choices=["nfl", "nba", "nhl"], default="nfl")
    p.add_argument("--afternoon", action="store_true", help="nhl: one pull after 3 PM ET (the close for prop CLV)")
    p.add_argument("--tip-window", type=float, nargs=2, metavar=("MIN", "MAX"),
                   help="nba: minutes before tip-off to price (default 15 75)")
    p.set_defaults(fn=cmd_pull_props)
    p = sub.add_parser("card")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--snapshot", help="price a specific snapshot file instead of the latest")
    p.add_argument("--asof", help="pretend it is this UTC time (YYYY-MM-DDTHH:MM)")
    p.set_defaults(fn=cmd_card)
    p = sub.add_parser("fun")
    p.add_argument("--event", help="only this Odds API event id")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_fun)
    sub.add_parser("lock-due").set_defaults(fn=cmd_lock_due)
    sub.add_parser("preview").set_defaults(fn=cmd_preview)
    sub.add_parser("refresh").set_defaults(fn=cmd_refresh)
    sub.add_parser("nhl").set_defaults(fn=cmd_nhl)
    sub.add_parser("ufc", help="the UFC fight pages for the next card (exports/ufc.json)").set_defaults(fn=cmd_ufc)
    sub.add_parser("pregame").set_defaults(fn=cmd_pregame)
    p = sub.add_parser("alert")
    p.add_argument("--test", action="store_true", help="the confirmation to devices that just turned alerts on")
    p.add_argument("--held", action="store_true", help="send what quiet hours held")
    p.set_defaults(fn=cmd_alert)
    sub.add_parser("leg-news").set_defaults(fn=cmd_leg_news)
    sub.add_parser("rotation").set_defaults(fn=cmd_rotation)
    p = sub.add_parser("ladders")
    p.set_defaults(fn=cmd_ladders)
    p = sub.add_parser("resets")
    p.set_defaults(fn=cmd_resets)
    p = sub.add_parser("challenges")
    p.set_defaults(fn=cmd_challenges)
    p = sub.add_parser("pickem")
    p.set_defaults(fn=cmd_pickem)
    p = sub.add_parser("archive")
    p.set_defaults(fn=cmd_archive)
    p = sub.add_parser("wind-watch")
    p.set_defaults(fn=cmd_wind_watch)
    p = sub.add_parser("dfs")
    p.add_argument("--grade", action="store_true")
    p.set_defaults(fn=cmd_dfs)
    p = sub.add_parser("calendar")
    p.set_defaults(fn=cmd_calendar)
    p = sub.add_parser("backup")
    p.set_defaults(fn=cmd_backup)
    p = sub.add_parser("health")
    p.add_argument("--no-alert", action="store_true")
    p.set_defaults(fn=cmd_health)
    p = sub.add_parser("watchdog")
    p.add_argument("--day", help="Eastern date to check, YYYY-MM-DD (default yesterday)")
    p.add_argument("--no-alert", action="store_true", help="print the findings, don't alert")
    p.set_defaults(fn=cmd_watchdog)
    p = sub.add_parser("grade")
    p.add_argument("--no-alert", action="store_true", help="don't send the problem alert (the overnight grade)")
    p.set_defaults(fn=cmd_grade)
    sub.add_parser("export-page").set_defaults(fn=cmd_export_page)
    sub.add_parser("publish").set_defaults(fn=cmd_publish)
    p = sub.add_parser("db-migrate")
    p.add_argument("--already", nargs="*", metavar="NAME", help="migration files applied by hand")
    p.set_defaults(fn=cmd_db_migrate)
    p = sub.add_parser("sync-personal")
    p.add_argument("--to-json", metavar="DIR", help="write the lists to DIR instead of the ledgers")
    p.set_defaults(fn=cmd_sync_personal)
    sub.add_parser("novig-sync").set_defaults(fn=cmd_novig_sync)
    p = sub.add_parser("import-page-db")
    p.add_argument("dir", help="folder with todos/*.json and reviews/*.json from the page")
    p.set_defaults(fn=cmd_import_page_db)
    p = sub.add_parser("todo")
    p.add_argument("action", choices=["list", "add", "done", "reopen", "set"])
    p.add_argument("--id")
    p.add_argument("--owner", choices=["you", "claude"], default=None)
    p.add_argument("--title")
    p.add_argument("--detail")
    p.add_argument("--due", help="YYYY-MM-DD")
    p.add_argument("--all", action="store_true", help="list: include done items")
    p.add_argument("-v", "--verbose", action="store_true", help="list: show each item's detail")
    p.set_defaults(fn=cmd_todo)
    p = sub.add_parser("review")
    p.add_argument("--title", required=True)
    p.add_argument("--body-file", required=True)
    p.add_argument("--id")
    p.set_defaults(fn=cmd_review)
    p = sub.add_parser("import-taken")
    p.add_argument("file", help="JSON list of the page's 'taken' documents")
    p.set_defaults(fn=cmd_import_taken)
    p = sub.add_parser("import-page-taps")
    p.add_argument("--taken")
    p.add_argument("--fun-taken")
    p.add_argument("--quotes")
    p.set_defaults(fn=cmd_import_page_taps)
    p = sub.add_parser("import-fun")
    p.add_argument("--quotes", help="JSON list of the page's fun_quotes documents")
    p.add_argument("--taken", help="JSON list of the page's fun_taken documents")
    p.set_defaults(fn=cmd_import_fun)
    p = sub.add_parser("backfill")
    p.add_argument("what", choices=["props", "nba-lines", "nhl-lines"])
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--weeks", default="3-18", help="e.g. 3-18 or 5")
    p.add_argument("--limit", type=int, help="at most this many games or snapshots (a pilot)")
    p.add_argument("--max-credits", type=int, default=4800, help="nba-lines: stop before spending more")
    p.set_defaults(fn=cmd_backfill)
    p = sub.add_parser("backtest")
    p.add_argument("league", choices=["nfl", "props", "script", "game", "cfb", "nba", "sgp", "soccer", "ncaab", "td", "lag", "nhl", "nhl-props",
                                           "soccer-props", "nfl-props-ml", "ufc"])
    p.set_defaults(fn=cmd_backtest)
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
