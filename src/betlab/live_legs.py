"""Live leg states for the worker: a Python port of the web app's tracker (web/lib/live.ts, live-bets.ts).

The leg push alerts (leg_alerts.py, Oct 24) need each open bet's legs judged while the games are on, and the worker
is what holds the push keys and runs on a clock, so the judging is ported here. ESPN's free scoreboards and game
summaries carry the live score and every player's box score; a bet's game is found on today's board by its teams.

Keep the two in step: tests/fixtures/live_legs.json holds leg labels and game states that both test suites run
(tests/test_live_legs.py and web/tests/live.test.mjs), so a label one side reads and the other doesn't fails a test.
"""

from __future__ import annotations

import math
import re
import time
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

PATHS = {"nfl": "football/nfl", "ncaaf": "football/college-football", "nba": "basketball/nba",
         "ncaab": "basketball/mens-college-basketball", "nhl": "hockey/nhl", "ufc": "mma/ufc",
         "wnba": "basketball/wnba", "mlb": "baseball/mlb"}
SOCCER = {"epl": "eng.1", "la_liga": "esp.1", "serie_a": "ita.1", "bundesliga": "ger.1", "ligue_1": "fra.1",
          "mls": "usa.1", "ucl": "uefa.champions", "uel": "uefa.europa", "uecl": "uefa.europa.conf"}
EXTRA = {"ncaaf": "&groups=80&limit=300", "ncaab": "&groups=50&limit=400"}
BASE = "https://site.api.espn.com/apis/site/v2/sports"
GUESS = ["nfl", "nba", "nhl", "ncaaf", "ncaab", "ufc"]     # a bet that doesn't say its sport

TTL = 50                 # seconds: the alert loop runs every minute
DONE_TTL = 6 * 3600      # a finished game's board or box score never changes
_cache: dict[str, tuple[float, float, dict | None]] = {}


def espn(url: str, ttl: float = TTL) -> dict | None:
    """ESPN JSON through a small cache; None when ESPN fails (the next minute tries again)."""
    import requests

    hit = _cache.get(url)
    if hit and time.time() - hit[0] < hit[1]:
        return hit[2]
    try:
        r = requests.get(url, headers={"User-Agent": "BetLab"}, timeout=10)
        data = r.json() if r.ok else None
    except Exception:  # noqa: BLE001 - ESPN down: no live state this minute
        data = None
    _cache[url] = (time.time(), ttl, data)
    if len(_cache) > 800:
        for k in [k for k, v in _cache.items() if time.time() - v[0] > v[1]]:
            _cache.pop(k, None)
    return data


def _path(sport: str, league: str | None) -> str | None:
    return f"soccer/{SOCCER.get(league or '', league)}" if sport == "soccer" else PATHS.get(sport)


def ymd(t: datetime) -> str:
    return t.astimezone(ET).strftime("%Y%m%d")


def scoreboard(sport: str, league: str | None, days: list[str], get=espn) -> list[dict]:
    """The games on these Eastern days' boards: {key, sport, espn_id, state, detail, start, home, away} with each
    side {name, abbr, score}; a UFC fight per competition, with its winner."""
    p = _path(sport, league)
    if not p:
        return []
    yday = ymd(datetime.now(ET) - timedelta(days=1))
    out = []
    for d in days:
        sb = get(f"{BASE}/{p}/scoreboard?dates={d}{EXTRA.get(sport, '')}", *([DONE_TTL] if d < yday else []))
        for e in (sb or {}).get("events") or []:
            comps = e.get("competitions") or []
            for c in (comps if sport == "ufc" else comps[:1]):
                if not c:
                    continue
                cs = c.get("competitors") or []
                home = next((x for x in cs if x.get("homeAway") == "home"), cs[0] if cs else None)
                away = next((x for x in cs if x.get("homeAway") == "away"), cs[1] if len(cs) > 1 else None)
                if not home or not away:
                    continue

                def side(x):
                    if sport == "ufc":
                        name = (x.get("athlete") or {}).get("displayName") or ""
                        return {"name": name, "abbr": last_name(name), "score": 1 if x.get("winner") else None}
                    s = x.get("score")
                    s = s.get("value") if isinstance(s, dict) else s
                    t = x.get("team") or {}
                    return {"name": t.get("displayName") or "", "abbr": t.get("abbreviation") or "",
                            "score": None if s in (None, "") else float(s),
                            "color": team_color(t.get("color"), t.get("alternateColor")), "logo": t.get("logo")}

                st = (c.get("status") or {}).get("type") or (e.get("status") or {}).get("type") or {}
                g = {"key": f"{sport}:{c.get('id') if sport == 'ufc' else e.get('id')}", "sport": sport,
                     "espn_id": str(e.get("id")), "state": st.get("state") or "pre",
                     "detail": st.get("shortDetail") or st.get("detail") or "", "start": c.get("date") or e.get("date"),
                     "home": side(home), "away": side(away)}
                if sport == "ufc":
                    g["winner"] = "home" if home.get("winner") else "away" if away.get("winner") else None
                    g["result"] = ((c.get("status") or {}).get("result") or {}).get("displayName")
                out.append(g)
    return out


def boxscore(g: dict, league: str | None, get=espn) -> dict:
    """A game's players' stats, {normalized name: {stat: value}} (soccer: from its rosters)."""
    p = _path(g["sport"], league)
    if not p or g["sport"] == "ufc":
        return {}
    s = get(f"{BASE}/{p}/summary?event={g['espn_id']}", *([DONE_TTL] if g["state"] == "post" else []))
    return parse_box(s, g["sport"]) if s else {}


def parse_box(s: dict, sport: str) -> dict:
    out: dict[str, dict[str, float]] = {}

    def put(name, k, v):
        if not name or v is None or not math.isfinite(v):
            return
        row = out.setdefault(norm_name(name), {})
        row[k] = row.get(k, 0) + v

    if sport == "soccer":
        for team in s.get("rosters") or []:
            for pl in team.get("roster") or []:
                for st in pl.get("stats") or []:
                    put((pl.get("athlete") or {}).get("displayName") or "", st.get("name"), _num(st.get("value")))
        play_stats(s, sport, out)
        return out
    for team in (s.get("boxscore") or {}).get("players") or []:
        for grp in team.get("statistics") or []:
            keys = grp.get("keys") or []
            # football: a QB's "sacks" (taken) and "interceptions" (thrown) aren't a defender's (made); Nov 6
            rename = {"passing": {"sacks": "sacksTaken"}, "interceptions": {"interceptions": "interceptionsMade"},
                      "defensive": {}}.get(grp.get("name") or "", {})
            for a in grp.get("athletes") or []:
                name = (a.get("athlete") or {}).get("displayName") or ""
                stats = a.get("stats") or []
                for i, k in enumerate(keys):
                    raw = str(stats[i]) if i < len(stats) and stats[i] is not None else ""
                    if not raw or ":" in raw:                       # clocks (time on ice) aren't counts
                        continue
                    # "6-10", "24/31": both halves (Nov 6: pass attempts and shots attempted were dropped)
                    for kk, vv in zip(re.split(r"[-/]", k), re.split(r"(?<=\d)[-/]", raw)):
                        put(name, rename.get(kk, kk), _num(vv))
    play_stats(s, sport, out)
    return out


GAME = "_game"     # a box's game-wide row: who scored first is decided ("firstBasket", "firstGoal", "firstTd": 1)


def play_stats(s: dict, sport: str, out: dict) -> None:
    """What only ESPN's play-by-play says (Nov 6, Mike: "we can set up smart ways to track those"), added to the box's
    rows: NBA quarter stats ("q1:points", "q2:rebounds", "q3:assists", "q4:threes") and the first basket (the game's
    first field goal; free throws don't count); NHL period stats ("p1:goals", "p1:assists"), power-play goals and
    points and the first goal; NFL longest completion (a QB's longest pass caught) and the first touchdown; soccer's
    first goal. web lib/live.ts playStats and iPhone Live.playStats are the same."""
    def add(name, k, v=1.0):
        if name:
            row = out.setdefault(norm_name(name), {})
            row[k] = row.get(k, 0) + v

    def first(k, name):
        if name and k not in out.get(GAME, {}):
            out.setdefault(GAME, {})[k] = 1.0
            add(name, k)

    if sport == "nba":
        ids = {str((a.get("athlete") or {}).get("id")): (a.get("athlete") or {}).get("displayName") or ""
               for t in (s.get("boxscore") or {}).get("players") or [] for g in t.get("statistics") or [] for a in g.get("athletes") or []}
        for p in s.get("plays") or []:
            q = (p.get("period") or {}).get("number")
            who = [ids.get(str((x.get("athlete") or {}).get("id")), "") for x in p.get("participants") or []]
            typ = (p.get("type") or {}).get("text") or ""
            if p.get("scoringPlay") and who:
                v = float(p.get("scoreValue") or 0)
                add(who[0], f"q{q}:points", v)
                if v >= 2:
                    first("firstBasket", who[0])
                    if v == 3:
                        add(who[0], f"q{q}:threes")
                    if len(who) > 1:
                        add(who[1], f"q{q}:assists")
            elif "Rebound" in typ and who:
                add(who[0], f"q{q}:rebounds")
    elif sport == "nhl":
        for p in s.get("plays") or []:
            if ((p.get("type") or {}).get("text") or "") != "Goal":
                continue
            per = (p.get("period") or {}).get("number")
            who = [(x.get("athlete") or {}).get("displayName") or "" for x in p.get("participants") or []
                   if x.get("type") in ("scorer", "assister", None)]
            if not who:
                continue
            pp = ((p.get("strength") or {}).get("abbreviation") or "") == "power-play"
            first("firstGoal", who[0])
            add(who[0], f"p{per}:goals")
            if pp:
                add(who[0], "ppGoals")
            for a in who[1:]:
                add(a, f"p{per}:assists")
            for x in who if pp else []:
                add(x, "ppPoints")
    elif sport == "nfl":
        names = [n for n in out if n != GAME]
        for d in ((s.get("drives") or {}).get("previous") or []):
            for p in d.get("plays") or []:
                typ = ((p.get("type") or {}).get("text") or "")
                if typ not in ("Pass Reception", "Passing Touchdown"):
                    continue
                if m := re.search(r"([A-Z][a-zA-Z'-]*)\.\s?([A-Za-z'.-]+(?:\s(?:Jr|Sr|II|III|IV)\.?)?) pass", p.get("text") or ""):
                    qb = next((n for n in names if n.startswith(m[1][0].lower()) and plain(m[2]) in n.split()), None)
                    y = _num(p.get("statYardage"))
                    if qb and y is not None:
                        row = out[qb]
                        row["longCompletion"] = max(row.get("longCompletion", 0), y)
        for p in s.get("scoringPlays") or []:
            if "Touchdown" in ((p.get("type") or {}).get("text") or "") and (m := re.match(r"^(.+?) \d+ Yd", p.get("text") or "")):
                first("firstTd", m[1])
                break
    elif sport == "soccer":
        for k in s.get("keyEvents") or []:
            typ = ((k.get("type") or {}).get("text") or "").lower()
            if typ == "goal" or (k.get("scoringPlay") and "own" not in typ and "goal" in typ):
                who = [(x.get("athlete") or {}).get("displayName") or "" for x in k.get("participants") or []]
                if who:
                    first("firstGoal", who[0])
                    break


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ names

def plain(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_name(s) -> str:
    return " ".join(t for t in plain(s).split() if t not in SUFFIX)


def last_name(s) -> str:
    t = norm_name(s).split()
    return t[-1] if t else ""


def find_player(box: dict, name: str):
    """A player in a box score: exact name, else first initial + last name, else a unique last name."""
    n = norm_name(name)
    if n in box:
        return box[n]
    parts = n.split()
    if not parts:
        return None
    first, last = parts[0], parts[-1]
    by_initial = [k for k in box if k.split()[-1:] == [last] and k[:1] == first[:1]]
    if len(by_initial) == 1:
        return box[by_initial[0]]
    by_last = [k for k in box if k.split()[-1:] == [last]]
    return box[by_last[0]] if len(by_last) == 1 else None


ALIAS = {"njd": "nj", "sjs": "sj", "tbl": "tb", "lak": "la", "wsh": "wsh", "vgk": "vgk", "uta": "utah", "clb": "cbj"}
# The books' club names ESPN writes differently (plain form -> ESPN's display name; web lib/live.ts CLUB_ALIASES,
# iPhone SoccerClubs.aliases): a slip's "Rennes" is ESPN's "Stade Rennais" (Oct 30: that game's legs never tracked).
CLUB_ALIASES = {
    "1 fc koln": "FC Cologne", "agf aarhus": "AGF", "athletic bilbao": "Athletic Club",
    "brighton and hove albion": "Brighton & Hove Albion", "fc copenhagen": "F.C. København", "hamburger sv": "Hamburg SV",
    "hapoel be er sheva": "Hapoel Be'er", "los angeles fc": "LAFC", "new york red bulls": "Red Bull New York",
    "omonoia fc": "Omonia Nicosia", "pfc cska sofia": "CSKA Sofia", "pfc levski sofia": "Levski Sofia",
    "sporting lisbon": "Sporting CP", "union saint gilloise": "Union St.-Gilloise", "universitatea craiova": "CSU Craiova",
    "inter milan": "Internazionale", "fc iberia 1999": "Iberia 1999", "rennes": "Stade Rennais",
    "olympiakos piraeus": "Olympiacos", "hearts": "Heart of Midlothian", "fc nordsjaelland": "FC Nordsjælland",
    "koln": "FC Cologne", "copenhagen": "F.C. København",
}
GENERIC = {"fc", "cf", "sc", "ac", "club", "city", "united", "real", "de", "sporting", "athletic", "the", "of", "st"}


def team_match(ours: str, side: dict) -> int:
    """How well our team text ("Chicago Bears", "CHI", "Inter Milan", a fighter's name) names this side: 3 the full
    name or abbreviation, 2 the nickname or last name, 1 a shared strong word, 0 not at all."""
    o = plain(ours)
    if not o:
        return 0
    abbr, full = plain(side.get("abbr")), plain(side.get("name"))
    if o in (abbr, full) or ALIAS.get(o) == abbr or (o in CLUB_ALIASES and plain(CLUB_ALIASES[o]) == full):
        return 3
    ot, ft = o.split(), full.split()
    if len(ot) > 1 and ft and ot[-1] == ft[-1] and ot[-1] not in GENERIC:      # nickname / last name
        return 2

    def strong(t):
        return len(t) >= 4 and t not in GENERIC

    return 1 if any(strong(t) and t in ft for t in ot) and any(strong(t) and t in ot for t in ft) else 0


def is_team(ours: str, side: dict) -> bool:
    return team_match(ours, side) > 0


def side_of(ours: str, g: dict) -> str | None:
    """Which side of a game our team text names: the better match when both do (Oct 24: "LSU Tigers" at Auburn
    Tigers read as Auburn by the shared nickname); a tie names no side."""
    h, a = team_match(ours, g["home"]), team_match(ours, g["away"])
    return None if h == a else "home" if h > a else "away"


def find_game(games: list[dict], matchup: str) -> dict | None:
    """Our matchup "Away @ Home" / "A vs B" on a scoreboard; a game in progress first."""
    parts = re.split(r" @ | vs\.? | v ", str(matchup))
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    x, y = parts[0], parts[1]
    hits = [(game_match(g, x, y), g) for g in games]
    hits = [(m, g) for m, g in hits if m > 0]
    order = {"in": 0, "pre": 1}
    # the best-named game first (Oct 24: "Boise State Broncos @ Washington State Cougars" matched Sacramento State @
    # Ball State by the shared word "State", live first), then a game in progress first
    return sorted(hits, key=lambda h: (-h[0], order.get(h[1]["state"], 2)))[0][1] if hits else None


def game_match(g: dict, x: str, y: str) -> int:
    """How well our matchup names a game: both teams must match (either way round); the sum of the two, else 0."""
    fwd = (team_match(x, g["away"]) + team_match(y, g["home"])) if min(team_match(x, g["away"]), team_match(y, g["home"])) else 0
    rev = (team_match(x, g["home"]) + team_match(y, g["away"])) if min(team_match(x, g["home"]), team_match(y, g["away"])) else 0
    return max(fwd, rev)


# ------------------------------------------------------------------------------------------------- legs

STAT_WORDS = sorted(["receiving yds", "rushing yds", "passing yds", "receptions", "pts + reb + ast", "pts + reb",
                     "pts + ast", "reb + ast", "points", "rebounds", "assists", "threes", "steals", "blocks",
                     "shots on target", "shots on goal", "shots", "saves", "goals", "passing tds", "rush + rec yds",
                     # Nov 6 (Mike: "track more stats... all possible markets"): what ESPN's box scores carry
                     "longest reception", "longest rush", "rush attempts", "pass attempts", "completions", "interceptions",
                     "tackles", "sacks", "kicking points", "field goals made", "turnovers", "stl + blk", "free throws made",
                     "offensive rebounds", "blocked shots", "hits", "fouls", "longest completion", "power play points",
                     "power play goals",
                     # Nov 9: touchdowns by count ("2+ TDs", "1+ rushing TDs"); a rusher's and receiver's together
                     "touchdowns", "rushing tds", "receiving tds"]
                    # quarter and half (NBA) and period (NHL) stats from the play-by-play: "1q points", "2h rebounds", "1p goals"
                    + [f"{n}q {w}" for n in range(1, 5) for w in ("points", "rebounds", "assists", "threes")]
                    + [f"{n}h {w}" for n in (1, 2) for w in ("points", "rebounds", "assists", "threes")]
                    + [f"{n}p {w}" for n in range(1, 4) for w in ("goals", "assists", "points")],
                    key=len, reverse=True)
# the stats a "most ... in the game" leg can be about (Nov 6): one player's count against everyone else's in the box
LEADER_WORDS = ("receiving yds", "rushing yds", "passing yds", "receptions", "points", "rebounds", "assists", "threes",
                "shots on goal", "shots", "goals")


# (pattern at the end of a leg, our stat words): the same list in web lib/live.ts ALIASES and iPhone Live.aliases
ALIASES = [
    (r"\s+(?:points\s*\+\s*rebounds\s*\+\s*assists|pts\s*\+\s*rebs?\s*\+\s*asts?|pra)(?=$|\s+(?:over|under)\s+\d)", " pts + reb + ast"),
    (r"\s+(?:points\s*\+\s*rebounds|pts\s*\+\s*rebs?)(?=$|\s+(?:over|under)\s+\d)", " pts + reb"),
    (r"\s+(?:points\s*\+\s*assists|pts\s*\+\s*asts?)(?=$|\s+(?:over|under)\s+\d)", " pts + ast"),
    (r"\s+(?:rebounds\s*\+\s*assists|rebs?\s*\+\s*asts?)(?=$|\s+(?:over|under)\s+\d)", " reb + ast"),
    (r"\s+(?:steals\s*\+\s*blocks|blocks\s*\+\s*steals|stl\s*\+\s*blk|stocks)(?=$|\s+(?:over|under)\s+\d)", " stl + blk"),
    (r"\s+(?:threes\s+made|made\s+threes|three[\s-]*pointers(?:\s+made)?|3[\s-]*pointers(?:\s+made)?|3pt\s+made|3pm)(?=$|\s+(?:over|under)\s+\d)", " threes"),
    (r"\s+(?:longest\s+(?:reception|catch|rec)|long\s+reception)(?:\s+(?:yds|yards))?(?=$|\s+(?:over|under)\s+\d)", " longest reception"),
    (r"\s+(?:longest\s+(?:rush|rushing\s+attempt|run)|long\s+rush)(?:\s+(?:yds|yards))?(?=$|\s+(?:over|under)\s+\d)", " longest rush"),
    (r"\s+(?:rushing\s+attempts|rush\s+attempts|carries)(?=$|\s+(?:over|under)\s+\d)", " rush attempts"),
    (r"\s+(?:passing\s+attempts|pass\s+attempts)(?=$|\s+(?:over|under)\s+\d)", " pass attempts"),
    (r"\s+(?:pass(?:ing)?\s+completions|completions)(?=$|\s+(?:over|under)\s+\d)", " completions"),
    (r"\s+(?:interceptions\s+thrown|passing\s+interceptions|ints?\s+thrown)(?=$|\s+(?:over|under)\s+\d)", " interceptions"),
    (r"\s+(?:tackles\s*(?:\+|and|&)\s*assists|total\s+tackles|tackles)(?=$|\s+(?:over|under)\s+\d)", " tackles"),
    (r"\s+(?:made\s+field\s+goals|field\s+goals(?:\s+made)?|fgm)(?=$|\s+(?:over|under)\s+\d)", " field goals made"),
    (r"\s+(?:made\s+free\s+throws|free\s+throws(?:\s+made)?|ftm)(?=$|\s+(?:over|under)\s+\d)", " free throws made"),
    (r"\s+(?:offensive\s+rebounds|off\s+rebounds)(?=$|\s+(?:over|under)\s+\d)", " offensive rebounds"),
    (r"\s+(?:fouls\s+committed|fouls)(?=$|\s+(?:over|under)\s+\d)", " fouls"),
    (r"\s+(?:longest\s+(?:pass\s+)?completion|longest\s+pass(?:\s+completed)?)(?:\s+(?:yds|yards))?(?=$|\s+(?:over|under)\s+\d)", " longest completion"),
    (r"\s+(?:power[\s-]*play\s+points|pp\s+points|ppp)(?=$|\s+(?:over|under)\s+\d)", " power play points"),
    (r"\s+(?:power[\s-]*play\s+goals|pp\s+goals|ppg)(?=$|\s+(?:over|under)\s+\d)", " power play goals"),
    # Nov 9: short forms ("25+ Pts", "Over 2.5 SOG") and touchdowns by kind ("2+ Passing Touchdowns", "1+ rushing TDs"); a
    # combo's last word ("pts + reb") is left alone
    (r"(?<!\s\+)\s+pts(?=$|\s+(?:over|under)\s+\d)", " points"),
    (r"(?<!\s\+)\s+rebs?(?=$|\s+(?:over|under)\s+\d)", " rebounds"),
    (r"(?<!\s\+)\s+asts?(?=$|\s+(?:over|under)\s+\d)", " assists"),
    (r"\s+sog(?=$|\s+(?:over|under)\s+\d)", " shots on goal"),
    (r"\s+sot(?=$|\s+(?:over|under)\s+\d)", " shots on target"),
    (r"\s+(?:passing\s+(?:touchdowns|tds?)|pass\s+tds?)(?=$|\s+(?:over|under)\s+\d)", " passing tds"),
    (r"\s+(?:rushing\s+(?:touchdowns|tds?)|rush\s+tds?)(?=$|\s+(?:over|under)\s+\d)", " rushing tds"),
    (r"\s+(?:receiving\s+(?:touchdowns|tds?)|rec\s+tds?)(?=$|\s+(?:over|under)\s+\d)", " receiving tds"),
    (r"(?<=[\d+])\s+(?:touchdowns|tds?)(?=$|\s+(?:over|under)\s+\d)", " touchdowns"),
    # "1st quarter points", "first half rebounds", "1Q assists", "1st period goals" (one word each: "1q points", "1p goals")
    (r"\s+(?:(1)st|(2)nd|(3)rd|(4)th|first|second|third|fourth|q([1-4])|([1-4])q)\s*(quarter|qtr|half|period)?\s+"
     r"(points|rebounds|assists|threes|goals)(?=$|\s+(?:over|under)\s+\d)", None),
]


WORD_N = {"first": "1", "second": "2", "third": "3", "fourth": "4"}


def _period(m: re.Match) -> str:
    """"1st quarter points" -> " 1q points", "first half rebounds" -> " 1h rebounds", "1st period goals" -> " 1p goals"; a
    bare "1Q points" is a quarter. Halves exist for 1 and 2 only."""
    n = next((g for g in m.groups()[:6] if g), None) or WORD_N.get(m[0].split()[0].lower(), "1")
    unit = (m[7] or "quarter").lower()
    k = "h" if unit == "half" else "p" if unit == "period" else "q"
    return f" {n}{k} {m[8].lower()}"


def canon_stat(label: str) -> str:
    """The stat's wording as books and slips write it, made ours (web lib/live.ts canonStat, Oct 25):
    rushing + receiving / rush & rec -> "rush + rec yds", "... yards" -> "... yds"."""
    l = re.sub(r"\s+(?:rushing|rush)\s*(?:\+|&|and)\s*(?:receiving|rec)(?:\s+(?:yds|yards))?$", " rush + rec yds", str(label).strip(), flags=re.I)
    l = re.sub(r"\s+(rushing|receiving|passing)\s+yards(?=$|\s+(?:over|under)\s+\d)", lambda m: f" {m[1].lower()} yds", l, flags=re.I)
    # "X Anytime Touchdown Scorer", "X anytime TD scorer" (Nov 9): ours is "X anytime TD"
    l = re.sub(r"^(.+?)\s+anytime\s+(?:touchdown|td)(?:\s+scorer)?$", r"\1 anytime TD", l, flags=re.I)
    # an anytime scorer (Oct 25: "Lamine Yamal anytime goalscorer" wasn't tracked): one goal is the line
    l = re.sub(r"^(?!both teams\b)(.+?)\s+(?:anytime\s+(?:goal\s*scorer|goal|scorer)|to\s+score(?:\s+a\s+goal)?|anytime\s+to\s+score)$",
               r"\1 1+ goals", l, flags=re.I)
    # Nov 6: the books' other wordings of the stats tracked, made ours (each tested in tests/fixtures/live_legs.json)
    for pat, ours in ALIASES:
        l = re.sub(pat, ours if ours is not None else _period, l, flags=re.I)
    # "To Record Double Double", "double-double" (Oct 25, Mike's Towns leg): one wording
    return re.sub(r"^(.+?)\s+(?:to\s+record\s+(?:an?\s+)?)?(double|triple)[\s-]*double$", lambda m: f"{m[1]} {m[2].lower()}-double",
                  l, flags=re.I)


# A part of a game ("1H", "1st quarter", "2nd period", "first 5 innings", "60 min", "regulation"): a team's line on it isn't
# the full game's, so it's not tracked rather than judged on the final score (Nov 9). web SEGMENT, iPhone Live.segment.
SEGMENT = re.compile(r"(?:^|[\s(])(?:(?:1st|2nd|3rd|4th|first|second|third|fourth)\s+(?:half|quarter|qtr|period|inning)s?"
                     r"|[1-4][hqp]|[qp][1-4]|first\s+\d+\s+innings?|f5|60[\s-]*min(?:ute)?s?|regulation(?:\s+time)?)\)?(?=$|[\s)])", re.I)


def parse_leg(label: str) -> dict | None:
    """A leg label as web/lib/live.ts parseLeg reads it (same keys)."""
    l = canon_stat(label)
    if re.fullmatch(r"both teams to score(?:: ?yes)?", l, re.I):
        return {"kind": "btts"}
    if re.fullmatch(r"both teams to score: ?no", l, re.I):       # Nov 4: Build offers these three; none tracked
        return {"kind": "btts_no"}
    if re.fullmatch(r"draw", l, re.I):
        return {"kind": "draw"}
    if re.fullmatch(r"no draw", l, re.I):                         # Nov 9: Novig's 3-way "no" sides (novig_sync)
        return {"kind": "no_draw"}
    if m := re.fullmatch(r"(.+) not to win", l, re.I):
        return {"kind": "not_win", "team": m[1]}
    if m := re.fullmatch(r"(.+) or draw", l, re.I):
        return {"kind": "draw_or", "team": m[1]}
    if m := re.fullmatch(r"(over|under) (\d+(?:\.\d+)?)(?: (?:total points|total goals|total|goals|points|runs|rounds))?", l, re.I):
        return {"kind": "total", "side": m[1].lower(), "point": float(m[2])}
    if m := re.fullmatch(r"(.+) anytime TD", l, re.I):
        return {"kind": "td", "player": m[1], "first": False}
    if m := re.fullmatch(r"(.+?) (?:first TD scorer|first touchdown(?: scorer)?|to score (?:the )?first (?:TD|touchdown))", l, re.I):
        return {"kind": "td", "player": m[1], "first": True}
    if m := re.fullmatch(r"(.+?) (?:to (?:make|score) (?:the )?)?first (basket|field goal|fg)(?: scorer)?", l, re.I):
        return {"kind": "first", "player": m[1], "what": "basket"}
    if m := re.fullmatch(r"(.+?) (?:to score (?:the )?)?first (?:goal\s*scorer|goal)", l, re.I):
        return {"kind": "first", "player": m[1], "what": "goal"}
    if m := re.fullmatch(r"(.+) to score or assist", l, re.I):
        return {"kind": "goal_or_assist", "player": m[1]}
    # "X most receiving yds", "X to have the most receiving yards in the game" (Nov 6, Mike: "most rcv/rush yards in game")
    if m := re.fullmatch(r"(.+?) (?:to (?:have|record|get) )?(?:the )?most (.+?)(?: in (?:the )?game)?", l, re.I):
        w = canon_stat("x " + m[2])[2:].lower()
        if w in LEADER_WORDS:
            return {"kind": "leader", "player": m[1], "stat": w}
    if m := re.fullmatch(r"(.+?) to (?:be (?:carded|booked|shown a card)|receive a card|get a card)", l, re.I):
        return {"kind": "card", "player": m[1]}
    if m := re.fullmatch(r"(.+) (double|triple)-double", l, re.I):
        return {"kind": "double", "player": m[1], "n": 2 if m[2].lower() == "double" else 3}
    for w in STAT_WORDS:          # the stat before its number ("Puka Nacua longest reception over 22.5"): ours puts it last
        if m := re.fullmatch(rf"(.+?) {re.escape(w)} (over|under) (\d+(?:\.\d+)?)", l, re.I):
            l = f"{m[1]} {m[2]} {m[3]} {w}"
            break
    for w in STAT_WORDS:
        if not l.lower().endswith(" " + w):
            continue
        head = l[: len(l) - len(w) - 1]
        m = re.fullmatch(r"(.+?) (\d+)\+", head) or re.fullmatch(r"(.+?) (over|under) (\d+(?:\.\d+)?)", head, re.I)
        if m and SEGMENT.search(m[1]):       # "Knicks 1H over 55.5 points": a part of the game, not tracked
            return None
        if m and m.lastindex == 2:
            return {"kind": "prop", "player": m[1], "stat": w, "side": "over", "need": int(m[2]), "point": int(m[2]) - 0.5}
        if m:
            pt = float(m[3])
            return {"kind": "prop", "player": m[1], "stat": w, "side": m[2].lower(), "need": math.floor(pt) + 1, "point": pt}
    team = None
    if m := re.fullmatch(r"(.+) (?:ML|to win)", l, re.I):
        team = {"kind": "ml", "team": m[1]}
    elif m := re.fullmatch(r"(.+) ([+-]\d+(?:\.\d+)?)", l):
        team = {"kind": "spread", "team": m[1], "point": float(m[2])}
    elif m := re.fullmatch(r"(.+) (?:pk|pick'?em|pick)", l, re.I):     # "Chiefs PK": a spread of 0 (Nov 9)
        team = {"kind": "spread", "team": m[1], "point": 0.0}
    return None if team and SEGMENT.search(team["team"]) else team


def stat_value(row: dict, stat: str, sport: str) -> float | None:
    def v(*ks):
        return sum(row.get(k, 0) for k in ks)

    def has(k):
        return k in row

    simple = {"passing yds": "passingYards", "rushing yds": "rushingYards", "receiving yds": "receivingYards",
              "receptions": "receptions", "passing tds": "passingTouchdowns", "rebounds": "rebounds",
              "threes": "threePointFieldGoalsMade", "steals": "steals", "blocks": "blocks", "shots on goal": "shotsTotal",
              "shots on target": "shotsOnTarget", "saves": "saves",
              # Nov 6: ESPN's box keys (parse_box keeps both halves of "completions/passingAttempts")
              "longest reception": "longReception", "longest rush": "longRushing", "rush attempts": "rushingAttempts",
              "pass attempts": "passingAttempts", "completions": "completions", "interceptions": "interceptions",
              "tackles": "totalTackles", "sacks": "sacks", "kicking points": "totalKickingPoints",
              "turnovers": "turnovers", "free throws made": "freeThrowsMade", "offensive rebounds": "offensiveRebounds",
              "blocked shots": "blockedShots", "hits": "hits", "fouls": "foulsCommitted",
              "longest completion": "longCompletion", "power play points": "ppPoints", "power play goals": "ppGoals"}
    if stat in simple:
        return v(simple[stat]) if has(simple[stat]) else None
    if stat == "rush + rec yds":
        return v("rushingYards", "receivingYards") if has("rushingYards") or has("receivingYards") else None
    if stat in ("touchdowns", "rushing tds", "receiving tds"):      # Nov 9: a player's own scores, rushing and receiving
        ks = {"touchdowns": ("rushingTouchdowns", "receivingTouchdowns"), "rushing tds": ("rushingTouchdowns",),
              "receiving tds": ("receivingTouchdowns",)}[stat]
        return v(*ks) if any(has(k) for k in ks) else None
    if stat == "points":
        return v("goals", "assists") if sport == "nhl" else v("points") if has("points") else None
    if stat == "assists":
        return v("assists") if has("assists") else v("goalAssists") if sport == "soccer" and has("goalAssists") else None
    if stat in ("pts + reb", "pts + ast", "pts + reb + ast"):
        ks = {"pts + reb": ("points", "rebounds"), "pts + ast": ("points", "assists"),
              "pts + reb + ast": ("points", "rebounds", "assists")}[stat]
        return v(*ks) if has("points") else None
    if pm := re.fullmatch(r"([1-4])([qhp]) (points|rebounds|assists|threes|goals)", stat):
        n, k, w = int(pm[1]), pm[2], pm[3]
        if k == "p":                       # NHL periods: points are goals plus assists
            ws = ("goals", "assists") if w == "points" else (w,)
            return sum(row.get(f"p{n}:{x}", 0) for x in ws)
        qs = (1, 2) if k == "h" and n == 1 else (3, 4) if k == "h" else (n,)
        return sum(row.get(f"q{q}:{w}", 0) for q in qs)
    if stat == "stl + blk":
        return v("steals", "blocks") if has("steals") or has("blocks") else None
    if stat == "field goals made":      # basketball's made shots, football's kicks: the same ESPN key
        return v("fieldGoalsMade") if has("fieldGoalsMade") else None
    if stat == "reb + ast":
        return v("rebounds", "assists") if has("rebounds") else None
    if stat == "shots":
        if sport == "soccer":
            return v("totalShots") if has("totalShots") else None
        return v("shotsTotal") if has("shotsTotal") else None
    if stat == "goals":
        if sport == "soccer":
            return v("totalGoals") if has("totalGoals") else None
        return v("goals") if has("goals") else None
    return None


def first_state(row: dict | None, box: dict | None, key: str, final: bool, unit: str) -> dict:
    """A first scorer leg (first TD, basket or goal) from the play-by-play's mark (play_stats): won once his is first,
    lost once someone else's is (or the game ends with none)."""
    mine, taken = bool(row and row.get(key)), bool((box or {}).get(GAME, {}).get(key))
    status = "won" if mine else "lost" if taken or final else "live"
    text = "Scored first" if mine else "Someone else scored first" if taken else f"No {unit} yet" if not final else f"No {unit}"
    return {"status": status, "current": 1 if mine else 0, "target": 1, "unit": unit, "text": text}


DOUBLE_CATS = [("points", "pts"), ("rebounds", "reb"), ("assists", "ast"), ("steals", "stl"), ("blocks", "blk")]


def double_state(row: dict | None, n: int, final: bool) -> dict:
    """A double-double (n 2) or triple-double (n 3): web lib/live.ts doubleState."""
    vals = sorted(({"u": u, "v": (row or {}).get(k, 0)} for k, u in DOUBLE_CATS), key=lambda x: -x["v"])
    at10 = sum(1 for x in vals if x["v"] >= 10)
    keep = max(n, 2) + (1 if n == 2 else 0)
    shown = " · ".join(f"{_fmt(x['v'])} {x['u']}" for i, x in enumerate(vals[:keep]) if x["v"] > 0 or i < n)
    short = ", ".join(f"{_fmt(10 - x['v'])} {x['u']}" for x in [x for x in vals if x["v"] < 10][:max(n - at10, 0)])
    done = at10 >= n
    text = f"Done: {shown}" if done else "No stats yet" if not row else f"{shown} · {short} {'short' if final else 'to go'}"
    return {"status": "won" if done else "lost" if final else "live", "current": min(at10, n), "target": n,
            "unit": "at 10+", "text": text}


UNIT = {"passing yds": "pass yds", "rushing yds": "rush yds", "receiving yds": "rec yds", "rush + rec yds": "yds",
        "receptions": "rec", "points": "pts", "rebounds": "reb", "assists": "ast", "threes": "3PM", "pts + reb": "P+R",
        "pts + ast": "P+A", "reb + ast": "R+A", "pts + reb + ast": "PRA", "shots on target": "SOT",
        "shots on goal": "SOG", "shots": "shots", "saves": "saves", "goals": "goals", "passing tds": "pass TD",
        "longest reception": "long rec", "longest rush": "long rush", "rush attempts": "carries", "pass attempts": "att",
        "completions": "cmp", "interceptions": "INT", "tackles": "tkl", "sacks": "sacks", "kicking points": "kick pts",
        "field goals made": "FGM", "turnovers": "TO", "stl + blk": "S+B", "free throws made": "FTM",
        "offensive rebounds": "OREB", "blocked shots": "BLK", "hits": "hits", "fouls": "fouls", "longest completion": "long cmp",
        "power play points": "PPP", "power play goals": "PPG", "touchdowns": "TD", "rushing tds": "rush TD",
        "receiving tds": "rec TD"}


def team_color(primary: str | None, alternate: str | None) -> str | None:
    """A team's color for a band ("#rrggbb"): the first of ESPN's two that's neither near black nor near white
    (Live.teamColor in the iPhone app)."""
    def lum(h: str) -> float:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    for c in (primary, alternate):
        if isinstance(c, str) and re.fullmatch(r"[0-9a-fA-F]{6}", c) and 0.08 < lum(c) < 0.85:
            return "#" + c
    return None


def _fmt(x) -> str:
    return str(int(x)) if x is not None and float(x).is_integer() else str(x)


def total_state(total: float, side: str, point: float, final: bool, unit: str) -> dict:
    """A game total or a team's total against its line; landing on a whole-number line at the final is a push (void),
    as the grader settles it (fun_ledger), not a loss (Nov 9)."""
    over = total > point
    if final and total == point:
        status = "void"
    elif side == "over":
        status = "won" if over else "lost" if final else "live"
    else:
        status = "lost" if over else "won" if final else "live"
    return {"status": status, "current": total, "unit": unit,
            "target": math.floor(point) + 1 if side == "over" else point,
            "text": f"Push at {_fmt(total)}" if status == "void" else f"{_fmt(total)} of {_fmt(point)}"}


FOOTBALL = ("nfl", "ncaaf")


def judge(label: str, g: dict | None, box: dict | None) -> dict:
    """One leg's live state ({label, status, current, target, unit, text}); status as the web's LegStatus."""
    p = parse_leg(label)
    base = {"label": label, "current": None, "target": None, "unit": "", "text": "", "game": g["key"] if g else None}
    if not g:
        return base | {"status": "pending", "text": "Not live today"}
    if not p:
        pre = g["state"] == "pre"
        return base | {"status": "pending" if pre else "unknown", "text": "Not started" if pre else "Not tracked"}
    final, pre = g["state"] == "post", g["state"] == "pre"
    hs, as_ = g["home"].get("score") or 0, g["away"].get("score") or 0

    def lead(s):
        return hs - as_ if s == "home" else as_ - hs

    def outcome(margin):
        if final:
            return "won" if margin > 0 else "lost" if margin < 0 else "void"
        return "winning" if margin > 0 else "losing" if margin < 0 else "tied"

    if p["kind"] == "ml":
        s = side_of(p["team"], g)
        if not s:
            return base | {"status": "unknown", "text": "Team not found"}
        if g["sport"] == "ufc":
            w = g.get("winner")
            if final:
                return base | {"status": "won" if w == s else "lost" if w else "void", "text": g.get("result") or g["detail"]}
            return base | {"status": "pending" if pre else "live", "text": g["detail"]}
        if pre:
            return base | {"status": "pending", "text": "Not started"}
        st = outcome(lead(s))
        status = "lost" if g["sport"] == "soccer" and st == "void" else st     # soccer's "to win" is 3-way
        d = lead(s)
        return base | {"status": status, "current": d,
                       "text": (f"{'Up' if d > 0 else 'Down' if d < 0 else 'Level'} {_fmt(abs(d)) if d else ''}").strip()}
    if p["kind"] == "spread":
        s = side_of(p["team"], g)
        if not s:
            return base | {"status": "unknown", "text": "Team not found"}
        if pre:
            return base | {"status": "pending", "text": "Not started"}
        m = lead(s) + p["point"]
        return base | {"status": outcome(m), "current": lead(s),
                       "text": f"Covering by {_fmt(m)}" if m > 0 else f"Short by {_fmt(-m)}" if m < 0 else "Right on the number"}
    if p["kind"] in ("draw", "draw_or", "btts_no", "no_draw", "not_win"):
        if pre:
            return base | {"status": "pending", "text": "Not started"}
        if p["kind"] == "btts_no":
            both = hs > 0 and as_ > 0
            return base | {"status": "lost" if both else "won" if final else "live",
                           "text": "Both scored" if both else f"{_fmt(hs)}-{_fmt(as_)}"}
        s = side_of(p["team"], g) if p["kind"] in ("draw_or", "not_win") else "home"
        if not s:
            return base | {"status": "unknown", "text": "Team not found"}
        d = lead(s)
        hit = {"draw": hs == as_, "no_draw": hs != as_, "draw_or": d >= 0, "not_win": d <= 0}[p["kind"]]
        return base | {"status": ("won" if hit else "lost") if final else "winning" if hit else "losing",
                       "text": "Level" if d == 0 else f"{_fmt(hs)}-{_fmt(as_)}" if d > 0 else f"{_fmt(as_)}-{_fmt(hs)}"}
    if p["kind"] in ("total", "btts"):
        if pre:
            return base | {"status": "pending", "text": "Not started", "target": p.get("point")}
        total = hs + as_
        if p["kind"] == "btts":
            both = hs > 0 and as_ > 0
            return base | {"status": "won" if both else "lost" if final else "live",
                           "text": "Both scored" if both else f"{_fmt(hs)}-{_fmt(as_)}"}
        return base | total_state(total, p["side"], p["point"], final, "total")
    # player legs
    if pre:
        unit = (UNIT.get(p.get("stat"), p.get("stat")) if p["kind"] in ("prop", "leader") else "TD" if p["kind"] == "td"
                else p["what"] if p["kind"] == "first"
                else "at 10+" if p["kind"] == "double" else "card" if p["kind"] == "card" else "G+A")
        target = p["need"] if p["kind"] == "prop" else p["n"] if p["kind"] == "double" else None if p["kind"] == "leader" else 1
        return base | {"status": "pending", "current": 0, "target": target, "unit": unit, "text": "Not started"}
    row = find_player(box, p["player"]) if box else None
    if row is None and p["kind"] == "prop":
        # a team's own total ("New York Knicks over 110.5 points", Nov 9): the team's score, not a player named after it
        side = side_of(p["player"], g)
        if side and team_match(p["player"], g[side]) >= 2:
            if p["stat"] not in ("points", "goals"):
                return base | {"status": "unknown", "text": "Not tracked"}
            return base | total_state(g[side].get("score") or 0, p["side"], p["point"], final, UNIT[p["stat"]])
    players = [k for k in (box or {}) if k != GAME]
    if row is None and not players and final:
        return base | {"status": "unknown", "text": "No box score"}    # ESPN's box didn't come: never a guess
    # Nov 9: a basketball, hockey or soccer box lists everyone who dressed, so a player missing from it didn't play (yet):
    # void at the final, as the books settle it; football's leaves out players with no stats, so there he counts 0
    if row is None and players and g["sport"] not in FOOTBALL:
        taken = p["kind"] == "first" and (box or {}).get(GAME, {}).get("firstBasket" if p.get("what") == "basket" else "firstGoal")
        if not taken:
            return base | ({"status": "void", "text": "Didn't play"} if final
                           else {"status": "pending", "current": 0, "text": "Not in the box score yet"})
    if p["kind"] == "double":
        return base | double_state(row, p["n"], final)
    if p["kind"] == "td":
        tds = (row.get("rushingTouchdowns", 0) + row.get("receivingTouchdowns", 0)) if row else 0
        if p["first"]:          # Nov 6: the scoring plays say whose TD was first (it read "Scored: check if first")
            return base | first_state(row, box, "firstTd", final, "TD")
        return base | {"status": "won" if tds >= 1 else "lost" if final else "live", "current": tds, "target": 1,
                       "unit": "TD", "text": "Scored" if tds else "No TD yet"}
    if p["kind"] == "goal_or_assist":
        n = (row.get("totalGoals", 0) + row.get("goalAssists", 0)) if row else 0
        return base | {"status": "won" if n >= 1 else "lost" if final else "live", "current": n, "target": 1,
                       "unit": "G+A", "text": "Done" if n else "Not yet"}
    if p["kind"] == "first":
        return base | first_state(row, box, "firstBasket" if p["what"] == "basket" else "firstGoal", final,
                                  "basket" if p["what"] == "basket" else "goal")
    if p["kind"] == "card":
        n = (row.get("yellowCards", 0) + row.get("redCards", 0)) if row else 0
        return base | {"status": "won" if n >= 1 else "lost" if final else "live", "current": n, "target": 1,
                       "unit": "card", "text": "Carded" if n else "No card" if final else "No card yet"}
    if p["kind"] == "leader":
        mine = (stat_value(row, p["stat"], g["sport"]) or 0) if row else 0
        others = [stat_value(r, p["stat"], g["sport"]) or 0 for r in (box or {}).values() if r is not row]
        best = max(others, default=0)
        unit = UNIT.get(p["stat"], p["stat"])
        ahead = mine - best
        if final and ahead == 0 and mine > 0:
            # a tie for the most is a dead heat: the books pay a share, so it's a win (as the grader reads it) that the
            # tracker never settles at the full price (rollup leaves `deadHeat` to the grader; Nov 9)
            return base | {"status": "won", "deadHeat": True, "current": mine, "target": best, "unit": unit,
                           "text": f"Dead heat at {_fmt(mine)}"}
        if final:
            status = "won" if ahead > 0 else "lost"
        else:
            status = "winning" if ahead > 0 else "tied" if ahead == 0 and mine > 0 else "losing"
        text = (f"Most, by {_fmt(ahead)}" if ahead > 0 else f"Tied for most at {_fmt(mine)}" if ahead == 0 and mine > 0
                else f"{_fmt(-ahead)} behind the leader")
        return base | {"status": status, "current": mine, "target": best + (1 if ahead <= 0 else 0), "unit": unit, "text": text}
    val = stat_value(row, p["stat"], g["sport"]) if row else None
    cur = val or 0                                          # not in the box yet = 0
    unit = UNIT.get(p["stat"], p["stat"])
    if final and cur == p["point"]:                         # a whole-number line hit exactly: a push (Nov 9)
        return base | {"status": "void", "current": cur, "target": p["point"], "unit": unit, "text": f"Push at {_fmt(cur)}"}
    if p["side"] == "over":
        hit = cur >= p["need"]
        return base | {"status": "won" if hit else "lost" if final else "live", "current": cur, "target": p["need"],
                       "unit": unit,
                       "text": "Hit" if hit else f"Missed by {_fmt(p['need'] - cur)}" if final else f"{_fmt(p['need'] - cur)} to go"}
    busted = cur > p["point"]
    return base | {"status": "lost" if busted else "won" if final else "live", "current": cur, "target": p["point"],
                   "unit": unit,
                   "text": "Over the line" if busted else "Stayed under" if final else f"{_fmt(math.floor(p['point'] - cur + 1))} of room"}


# ---------------------------------------------------------------------------------------------- one bet

def ref_sport(ref) -> tuple[str | None, str | None]:
    """(sport, soccer league) from a leg's game ref: "nhl:2026020162", "2026_07_NE_CHI", "nba|NYK|BOS|tip",
    "epl|Home|Away|kickoff", "ufc:<event>:<fight>", "ncaaf:401856841"."""
    s = str(ref or "")
    if "|" in s:
        head = s.split("|")[0]
        return ("nba", None) if head == "nba" else ("soccer", head) if head in SOCCER else (None, None)
    head = s.split(":")[0]
    if head in ("nhl", "ncaaf", "ncaab", "ufc", "nba", "nfl") and ":" in s:
        return head, None
    if re.match(r"^\d{4}_\d{2}_", s):
        return "nfl", None
    return None, None


def sport_of(key) -> tuple[str | None, str | None]:
    k = str(key or "").lower()
    if k in SOCCER:
        return "soccer", k
    return (k if k and k not in ("mixed", "none") else None), None


def _label(l) -> str:
    return l if isinstance(l, str) else (l or {}).get("label") or ""


def ref_time(ref) -> str | None:
    """A game ref's kickoff where the ref carries it ("nba|CHI|WSH|2026-10-24T23:10:00+00:00", soccer the same)."""
    m = re.search(r"\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?", str(ref or ""))
    return m[0] if m else None


def ref_game_id(ref) -> str | None:
    """The games table's id for a ref without a time: NFL "2026_07_PIT_NO" -> "nfl:2026_07_PIT_NO"; college and NHL refs
    are the id. UFC refs name ESPN's fight: None (web refGameId)."""
    r = str(ref or "")
    if re.match(r"^\d{4}_\d{2}_", r):
        return f"nfl:{r}"
    return r if re.fullmatch(r"(ncaaf|ncaab|nhl|nfl):[^:]+", r) else None


def groups(bet: dict, ticket: dict | None) -> list[dict]:
    """A bet's games and the legs on each: {sport, league, matchup, legs} and, when known, the game's `start`. Custom
    bets carry `games` (each game's start from its ref, else the bet's `game_starts` by the games table's id); a fun
    ticket's come from its body; a single pick is its label on its matchup."""
    def with_sport(ref, fallback):
        s, lg = ref_sport(ref)
        return (s, lg) if s else sport_of(fallback)

    def start(g) -> dict:
        t = ref_time(g.get("game_ref")) or (bet.get("game_starts") or {}).get(ref_game_id(g.get("game_ref")) or "") \
            or g.get("commence_time")
        return {"start": t} if t else {}

    games = bet.get("games")
    if isinstance(games, list) and games:
        return [dict(zip(("sport", "league"), with_sport(g.get("game_ref"), bet.get("sport") or bet.get("league"))),
                     matchup=g.get("matchup") or "", legs=[_label(x) for x in g.get("legs") or []], **start(g)) for g in games]
    if ticket and ticket.get("games"):
        return [dict(zip(("sport", "league"), with_sport(g.get("game_ref"), ticket.get("sport") or bet.get("sport"))),
                     matchup=g.get("matchup") or "", legs=[_label(x) for x in g.get("legs") or []], **start(g))
                for g in ticket["games"]]
    legs = bet.get("legs") or ([bet["label"]] if bet.get("label") else [])
    sport, league = sport_of(bet.get("league") or bet.get("sport"))
    return [{"sport": sport, "league": league, "matchup": (ticket or {}).get("matchup") or bet.get("matchup") or "",
             "legs": [_label(x) for x in legs]}]


def _when(iso) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=ET)


def search_days(bet: dict, grp: dict, open_: bool, now: datetime, single: bool = True) -> list[str]:
    """The Eastern days to look for a group's game (web searchDays, iPhone Live.searchDays; tests/fixtures/live_legs.json
    "days"): its game's day and the next (late games run past midnight) when the start is known (the group's, the bet's,
    the time in its ref, or for a one-game bet its first kickoff); else the day it was placed and the next, and for an open
    bet yesterday and today too (Nov 9: an open bet looked only at yesterday and today, so a game two days back that wasn't
    graded yet, or one tomorrow, had no tracker)."""
    start = (grp.get("start") or bet.get("pick_commence_time") or bet.get("ticket_commence_time") or ref_time(grp.get("ref"))
             or (bet.get("game_start") if single else None))
    t = _when(start) if start else None
    if t:
        return [ymd(t), ymd(t.astimezone(ET) + timedelta(days=1))]
    placed = _when(bet.get("placed_at"))
    days = [ymd(placed), ymd(placed.astimezone(ET) + timedelta(days=1))] if placed else []
    if open_ or not days:
        days += [ymd(now.astimezone(ET) - timedelta(days=1)), ymd(now)]
    return sorted(set(days))


def live_bet(bet: dict, ticket: dict | None, board, box, now: datetime | None = None) -> dict:
    """Every leg's state for one open bet ({legs, games, status}); `board(sport, league, days)` and `box(game, league)`
    are the caller's cached ESPN readers."""
    now = now or datetime.now(ET)
    legs, games = [], []
    grps = groups(bet, ticket)
    for grp in grps:
        days = search_days(bet, grp, True, now, len(grps) == 1)
        game, league = None, grp.get("league")
        if grp["sport"] == "soccer" and not league:
            tries = [("soccer", lg) for lg in SOCCER]
        elif grp["sport"]:
            tries = [(grp["sport"], league)]
        else:
            tries = [(s, None) for s in GUESS]
        for sport, lg in tries:
            game = find_game(board(sport, lg, days), grp["matchup"])
            if game:
                league = lg
                break
        if game and all(x["key"] != game["key"] for x in games):
            games.append(game)
        bx = box(game, league) if game and game["state"] != "pre" else None
        legs += [judge(l, game, bx) for l in grp["legs"]]
    return rollup(legs, games)


def rollup(legs: list[dict], games: list[dict]) -> dict:
    """A bet's state from its legs; `settle` as the apps' rollup: any lost leg, or every leg won outright (a void or a
    dead heat pays a reduced price, which is the grader's to work out)."""
    lost = any(l["status"] == "lost" for l in legs)
    done = sum(l["status"] in ("won", "void") for l in legs)
    status = ("lost" if lost else "won" if legs and done == len(legs)
              else "live" if any(g["state"] != "pre" for g in games) else "pending")
    settle = "lost" if lost else "won" if legs and all(l["status"] == "won" and not l.get("deadHeat") for l in legs) else None
    return {"legs": legs, "games": games, "status": status, "hit": sum(l["status"] == "won" for l in legs),
            "total": len(legs), **({"settle": settle} if settle else {})}
