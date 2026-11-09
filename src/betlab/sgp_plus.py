"""The fun bucket across games: one SGP+ ticket per slate, and straight overs to root for.

Mike likes one parlay per slate across its games (FanDuel's SGP+ joins same-game
parlays from different games into one bet) and something to cheer for on every play.

- **Slates** are kickoff windows on one Eastern day: early (before 3 PM), late (3-7 PM)
  and night. A window needs at least two games for an SGP+ ticket.
- **The ticket** takes one small same-game parlay ("mini", 2-3 legs, from the same
  simulator and leg rules as the Fun tab's slips: overs and TDs first, unders only as
  near-locks) from each of 2-4 games in the window. Games are independent, so the
  ticket's fair chance is the product of the minis' chances. Tickets are ranked by leg
  value (fair chance x FanDuel payout, with our game read where we have one), and the
  most games that fit the payout band win. Only FanDuel's quoted SGP+ price, typed on
  the page, can show an edge: FanDuel prices each game's correlation itself.
- **Anytime TD ticket** (Mike, 2026-09-26: "choose one person from each game for every
  slate"): one anytime scorer from every game in the window, each the likeliest scorer at a
  fair price (chance x value). The legs come from different games, so FanDuel pays the
  plain product of their prices and the ticket's EV is known without a quote.
- **Overs to root for:** the straight overs (and anytime TDs) in the window with the best
  value. The props market leans toward overs (2025: receptions and receiving-yards overs
  hit about 4 points under their price, at every line size), so these are fun bets with
  an honest cost shown, never picks.
"""

from __future__ import annotations

import hashlib
import itertools

import numpy as np
import pandas as pd

from betlab import odds_math as om
from betlab import sgp

ET = "America/New_York"
# One ticket per kickoff slice of each Eastern day (Mike, 2026-10-10). Each slice's tickets follow the lines
# and the news until LOCK_MINUTES before its first kickoff, then never change ("stop making new parlays as
# time goes": a day-long ticket was rebuilt from the games not yet started at every kickoff).
# sport: ((name, ends before this ET hour, what its title calls it), ...)
SLICES = {
    # the 9:30 AM international game is its own slice, a standalone like prime time (Mike, Oct 10): one game makes
    # no SGP+ or TD ticket, so it gets single-game slips, and it never joins the 1 PM ticket
    "nfl": (("morning", 12, "morning"), ("early", 15, "early"), ("late", 19, "late"), ("night", 24, "night")),
    "ncaaf": (("noon", 15, "noon"), ("afternoon", 19, "afternoon"), ("night", 24, "night")),  # noon, 3:30, 7:30 PM
    # Soccer has the most kickoff times, so the most slices (Mike, Oct 13: split cup days 12:45 / 3 PM; "more slices,
    # since there's so many games"; "maximize having max info available per slice on the weekends while also having
    # enough games per slice"). A slice locks at the tick 10-25 minutes before its first kickoff and a match's
    # lineups-in pull is the first tick within 55 minutes of it, so every lineup is in only when the slice's kickoffs
    # span about 30 minutes. Each ET kickoff cluster gets its own slice (weekend matches a day, Oct 10-18): before
    # 8:45 (~2), 9-9:30 (~6), 10-10:15 (1-5), 11:15-11:30 (1-5), 12-12:30 (2-4), 12:45 (cups), 2:30-3 (3-7),
    # MLS 7-7:30 (1-7), 8:30 (~3), 9:30 PM on (2-4). Merging neighbors would cost the later matches' lineups.
    # Oct 24: a 5:30 PM MLS match (playoffs) fell into the 7:30 slice, which then locked at 5:15 with its 7:30 matches
    # two hours before their lineups: 5-6:45 PM is its own slice now, and a soccer slice is titled by its first kickoff.
    "soccer": (("early", 8.75, "early"), ("nine", 9.75, "9 AM"), ("ten", 11, "10 AM"), ("eleven", 12, "11 AM"),
               ("noon", 12.67, "noon"), ("lunch", 14.25, "12:45"), ("three", 17, "3 PM"), ("five", 18.75, "5:30 PM"),
               ("mls", 20.25, "7:30 PM"),
               ("evening", 21.25, "8:30 PM"), ("night", 24, "late")),
    # NHL and NBA "dusk" (Nov 7): 5-6:30 PM starts lock on their own. Without it a 5:10 NBA tip led the early slice, and
    # the 8:10 Knicks game locked at 4:45 with it, priced before its pull; the slice's word is its first start ("5 PM")
    "nhl": (("afternoon", 17, "afternoon"), ("dusk", 18.75, "5 PM"), ("evening", 21, "evening"),
            ("late", 24, "late")),                                                                    # matinees, 5-6:30, 7 PM, West
    # college basketball's morning slice (Oct 27): tips before noon (the Nov 1 opener in Rome at 9:30; 24 days of
    # 2025-26 had an 11 AM tournament game with noon-4:30 games after it) lock on their own, not with the afternoon,
    # whose later games would otherwise go on a ticket locked before their pre-game pulls
    "ncaab": (("morning", 12, "morning"), ("afternoon", 17, "afternoon"), ("evening", 21, "evening"),
              ("late", 24, "late")),                                                                   # noon-4, 6-8:30, 9 PM+
    # Mike, Oct 21: "early and late slices" instead of 30-minute tip windows (six slices on Oct 21, most games without
    # slips of their own). Every game in a slice is pulled 15-45 minutes before the slice's first tip (pregame), so
    # later games are priced before their own lineups; a lineup change re-pulls them, but after the lock a ticket stays.
    "nba": (("afternoon", 17, "afternoon"), ("dusk", 18.75, "5 PM"), ("early", 21, "early"),
            ("late", 24, "late")),                                                                    # matinees, 5-6:30, 7-8:40, 9 PM+
    # UFC (Oct 23): one slice per card segment. International cards run 10 AM / noon / 2 PM (UFC 333), US cards
    # 6 / 8 / 10 PM: early prelims, prelims, main card each lock about 15 minutes before they start
    "ufc": (("morning", 11.5, "morning"), ("midday", 13.5, "midday"), ("afternoon", 17, "afternoon"),
            ("evening", 19.5, "evening"), ("prelims", 21.5, "prelims"), ("main", 24, "main card")),
}
NOUN = {"nfl": "game", "ncaaf": "game", "soccer": "match", "nhl": "game", "ncaab": "game", "nba": "game", "ufc": "fight"}
SPORT_NAME = {"nfl": "NFL", "ncaaf": "college football", "soccer": "soccer", "nhl": "NHL", "ncaab": "college basketball",
              "nba": "NBA", "ufc": "UFC"}
# the app's heading names the market, not the day (Mike, Oct 10: a parlay shows only around its lock)
SPORT_TITLE = {"nfl": "NFL", "ncaaf": "College football", "soccer": "Soccer", "nhl": "NHL", "ncaab": "College basketball",
               "nba": "NBA", "ufc": "UFC"}
# Lock at the first pre-game tick (every 15 minutes, on the quarter hour) within 25 minutes of the slice's first
# kickoff: always 10-25 minutes before it, exactly 15 for :00 and :30 kickoffs (Mike: "like 15 min before").
# A strict 15 would lock a 7:07 PM slice at 7:00, too late to place the bet.
LOCK_MINUTES = 25
LATE_NIGHT_HOUR = 4          # a 12:30 AM kickoff belongs to the night before


def primetime(sport: str, home: str | None, away: str | None) -> str | None:
    """A prime-time match's name ("El Clásico") from fun.<sport>.primetime, either way round; None for the rest."""
    if not home or not away:
        return None
    from betlab import config
    want = {home.strip().lower(), away.strip().lower()}
    for m in (config.settings().get("fun", {}).get(sport) or {}).get("primetime") or []:
        if {t.strip().lower() for t in m.get("teams", [])} == want:
            return m.get("name") or f"{away} @ {home}"
    return None


def slice_of(commence_time, sport: str, home: str | None = None, away: str | None = None) -> tuple[str, str]:
    """(ET day "2026-10-10", slice name) for a kickoff. A prime-time match (fun.<sport>.primetime: El Clásico, Oct 25)
    is a slice of its own, "prime", like the NFL's night games: pass its teams."""
    t = pd.Timestamp(commence_time).tz_convert(ET)
    if t.hour < LATE_NIGHT_HOUR:
        day = f"{t - pd.Timedelta(days=1):%Y-%m-%d}"
        return day, "prime" if primetime(sport, home, away) else SLICES[sport][-1][0]
    if primetime(sport, home, away):
        return f"{t:%Y-%m-%d}", "prime"
    h = t.hour + t.minute / 60                           # soccer's slices end on the quarter hour
    return f"{t:%Y-%m-%d}", next(n for n, end, _ in SLICES[sport] if h < end)


def kickoff_word(kickoff) -> str:
    """An Eastern kickoff as a slice's word: "3 PM", "7:30 PM", "noon"."""
    t = pd.Timestamp(kickoff).tz_convert(ET)
    if t.hour == 12 and t.minute == 0:
        return "noon"
    h = t.hour % 12 or 12
    return f"{h}{'' if t.minute == 0 else f':{t.minute:02d}'} {'AM' if t.hour < 12 else 'PM'}"


def slice_names(sport: str, day: str, name: str, n_games: int, kickoff=None, feature: str | None = None) -> dict:
    """The slate's id, label (the ticket's matchup line) and title (the app's heading):
    {"slate": "2026-10-10-ncaaf-noon", "label": "Sat Oct 10 · college football noon games",
     "title": "College football noon games"}. NFL ids keep their old form ("2026-09-27-early")."""
    t = pd.Timestamp(day)
    word = dict((n, w) for n, _, w in SLICES[sport]).get(name, name)
    if (sport == "soccer" or name == "dusk") and kickoff is not None:
        word = kickoff_word(kickoff)        # the slice's real first kickoff, not the usual one (Oct 24)
    noun = NOUN[sport] + ("es" if NOUN[sport].endswith("ch") else "s") * (n_games != 1)
    sid = f"{day}-{name}" if sport == "nfl" else f"{day}-{sport}-{name}"
    if feature:                             # a prime-time match: its own name (El Clásico)
        return {"slate": sid, "label": f"{t:%a %b} {t.day} · {feature}, {word}", "title": f"{feature} · {word}"}
    return {"slate": sid, "label": f"{t:%a %b} {t.day} · {SPORT_NAME[sport]} {word} {noun}",
            "title": f"{SPORT_TITLE[sport]} {word} {noun}"}


def slate_of(commence_time) -> tuple[str, str]:
    """(slate id, label) for an NFL kickoff: '2026-09-27-early', 'Sun Sep 27 · NFL early games'."""
    n = slice_names("nfl", *slice_of(commence_time, "nfl"), 2)
    return n["slate"], n["label"]


LOCKED = ("plus", "plus_short", "td")   # the tickets a slice keeps (plus_short: the NBA's likelier SGP+); overs and packs
                                        # stay live, and each game's own slips (sgps) lock by their game (lock_slips)
TICKETS = ("plus", "plus_short", "td")   # a slate's cross-game tickets (links, quotes, publish, alerts)
LOCK_SPORTS = ("nfl", "ncaaf", "soccer", "nhl", "nba", "ncaab", "ufc")
HOLD_HOURS = 4.0             # a locked slice stays on the app this long after its last kickoff


def _sliced(s: dict, sports) -> bool:
    """A slice-format slate of a locked sport: "<day>-<sport>-<slice>", the NFL's "<day>-<window>", or the
    NBA's tip time "<day>-nba-1900" (its games are priced 15-45 minutes before tip, so each tip time is
    its slice: cards/fun_nba.py). Day-long tickets from before Oct 10 aren't."""
    names = {n for sl in SLICES.values() for n, _, _ in sl} | {"prime"}   # a prime-time match's own slice (Oct 25)
    sport, tail = s.get("sport", "nfl"), s["slate"].rsplit("-", 1)[-1]
    return sport in sports and (tail in names or (sport == "nba" and tail.isdigit()))


def lock_time(s: dict, lock_minutes: float = LOCK_MINUTES) -> pd.Timestamp:
    return pd.Timestamp(s["kickoff"]) - pd.Timedelta(minutes=lock_minutes)


MAX_EARLY_HOURS = 3.0        # no real lock comes earlier than this before a slice's first kickoff: an early lock
                             # needs every game's post-news pull, at most 85 minutes out (schedule.pregame)


def _carried_early(prev: dict, now: pd.Timestamp, lock_minutes: float) -> bool:
    """A lock the carry-over below stamped on a slice long before its lock time, as it did until Nov 6: not a real
    lock, so the slice rebuilds until its real lock time. Judged by the stamp's age against the kickoff, not by
    emptied packs: on Nov 7 the two mis-locked soccer slices had new packs again (the "locked earlier" branch
    keeps each build's packs and overs), so the first form of this check saw a real lock and kept Friday's
    tickets through their kickoffs, with no lock alert."""
    if not prev.get("locked_at") or now >= lock_time(prev, lock_minutes):
        return False
    return pd.Timestamp(prev["locked_at"]) < pd.Timestamp(prev["kickoff"]) - pd.Timedelta(hours=MAX_EARLY_HOURS)


def _resliced(prev: dict) -> bool:
    """A slice locked under older slice hours: its first kickoff is in a newer slice now (Nov 7: the NBA early
    slice locked at 4:45 for a 5:10 tip that is now the dusk slice's). Not a real lock: it rebuilds and locks again at
    its own first start's lock time, alerted once more (`resliced`)."""
    sport, kickoff = prev.get("sport"), prev.get("kickoff")
    name = str(prev.get("slate", "")).rsplit("-", 1)[-1]
    if sport not in SLICES or not kickoff or name not in {n for n, _, _ in SLICES[sport]}:
        return False
    return name != "dusk" and slice_of(kickoff, sport)[1] == "dusk"     # the one change of slice hours so far


def lock_slips(new: list[dict] | None, old: list[dict] | None, now: pd.Timestamp,
               lock_minutes: float = LOCK_MINUTES, hold_hours: float = HOLD_HOURS) -> list[dict]:
    """Each game's own slips (a slate's `sgps`) lock by their own game, never by the slice (Mike, Nov 7: "locks on a sgp
    shouldn't depend on slices at all"): they follow the rebuilds until `lock_minutes` before that game's start; the
    first build from then on is final, each slip stamped `locked_at`, and later builds keep it until `hold_hours` after
    the start. `old`: the slate's slips in the previous build."""
    stamp = now.isoformat(timespec="seconds")
    by = lambda slips: {str(x.get("event_id")): [y for y in slips or [] if str(y.get("event_id")) == str(x.get("event_id"))]
                        for x in slips or []}
    fresh, prev = by(new), by(old)
    out = []
    for eid in list(fresh) + [e for e in prev if e not in fresh]:
        start = pd.Timestamp((fresh.get(eid) or prev[eid])[0]["commence_time"])
        kept = prev.get(eid) or []
        if kept and kept[0].get("locked_at"):                         # locked earlier: final
            slips = kept if now < start + pd.Timedelta(hours=hold_hours) else []
        elif now >= start - pd.Timedelta(minutes=lock_minutes):       # its lock time: this build is final
            slips = [x | {"locked_at": stamp} for x in (fresh.get(eid) if now < start or not kept else kept) or kept]
            slips = slips if now < start + pd.Timedelta(hours=hold_hours) else []
        else:
            slips = fresh.get(eid) or []                               # a preview; gone from the build: gone
        out += slips
    return out


def keep_tickets(new: list[dict], old: list[dict], now: pd.Timestamp, sports: tuple[str, ...] = LOCK_SPORTS,
                 lock_minutes: float = LOCK_MINUTES, hold_hours: float = HOLD_HOURS, early: set[str] | None = None,
                 reopen: set[str] | None = None) -> list[dict]:
    """Every slice's SGP+ and TD tickets follow the rebuilds (the latest lines and news) until `lock_minutes`
    before its first kickoff. The first build at or after that time is final: the slate gets `locked_at`,
    and every later build keeps those tickets (even none), so nothing new appears as games start (Mike,
    Oct 10). `old` is the previous build (exports/fun.json). A slice whose games have all kicked off (gone
    from the new build) stays, without overs and builder packs, until `hold_hours` after its last kickoff.
    `early`: slices whose news is in for every game (pregame.settled_slates) lock now, before their lock time.
    `reopen`: early-locked slices one of whose games had new news since (pregame.reopened_slates): before their
    usual lock time they rebuild and lock again with the new news (`updated` counts it; the alert says so), or
    go back to a preview if the news isn't all in anymore. From the usual lock time on, a lock is final."""
    stamp = now.isoformat(timespec="seconds")
    early, reopen = early or set(), reopen or set()
    prev_by = {s["slate"]: s for s in old or [] if _sliced(s, sports)}
    out = []
    for s in new:
        prev = prev_by.pop(s["slate"], None)
        s = s | {"sgps": lock_slips(s.get("sgps"), (prev or {}).get("sgps"), now, lock_minutes, hold_hours)} \
            if _sliced(s, sports) and (s.get("sgps") or (prev or {}).get("sgps")) else s
        if prev and prev.get("locked_at") and not prev.get("resliced") and _resliced(prev):   # once (Nov 7)
            prev, s = None, s | {"resliced": True}
        elif prev and prev.get("resliced"):
            s = s | {"resliced": True}
        if not _sliced(s, sports):
            out.append(s)
        elif prev and prev.get("locked_at") and s["slate"] in reopen and now < lock_time(prev, lock_minutes):
            n = int(prev.get("updated") or 0) + 1                 # new news after an early lock: rebuild on it
            out.append(s | {"locked_at": stamp, "updated": n} if s["slate"] in early else s | {"updated": n})
        elif prev and prev.get("locked_at") and _carried_early(prev, now, lock_minutes):
            out.append(s)                                         # locked by mistake (below): a preview again
        elif prev and prev.get("locked_at"):                      # locked earlier: keep its tickets
            out.append(s | {k: prev.get(k) for k in LOCKED} | {"locked_at": prev["locked_at"], "kickoff": prev["kickoff"]})
        elif now >= lock_time(prev or s, lock_minutes) or (s["slate"] in early and now < pd.Timestamp(s["kickoff"])):
            if prev and now >= pd.Timestamp(prev["kickoff"]):     # no run since before the lock and games began:
                s = s | {k: prev.get(k) for k in LOCKED} | {"kickoff": prev["kickoff"]}   # the last full build
            out.append(s | {"locked_at": stamp})                  # this build is final
        else:
            out.append(s)                                         # a preview: rebuilt every run
    for s in prev_by.values():
        s = s | {"sgps": lock_slips(None, s.get("sgps"), now, lock_minutes, hold_hours)} if s.get("sgps") else s
        tickets = [t for k in LOCKED + ("sgps",) for t in (s.get(k) if isinstance(s.get(k), list) else [s.get(k)]) if t]
        games = [g for t in tickets for g in t.get("games") or []]
        starts = [pd.Timestamp(g["commence_time"]) for g in games]
        if not starts or max(starts) <= now - pd.Timedelta(hours=hold_hours):
            continue
        if s.get("locked_at") or min(starts) <= now:          # locked, or its games have begun: held as it is
            out.append(s | {"packs": [], "overs": [], "locked_at": s.get("locked_at") or stamp})
        else:
            # gone from one build before any of its games began (Nov 6: a league's lines passed the 24-hour age
            # limit after a lost morning pull, and tomorrow's 7:30 and 10 AM soccer slices locked, with lock
            # alerts, 18 hours early): still a preview, rebuilt once its games are back
            out.append(s)
    return sorted(out, key=lambda s: pd.Timestamp(s["kickoff"]))


def lock_due(slates: list[dict], now: pd.Timestamp, sports: tuple[str, ...] = LOCK_SPORTS,
             lock_minutes: float = LOCK_MINUTES, early: set[str] | None = None) -> list[str]:
    """The slices that reach their lock time and aren't locked yet: each pre-game tick checks (free), and
    rebuilds and publishes when one is due, so the lock and its notification come on time even when no
    odds were pulled. A slate is also due when one of its games' own slips reaches that game's lock time
    (`slips_due`, Nov 9): before, only the slice's lock started a rebuild, so a watched game later than its slice's
    first kickoff locked at the first tick with a pull, often after its start, and its watchers heard nothing."""
    early = early or set()
    return [s["slate"] for s in slates if _sliced(s, sports)
            and ((not s.get("locked_at")
                  and (lock_time(s, lock_minutes) <= now or (s["slate"] in early and now < pd.Timestamp(s["kickoff"])))
                  and now < pd.Timestamp(s["kickoff"]) + pd.Timedelta(hours=HOLD_HOURS))
                 or slips_due(s, now, lock_minutes))]


def slips_due(s: dict, now: pd.Timestamp, lock_minutes: float = LOCK_MINUTES) -> list[str]:
    """The games whose own slips on slate `s` reach their lock time (`lock_slips`: `lock_minutes` before the game) and
    aren't locked yet, before the game starts: the tick must rebuild so they lock (and alert) on time."""
    out = []
    for x in s.get("sgps") or []:
        start = pd.Timestamp(x["commence_time"])
        eid = str(x.get("event_id"))
        if not x.get("locked_at") and start - pd.Timedelta(minutes=lock_minutes) <= now < start and eid not in out:
            out.append(eid)
    return out


def own(slip: dict, game: dict, sport: str, style: str | None = None) -> dict:
    """One game's own slip as a slate carries it (Nov 7, watched games): its game, sport and start on the slip, and
    `games` in the SGP+ tickets' shape, so links, the Novig pricer, publish and the fun ledger read it as they read a
    ticket's game."""
    legs = [{k: v for k, v in l.items() if k != "_price"} for l in slip.get("legs") or []]
    g = {"event_id": str(game["event_id"]), "game_ref": game.get("game_ref"), "matchup": game["matchup"],
         "commence_time": str(game["commence_time"])}
    return slip | {"legs": legs, "sport": sport, "matchup": game["matchup"], "event_id": g["event_id"],
                   "commence_time": g["commence_time"], "style": slip.get("style") or style or "value",
                   "games": slip.get("games") or [g | {"legs": [l["label"] for l in legs]}]}


def own_slips(games: list[dict], sport: str, key: str = "minis", n: int = 3) -> list[dict]:
    """Every game's own slips on its slice (Nov 7: Mike marks the games he'll watch, and those games' slips show next to
    the slice's tickets, replacing the Knicks rule and the lone prime-time game): `key` is where a game keeps them, the
    NFL's and the NBA's full slips (`sgps`), or the small same-game parlays the other sports build their tickets from
    (`minis`, at most `n`). One-leg pieces aren't parlays and are left out."""
    out = []
    for g in games:
        for s in (g.get(key) or [])[:n if key == "minis" else None]:
            if len(s.get("legs") or []) >= 2:
                out.append(own(s, g, sport, "mini" if key == "minis" else None))
    return out


def pack_own_slips(packs: list[dict], sport: str) -> list[dict]:
    """Every game's own same-game slips from its builder pack (Nov 7, Mike: "if a game is watched that means i want
    single game slips for it"), for the sports whose builders make no full slips: college, soccer, the NHL, UFC.
    sgp.pack_slips picks them by how much the legs move together; a lines-only game (college, a UFC fight: its winner
    and total) gets its best single bet instead (sgp.best_single). A failure costs that game its slips, never the slice."""
    out = []
    for pk in packs:
        try:
            out += [own(s, pk, sport) for s in sgp.pack_slips(pk, pk, sport)]
        except Exception as e:  # noqa: BLE001
            print(f"own slips skipped for {pk.get('matchup')} ({type(e).__name__}: {e})")
    return out


def minis(legs: list, w: np.ndarray, cfg: dict, fun: dict) -> list[dict]:
    """The best small same-game parlays for one game (candidates from sgp.search)."""
    cands = sgp.search(legs, w, band=tuple(cfg["mini_band"]), min_legs=int(cfg["mini_legs"][0]),
                       max_legs=int(cfg["mini_legs"][1]), min_leg_p=float(cfg.get("min_leg_p", fun["min_leg_p"])),
                       max_leg_p=float(fun["max_leg_p"]), under_min_p=float(fun.get("under_min_p", 0.75)),
                       under_max_p=float(fun.get("under_max_p", 0.92)), max_unders=int(cfg.get("max_unders_mini", 0)),
                       one_per_player=bool(fun.get("one_leg_per_player", True)),
                       min_pair_lift=float(cfg.get("min_pair_lift", 1.10)))
    return sgp.pick(cands, k=int(cfg["minis_per_game"]), max_overlap=1)


def rooting_overs(legs: list, cfg: dict) -> list[dict]:
    """Straight overs and anytime TDs worth cheering for, best value first (one per player)."""
    lo, hi = cfg["over_p"]
    pool = [l for l in legs if l.side in ("over", "yes") and l.stat not in sgp.GAME_STATS and lo <= l.p <= hi
            and sgp.plausible(l)]
    pool.sort(key=lambda l: -l.read_value)
    out, seen = [], set()
    for l in pool:
        if l.player in seen:
            continue
        seen.add(l.player)
        ev = l.p * om.american_to_decimal(l.price) - 1
        ev_read = None if l.p_read is None else l.p_read * om.american_to_decimal(l.price) - 1
        out.append(sgp.leg_doc(l) | {"ev": round(ev, 4), "ev_read": None if ev_read is None else round(ev_read, 4)})
        if len(out) == int(cfg["overs_per_game"]):
            break
    return out


def td_candidates(legs: list, cfg: dict) -> list[dict]:
    """A game's anytime scorers for the window's TD ticket, likeliest first by Pinnacle's no-vig chance, at least
    td_min_p likely (Mike, Oct 25: "switch the TD tickets to the likeliest scorers"). Until then they were ranked by
    value with our TD read; the read never beat Pinnacle on 581 graded reads (models/td_nfl.py, MODEL_CHANGELOG)."""
    pool = [l for l in legs if l.stat == "tds" and l.p >= float(cfg.get("td_min_p", 0.20)) and sgp.plausible(l)]
    pool.sort(key=lambda l: -l.p)
    return [sgp.leg_doc(l) | {"read_value": round(l.read_value, 4), "value": round(l.value, 4)}
            for l in pool[: int(cfg.get("td_per_game", 3))]]


def td_chalk(legs: list, cfg: dict) -> dict | None:
    """The game's likeliest scorer at a fair price (chance x value): the comparison for the
    read's pick, since FanDuel's TD margin is smallest on favorites."""
    pool = [l for l in legs if l.stat == "tds" and l.p >= float(cfg.get("td_min_p", 0.20)) and sgp.plausible(l)]
    return sgp.leg_doc(max(pool, key=lambda l: l.p * l.value)) if pool else None


def td_ticket(games: list[dict], slate_id: str, label: str) -> dict | None:
    """One anytime scorer per game (the first candidate of each), fair and FanDuel payout as
    plain products: the games are independent and FanDuel pays a cross-game parlay at the
    product of its legs."""
    picks = [(g, g["tds"][0]) for g in games if g.get("tds")]
    if len(picks) < 2:
        return None
    p = float(np.prod([l["p_fair"] for _, l in picks]))
    p_read = float(np.prod([l["p_read"] if l.get("p_read") is not None else l["p_fair"] for _, l in picks]))
    dec = float(np.prod([om.american_to_decimal(l["price"]) for _, l in picks]))
    key = "|".join(sorted(l["label"] for _, l in picks))
    chalk = [g["td_chalk"] for g, _ in picks if g.get("td_chalk")]
    ch = None
    if len(chalk) == len(picks):
        cp = float(np.prod([l["p_fair"] for l in chalk]))
        cd = float(np.prod([om.american_to_decimal(l["price"]) for l in chalk]))
        ch = {"price": sgp._american(1 / cd), "fair_price": sgp._american(cp), "ev": round(cp * cd - 1, 4),
              "players": [l["player"] for l in chalk]}
    return {"sgp_id": "td-" + hashlib.sha1((slate_id + "|" + key).encode()).hexdigest()[:10], "kind": "td",
            "slate": slate_id, "matchup": f"TD ticket {label}: " + ", ".join(g["matchup"] for g, _ in picks),
            "games": [{"event_id": g["event_id"], "game_ref": g.get("game_ref"), "matchup": g["matchup"],
                       "commence_time": g["commence_time"], "legs": [l]} for g, l in picks],
            "legs": [l for _, l in picks], "n_games": len(picks), "n_legs": len(picks),
            "p_fair": round(p, 7), "fair_price": sgp._american(p), "price": sgp._american(1 / dec),
            "p_read": round(p_read, 7), "read_price": sgp._american(p_read), "ev_read": round(p_read * dec - 1, 4),
            "fits_read": sum(bool(l.get("read")) for _, l in picks), "chalk": ch,
            "naive_price": sgp._american(1 / dec), "ev": round(p * dec - 1, 4),
            "why": (f"The likeliest anytime scorer in each of {len(picks)} games by Pinnacle's no-vig chance (since "
                    f"Oct 25; our TD read is tracked but carries no weight: it never beat Pinnacle). The games don't "
                    f"affect each other, so the chance is the product: 1 in {1 / p:,.0f} ({sgp._american(p):+,d}). "
                    f"FanDuel pays a parlay across games at the product of its legs, {sgp._american(1 / dec):+,d}: "
                    f"EV {p * dec - 1:+.0%} by Pinnacle, before any boost.")}


def _ticket(chosen: list[tuple[dict, dict]], slate_id: str, label: str) -> dict:
    """chosen: [(game, mini doc)]: the SGP+ ticket as the page shows it."""
    p = float(np.prod([m["p_fair"] for _, m in chosen]))
    reads = [m["p_read"] if m.get("p_read") is not None else m["p_fair"] for _, m in chosen]
    p_read = float(np.prod(reads))
    legs = [l for _, m in chosen for l in m["legs"]]
    naive = float(np.prod([om.american_to_decimal(l["price"]) for l in legs]))
    key = "|".join(sorted(l["label"] for l in legs))
    games = [{"event_id": g["event_id"], "game_ref": g.get("game_ref"), "matchup": g["matchup"], "commence_time": g["commence_time"],
              "sgp_id": m["sgp_id"], "theme": m["theme"], "p_fair": m["p_fair"], "fair_price": m["fair_price"],
              "legs": m["legs"]} for g, m in chosen]
    return {"sgp_id": "plus-" + hashlib.sha1((slate_id + "|" + key).encode()).hexdigest()[:10],
            "kind": "sgp_plus", "slate": slate_id, "matchup": f"SGP+ {label}: " + ", ".join(g["matchup"] for g in games),
            "games": games, "n_games": len(games), "n_legs": len(legs), "legs": legs,
            "p_fair": round(p, 5), "fair_price": sgp._american(p),
            "p_read": round(p_read, 5) if abs(p_read - p) > 1e-6 else None,
            "read_price": sgp._american(p_read) if abs(p_read - p) > 1e-6 else None,
            "naive_price": sgp._american(1 / naive),
            "fits_read": sum(bool(l.get("read")) for l in legs),
            "why": (f"{len(games)} games, {len(legs)} legs. Each game's mini-parlay is priced from our simulation "
                    f"of that game (legs anchored to the market); games don't affect each other, so the ticket's "
                    f"chance is their product: {p:.1%}, fair {sgp._american(p):+d}. The legs alone multiply to "
                    f"{sgp._american(1 / naive):+d} at FanDuel's prices; FanDuel's SGP+ price replaces each game's "
                    f"product with its own same-game price, so type what it quotes to see the real EV.")}


def ticket(games: list[dict], slate_id: str, label: str, cfg: dict) -> dict | None:
    """The best ticket for a slate: the most games (up to max_games) whose minis land in the band."""
    lo_p, hi_p = 1 / (1 + cfg["band"][1] / 100), 1 / (1 + cfg["band"][0] / 100)
    from betlab import bans                      # the ban list (Oct 25): no mini with a banned player or team

    if bans.ACTIVE:
        games = [g | {"minis": [m for m in g.get("minis") or [] if not bans.any_leg(bans.ACTIVE, m.get("legs"))]}
                 for g in games]
    playable = [g for g in games if g.get("minis")]
    for size in range(min(int(cfg["max_games"]), len(playable)), int(cfg["min_games"]) - 1, -1):
        best, best_score = None, -1.0
        for combo in itertools.combinations(playable, size):
            for picks in itertools.product(*[g["minis"] for g in combo]):
                if sum(m["n_legs"] for m in picks) > int(cfg["max_legs"]):
                    continue
                p = float(np.prod([m["p_fair"] for m in picks]))
                if not lo_p <= p <= hi_p:
                    continue
                score = float(np.prod([m.get("read_value", m["leg_value"]) for m in picks]))
                if score > best_score:
                    best, best_score = list(zip(combo, picks)), score
        if best:
            return _ticket(best, slate_id, label)
    return None


def build(game_docs: list[dict], asof: pd.Timestamp, cfg: dict) -> list[dict]:
    """The Fun tab's slates: per kickoff window, an SGP+ ticket (2+ games) and the overs to
    root for. game_docs: fun_nfl.build_game outputs carrying "minis" and "overs"."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for g in game_docs:
        if pd.Timestamp(g["commence_time"]) <= asof:
            continue
        groups.setdefault(slice_of(g["commence_time"], "nfl"), []).append(g)
    out = []
    for key in sorted(groups, key=lambda k: min(pd.Timestamp(g["commence_time"]) for g in groups[k])):
        games = sorted(groups[key], key=lambda g: g["commence_time"])
        names = slice_names("nfl", *key, len(games))
        sid = names["slate"]
        overs = [o | {"kind": "over", "matchup": g["matchup"], "event_id": g["event_id"], "commence_time": g["commence_time"],
                      "sgp_id": "over-" + hashlib.sha1((g["event_id"] + "|" + o["label"]).encode()).hexdigest()[:10]}
                 for g in games for o in g.get("overs", [])]
        overs.sort(key=lambda o: -((o["p_read"] if o.get("p_read") is not None else o["p_fair"])
                                   * om.american_to_decimal(o["price"])))
        out.append({**names, "sport": "nfl", "kickoff": games[0]["commence_time"], "n_games": len(games),
                    "plus": ticket(games, sid, names["label"], cfg) if len(games) >= int(cfg["min_games"]) else None,
                    "td": td_ticket(games, sid, names["label"]),
                    "sgps": own_slips(games, "nfl", "sgps"),    # shown for the games an account watches (Nov 7)
                    "overs": overs[: int(cfg["overs_per_slate"])]})
    return out
