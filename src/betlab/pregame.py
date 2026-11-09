"""Pre-game pulls (`betlab pregame`), the new schedule (Mike, 2026-10-04): "Every gameline can
be pulled in the morning, props and adjustments to gamelines should only be pulled after injury
reports/starters come out for the game."

The worker runs this every 15 minutes. For each league in season it asks the Odds API which games
start soon (free), and pulls each game **once**, at the first run when its start is inside the
league's window (`schedule.pregame` in settings.yaml: NFL and college after inactives, NBA after the
injury report, NHL after confirmed goalies, soccer after lineups):
- the game lines of just those games (one call per league, `eventIds`; about 3 credits), and
- their props: NFL (main, alt ladders, anytime TD), NBA, NHL (shots, points, saves) and soccer.

In the last tick before a start (CLOSING_MINUTES), a game with an open prop pick or lean that no props pull has
followed since it was logged gets one more look at just those markets (`_closing`): the close its CLV is
measured against. Without it, a bet logged in the game's final pull had no close at all (NFL, NBA) or was
"closed" against the very prices it was logged from (NHL, soccer). The European cups' 3-way bets close from our own
game-line pulls (cards/soccer.close_3way), so an open cup 3-way bet logged after its game's last lines pull gets the
same look at h2h, saved with the game lines (Oct 20: the Viking draw and the Nijmegen lean had no close).

Each pull is merged into the latest snapshot of its kind (`merge_latest`): the pulled games get
new prices, every other game not yet started keeps its earlier ones. The card prices each league
from its latest snapshot, so other games neither vanish from the card nor get re-priced without
their news. Games already pulled today are listed in data/odds/<sport>/<ET date>/pregame.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from betlab import config
from betlab.sources import odds_api

from betlab.cards.soccer import CUPS, LEAGUES as SOCCER   # the leagues and the European cups (Oct 12)


def windows() -> dict[str, tuple[int, int]]:
    """{league: (lo, hi) minutes before the start}; soccer's window applies to every soccer league."""
    w = (config.settings().get("schedule") or {}).get("pregame") or {}
    out = {lg: tuple(v) for lg, v in w.items() if lg != "soccer"}
    if "soccer" in w:
        out |= {lg: tuple(w["soccer"]) for lg in SOCCER}
    return out


def latest(sport_key: str, kind: str) -> pd.DataFrame | None:
    files = sorted((config.DATA_DIR / "odds" / sport_key).glob(f"*/*_{kind}.parquet"))
    return pd.read_parquet(files[-1]) if files else None


def merge_latest(new: pd.DataFrame, prev: pd.DataFrame | None, now: pd.Timestamp) -> pd.DataFrame:
    """The new rows, plus the previous snapshot's rows for games not in this pull and not started."""
    if prev is None or prev.empty:
        return new
    keep = prev[~prev["event_id"].isin(set(new["event_id"]))
                & (pd.to_datetime(prev["commence_time"], utc=True, format="ISO8601") > now)]
    return pd.concat([new, keep], ignore_index=True) if len(keep) else new


def due(events: list[dict], now: pd.Timestamp, window: tuple[int, int], done: set[str]) -> list[dict]:
    """Games starting lo..hi minutes from now that haven't had their pre-game pull."""
    lo, hi = window
    out = []
    for e in events:
        mins = (pd.Timestamp(e["commence_time"]) - now).total_seconds() / 60
        if lo <= mins <= hi and e["id"] not in done:
            out.append(e)
    return out


def due_by_slice(events: list[dict], now: pd.Timestamp, window: tuple[int, int], done: set[str], sport: str) -> list[dict]:
    """`due`, with every game of a fun slice due once the slice's first start is in the window (the NBA's early and
    late slices, Oct 21): a slice locks before its first tip, so its later games are pulled with the first one."""
    from betlab import sgp_plus

    first: dict[tuple[str, str], pd.Timestamp] = {}
    for e in events:
        k, t = sgp_plus.slice_of(e["commence_time"], sport), pd.Timestamp(e["commence_time"])
        first[k] = min(first.get(k, t), t)
    lo, hi = window
    out = []
    for e in events:
        if e["id"] in done:
            continue
        lead = (first[sgp_plus.slice_of(e["commence_time"], sport)] - now).total_seconds() / 60
        own = (pd.Timestamp(e["commence_time"]) - now).total_seconds() / 60
        if lo <= lead <= hi or lo <= own <= hi:
            out.append(e)
    return out


SLICE_PULLS = {"nba": "nba"}   # leagues whose games are pulled by slice (due_by_slice), and their slice sport


STICKY_MINUTES = 30     # a start the feed moves later by up to this much keeps its first time (below)
MAX_REPULLS = 2          # news re-pulls per game: a goalie swap, a late scratch (bounded credits)
# one closing look at open prop picks and leans in the last tick before the start: ticks come every 15 minutes, so one
# always falls 1-15 minutes out (16: the tick's own few seconds). At 30, the Oct 20 dry run closed NBA games only 15
# minutes after their pull, 30 minutes before tip.
CLOSING_MINUTES = 16


def _state_path(sport_key: str, now: pd.Timestamp):
    day = now.tz_convert(config.settings()["timezone"]).strftime("%Y-%m-%d")
    return config.DATA_DIR / "odds" / sport_key / day / "pregame.json"


def load_state(sport_key: str, now: pd.Timestamp) -> dict:
    """{"pulled": {event id: {"news": {source: hash}, "repulls": n}}, "closing": [event ids]}."""
    p = _state_path(sport_key, now)
    raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    if isinstance(raw, list):                                  # the first version kept just the ids
        raw = {"pulled": {eid: {} for eid in raw}}
    return {"pulled": raw.get("pulled", {}), "closing": raw.get("closing", []), "start": raw.get("start", {}),
            "files": raw.get("files", [])}


def _save_state(sport_key: str, now: pd.Timestamp, state: dict) -> None:
    p = _state_path(sport_key, now)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")


SCHEDULED = ("nba", "ncaab")   # no free schedule of their own in the apps: their games reach `games` from this (Nov 2)


def _schedule_path(league: str):
    return config.CACHE_DIR / "schedule" / f"{league}.json"


def save_schedule(league: str, events: list[dict]) -> None:
    p = _schedule_path(league)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(events), encoding="utf-8")


def schedule() -> dict[str, list[dict]]:
    """The NBA's and college basketball's games from each tick's free /events call, for publish: a game's other rows come
    only from its paid pull or a bet (Mike, Nov 2: 15 NBA and 117 college games today, none on Games or in Home's locks).
    Empty when the cache was cleared (worker.check_disk): the games table keeps what it has, and the next tick refills."""
    out = {}
    for league in SCHEDULED:
        try:
            out[league] = json.loads(_schedule_path(league).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def pregame_files(sport_key: str, now: pd.Timestamp) -> set[str]:
    """Today's snapshots from these pulls, a few games each: not the morning's whole-league pull (cli._hours_since_pull)."""
    return set(load_state(sport_key, now)["files"])


def pulled_today(sport_key: str, now: pd.Timestamp) -> set[str]:
    return set(load_state(sport_key, now)["pulled"])



# The fun slices' sports for each league (sgp_plus.SLICES) that may lock early once their news is in; the NBA's slices
# lock at the usual time: their later games are pulled with the first one, before their own lineups (due_by_slice)
SLICE_SPORT = {"nfl": "nfl", "ncaaf": "ncaaf", "nhl": "nhl", "ufc": "ufc", "ncaab": "ncaab", **{lg: "soccer" for lg in SOCCER}}
# College basketball has no props to wait for and no news check (Mike, Nov 2): a slice locks once its first tip has had its
# pull. Its later games keep their own pulls for the card, and the ticket has their morning lines, as at the usual lock.
FIRST_TIP_ONLY = {"ncaab"}


def _goalies_confirmed(now: pd.Timestamp) -> dict[str, bool]:
    """{team key: its starting goalie is confirmed} from ESPN's free scoreboard (news._nhl_goalies)."""
    from betlab import news

    day = now.tz_convert("America/New_York").strftime("%Y%m%d")
    return {k: bool(v) and all(str(x).endswith(":confirmed") for x in v) for k, v in news._nhl_goalies(day).items()}


def _slice_games(now: pd.Timestamp) -> list[dict]:
    """The games of the next 18 hours not yet started, with their fun slice and pre-game state: {slate, sport,
    event_id, home, away, pulled, news_at}. From each league's latest game-line snapshot and pregame.json."""
    from betlab import sgp_plus

    today = now.tz_convert(config.settings()["timezone"]).strftime("%Y-%m-%d")
    out = []
    for league, sport in SLICE_SPORT.items():
        lg = config.settings()["leagues"].get(league)
        if not lg or str(lg["start"]) > today:
            continue
        snap = latest(lg["sport_key"], "pick")
        if snap is None or snap.empty:
            continue
        games = snap.drop_duplicates("event_id")
        ct = pd.to_datetime(games["commence_time"], utc=True, format="ISO8601")
        games = games[(ct > now) & (ct <= now + pd.Timedelta(hours=18))]
        pulled = load_state(lg["sport_key"], now)["pulled"]
        for g in games.itertuples():
            day, name = sgp_plus.slice_of(g.commence_time, sport, g.home_team, g.away_team)
            rec = pulled.get(str(g.event_id))
            out.append({"slate": sgp_plus.slice_names(sport, day, name, 2)["slate"], "sport": sport,
                        "event_id": str(g.event_id), "home": g.home_team, "away": g.away_team, "start": pd.Timestamp(g.commence_time),
                        "pulled": rec is not None, "news_at": (rec or {}).get("news_at")})
    return out


def settled_slates(now: pd.Timestamp | None = None, goalies=None) -> set[str]:
    """Slices whose news is in for every game not yet started, so they can lock early (Mike, Oct 12: "if all
    games within a slice have injury reports/starting 11's/etc out then you can lock the slice so I can get
    picks earlier"). A game's news is in once it has had its pre-game pull, which `schedule.pregame` times after
    its sport's news (NFL inactives, soccer lineups); the NHL also needs both starting goalies confirmed. Games
    of the next 18 hours only; a slice with any game still waiting isn't settled. Free: local files, plus ESPN's
    scoreboard when an NHL slice is otherwise ready."""
    now = now or pd.Timestamp.now(tz="UTC")
    ready: dict[str, list[bool]] = {}
    nhl_games = []
    games = _slice_games(now)
    first: dict[str, pd.Timestamp] = {}
    for g in games:
        first[g["slate"]] = min(first.get(g["slate"], g["start"]), g["start"])
    for g in games:
        if g["sport"] in FIRST_TIP_ONLY and g["start"] != first[g["slate"]]:
            continue
        ready.setdefault(g["slate"], []).append(g["pulled"])
        if g["pulled"] and g["sport"] == "nhl":
            nhl_games.append(g)
    if nhl_games:
        from betlab.news import team_key

        try:
            conf = goalies if goalies is not None else _goalies_confirmed(now)
        except Exception:  # ESPN down: the NHL slices lock at the usual time
            conf = {}
        for g in nhl_games:
            ready[g["slate"]].append(bool(conf.get(team_key(g["home"]))) and bool(conf.get(team_key(g["away"]))))
    return {sid for sid, oks in ready.items() if oks and all(oks)}


def reopened_slates(locked: dict[str, str], now: pd.Timestamp | None = None) -> set[str]:
    """Early-locked slices to rebuild: one of their games was re-pulled on new news (news.py) after the slice
    locked (Mike, Oct 12: a locked ticket must still follow late news). `locked`: {slate: locked_at}.
    keep_tickets only reopens a slice before its usual lock time."""
    now = now or pd.Timestamp.now(tz="UTC")
    out = set()
    for g in _slice_games(now):
        at = locked.get(g["slate"])
        if at and g["news_at"] and pd.Timestamp(g["news_at"]) > pd.Timestamp(at):
            out.add(g["slate"])
    return out

def stick_starts(events: list[dict], state: dict) -> list[dict]:
    """Each game at the first start time seen today. Near kickoff the books move a game's start to the real kickoff
    (Oct 12: Monday night went from 8:15 to 8:18 at 8:15 PM), so the 8:15 tick saw a game not yet started: it
    re-pulled it, the card logged three prop leans at 8:15:31 and the fun slips were rebuilt. A move later by up to
    STICKY_MINUTES keeps the first time; a bigger move (a real reschedule, a weather delay) is taken and recorded.
    Updates state["start"]; returns the events with their sticky start."""
    out = []
    for e in events:
        first, now_t = state["start"].get(e["id"]), pd.Timestamp(e["commence_time"])
        if first and pd.Timedelta(0) < now_t - pd.Timestamp(first) <= pd.Timedelta(minutes=STICKY_MINUTES):
            e = e | {"commence_time": first}
        else:
            state["start"][e["id"]] = e["commence_time"]
        out.append(e)
    return out


def _sticky(df: pd.DataFrame, events: list[dict]) -> pd.DataFrame:
    """A pull's rows with each game's sticky start (the card and the fun slips read start times from snapshots)."""
    if df.empty or "commence_time" not in df:
        return df
    start = {e["id"]: e["commence_time"] for e in events}
    return df.assign(commence_time=[start.get(str(i), c) for i, c in zip(df["event_id"], df["commence_time"])])


def _props_markets(league: str):
    if league == "nfl":
        return odds_api.NFL_PROP_MARKETS + odds_api.NFL_ALT_MARKETS + odds_api.NFL_TD_MARKETS
    if league == "nba":
        return odds_api.NBA_PROP_MARKETS + odds_api.NBA_ALT_MARKETS
    if league == "nhl":
        from betlab.cards.props_nhl import MARKETS
        return tuple(MARKETS)
    from betlab.cards.soccer import LEAGUES
    if league in LEAGUES:                     # after lineups (the [15, 55] window): tracking_soccer_props, and
        from betlab.cards.soccer_goals import MARKETS as GOALS   # FanDuel's goals and BTTS (cards/soccer_goals, Oct 12)
        return tuple(odds_api.SOCCER_PROP_MARKETS) + GOALS
    return None


# Soccer goals and both-teams-to-score bets are game lines on the card but are priced, and closed, from the
# props pull's goals ladder (cards/soccer_goals.py)
GOALS_FEED = {"totals": "alternate_totals", "btts": "btts"}
# closing-look markets that live in the game-line ("pick") snapshot: the cups' 3-way, and UFC's moneyline and total
# rounds (open_rows never gives other leagues a "totals" row: soccer's go to its goals ladder, the rest are props)
LINE_CLOSING = ("h2h", "totals")
CLOSE_LINES = ("ufc",)   # leagues whose open game-line bets get a closing look (Oct 23): their last pull is often the
                         # bet's own, so without one a UFC bet had no close (a whole card segment shares one pull)


def open_rows(league: str) -> pd.DataFrame:
    """Open prop picks and leans in a league that a closing look can serve (and the cups' 3-way bets): event_id,
    feed market, created_at."""
    from betlab import ledger

    frames = []
    for path in (None, ledger.LEANS):
        df = ledger.load(path)
        if df.empty or "kind" not in df:
            continue
        df = df[(df["league"] == league) & (df["status"] == "open")]
        goals = (df["kind"] == "game_line") & df["market"].isin(GOALS_FEED) if league in SOCCER else False
        three_way = (df["kind"] == "game_line") & (df["market"] == "h2h") if league in CUPS else False
        lines = (df["kind"] == "game_line") & df["market"].isin(LINE_CLOSING) if league in CLOSE_LINES else False
        df = df[(df["kind"] == "prop") | goals | three_way | lines]
        frames.append(df.assign(market=df["market"].map(lambda m: GOALS_FEED.get(m, m) if league in SOCCER else m))
                      [["event_id", "market", "created_at"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["event_id", "market", "created_at"])


def _closing(league: str, sport_key: str, events: list[dict], skip: set[str], done: set[str],
             now: pd.Timestamp) -> dict[str, list[str]]:
    """{event id: markets} for one closing look: games starting within CLOSING_MINUTES with an open prop pick or
    lean logged after the game's last props pull (so nothing since could be its close); a cup 3-way bet against
    the game's last lines pull. Once per game."""
    soon = {e["id"] for e in events
            if 0 < (pd.Timestamp(e["commence_time"]) - now).total_seconds() / 60 <= CLOSING_MINUTES}
    rows = open_rows(league)
    rows = rows[rows["event_id"].astype(str).isin(soon - skip - done)]
    if rows.empty:
        return {}
    def last_pull(kind):
        snap = latest(sport_key, kind)
        return ({} if snap is None or snap.empty else
                pd.to_datetime(snap["snapshot_ts"], utc=True, format="ISO8601").groupby(snap["event_id"].astype(str)).max().to_dict())

    last = {"props": last_pull("props"), "pick": last_pull("pick") if rows["market"].isin(LINE_CLOSING).any() else {}}
    out: dict[str, set] = {}
    for eid, market, logged in zip(rows["event_id"].astype(str), rows["market"], rows["created_at"]):
        seen = last["pick" if market in LINE_CLOSING else "props"]
        if eid not in seen or seen[eid] <= pd.Timestamp(logged):
            out.setdefault(eid, set()).add(market)
    return {k: sorted(v) for k, v in out.items()}


def with_other_markets(new: pd.DataFrame, prev: pd.DataFrame | None, markets: dict[str, list[str]]) -> pd.DataFrame:
    """A closing look pulls only a game's open markets: keep its other markets from the previous snapshot (with
    their own, older times), so merge_latest doesn't drop them from the card."""
    if prev is None or prev.empty or not markets:
        return new
    eid = prev["event_id"].astype(str)
    keep = pd.Series(False, index=prev.index)
    for e, ms in markets.items():
        keep |= (eid == e) & ~prev["market"].isin(ms)
    return pd.concat([new, prev[keep]], ignore_index=True) if keep.any() else new


def _news_changes(league: str, events: list[dict], state: dict, now: pd.Timestamp, src: dict) -> dict[str, list[str]]:
    """{event id: changed sources} for games already pulled, not started, under the re-pull cap."""
    from betlab import news

    out = {}
    for e in events:
        rec = state["pulled"].get(e["id"])
        if rec is None or rec.get("repulls", 0) >= MAX_REPULLS or pd.Timestamp(e["commence_time"]) <= now:
            continue
        diff = news.changed(rec.get("news"), news.fingerprint(src, e["home_team"], e["away_team"]))
        if diff:
            out[e["id"]] = diff
    return out


def run(client, now: pd.Timestamp | None = None) -> list[str]:
    """Pull every game whose window is open, and re-pull a pulled game whose news changed since;
    returns what was pulled, one line per league."""
    from betlab import news

    now = now or pd.Timestamp.now(tz="UTC")
    s = config.settings()
    day = now.tz_convert(s["timezone"]).strftime("%Y-%m-%d")
    done_lines, failed = [], []
    for league, window in windows().items():
        lg = s["leagues"].get(league)
        if not lg or str(lg["start"]) > day or (lg.get("paid_odds_from") and day < str(lg["paid_odds_from"])):
            continue
        sport_key = lg["sport_key"]
        try:
            events = client.events(sport_key)                   # free
            if league == "ufc":                                 # UFC fights only, at their ESPN segment starts
                from betlab.cards import ufc
                events = ufc.align(events, ufc.card_fights(now))
        except odds_api.OddsApiError as exc:
            # one league's hiccup (a 502 on Oct 8) shouldn't skip the others; the next tick retries
            failed.append(f"{league}: {exc}")
            continue
        state = load_state(sport_key, now)
        known = dict(state["start"])
        events = stick_starts(events, state)
        if league in SCHEDULED:
            save_schedule(league, events)
        chosen = (due_by_slice(events, now, window, set(state["pulled"]), SLICE_PULLS[league]) if league in SLICE_PULLS
                  else due(events, now, window, set(state["pulled"])))
        live_pulled = [e for e in events if e["id"] in state["pulled"] and pd.Timestamp(e["commence_time"]) > now]
        src = news.sources(league, now) if (chosen or live_pulled) and league in news.PATH else {}
        changes = _news_changes(league, live_pulled, state, now, src) if src else {}
        targets = chosen + [e for e in live_pulled if e["id"] in changes]
        # a game pulled now gets a fresh close anyway; the props leagues only (never college: NY rules)
        closing = (_closing(league, sport_key, events, {e["id"] for e in targets}, set(state["closing"]), now)
                   if _props_markets(league) or league in CLOSE_LINES else {})
        if not targets and not closing:
            if state["start"] != known:                   # the first start times seen (stick_starts); quiet ticks
                _save_state(sport_key, now, state)        # otherwise write nothing (no commit every 15 minutes)
            continue
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ids = [e["id"] for e in targets]
        n_lines = n_props = 0
        try:
            if ids:
                markets = tuple(lg.get("markets") or odds_api.GAME_MARKETS)
                lines = _sticky(odds_api.flatten(client.odds(sport_key, markets=markets, event_ids=ids), sport_key, ts), events)
                if lg.get("family") == "soccer":                     # Novig's soccer, from its free public catalog (Oct 22)
                    from betlab.sources import novig
                    lines = novig.add_rows(lines, sport_key, ts)
                if len(lines):
                    saved = odds_api.save_snapshot(merge_latest(lines, latest(sport_key, "pick"), now), sport_key, ts, "pick")
                    state["files"].append(saved.name)
                    n_lines = lines["event_id"].nunique()
            line_closing = {e: [m for m in ms if m in LINE_CLOSING] for e, ms in closing.items()}
            line_closing = {e: ms for e, ms in line_closing.items() if ms}
            if line_closing:                                         # the cups' 3-way close, kept with the game lines
                got = [odds_api.flatten(client.event_odds(sport_key, eid, ms, priority="closing"), sport_key, ts)
                       for eid, ms in line_closing.items()]
                got = [f for f in got if len(f)]
                if got:
                    prev = latest(sport_key, "pick")
                    lines = with_other_markets(_sticky(pd.concat(got, ignore_index=True), events), prev, line_closing)
                    saved = odds_api.save_snapshot(merge_latest(lines, prev, now), sport_key, ts, "pick")
                    state["files"].append(saved.name)
                    n_lines += lines["event_id"].nunique()
        except odds_api.OddsApiError as exc:
            failed.append(f"{league}: {exc}")                    # nothing is marked pulled: the next tick retries
            continue
        prop_markets = _props_markets(league)
        frames, missed = [], set()

        def props_for(eid, markets, **kw):
            """One game's call; a refusal (Nov 2: a 429 lost the whole tick) leaves that game for the next tick."""
            try:
                frames.append(odds_api.flatten(client.event_odds(sport_key, eid, markets, **kw), sport_key, ts))
            except odds_api.OddsApiError as exc:
                missed.add(eid)
                failed.append(f"{league} {eid}: {exc}")

        if prop_markets:                                         # NFL, NBA, NHL (never college: NY rules)
            for e in targets:
                props_for(e["id"], prop_markets)
        for eid, markets in closing.items():
            markets = [m for m in markets if m not in LINE_CLOSING]
            if markets:
                props_for(eid, markets, priority="closing")
        frames = [f for f in frames if len(f)]
        if frames:
            props, prev = _sticky(pd.concat(frames, ignore_index=True), events), latest(sport_key, "props")
            props = with_other_markets(props, prev, {e: [x for x in m if x not in LINE_CLOSING]
                                                     for e, m in closing.items() if e not in ids})
            odds_api.save_snapshot(merge_latest(props, prev, now), sport_key, ts, "props")
            n_props = props["event_id"].nunique()
        for e in targets:                                        # the news as of this pull
            if e["id"] in missed:
                continue
            rec = state["pulled"].setdefault(e["id"], {})
            if e["id"] in changes:
                rec["repulls"] = rec.get("repulls", 0) + 1
                rec["news_at"] = now.isoformat(timespec="seconds")   # an early-locked slice reopens on it
            rec["news"] = news.fingerprint(src, e["home_team"], e["away_team"])
        state["closing"] = sorted(set(state["closing"]) | (set(closing) - missed))
        _save_state(sport_key, now, state)
        parts = []
        if chosen:
            shown = ", ".join(f"{e['away_team']} @ {e['home_team']}" for e in chosen[:4]) + (" ..." if len(chosen) > 4 else "")
            parts.append(f"{len(chosen)} game(s) in the {window[0]}-{window[1]} min window ({shown})")
        for e in targets:
            if e["id"] in changes:
                parts.append(f"news changed for {e['away_team']} @ {e['home_team']} ({', '.join(changes[e['id']])}): re-pulled")
        if closing:
            parts.append(f"{len(closing)} closing look(s) at open prop picks"
                         + (f" ({len(line_closing)} at 3-way)" if line_closing else ""))
        done_lines.append(f"{league}: " + "; ".join(parts) + f"; lines for {n_lines}, props for {n_props}")
    if failed:
        raise PregameError(done_lines, failed)
    return done_lines


class PregameError(Exception):
    """Some leagues' event lists failed; the rest ran. Carries both so the caller still
    publishes what was pulled and then exits non-zero (the runs log shows the failure)."""

    def __init__(self, done: list[str], failed: list[str]):
        super().__init__("; ".join(failed))
        self.done, self.failed = done, failed
