"""The fun bucket's ledger: data/ledger/fun.csv. Every parlay Mike priced at the book (the
FanDuel/DraftKings price he typed on the Fun tab, saved as `fun_quotes`) or marked as his
(`fun_taken`), graded leg by leg once the game's stats are out.

- **Where the rows come from:** the page-sync routine saves both collections to branch
  `claude/page-sync` (data/ledger/fun_quotes.json, fun_taken.json) and the daily run
  imports them (`betlab import-fun`). Kept apart from the pick ledger: fun money is never
  part of the real record.
- **Legs are graded from their labels** ("X over 4.5 receptions", "X 40+ receiving yds",
  "X anytime TD", and game lines "Buffalo Bills ML", "Buffalo Bills -3.5", "Over 47.5 total
  points" from the final score), so custom slips grade too, and a slip that a later build
  replaced still grades. Anytime TD counts rushing and receiving TDs. A pushed line leg is
  treated like a void (the book reprices the slip: check the app).
- **Settlement:** a leg on a player who didn't play is void. Any losing leg loses the
  slip. A void (or pushed) leg comes off the slip, as FanDuel settles it (Oct 10): the rest
  stands, at the price with that leg taken out at its fair chance (`leg_p`, saved at sync; the
  leg's entry in `leg_results` carries its `p`, so My bets reduces your own price the same way).
  FanDuel reprices same-game legs itself, so the reduced price is close, not exact. Every leg
  void: the slip is void. A void leg without a known fair chance voids an unmarked slip; a marked one (a screenshot's
  slip has no `leg_p`) waits with a "not graded" warning until what the book paid is entered as its cash-out (Nov 9).
- **Novig cash bets** synced from Mike's account (`novig-...`) settle as Novig did (`novig_settled`), never graded here.
- **Profit:** 1 unit at the quoted price for every slip (what the slip would have paid,
  for learning), and the real stake for slips Mike marked.
- **Across games:** an SGP+ ticket (sgp_plus.py) carries its games; each leg is graded
  from its own game (`leg_games`), and the ticket waits until every game's stats are out.
  A straight over to root for is a one-leg slip.
- **College** (`sport` "ncaaf": lines-only tickets, cards/fun_ncaaf.py): legs settle from
  CollegeFootballData's final scores (`cfbd.games`), team names via `cfbd.team_names`.
- **Soccer** (`sport` "soccer": the daily ticket, cards/fun_soccer.py): legs ("Arsenal to
  win", "Over 2.5 goals", "Both teams to score") settle from football-data.co.uk's final
  score, found from each leg's game_ref "league|home|away|kickoff".
- **Across sports** (`sport` "mixed", Oct 22: Mike's own parlays): each leg's sport comes from its game ref
  (`leg_sport`; college and NHL refs carry a prefix, "ncaaf:401871056"), each sport's legs go through that sport's
  grader, and the slip settles from all of them (`_grade_mixed`).
- **Novig** (Oct 28, `book` "novig"): a void leg counts at its fair value instead of coming off (docs.novig.com, RFQ >
  Settlement): the pot times the legs' values, so a slip can pay back less than its stake, and all legs void still
  pays that share. A lost leg loses it all.
- **Bet Protect+** (Oct 26, `protect`): FanDuel's 3% fee comes off a marked slip's profit unless it's void, and a
  protected slip's did-not-play leg counts as won ("INJURY COVERED, WON ON FANDUEL").
- **Games without a ref** (Oct 26): a slip's game that came with only its matchup gets its ref at sync (`_find_ref`:
  NBA from ESPN's schedule, college from CFBD, a soccer ref's kickoff from our soccer lines); an NFL leg with no game
  is found in that week's player stats (`_find_games`). "X first TD scorer" grades from the play-by-play's first TD.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

PATH = config.DATA_DIR / "ledger" / "fun.csv"
DK = "~dk"          # a slip's DraftKings version (Oct 12): the same sgp_id + "~dk", its own price, legs and book
NV = "~nv"          # a Build-tab slip at Novig (Oct 28): its exact price from Novig's pricer
COLUMNS = ["sgp_id", "source", "book", "sport", "matchup", "event_id", "game_id", "legs", "leg_games", "n_legs", "fair_price", "p_fair",
           "naive_price", "price", "quoted_at", "marked", "mode", "stake", "status", "leg_results", "profit_1u",
           "profit", "graded_at", "grade", "grade_parts", "leg_p", "bonus", "cashout", "boost", "protect", "boost_cap"]
TEXT = ["sgp_id", "source", "book", "sport", "matchup", "event_id", "game_id", "legs", "leg_games", "quoted_at", "mode", "status",
        "leg_results", "graded_at", "grade", "grade_parts", "leg_p"]


def _leg_p(leg) -> float | None:
    """A leg doc's fair chance (p_fair, else its fair price); None for a bare label."""
    if not isinstance(leg, dict):
        return None
    if leg.get("p_fair") is not None:
        return float(leg["p_fair"])
    fp = leg.get("fair_price")
    if fp is None:
        return None
    from betlab import odds_math as om
    return 1 / om.american_to_decimal(float(fp))
STAT_OF_LABEL = {"receptions": "receptions", "receiving yds": "receiving_yards", "rushing yds": "rushing_yards",
                 "passing yds": "passing_yards", "rush + rec yds": "rush_rec_yards"}   # rush + rec: the sum (Oct 25)
LEG = re.compile(r"^(?P<player>.+?) (?:(?P<side>over|under) (?P<point>\d+(?:\.\d+)?)|(?P<alt>\d+)\+) "
                 r"(?P<stat>receptions|receiving yds|rushing yds|passing yds|rush \+ rec yds)$", re.I)   # "Over 229.5" as slips write it (Oct 25)
ML = re.compile(r"^(?P<team>.+) (?:ML|to win)$")
SPREAD = re.compile(r"^(?P<team>.+) (?P<point>[+-]\d+(?:\.\d+)?)$")
TOTAL = re.compile(r"^(?P<side>Over|Under) (?P<point>\d+(?:\.\d+)?)(?: total points| total| points)?$")
GAME_STATS = ("moneyline", "spread", "total")


def parse_leg(label: str) -> dict | None:
    """{player, stat, side, point} from a leg label ({team, stat, side, point} for a game
    line: "Buffalo Bills ML", "Buffalo Bills -3.5", "Over 47.5 total points"), or None."""
    label = label.strip()
    if m := TOTAL.match(label):
        return {"team": None, "stat": "total", "side": m["side"].lower(), "point": float(m["point"])}
    if m := ML.match(label):
        return {"team": m["team"], "stat": "moneyline", "side": "yes", "point": 0.0}
    if m := SPREAD.match(label):
        return {"team": m["team"], "stat": "spread", "side": "yes", "point": float(m["point"])}
    if label.endswith(" anytime TD"):
        return {"player": label[: -len(" anytime TD")], "stat": "tds", "side": "over", "point": 0.5}
    if m := re.fullmatch(r"(.+) first TD scorer", label, re.I):     # Oct 22: Mike's Drake Maye leg at Novig
        return {"player": m[1], "stat": "first_td", "side": "over", "point": 0.5}
    from betlab.live_legs import canon_stat
    m = LEG.match(canon_stat(label))      # "rushing + receiving yds", "rushing yards": the trackers' wording
    if not m:
        return None
    point = float(m["point"]) if m["point"] else float(m["alt"]) - 0.5
    return {"player": m["player"], "stat": STAT_OF_LABEL[m["stat"].lower()], "side": (m["side"] or "over").lower(),
            "point": point}


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)  # older files lack new columns
    df["marked"] = df["marked"].fillna(False).astype(bool)
    df["bonus"] = df["bonus"].fillna(False).astype(str).str.lower().isin(["true", "1"])
    return df


PROTECT_FEE = 0.03     # FanDuel Bet Protect+: 3% of the stake on top, in cash even on a bonus bet (Oct 26)


def marked_profit(p1: float | None, r, status: str | None = None) -> float | None:
    """A marked slip's profit in units: profit_1u x stake, except a bonus bet (Oct 19: the book's credit), whose
    loss costs nothing (a win already pays only the profit), and a cashed-out slip (Oct 22), settled at what the book
    paid back (`cashout`, in units) whatever its legs do; less Bet Protect+'s fee (`protect`, Oct 26) unless the slip
    is void. None when unmarked, unstaked or unsettled."""
    stake = float(r["stake"]) if bool(r["marked"]) and pd.notna(r["stake"]) else None
    fee = PROTECT_FEE * stake if stake is not None and _true(r.get("protect")) and status != "void" else 0.0
    cash = pd.to_numeric(pd.Series([r.get("cashout")]), errors="coerce").iloc[0]
    if stake is not None and pd.notna(cash):
        return round(float(cash) - (0.0 if bool(r.get("bonus")) else stake) - fee, 2)
    if stake is None or p1 is None:
        return None
    won = (max(p1, 0.0) if bool(r.get("bonus")) else p1) * stake
    boost = pd.to_numeric(pd.Series([r.get("boost")]), errors="coerce").iloc[0]
    if won > 0 and pd.notna(boost) and boost > 0:      # a profit boost (Oct 22): the price is the book's own
        extra = won * float(boost) / 100
        cap = pd.to_numeric(pd.Series([r.get("boost_cap")]), errors="coerce").iloc[0]
        won += min(extra, float(cap)) if pd.notna(cap) and cap >= 0 else extra   # its max extra winnings (Oct 30)
    return round(won - fee, 2)


def _repriced(p1: float | None, old_price, new_price, status: str, novig: bool = False) -> float | None:
    """A graded win's profit per unit at an edited price. Grading paid max(decimal x factor, 1) - 1 (Novig: decimal x
    factor - 1), the factor being the dropped legs' fair chances (1 with none), so the factor is read back from the old
    price and applied to the new one. Anything else (a loss, a push, the same price, no price) keeps its profit."""
    from betlab import odds_math as om

    old, new = (pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0] for x in (old_price, new_price))
    if p1 is None or status != "won" or pd.isna(old) or pd.isna(new) or float(old) == float(new):
        return p1
    factor = (p1 + 1) / om.american_to_decimal(float(old))
    dec = om.american_to_decimal(float(new)) * factor
    return dec - 1 if novig else max(dec, 1.0) - 1


def _true(v) -> bool:
    """A flag from the CSV ("True", True, 1) or a row; NaN and blanks are False."""
    return v is True or str(v).strip().lower() in ("true", "1")


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def _game_id(matchup: str, when: str, games: pd.DataFrame, abbr: dict) -> str | None:
    """nflverse game id for "Away @ Home" on or after the quote date (within a week)."""
    away, _, home = (matchup or "").partition(" @ ")
    h, a = abbr.get(home.strip()), abbr.get(away.strip())
    if not h or not a:
        return None
    day = pd.Timestamp(when).tz_convert("America/New_York").tz_localize(None).normalize() if when else None
    g = games[(games["home_team"] == h) & (games["away_team"] == a)]
    if day is not None:
        g = g[(g["date"] >= day) & (g["date"] <= day + pd.Timedelta(days=7))]
    return g["game_id"].iloc[0] if len(g) else None


NFL_GAME_ID = re.compile(r"^\d{4}_\d{2}_[A-Z]+_[A-Z]+$")
PREFIXED = ("ncaaf", "ncaab", "nhl", "ufc")   # game refs "ncaaf:401871056" (the app's game ids), "nhl:2026020123",
                                              # "ufc:<ESPN event>:<fight>" (Oct 23)


def leg_sport(ref) -> str | None:
    """One leg's sport from its game ref: "nba|HOME|AWAY|tip", "<soccer league>|home|away|kickoff", "ncaaf:<id>" /
    "ncaab:<id>" / "nhl:<id>", or an nflverse game id ("2026_07_KC_LV"); None when the ref doesn't say."""
    from betlab.cards.soccer import LEAGUES as SOCCER

    s = str(ref or "")
    if "|" in s:
        head = s.split("|")[0]
        return "nba" if head == "nba" else "soccer" if head in SOCCER else None
    head, sep, _ = s.partition(":")
    if sep and head in PREFIXED:
        return head
    return "nfl" if NFL_GAME_ID.match(s) else None


def _bare(gid) -> str:
    """A game id without its sport prefix ("ncaaf:401871056" -> "401871056"), as the score files key it."""
    head, sep, rest = str(gid).partition(":")
    return rest if sep and head in PREFIXED else str(gid)


def sport_of_refs(refs) -> str | None:
    """A slip's sport from its legs' game refs (leg_sport), for a bet with no sport of its own: the app's bets rows
    have none, so Mike's own soccer and NBA parlays (Oct 20) were read as NFL and could never grade. "mixed" when the
    legs span sports (Oct 22: a Europa League + college football parlay; each leg grades by its own sport,
    _grade_mixed). None for NFL-only refs or no refs (the NFL default)."""
    sports = {leg_sport(r) for r in refs if r}
    if len(sports) > 1:
        return "mixed"
    sport = next(iter(sports), None)
    return None if sport == "nfl" else sport


ODDS_ID = re.compile(r"^(?:ncaaf|ncaab|nhl):[0-9a-f]{32}$")


def unusable_ref(ref) -> bool:
    """A college or NHL ref built from the Odds API's 32-hex event id (the app's games.game_id for a game the paid pull
    added): the graders key those sports by CFBD's, CBBD's and the NHL's numeric ids, so it never grades (Nov 9: a
    Georgia + Miami slip, open two days after both finals). Read as no ref, and found again from the matchup."""
    return bool(ODDS_ID.match(str(ref or "")))


def game_sport(g: dict, sport: str | None = None) -> str | None:
    """One game's sport on a slip: its ref's (leg_sport), else the sport the slip reader saved with it (Nov 9: a game
    with no usable ref), else the slip's own."""
    return leg_sport(g.get("game_ref")) or (str(g["sport"]).lower() if g.get("sport") else None) or sport


def _find_ref(sport: str, matchup, ref, when, found: dict):
    """The game ref for a slip's game that came without a full one, from its matchup ("Away @ Home") and the slip's
    date (Oct 22-24: slips entered by hand carried only matchups, and soccer refs without a kickoff, so none graded):
    NBA from ESPN's schedule, college football from CFBD, college basketball from CBBD, the NHL from its own scores
    (Nov 9), a soccer ref's kickoff from our soccer lines. A ref on the Odds API's id (unusable_ref) counts as none.
    The ref as it was when nothing fits."""
    if unusable_ref(ref):
        ref = None
    away, _, home = str(matchup or "").partition(" @ ")
    if not when or (not home and not ref):
        return ref
    t = pd.Timestamp(when)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    lo, hi = t - pd.Timedelta(hours=12), t + pd.Timedelta(days=7)

    def load(key, fn):
        if key not in found:
            try:
                found[key] = fn()
            except Exception as exc:  # noqa: BLE001 - a source down: the slip stays open, try next sync
                print(f"fun sync: {key} unavailable ({type(exc).__name__}: {exc})")
                found[key] = None
        return found[key]

    if sport == "soccer" and ref and len(str(ref).split("|")) == 3:
        from betlab import tracking_soccer
        lines = load("soccer", lambda: pd.read_csv(tracking_soccer.PATH, usecols=["league", "home", "away", "commence_time"]))
        if lines is None:
            return ref
        league, h, a = str(ref).split("|")
        kick = pd.to_datetime(lines["commence_time"], utc=True, format="ISO8601")
        m = lines[(lines["league"] == league) & (lines["home"] == h) & (lines["away"] == a) & kick.between(lo, hi)]
        return f"{ref}|{kick[m.index].min().isoformat()}" if len(m) else ref
    if ref or not home:
        return ref
    if sport == "nba":
        from betlab.sources import nba
        sch = load("nba", lambda: nba.load_schedules([nba.current_season(t.tz_convert("America/New_York"))]))
        if sch is None:
            return None
        start = pd.to_datetime(sch["start_date"], utc=True, format="ISO8601")
        m = sch[(sch["home_display_name"] == home.strip()) & (sch["away_display_name"] == away.strip()) & start.between(lo, hi)]
        return f"nba|{m['home_abbreviation'].iloc[0]}|{m['away_abbreviation'].iloc[0]}|{m['start_date'].iloc[0]}" if len(m) else None
    if sport == "ncaaf":
        from betlab.sources import cfbd
        got = load("ncaaf", lambda: (cfbd.games(), cfbd.team_names()))
        if got is None:
            return None
        g, names = got
        h, a = names.get(home.strip()), names.get(away.strip())
        kick = pd.to_datetime(g["kickoff"], utc=True)
        m = g[(g["home_team"] == h) & (g["away_team"] == a) & kick.between(lo - pd.Timedelta(days=1), hi)]
        return f"ncaaf:{m['game_id'].iloc[0]}" if len(m) else None
    if sport == "ncaab":            # finished games only: the slip finds its ref once its game is final
        from betlab.sources import cbbd
        got = load("ncaab", lambda: (cbbd.games(), {}))
        if got is None:
            return None
        g, names = got
        if home.strip() not in names or away.strip() not in names:    # each slip's own feed names, matched once
            names.update(cbbd.team_names(feed_names=[home.strip(), away.strip()]))
        h, a = names.get(home.strip()), names.get(away.strip())
        kick = pd.to_datetime(g["start"], utc=True)
        m = g[(g["home_team"] == h) & (g["away_team"] == a) & kick.between(lo - pd.Timedelta(days=1), hi)]
        return f"ncaab:{m['game_id'].iloc[0]}" if h and a and len(m) else None
    if sport == "nhl":              # the NHL's scores (finished games), matched on codes or full names
        from betlab.sources import nhl
        tg = load("nhl", lambda: nhl.load_team_games([nhl.current_season()]))
        if tg is None:
            return None
        day = t.tz_convert("America/New_York").tz_localize(None).normalize()
        hg = tg[(tg["home"] == 1) & pd.to_datetime(tg["date"]).between(day - pd.Timedelta(days=1), day + pd.Timedelta(days=7))]
        m = hg[[_nhl_team(home.strip(), x) and _nhl_team(away.strip(), y) for x, y in zip(hg["team"], hg["opp"])]]
        return f"nhl:{m.sort_values('date')['game_id'].iloc[0]}" if len(m) else None
    return ref


def _nhl_team(name: str, code: str) -> bool:
    """An NHL side named either way: its code ("NYR") or its full name ("New York Rangers")."""
    from betlab.novig_sync import _full

    return name.upper() == str(code).upper() or name.lower() == _full(str(code), "nhl").lower()


NOVIG_SYNCED = "novig-"     # Mike's own Novig cash bets, synced from his account (novig_sync.py): Novig settles them


def novig_settled(q: dict, r: dict) -> dict:
    """A synced Novig bet's result as Novig settled it (novig_sync writes custom_parlays.status). Nov 9: these rows came
    with no game the fun ledger can grade and sat open in fun.csv for good while the app showed them settled; Novig's
    own settlement is the truth for them, so the ledger takes it and never grades them itself."""
    from betlab import odds_math as om

    status = q["status"]
    price = pd.to_numeric(pd.Series([r.get("price")]), errors="coerce").iloc[0]
    p1 = q.get("profit_1u")
    if p1 is None or pd.isna(p1):
        p1 = (-1.0 if status == "lost" else 0.0 if status == "void"
              else om.american_to_decimal(float(price)) - 1 if pd.notna(price) else None)
    p1 = None if p1 is None else round(float(p1), 4)
    graded = q.get("graded_at")
    return {"status": status, "profit_1u": p1, "profit": marked_profit(p1, r, status),
            "graded_at": graded.isoformat() if hasattr(graded, "isoformat") else graded or
            datetime.now(timezone.utc).isoformat(timespec="seconds")}


def sync(quotes: list[dict], taken: list[dict]) -> int:
    """Add or refresh a row for every quoted or marked slip; graded rows keep their results.
    Returns the number of slips in the ledger."""
    from betlab.sources import nflverse

    games, abbr = nflverse.load_games(), nflverse.team_abbr_by_name()
    df = load().set_index("sgp_id", drop=False)
    found: dict = {}            # _find_ref's loaded schedules, once per sync
    by_id: dict[str, dict] = {}
    for q in quotes:
        if q.get("sgp_id"):
            by_id[q["sgp_id"]] = {"source": "custom" if str(q["sgp_id"]).startswith("custom") else "fun tab", **q}
    for t in taken:
        if t.get("sgp_id"):
            row = by_id.setdefault(t["sgp_id"], {"source": "fun tab", **t})
            row.update(marked=True, mode=t.get("mode"), stake=t.get("stake"), bonus=bool(t.get("bonus")), cashout=t.get("cashout"), boost=t.get("boost"),
                       boost_cap=t.get("boost_cap"), protect=bool(t.get("protect")),
                       price=t.get("price") if t.get("price") is not None else row.get("price"))
    for sid, q in by_id.items():
        when = q.get("quoted_at") or q.get("placed_at")
        games_of = q.get("games") or []            # an SGP+ ticket: legs from several games
        leg_docs = [l for g in games_of for l in g.get("legs") or []] if games_of else list(q.get("legs") or [])
        leg_p = [_leg_p(l) for l in leg_docs]
        if games_of:
            q = q | {"legs": [l if isinstance(l, str) else l["label"] for g in games_of for l in g.get("legs") or []]}
        book = "draftkings" if str(sid).endswith(DK) else "novig" if str(sid).endswith(NV) else str(q.get("book") or "fanduel").lower()
        sports = {game_sport(g) for g in games_of} - {None}       # a game's saved sport counts when its ref is gone
        sport = q.get("sport") or ("mixed" if len(sports) > 1 else next(iter(sports - {"nfl"}), None)) or "nfl"
        new = {"sgp_id": sid, "source": q.get("source"), "book": book, "sport": sport,
               "matchup": q.get("matchup"),
               "event_id": q.get("event_id"), "legs": json.dumps(q.get("legs") or []), "n_legs": len(q.get("legs") or []),
               "fair_price": q.get("fair_price"), "p_fair": q.get("p_fair"), "naive_price": q.get("naive_price"),
               "price": q.get("price"), "quoted_at": q.get("quoted_at") or q.get("placed_at"),
               "marked": bool(q.get("marked", False)), "mode": q.get("mode"), "stake": q.get("stake"),
               "bonus": bool(q.get("bonus", False)), "cashout": q.get("cashout"), "boost": q.get("boost"),
               "boost_cap": q.get("boost_cap"), "protect": bool(q.get("protect", False)),
               "leg_p": json.dumps(leg_p) if any(p is not None for p in leg_p) else None,
               "grade": q.get("grade"),     # the page's builder grade for Mike's own parlays
               "grade_parts": json.dumps(q["grade_parts"]) if q.get("grade_parts") else None}
        if games_of:
            graded = sid in df.index and df.loc[sid, "status"] in ("won", "lost", "void")
            refs = [g.get("game_ref") or _game_id(g.get("matchup"), when, games, abbr) if sport == "nfl"
                    else g.get("game_ref") if graded
                    else _find_ref(game_sport(g, sport), g.get("matchup"), g.get("game_ref"), when, found)
                    for g in games_of]
            per_leg = [ref for g, ref in zip(games_of, refs) for _ in g.get("legs") or []]
            new["leg_games"] = json.dumps(per_leg)
            new["game_id"] = next((x for x in per_leg if x), None)
        else:
            new["game_id"] = _game_id(new["matchup"], new["quoted_at"], games, abbr)
        if sid in df.index:
            old = df.loc[sid]
            if old["status"] in ("won", "lost", "void"):
                new.update({k: old[k] for k in ("status", "leg_results", "profit_1u", "profit", "graded_at")})
                # the stake, bonus, boost or cash-out can change after grading (Edit in My bets): profit follows them
                p1 = pd.to_numeric(pd.Series([old["profit_1u"]]), errors="coerce").iloc[0]
                p1 = None if pd.isna(p1) else float(p1)
                # and so does the price (Nov 9: Edit works on settled bets, to fix a misread price): a win's profit
                # per unit is worked out again at the new price, with the same share for any leg that was dropped
                p1 = _repriced(p1, old.get("price"), new.get("price"), old["status"], book == "novig")
                new["profit_1u"] = round(p1, 4) if p1 is not None else None
                new["profit"] = marked_profit(p1, new, old["status"])
            else:
                new["status"] = "open"
            df = df.drop(index=sid)
        else:
            new["status"] = "open"
        if new["status"] == "open" and str(sid).startswith(NOVIG_SYNCED) and q.get("status") in ("won", "lost", "void"):
            new |= novig_settled(q, new)
        df = pd.concat([df, pd.DataFrame([new]).set_index("sgp_id", drop=False)])
    for c in COLUMNS:
        if c not in df:
            df[c] = np.nan
    save(df.reset_index(drop=True).sort_values(["quoted_at", "sgp_id"]))
    return len(df)


def _settle_line(leg: dict, game, abbr: dict) -> tuple[str, float | None]:
    """(result, value) of a game-line leg from the final score; ("open", None) before it's final."""
    if game is None or pd.isna(game.get("home_pts")) or pd.isna(game.get("away_pts")):
        return "open", None
    home, away = float(game["home_pts"]), float(game["away_pts"])
    if leg["stat"] == "total":
        value = home + away
        return _settle_leg(leg, value), value
    team = abbr.get(leg["team"])
    if team not in (game["home_team"], game["away_team"]):
        return "unknown", None
    value = home - away if team == game["home_team"] else away - home      # the team's margin
    return _settle_leg({"side": "over", "point": -leg["point"]}, value), value


def _settle_over_under(v: float, leg: dict) -> str:
    """A player's count against a tracker-read prop leg (`live_legs.parse_leg`): a whole-number line can push."""
    point = float(leg["point"])
    return "push" if v == point else "won" if (v > point) == (leg["side"] == "over") else "lost"


def _settle_leg(leg: dict, value: float | None) -> str:
    if value is None:
        return "void"
    diff = (value - leg["point"]) if leg["side"] == "over" else (leg["point"] - value)
    return "won" if diff > 0 else "lost" if diff < 0 else "push"


ESPN_STAT = {"passing_yards": "passingYards", "rushing_yards": "rushingYards", "receiving_yards": "receivingYards",
             "receptions": "receptions", "rushing_tds": "rushingTouchdowns", "receiving_tds": "receivingTouchdowns",
             "def_tds": ("defensiveTouchdowns", "interceptionTouchdowns"),
             "special_teams_tds": ("kickReturnTouchdowns", "puntReturnTouchdowns")}


def espn_nfl_box(gid: str, finals: pd.DataFrame, get=None) -> tuple[pd.DataFrame, pd.DataFrame, float, float] | None:
    """A finished game's stats from ESPN's box score, shaped like nflverse's player stats and snap counts, plus the
    final score (home, away); None unless ESPN has it final. nflverse posts a night game's stats the next morning
    (Oct 27: Monday night was still missing at the 3 AM grade), ESPN at the final whistle. Its players are named,
    not id'd ("espn:<name>"), and anyone in the box counts as played; one who isn't stays open for nflverse."""
    from betlab import live_legs as L

    get = get or L.espn
    espn_id = finals.loc[gid].get("espn") if gid in finals.index else None
    if espn_id is None or pd.isna(espn_id):
        return None
    s = get(f"{L.BASE}/football/nfl/summary?event={int(float(espn_id))}", L.DONE_TTL)
    comp = (((s or {}).get("header") or {}).get("competitions") or [{}])[0]
    if ((comp.get("status") or {}).get("type") or {}).get("state") != "post":
        return None
    score = {c.get("homeAway"): L._num(c.get("score")) for c in comp.get("competitors") or []}
    box = L.parse_box(s, "nfl")
    if not box or score.get("home") is None or score.get("away") is None:
        return None
    rows = [{"game_id": gid, "player_id": f"espn:{name}", "player_display_name": name}
            | {col: sum(st.get(k, 0.0) for k in (keys if isinstance(keys, tuple) else (keys,))) for col, keys in ESPN_STAT.items()}
            for name, st in box.items() if name != L.GAME]
    ps = pd.DataFrame(rows)
    sn = ps[["game_id", "player_id"]].assign(player=ps["player_display_name"], offense_snaps=1)
    return ps, sn, score["home"], score["away"]


def with_espn(gids, ps: pd.DataFrame, sn: pd.DataFrame, finals: pd.DataFrame, get=None):
    """nflverse's frames with ESPN's box scores added for the finished games nflverse hasn't posted yet (espn_nfl_box);
    returns (ps, sn, finals, the games taken from ESPN)."""
    from_espn = set()
    for gid in dict.fromkeys(g for g in gids if g):
        if (ps["game_id"] == gid).any() and (sn["game_id"] == gid).any():
            continue
        try:
            got = espn_nfl_box(gid, finals, get)
        except Exception as exc:  # noqa: BLE001 - ESPN down: the game waits for nflverse
            print(f"fun grading nfl: ESPN box for {gid} unavailable ({type(exc).__name__}: {exc})")
            got = None
        if got is None:
            continue
        g_ps, g_sn, home, away = got
        # ESPN's whole box replaces nflverse's half of it: on Oct 30 nflverse had posted Thursday's player stats but
        # not its snap counts, the two sources mixed, and every player read 0 (Golden's TD, Young's 209 yards: lost)
        ps, sn = ps[ps["game_id"] != gid], sn[sn["game_id"] != gid]
        ps, sn = pd.concat([ps, g_ps], ignore_index=True), pd.concat([sn, g_sn], ignore_index=True)
        if pd.isna(finals.loc[gid].get("home_pts")) or pd.isna(finals.loc[gid].get("away_pts")):
            finals = finals.copy()
            finals.loc[gid, ["home_pts", "away_pts"]] = [home, away]
        from_espn.add(gid)
    return ps, sn, finals, from_espn


def nfl_leg_results(labels: list[str], gids: list[str], ps: pd.DataFrame, sn: pd.DataFrame, finals: pd.DataFrame,
                    abbr: dict, first_td: dict | None = None, from_espn: set | None = None) -> list[dict] | None:
    """Each NFL leg's result and value from nflverse's player stats, snap counts and final scores
    (finals indexed by game_id); None until every game's stats are out. Shared with fun_offers.
    first_td: {game_id: the first touchdown's player id} (first_tds) for "X first TD scorer" legs.
    from_espn: games whose stats came from ESPN's box (with_espn): a player missing from it stays open."""
    from betlab import players

    box = {}
    for gid in set(gids):
        g_ps, g_sn = ps[ps["game_id"] == gid], sn[sn["game_id"] == gid]
        if g_ps.empty or g_sn.empty:
            return None  # not published yet
        roster = pd.concat([
            g_ps[["player_id", "player_display_name"]].set_axis(["gsis_id", "full_name"], axis=1),
            g_sn[["player_id", "player"]].set_axis(["gsis_id", "full_name"], axis=1),
        ]).drop_duplicates("gsis_id").assign(football_name=None)
        box[gid] = (roster, g_ps.drop_duplicates("player_id").set_index("player_id"),
                    set(g_sn.loc[g_sn["offense_snaps"] > 0, "player_id"]))
    results = []
    for label, gid in zip(labels, gids):
        roster, stats, played = box[gid]
        leg = parse_leg(label)
        if leg is None:
            results.append({"leg": label, "result": "unknown", "value": None})
            continue
        if leg["stat"] in GAME_STATS:
            result, value = _settle_line(leg, finals.loc[gid] if gid in finals.index else None, abbr)
            results.append({"leg": label, "result": result, "value": value})
            continue
        pid = players.match([leg["player"]], roster)[0].get(leg["player"])
        if leg["stat"] == "first_td":     # 1 if his was the game's first TD; a player who didn't play voids it
            if gid not in (first_td or {}):
                results.append({"leg": label, "result": "open", "value": None})
                continue
            value = float(pid == first_td[gid]) if pid in stats.index or pid in played else None
            results.append({"leg": label, "result": _settle_leg(leg, value), "value": value})
            continue
        if pid in stats.index:
            st = stats.loc[pid]
            from betlab.sources.nflverse import anytime_tds
            value = (anytime_tds(st) if leg["stat"] == "tds"     # returns count too (both books)
                     else float(st.get("rushing_yards", 0) or 0) + float(st.get("receiving_yards", 0) or 0)
                     if leg["stat"] == "rush_rec_yards" else float(st[leg["stat"]]))
        elif pid in played:
            value = 0.0
        elif gid in (from_espn or ()):
            results.append({"leg": label, "result": "open", "value": None})    # not in ESPN's box: nflverse decides
            continue
        else:
            value = None
        results.append({"leg": label, "result": _settle_leg(leg, value), "value": value})
    return results


def grade() -> int:
    """Grade open slips whose game's stats and snap counts are out; returns how many."""
    df = load()
    novig = df["sgp_id"].astype(str).str.startswith(NOVIG_SYNCED)       # Novig settles those (novig_settled, at sync)
    todo = df[(df["status"] == "open") & df["game_id"].notna() & ~novig]
    sport = todo["sport"].fillna("nfl")
    n = 0
    try:
        for name, grader in [(s, g) for s, g in GRADERS.items() if s != "nfl"] + [("mixed", _grade_mixed)]:
            if (sport == name).any():
                try:
                    n += grader(df, todo[sport == name])
                except Exception as exc:  # noqa: BLE001 - one sport's missing results file must not block the rest
                    print(f"fun grading {name}: not graded ({type(exc).__name__}: {exc})")
        nfl = todo[~sport.isin([s for s in GRADERS if s != "nfl"] + ["mixed"])]
        recheck = _settled_nfl(df)
        if not nfl.empty or not recheck.empty:
            try:
                n += _grade_nfl(df, pd.concat([nfl, recheck]), recheck=set(recheck.index))
            except Exception as exc:  # noqa: BLE001 - Nov 9: nflverse's 504s here threw away every other sport's settles
                print(f"fun grading nfl: not graded ({type(exc).__name__}: {exc})")
    finally:
        if n:
            save(df)            # what did settle is kept, whatever stopped the rest
    return n


def _grade_mixed(df: pd.DataFrame, todo: pd.DataFrame, graders: dict | None = None) -> int:
    """Parlays across sports (Oct 22: Lech Poznań over 1.5 goals, Juventus, Liberty and Memphis on one slip): each
    sport's legs go through that sport's own grader as a slip of their own, then the whole slip settles from every
    leg's result (_finish). Legs whose sport the ref doesn't say stay open."""
    graders = graders or GRADERS
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i, r in todo.iterrows():
        labels = json.loads(r["legs"])
        refs = json.loads(r["leg_games"]) if isinstance(r["leg_games"], str) and r["leg_games"] else [r["game_id"]] * len(labels)
        sports = [leg_sport(x) for x in refs]
        results = [{"leg": label, "result": "open", "value": None} for label in labels]
        for sp in dict.fromkeys(s for s in sports if s in graders):
            idx = [j for j, s in enumerate(sports) if s == sp]
            sub = pd.DataFrame([r.to_dict() | {"legs": json.dumps([labels[j] for j in idx]), "game_id": refs[idx[0]],
                                                "leg_games": json.dumps([refs[j] for j in idx]), "leg_p": None,
                                                "status": "open", "leg_results": None, "sport": sp}], dtype=object)
            try:
                graders[sp](sub, sub)
            except Exception as exc:  # noqa: BLE001 - that sport's results aren't out: its legs stay open
                print(f"fun grading mixed {sp}: not graded ({type(exc).__name__}: {exc})")
            got = sub.at[0, "leg_results"]
            if isinstance(got, str):
                for j, res in zip(idx, json.loads(got)):
                    results[j] = res
        n += _finish(df, i, r, results, stamp)
    return n


RECHECK_DAYS = 3


def _settled_nfl(df: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    """NFL slips settled in the last RECHECK_DAYS: graded again as nflverse fills in, and corrected where a leg's result
    changed (Oct 30: a 3 AM grade from a half-posted game read every player as 0, and a settled slip was never looked
    at again, so Golden's TD stayed lost)."""
    now = now or datetime.now(timezone.utc)
    sport = df["sport"].fillna("nfl")
    graded = pd.to_datetime(df["graded_at"], utc=True, format="ISO8601", errors="coerce")
    nfl = ~sport.isin(list(GRADERS) + ["mixed"]) | (sport == "nfl")
    return df[df["status"].isin(["won", "lost", "void"]) & df["game_id"].notna() & nfl
              & ~df["sgp_id"].astype(str).str.startswith(NOVIG_SYNCED) & (graded > now - pd.Timedelta(days=RECHECK_DAYS))]


def _same_legs(old, new: list[dict]) -> bool:
    try:
        before = json.loads(old) if isinstance(old, str) else old
    except ValueError:
        return False
    key = lambda xs: [(x.get("leg"), x.get("result"), x.get("value")) for x in xs or []]   # noqa: E731
    return key(before) == key(new)


def _grade_nfl(df: pd.DataFrame, todo: pd.DataFrame, recheck: set | None = None) -> int:
    """NFL slips, leg by leg from nflverse's player stats, snap counts and final scores. Rows in `recheck` are already
    settled: they change only when a leg's result or value did, and never back to open."""
    from betlab.sources import nflverse

    n = 0
    seasons = sorted({int(str(g)[:4]) for g in todo["game_id"]})
    ps, sn = nflverse.load_player_stats(seasons), nflverse.load_snap_counts(seasons)
    finals = nflverse.load_games().drop_duplicates("game_id").set_index("game_id")
    abbr = nflverse.team_abbr_by_name()
    gids_all = [g for _, r in todo.iterrows()
                for g in (json.loads(r["leg_games"]) if isinstance(r["leg_games"], str) and r["leg_games"] else [r["game_id"]])]
    ps, sn, finals, from_espn = with_espn(gids_all, ps, sn, finals)
    needs_first = any((parse_leg(l) or {}).get("stat") == "first_td" for legs in todo["legs"] for l in json.loads(legs))
    first_td = first_tds(seasons) if needs_first else {}
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i, r in todo.iterrows():
        labels = json.loads(r["legs"])
        gids = json.loads(r["leg_games"]) if isinstance(r["leg_games"], str) and r["leg_games"] else [r["game_id"]] * len(labels)
        gids = _find_games(labels, gids, ps)
        known = [(label, g) for label, g in zip(labels, gids) if g is not None]
        got = nfl_leg_results([x[0] for x in known], [x[1] for x in known], ps, sn, finals, abbr, first_td, from_espn)
        if got is None:
            continue  # stats not published yet
        got = iter(got)        # a leg whose game we still can't name stays open and visible
        results = [next(got) if g is not None else {"leg": label, "result": "open", "value": None}
                   for label, g in zip(labels, gids)]
        if i in (recheck or ()):
            results = espn_unknown(r, results)      # as _finish reads them, so a settled slip's ESPN legs compare
            if _same_legs(r["leg_results"], results) or any(x["result"] in ("open", "unknown") for x in results):
                continue
            print(f"fun grading nfl: regraded {r['sgp_id']} ({r['status']} before)")
        n += _finish(df, i, r, results, stamp)   # a lost leg settles it; otherwise it waits for every leg
    return n


def first_tds(seasons) -> dict:
    """{game_id: the player id of the game's first touchdown} from nflverse's play-by-play."""
    from betlab.sources import nflverse

    pbp = nflverse.load_pbp(seasons, columns=["game_id", "play_id", "touchdown", "td_player_id"])
    tds = pbp[pbp["touchdown"] == 1].sort_values(["game_id", "play_id"]).drop_duplicates("game_id")
    return dict(zip(tds["game_id"], tds["td_player_id"]))


def _find_games(labels: list[str], gids: list, ps: pd.DataFrame) -> list:
    """A slip read from a screenshot can leave a leg's game unnamed (Oct 25: Jordan Love, Joe Burrow and Geno Smith
    legs had none, and four slips with a lost leg stayed open): find the player in that week's player stats."""
    from betlab import players

    week = next((str(g)[:7] for g in gids if g is not None), None)          # "2026_07" of "2026_07_CIN_BAL"
    if week is None or all(g is not None for g in gids):
        return gids
    wk = ps[ps["game_id"].astype(str).str.startswith(week + "_")].drop_duplicates("player_id")
    roster = wk[["player_id", "player_display_name"]].set_axis(["gsis_id", "full_name"], axis=1).assign(football_name=None)
    game_of = wk.set_index("player_id")["game_id"]
    out = []
    for label, g in zip(labels, gids):
        leg = parse_leg(label) if g is None else None
        if leg and leg.get("player"):
            g = game_of.get(players.match([leg["player"]], roster)[0].get(leg["player"]))
        out.append(g)
    return out


def _dk_soccer_void(r, off: list[dict]) -> bool:
    """DraftKings settles a pre-game soccer same-game parlay as void when any leg other than a player who didn't take
    part is void or pushes (its house rules, Soccer > Pre-live Same Game Parlays, checked Oct 12, 2026); FanDuel drops
    the leg and reprices, as every other DraftKings sport does. A soccer leg that isn't a player's is a game leg."""
    if str(r.get("book") or "").lower() != "draftkings" or str(r.get("sport") or "") != "soccer":
        return False
    return any(not SOCCER_SHOTS.match(str(x.get("leg") or "")) for x in off)


# the stats the sport graders don't read (Nov 6: longest reception, carries, steals + blocks, "most receiving yards", cards
# and the rest): settled from ESPN's final box score by the live trackers' own reader (live_legs.judge), so a slip with one
# never sits "unknown", which holds a winning slip open for good
ESPN_ONLY = {"longest reception", "longest rush", "rush attempts", "pass attempts", "completions", "interceptions", "tackles",
             "sacks", "kicking points", "field goals made", "turnovers", "stl + blk", "free throws made", "offensive rebounds",
             "blocked shots", "hits", "fouls", "longest completion", "power play points", "power play goals",
             # Nov 9: "2+ passing TDs" (the NFL grader's LEG doesn't read it) and the NBA's lone steals or blocks (NBA_STAT
             # doesn't): the trackers showed them hit while the slip sat "unknown"
             "passing tds", "steals", "blocks",
             # and touchdowns by count ("2+ TDs", "1+ rushing TDs"), which the trackers learned the same day
             "touchdowns", "rushing tds", "receiving tds"}


def _espn_leg_game(ref, r) -> tuple[str | None, str | None, str, list[str]]:
    """(sport, league, matchup, ESPN days) for one leg from its game ref, else the slip's own sport and matchup."""
    from betlab import live_legs as L

    sport, league = L.ref_sport(ref)
    s, matchup, day = str(ref or ""), str(r.get("matchup") or ""), None
    if m := re.match(r"^\d{4}_\d{2}_([A-Z]+)_([A-Z]+)$", s):           # nflverse: AWAY_HOME
        matchup = f"{m[1]} @ {m[2]}"
    elif s.count("|") == 3:                                               # nba|HOME|AWAY|tip, <league>|Home|Away|kickoff
        _, home, away, at = s.split("|")
        matchup, day = f"{away} @ {home}", at
    sport = sport or L.sport_of(r.get("sport"))[0]
    base = pd.Timestamp(day or r.get("quoted_at") or pd.Timestamp.now(tz="UTC"))
    base = (base if base.tzinfo else base.tz_localize("UTC")).tz_convert("America/New_York")
    return sport, league, matchup, [(base + pd.Timedelta(days=k)).strftime("%Y%m%d") for k in range(3 if day is None else 1)]


def espn_unknown(r, results: list[dict], get=None) -> list[dict]:
    """The slip's "unknown" legs on ESPN_ONLY stats (and "most ..." and card legs) settled from ESPN once their game is
    final; anything else, or a game ESPN doesn't have final, stays as it was."""
    from betlab import live_legs as L

    get = get or L.espn
    refs = json.loads(r["leg_games"]) if isinstance(r.get("leg_games"), str) and r["leg_games"] else [r.get("game_id")] * len(results)
    out = []
    for x, ref in zip(results, refs + [None] * (len(results) - len(refs))):
        leg = L.parse_leg(x["leg"]) if x.get("result") == "unknown" else None
        # play-by-play stats too ("1q points", "1p goals"), and first basket / first goal (Nov 6)
        period = leg and leg.get("kind") == "prop" and re.fullmatch(r"[1-4][qhp] .+", leg["stat"])
        if not leg or not (leg["kind"] in ("leader", "card", "first") or period or (leg["kind"] == "prop" and leg["stat"] in ESPN_ONLY)):
            out.append(x)
            continue
        try:
            sport, league, matchup, days = _espn_leg_game(ref, r)
            g = L.find_game(L.scoreboard(sport, league, days, get), matchup) if sport else None
            if not g or g["state"] != "post":
                out.append(x | {"result": "open"})
                continue
            j = L.judge(x["leg"], g, L.boxscore(g, league, get))
            res = j["status"] if j["status"] in ("won", "lost", "void") else "open"
            out.append(x | {"result": res, "value": j.get("current")})
        except Exception as exc:  # noqa: BLE001 - ESPN down: the leg waits for the next grade
            print(f"fun grading: ESPN for {x['leg']!r} unavailable ({type(exc).__name__}: {exc})")
            out.append(x)
    return out


def _finish(df: pd.DataFrame, i, r, results: list[dict], stamp: str) -> bool:
    """Settle one slip from its legs' results; False when it must wait."""
    from betlab import odds_math as om

    results = espn_unknown(r, results)
    if _true(r.get("protect")):         # Bet Protect+ (Oct 26): a leg on a player who sat out counts as won
        results = [x | {"result": "won", "note": "did not play: covered by Bet Protect+"}
                   if x["result"] == "void" and x.get("value") is None else x for x in results]
    outcomes = [x["result"] for x in results]
    # a lost leg loses the slip whatever the rest do; only otherwise wait for every leg (Oct 20: a "to score or assist"
    # leg the grader can't read kept a slip with a lost leg open)
    if "lost" not in outcomes and ("unknown" in outcomes or "open" in outcomes):
        return False
    off = [j for j, o in enumerate(outcomes) if o in ("void", "push")]
    ps = json.loads(r["leg_p"]) if isinstance(r.get("leg_p"), str) and r["leg_p"] else []
    novig = str(r.get("book") or "").lower() == "novig"
    factor = 1.0
    unpriced = off and len(off) < len(outcomes) and any(j >= len(ps) or ps[j] is None for j in off)
    cash = pd.to_numeric(pd.Series([r.get("cashout")]), errors="coerce").iloc[0]
    if "lost" not in outcomes and unpriced and bool(r.get("marked")) and pd.isna(cash):
        # Nov 9: a real slip (a screenshot's: no leg_p) with a leg off, the rest won. The book pays the shorter parlay,
        # at a price we can't know without the leg's; voiding it all said 0 for a win. It waits, and says so (a grade
        # warning, once a day), until what the book paid is entered as its cash-out (marked_profit reads that)
        print(f"fun grading: {r.get('sgp_id')} not graded: {', '.join(str(results[j]['leg']) for j in off)} came off "
              "and the book's reduced price is unknown; enter what it paid as a cash-out")
        return False
    if "lost" in outcomes:
        status = "lost"
    elif not off:
        status = "won"
    elif unpriced and bool(r.get("marked")):
        status = "won"                        # paid what the book says it paid (cashout); its 1u price is unknown
    elif any(j >= len(ps) or ps[j] is None for j in off):
        status = "void"                       # every leg off, or an unmarked slip's leg off with no known fair chance
    elif novig:                               # Novig (Oct 28): each void leg counts at its fair value, even all of them
        status = "void" if len(off) == len(outcomes) else "won"
        for j in off:
            factor *= float(ps[j])
            results[j] = results[j] | {"p": round(float(ps[j]), 4)}
    elif len(off) == len(outcomes):
        status = "void"                       # every leg off
    elif _dk_soccer_void(r, [results[j] for j in off]):
        status = "void"                       # DraftKings' soccer rule: a game leg off voids the whole slip
    else:
        status = "won"                        # FanDuel drops the leg: the rest stands at a shorter price
        for j in off:                         # j: the leg (i is the slip's row)
            factor *= float(ps[j])
            results[j] = results[j] | {"p": round(float(ps[j]), 4)}
    price = float(r["price"]) if pd.notna(r["price"]) else None
    if novig and off and status != "lost" and price is not None:
        # the pot (stake / price) times the legs' values, never under 0.001 of it: it can pay back less than the stake
        p1 = om.american_to_decimal(price) * max(round(factor, 3), 0.001) - 1
    else:
        win_1u = (max(om.american_to_decimal(price) * factor, 1.0) - 1) if price is not None else None
        p1 = win_1u if status == "won" else -1.0 if status == "lost" else 0.0
    if status == "won" and unpriced:
        p1 = None                             # its cash-out says what it paid; the 1u price stays unknown
    df.at[i, "status"], df.at[i, "leg_results"] = status, json.dumps(results)
    df.at[i, "profit_1u"] = round(p1, 4) if p1 is not None else None
    df.at[i, "profit"] = marked_profit(p1, r, status)
    df.at[i, "graded_at"] = stamp
    return True


def _grade_college(df: pd.DataFrame, todo: pd.DataFrame) -> int:
    """College tickets: every leg a game line, settled from CFBD's final scores."""
    from betlab.sources import cfbd

    finals = cfbd.games().assign(game_id=lambda g: g["game_id"].astype(str)).drop_duplicates("game_id").set_index("game_id")
    names = cfbd.team_names()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i, r in todo.iterrows():
        labels = json.loads(r["legs"])
        gids = json.loads(r["leg_games"]) if isinstance(r["leg_games"], str) and r["leg_games"] else [r["game_id"]] * len(labels)
        results = []
        for label, gid in zip(labels, gids):
            leg = parse_leg(label)
            if leg is None or leg["stat"] not in GAME_STATS:
                results.append({"leg": label, "result": "unknown", "value": None})
                continue
            key = None if leg["team"] is None else names.get(leg["team"])
            result, value = _settle_line(leg | {"team": key}, finals.loc[_bare(gid)] if _bare(gid) in finals.index else None,
                                         {key: key} if key else {})
            results.append({"leg": label, "result": result, "value": value})
        n += _finish(df, i, r, results, stamp)
    return n



def _grade_ncaab(df: pd.DataFrame, todo: pd.DataFrame, finals: pd.DataFrame | None = None, names: dict | None = None) -> int:
    """College basketball tickets (cards/fun_ncaab.py): every leg a game line, settled from CollegeBasketballData's
    final scores; leg labels carry the odds feed's team names, mapped to CBBD's (cbbd.team_names)."""
    from betlab.sources import cbbd

    if finals is None:
        finals = cbbd.games()
    finals = finals.assign(game_id=lambda g: g["game_id"].astype(str)).drop_duplicates("game_id").set_index("game_id")
    if names is None:
        teams = {parse_leg(l)["team"] for r in todo.itertuples() for l in json.loads(r.legs)
                 if parse_leg(l) and parse_leg(l).get("team")}
        names = cbbd.team_names(feed_names=sorted(teams))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i, r in todo.iterrows():
        labels = json.loads(r["legs"])
        gids = json.loads(r["leg_games"]) if isinstance(r["leg_games"], str) and r["leg_games"] else [r["game_id"]] * len(labels)
        results = []
        for label, gid in zip(labels, gids):
            leg = parse_leg(label)
            if leg is None or leg["stat"] not in GAME_STATS:
                results.append({"leg": label, "result": "unknown", "value": None})
                continue
            key = None if leg["team"] is None else names.get(leg["team"])
            result, value = _settle_line(leg | {"team": key}, finals.loc[_bare(gid)] if _bare(gid) in finals.index else None,
                                         {key: key} if key else {})
            results.append({"leg": label, "result": result, "value": value})
        n += _finish(df, i, r, results, stamp)
    return n

SOCCER_WIN = re.compile(r"^(?P<team>.+) (?:to win|ML)$", re.I)
SOCCER_GOALS = re.compile(r"^(?P<side>over|under) (?P<point>\d+(?:\.\d+)?)(?: total goals| goals| total)?$", re.I)
SOCCER_DC = re.compile(r"^(?P<team>.+) or draw$", re.I)
SOCCER_BTTS = re.compile(r"^(?:both teams to score|btts)(?:: ?(?P<side>yes|no))?$", re.I)
SOCCER_LINE = re.compile(r"^(?P<team>.+) (?P<point>[+-]\d+(?:\.\d+)?)$")
SOCCER_SHOTS = re.compile(r"^(?P<player>.+) (?:\d+\+|(?:over|under) \d+(?:\.\d+)?) (?:shots on target|shots|goals|assists)$", re.I)   # goals: Oct 25
SOCCER_OR_ASSIST = re.compile(r"^(?P<player>.+) to score or assist$", re.I)
SOCCER_KEY = {"shots": "shots", "shots on target": "sot", "goals": "goals", "assists": "assists"}


def _espn_shots(league: str, home: str, away: str, kickoff: str, player: str, stat: str) -> tuple[str, float | None]:
    """(won-able status, count) for a soccer shot leg from ESPN's box score: ("open", None) until the
    match is final, ("void", None) when the player didn't play (FanDuel voids those)."""
    from betlab.sources import espn_soccer as E

    st, p = E.player_result(league, home, away, kickoff, player)
    if st != "ok":
        return st, None
    v = p[stat]
    return ("ok", float(v)) if pd.notna(v) else ("open", None)


def _soccer_side(team: str, home: str, away: str) -> str | None:
    """Which side a leg's team is. Nov 4: a slip writes ESPN's name ("Stade Rennais") and the game's ref holds the book's
    ("Rennes"), and an exact match left that leg "unknown" and a winning slip open for good. Two names that fit equally
    name no side."""
    from betlab.live_legs import CLUB_ALIASES, plain, side_of

    if team in (home, away):
        return "home" if team == home else "away"
    for side, name in (("home", home), ("away", away)):
        if plain(CLUB_ALIASES.get(plain(name), "")) == plain(team):
            return side
    return side_of(team, {"home": {"name": home}, "away": {"name": away}})


def settle_soccer(label: str, home: str, away: str, hg: int, ag: int) -> str:
    """won / lost / push / unknown for a soccer ticket leg (cards/fun_soccer.py labels, and a slip's own wording)."""
    if m := SOCCER_BTTS.match(label):
        both = hg > 0 and ag > 0
        return "won" if both == ((m["side"] or "yes").lower() == "yes") else "lost"
    if label.lower() == "draw":
        return "won" if hg == ag else "lost"
    if m := SOCCER_GOALS.match(label):
        total, point = hg + ag, float(m["point"])
        if total == point:
            return "push"
        return "won" if (total > point) == (m["side"].lower() == "over") else "lost"
    margin = None
    if m := (SOCCER_DC.match(label) or SOCCER_WIN.match(label) or SOCCER_LINE.match(label)):
        side = _soccer_side(m["team"], home, away)
        margin = None if side is None else hg - ag if side == "home" else ag - hg
    if margin is None:
        return "unknown"
    if SOCCER_DC.match(label):
        return "won" if margin >= 0 else "lost"
    if SOCCER_WIN.match(label):
        return "won" if margin > 0 else "lost"
    point = float(m["point"])
    if point * 2 != int(point * 2):      # a quarter line (-0.75) is half on each side of it: not read here
        return "unknown"
    return "won" if margin + point > 0 else "lost" if margin + point < 0 else "push"


def _soccer_result(league: str, home: str, away: str, kickoff) -> dict | None:
    """football-data.co.uk's final score, else ESPN's once the match is over (football-data's files
    update a few times a week and can lag for weeks: Oct 12, the 2026-27 files stopped at Sep 20)."""
    from betlab.sources import espn_soccer, soccer

    from betlab.cards.soccer import CUPS

    res = None if league in CUPS else soccer.result(league, home, away, kickoff)   # no cup files there
    if res is not None:
        return res
    try:
        score = espn_soccer.final_score(league, home, away, kickoff)
    except Exception:  # noqa: BLE001 - ESPN down: try tomorrow
        return None
    return None if score is None else {"hg": score[0], "ag": score[1]}


def _grade_soccer(df: pd.DataFrame, todo: pd.DataFrame, lookup=None, shots=None) -> int:
    """Soccer tickets: legs settle from each leg's match's final score (game_ref
    "league|home|away|kickoff"): football-data.co.uk's, else ESPN's; open until one has it."""
    lookup = lookup or _soccer_result
    shots = shots or _espn_shots
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i, r in todo.iterrows():
        labels = json.loads(r["legs"])
        refs = json.loads(r["leg_games"]) if isinstance(r["leg_games"], str) and r["leg_games"] else [r["game_id"]] * len(labels)
        results, cache = [], {}
        for label, ref in zip(labels, refs):
            parts = str(ref).split("|")
            if len(parts) != 4:
                results.append({"leg": label, "result": "unknown", "value": None})
                continue
            from betlab.live_legs import parse_leg as read_leg
            leg = read_leg(label) or {}
            if leg.get("kind") == "prop" and leg["stat"] in SOCCER_KEY:   # a player's shots or goals: ESPN's box score
                try:
                    st, v = shots(parts[0], parts[1], parts[2], parts[3], leg["player"], SOCCER_KEY[leg["stat"]])
                except Exception:  # noqa: BLE001 - ESPN down: try tomorrow
                    st, v = "open", None
                results.append({"leg": label, "result": st if st in ("open", "void") else _settle_over_under(v, leg), "value": v})
                continue
            if m := SOCCER_OR_ASSIST.match(label):           # Nov 4: a slip with this leg could only ever lose
                try:
                    got = [shots(parts[0], parts[1], parts[2], parts[3], m["player"], k) for k in ("goals", "assists")]
                except Exception:  # noqa: BLE001 - ESPN down: try tomorrow
                    got = [("open", None)]
                bad = next((st for st, _ in got if st in ("open", "void")), None)
                v = None if bad else sum(x for _, x in got)
                results.append({"leg": label, "result": bad or ("won" if v >= 1 else "lost"), "value": v})
                continue
            if ref not in cache:
                cache[ref] = lookup(parts[0], parts[1], parts[2], parts[3])
            res = cache[ref]
            if res is None:
                results.append({"leg": label, "result": "open", "value": None})
                continue
            results.append({"leg": label, "result": settle_soccer(label, parts[1], parts[2], res["hg"], res["ag"]),
                            "value": f"{res['hg']}-{res['ag']}"})
        n += _finish(df, i, r, results, stamp)
    return n


NHL_WIN = re.compile(r"^(?P<team>.+?) (?:to win|ML)$")
NHL_PUCK = re.compile(r"^(?P<team>.+?) (?P<point>[+-]\d+(?:\.\d+)?)$")
NHL_GOALS = re.compile(r"^(?P<side>over|under) (?P<point>\d+(?:\.\d+)?)(?: total goals| goals| total)?$", re.I)
NHL_BOX = {"shots": "shots", "shots on goal": "shots", "goals": "goals", "assists": "assists", "points": "points", "saves": "saves"}


def _nhl_prop(label: str) -> dict | None:
    """A player leg the NHL's box score settles, as the trackers read it: "over 2.5 shots" and, Nov 4, a slip's "3+ shots"
    or "1+ goals" (either wording of any stat here used to leave the leg "unknown" and a winning slip open for good)."""
    from betlab.live_legs import parse_leg as read_leg

    leg = read_leg(label) or {}
    return leg if leg.get("kind") == "prop" and leg["stat"] in NHL_BOX else None


def _nhl_goals_for(team: str, home: str, away: str, hg: float, ag: float) -> tuple[float, float] | tuple[None, None]:
    """(the team's goals, the other's). Nov 4: our legs say "NYR", a slip says "New York Rangers"; a slip's full name
    left its leg "unknown" and the bet open for good."""
    from betlab.novig_sync import _full
    from betlab.sources import novig

    is_home, is_away = [team == code or novig._same_team(team, _full(code, "nhl")) for code in (home, away)]
    return (hg, ag) if is_home and not is_away else (ag, hg) if is_away and not is_home else (None, None)


def settle_nhl(label: str, home: str, away: str, hg: float, ag: float, shots=None) -> tuple[str, float | None]:
    """(won / lost / unknown, value) for an NHL leg (cards/fun_nhl.py labels). Final scores as
    books settle them: overtime counts, and the shootout winner is credited one goal."""
    if m := NHL_GOALS.match(label):
        total, point = hg + ag, float(m["point"])
        return ("push" if total == point else "won" if (total > point) == (m["side"].lower() == "over") else "lost"), total
    if m := NHL_WIN.match(label):
        mine, theirs = _nhl_goals_for(m["team"], home, away, hg, ag)
        return ("unknown", None) if mine is None else (("won" if mine > theirs else "lost"), mine - theirs)
    if m := NHL_PUCK.match(label):
        mine, theirs = _nhl_goals_for(m["team"], home, away, hg, ag)
        if mine is None:
            return "unknown", None
        return ("won" if mine - theirs + float(m["point"]) > 0 else "lost"), mine - theirs
    if (leg := _nhl_prop(label)) and shots is not None:
        from betlab.sources.nhl import _plain
        row, stat = shots[shots["plain"] == _plain(leg["player"])], NHL_BOX[leg["stat"]]
        if row.empty or stat not in row or pd.isna(row[stat].iloc[0]):
            return "void", None                     # didn't play: books void a player prop
        v = float(row[stat].iloc[0])
        return _settle_over_under(v, leg), v
    return "unknown", None


def _grade_nhl(df: pd.DataFrame, todo: pd.DataFrame, team_games: pd.DataFrame | None = None, shots_for=None) -> int:
    """NHL tickets and shots overs: each leg's game (game_ref = the NHL game id) from the NHL's
    final scores and skater shots; open until the game is in the stats."""
    from betlab.sources import nhl

    if team_games is None:
        team_games = nhl.load_team_games([nhl.current_season()], max_age_hours=1.0)
    home = team_games[team_games["home"] == 1]
    home = home.set_index(home["game_id"].astype(str))
    shots_for = shots_for or (lambda gid: pd.concat([nhl.skater_box(gid), nhl.goalie_box(gid)], ignore_index=True))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i, r in todo.iterrows():
        labels = json.loads(r["legs"])
        gids = json.loads(r["leg_games"]) if isinstance(r["leg_games"], str) and r["leg_games"] else [r["game_id"]] * len(labels)
        results, shot_cache = [], {}
        for label, gid in zip(labels, gids):
            gid = _bare(gid) if gid is not None else None
            if gid is None or gid not in home.index:
                results.append({"leg": label, "result": "open", "value": None})
                continue
            g = home.loc[gid]
            shots = None
            if _nhl_prop(label):
                if gid not in shot_cache:
                    shot_cache[gid] = shots_for(gid)
                shots = shot_cache[gid]
            result, value = settle_nhl(label, g["team"], g["opp"], float(g["gf"]), float(g["ga"]), shots)
            results.append({"leg": label, "result": result, "value": value})
        n += _finish(df, i, r, results, stamp)
    return n


NBA_STAT = {"points": ("points",), "rebounds": ("rebounds",), "assists": ("assists",),
            "threes": ("three_point_field_goals_made",), "pts + reb + ast": ("points", "rebounds", "assists"),
            "pts + reb": ("points", "rebounds"), "pts + ast": ("points", "assists"), "reb + ast": ("rebounds", "assists")}
NBA_LEG = re.compile(r"^(?P<player>.+?) (?:(?P<side>over|under) (?P<point>\d+(?:\.\d+)?)|(?P<alt>\d+)\+) "
                     r"(?P<stat>pts \+ reb \+ ast|pts \+ reb|pts \+ ast|reb \+ ast|points|rebounds|assists|threes)$")


def parse_nba_leg(label: str) -> dict | None:
    """{player, stat parts, side, point} for an NBA prop leg, or a game-line leg, or None."""
    from betlab.live_legs import canon_stat
    label = canon_stat(label)
    if m := re.fullmatch(r"(.+) (double|triple)-double", label, re.I):     # Oct 25: Towns' double-double
        return {"player": m[1], "parts": ("points", "rebounds", "assists", "steals", "blocks"), "double": 2 if m[2].lower() == "double" else 3}
    if m := NBA_LEG.match(label):
        point = float(m["point"]) if m["point"] else float(m["alt"]) - 0.5
        return {"player": m["player"], "parts": NBA_STAT[m["stat"]], "side": m["side"] or "over", "point": point}
    return parse_leg(label) if (TOTAL.match(label) or ML.match(label) or SPREAD.match(label)) else None


def nba_data(refs, box: pd.DataFrame | None = None, sch: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(box scores, schedule) for the seasons of these "nba|HOME|AWAY|tipoff" game refs, under an hour old."""
    from betlab.sources import nba

    if box is None or sch is None:
        seasons = sorted({nba.current_season(pd.Timestamp(str(r).split("|")[3]).tz_convert("America/New_York"))
                          for r in refs if str(r).startswith("nba|")})
        box = nba.load_player_box(seasons, max_age_hours=1.0) if box is None else box
        sch = nba.load_schedules(seasons, max_age_hours=1.0) if sch is None else sch
    return box, sch


def _nba_sat(player: str, teams: set, box: pd.DataFrame) -> bool:
    """A player missing from his game's box sat out (the box files leave a DNP out): the season's box knows him on
    one of the game's two teams (abbreviations). A name it never matched is not a DNP."""
    from betlab import players

    if "team_abbreviation" not in box:
        return False
    roster = box[["athlete_id", "athlete_display_name"]].drop_duplicates("athlete_id").set_axis(
        ["gsis_id", "full_name"], axis=1).assign(football_name=None)
    pid = players.match([player], roster)[0].get(player)
    return pid is not None and bool(set(box.loc[box["athlete_id"] == pid, "team_abbreviation"]) & teams)


def nba_leg_results(labels: list[str], refs: list[str], box: pd.DataFrame, sch: pd.DataFrame) -> list[dict]:
    """Each NBA leg's result ({leg, result, value}): player legs from ESPN box scores (a player who didn't play voids
    the leg; a game whose box isn't in, or a name the season's box doesn't know, stays open), game lines from the final score; each leg's game from its ref "nba|HOME|AWAY|tipoff". Shared by the
    fun ledger and the offered-slips ledger (fun_offers)."""
    from betlab import players

    box = box.assign(minutes=pd.to_numeric(box["minutes"], errors="coerce"),
                     day=pd.to_datetime(box["game_date"]).dt.strftime("%Y-%m-%d"))
    s = sch.assign(day=pd.to_datetime(sch["start_date"], utc=True, format="ISO8601").dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d"))
    names = dict(zip(s["home_display_name"], s["home_abbreviation"])) | dict(zip(s["away_display_name"], s["away_abbreviation"]))
    results = []
    for label, ref in zip(labels, refs):
        parts = str(ref).split("|")
        leg = parse_nba_leg(label)
        if len(parts) != 4 or leg is None:
            results.append({"leg": label, "result": "unknown", "value": None})
            continue
        _, home, away, tip = parts
        day = pd.Timestamp(tip).tz_convert("America/New_York").strftime("%Y-%m-%d")
        game = s[(s["home_abbreviation"] == home) & (s["away_abbreviation"] == away) & (s["day"] == day)]
        if game.empty or pd.isna(game["home_score"].iloc[0]) or not bool(game["status_type_completed"].iloc[0]):
            results.append({"leg": label, "result": "open", "value": None})
            continue
        g = game.iloc[0]
        if "parts" not in leg:   # a game line
            fin = {"home_team": home, "away_team": away, "home_pts": g["home_score"], "away_pts": g["away_score"]}
            result, value = _settle_line(leg, fin, names)
            results.append({"leg": label, "result": result, "value": value})
            continue
        gb = box[(box["game_id"] == g["game_id"])]
        if gb.empty:     # Nov 9: the game's box didn't come (an ESPN hiccup): wait, never void every player on it
            results.append({"leg": label, "result": "open", "value": None})
            continue
        roster = gb[["athlete_id", "athlete_display_name"]].set_axis(["gsis_id", "full_name"], axis=1).assign(football_name=None)
        pid = players.match([leg["player"]], roster)[0].get(leg["player"])
        row = gb[gb["athlete_id"] == pid]
        if not len(row) and not _nba_sat(leg["player"], {home, away}, box):
            results.append({"leg": label, "result": "open", "value": None})   # a name we can't place: never guess a void
            continue
        played = len(row) and row["minutes"].iloc[0] > 0
        if "double" in leg:                       # categories at 10+ (points, rebounds, assists, steals, blocks)
            value = float(sum(float(row[p].iloc[0]) >= 10 for p in leg["parts"] if p in row)) if played else None
            results.append({"leg": label, "result": "void" if value is None else "won" if value >= leg["double"] else "lost",
                            "value": value})
            continue
        value = float(sum(float(row[p].iloc[0]) for p in leg["parts"])) if played else None
        results.append({"leg": label, "result": _settle_leg(leg, value), "value": value})
    return results


def _grade_nba(df: pd.DataFrame, todo: pd.DataFrame, box: pd.DataFrame | None = None,
               sch: pd.DataFrame | None = None) -> int:
    """NBA tickets, leg by leg (nba_leg_results)."""
    box, sch = nba_data([r for refs in todo["leg_games"].dropna() for r in json.loads(refs)], box, sch)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i, r in todo.iterrows():
        labels = json.loads(r["legs"])
        refs = json.loads(r["leg_games"]) if isinstance(r["leg_games"], str) and r["leg_games"] else [r["game_id"]] * len(labels)
        n += _finish(df, i, r, nba_leg_results(labels, refs, box, sch), stamp)
    return n


UFC_ROUNDS = re.compile(r"^(over|under) (\d+(?:\.\d+)?) rounds$", re.I)    # a fight's total rounds leg


def _grade_ufc(df: pd.DataFrame, todo: pd.DataFrame, fights: pd.DataFrame | None = None) -> int:
    """UFC tickets: a fighter's moneyline (a draw or no contest voids it) or the fight's total rounds ("Over 1.5
    rounds", + Add's slips, Oct 25), from ESPN's fight center. Leg refs are "ufc:<ESPN event>:<fight id>"."""
    from betlab import grading
    from betlab.sources import espn_ufc as src

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cache: dict[str, pd.DataFrame] = {}

    def fight(ref):
        event, _, fid = _bare(ref).partition(":")
        if fights is not None:
            rows = fights
        else:
            if event not in cache:
                try:
                    cache[event] = src.fights(src.event(event, refresh=True), event)
                except Exception:      # ESPN down: the slip waits
                    cache[event] = pd.DataFrame()
            rows = cache[event]
        m = rows[rows["fight_id"].astype(str) == fid] if len(rows) else rows
        return m.iloc[0] if len(m) else None

    n = 0
    for i, r in todo.iterrows():
        labels = json.loads(r["legs"])
        refs = json.loads(r["leg_games"]) if isinstance(r["leg_games"], str) and r["leg_games"] else [r["game_id"]] * len(labels)
        results = []
        for label, ref in zip(labels, refs):
            leg, f = parse_leg(label), fight(ref)
            if f is None and fights is None and _bare(ref).partition(":")[0] in cache and len(cache[_bare(ref).partition(":")[0]])                     and bool(cache[_bare(ref).partition(":")[0]]["done"].all()):
                results.append({"leg": label, "result": "void", "value": None})   # cancelled: the book voids the leg
                continue
            rounds = UFC_ROUNDS.match(str(label).strip())
            if f is None or (rounds is None and (leg is None or leg["stat"] != "moneyline")):
                results.append({"leg": label, "result": "unknown", "value": None})
                continue
            res = grading.ufc_outcome(f, {"market": "totals", "side": rounds[1].title(), "point": float(rounds[2])}
                                      if rounds else {"market": "h2h", "side": leg["team"]})
            results.append({"leg": label, "result": {None: "open", "push": "void"}.get(res, res), "value": None})
        n += _finish(df, i, r, results, stamp)
    return n


GRADERS = {"ufc": _grade_ufc, "ncaaf": _grade_college, "soccer": _grade_soccer, "nba": _grade_nba, "nhl": _grade_nhl,
           "ncaab": _grade_ncaab, "nfl": _grade_nfl}


# What FanDuel paid, as a share of our fair payout, by the parlay's size (fair American odds),
# on Mike's first 101 quotes (Sep 28): 78% up to +300 (22 quotes), 79% at +300-700 (53), 96% at
# +700-1500 (8), 107% at +1500+ (18). FanDuel takes its full margin on small, likely parlays and
# pays near or above fair on long shots, so each parlay is judged against its own size's usual.
RATIO_BANDS = ((300, 0.78), (700, 0.79), (1500, 0.95), (None, 1.05))   # (fair odds up to, prior ratio)


def typical_ratio(df: pd.DataFrame, min_quotes: int = 10) -> dict:
    """What FanDuel usually pays on a same-game parlay of each size, as its quoted payout over our
    fair payout (decimal odds): the median of Mike's FanDuel quotes in each fair-odds band (the
    prior with fewer than min_quotes). The builder grade's benchmark."""
    from betlab import odds_math as om

    q = pd.DataFrame(columns=["price", "fair_price"])
    if df is not None and not df.empty:
        q = df[(df["book"].fillna("fanduel") == "fanduel") & df["price"].notna() & df["fair_price"].notna()]
        q = q[~q["sgp_id"].astype(str).str.startswith(("over-", "td-"))]    # straights and TD tickets pay the product
    fair = q["fair_price"].astype(float)
    ratio = pd.Series([om.american_to_decimal(float(a)) / om.american_to_decimal(float(b))
                       for a, b in zip(q["price"], q["fair_price"])], index=q.index, dtype=float)
    bands, lo = [], -np.inf
    for hi, prior in RATIO_BANDS:
        inb = (fair > lo) & (fair <= (np.inf if hi is None else hi))
        n = int(inb.sum())
        bands.append({"max_fair": hi, "ratio": round(float(ratio[inb].median()), 3) if n >= min_quotes else prior,
                      "quotes": n, "from_quotes": n >= min_quotes})
        lo = np.inf if hi is None else hi
    return {"bands": bands, "quotes": int(len(q))}



QUOTE_FEATURES = ("log_fair", "legs", "cross_game", "naive_gap")


def quote_features(fair_price, naive_price, n_legs, cross_game) -> list[float] | None:
    """[log fair decimal odds, legs, cross-game ticket (1/0), log(FanDuel's leg product / fair)]."""
    from betlab import odds_math as om

    if fair_price is None or naive_price is None or pd.isna(fair_price) or pd.isna(naive_price):
        return None
    f, nv = om.american_to_decimal(float(fair_price)), om.american_to_decimal(float(naive_price))
    return [float(np.log(f)), float(n_legs), float(bool(cross_game)), float(np.log(nv / f))]


def quote_model(df: pd.DataFrame | None, min_quotes: int = 40, ridge: float = 1.0, book: str = "fanduel") -> dict | None:
    """FanDuel's same-game parlay pricing (Oct 12): log(its quoted payout / our fair payout) from fair odds,
    legs, cross-game (SGP+) and its own leg prices. Least squares with a light ridge on Mike's typed FanDuel
    quotes (straights and TD tickets excluded: they pay the product). Leave-one-out on 127 quotes: error 0.124
    vs 0.181 from fair odds alone (about the old bands); each leg costs ~7%, and the quote moves ~38% of the
    way toward FanDuel's own leg product. None with fewer than min_quotes. `book`: whose quotes (Oct 12: DraftKings
    gets its own model once ~40 of its quotes are typed; until then FanDuel's stands in, labeled)."""
    if df is None or df.empty:
        return None
    from betlab import odds_math as om

    q = df[(df["book"].fillna("fanduel").str.lower() == book) & df["price"].notna() & df["fair_price"].notna()]
    q = q[~q["sgp_id"].astype(str).str.startswith(("over-", "td-"))]
    rows, ys = [], []
    for r in q.itertuples():
        x = quote_features(r.fair_price, r.naive_price, r.n_legs, str(r.sgp_id).startswith("plus-"))
        if x is None:
            continue
        rows.append(x)
        ys.append(float(np.log(om.american_to_decimal(float(r.price)) / om.american_to_decimal(float(r.fair_price)))))
    if len(rows) < min_quotes:
        return None
    X = np.column_stack([np.ones(len(rows)), np.array(rows)])
    y = np.array(ys)
    pen = ridge * np.eye(X.shape[1])
    pen[0, 0] = 0.0
    b = np.linalg.solve(X.T @ X + pen, X.T @ y)
    resid = y - X @ b
    return {"coef": dict(zip(("intercept",) + QUOTE_FEATURES, [round(float(v), 4) for v in b])),
            "rmse": round(float(np.sqrt((resid ** 2).mean())), 4), "quotes": len(rows)}


def likely_price(model: dict | None, fair_price, naive_price, n_legs, cross_game) -> int | None:
    """FanDuel's likely quote (American) for a slip, from quote_model; None without a model or prices."""
    from betlab import odds_math as om

    x = quote_features(fair_price, naive_price, n_legs, cross_game)
    if model is None or x is None:
        return None
    c = model["coef"]
    log_ratio = c["intercept"] + sum(c[k] * v for k, v in zip(QUOTE_FEATURES, x))
    dec = om.american_to_decimal(float(fair_price)) * float(np.exp(log_ratio))
    return int(round(om.prob_to_american(1 / dec))) if dec > 1 else None

def custom_summary(df: pd.DataFrame) -> dict:
    """Mike's own parlays (the page's builder, sgp_id "custom-..."): the record overall and by the
    builder's grade, against what their fair odds expected. Whether higher grades do better is the
    grade's own test."""
    if df is None or df.empty:
        return {"slips": 0, "graded": 0, "by_grade": []}
    c = df[df["sgp_id"].astype(str).str.startswith("custom")]
    g = c[c["status"].isin(["won", "lost"])]
    rows = []
    for grade, x in g.groupby(g["grade"].fillna("?").str[0]):
        rows.append({"grade": grade, "graded": int(len(x)), "won": int((x["status"] == "won").sum()),
                     "expected": round(float(x["p_fair"].astype(float).sum()), 2),
                     "units": round(float(x["profit_1u"].astype(float).fillna(0).sum()), 2)})
    return {"slips": int(len(c)), "graded": int(len(g)), "won": int((g["status"] == "won").sum()),
            "expected": round(float(g["p_fair"].astype(float).sum()), 2) if len(g) else 0.0,
            "units": round(float(g["profit_1u"].astype(float).fillna(0).sum()), 2) if len(g) else 0.0,
            "by_grade": sorted(rows, key=lambda r: r["grade"])}


def summary(df: pd.DataFrame | None = None) -> dict:
    """The page's app/fun_results document: totals, and the latest graded slips."""
    df = load() if df is None else df
    g = df[df["status"].isin(["won", "lost"])] if len(df) else df
    out = {"slips": int(len(df)), "graded": int(len(g)),
           "won": int((g["status"] == "won").sum()) if len(g) else 0,
           "units_at_quoted_price": round(float(g["profit_1u"].astype(float).sum()), 2) if len(g) else 0.0,
           "expected_hits": round(float(g["p_fair"].astype(float).sum()), 2) if len(g) else 0.0,
           "marked_profit": round(float(g.loc[g["marked"], "profit"].astype(float).sum()), 2) if len(g) else 0.0,
           "recent": []}
    out["custom"] = custom_summary(df)
    out["typical_ratio"] = typical_ratio(df) | {"model": quote_model(df)}
    done = df[df["status"].isin(["won", "lost", "void"])].sort_values("graded_at", ascending=False) if len(df) else df
    for r in done.head(30).itertuples():
        out["recent"].append({"sgp_id": r.sgp_id, "matchup": r.matchup, "book": r.book, "price": r.price,
                              "fair_price": r.fair_price, "p_fair": r.p_fair, "status": r.status, "marked": bool(r.marked),
                              "profit_1u": r.profit_1u, "legs": json.loads(r.leg_results) if isinstance(r.leg_results, str) else []})
    out["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def write_results() -> dict:
    doc = summary()
    (config.EXPORTS_DIR / "fun_results.json").write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    return doc
