"""Soccer player box scores and lineups from ESPN's free site API (no key), for the soccer props
(Mike, 2026-10-10: "we can win money on shots / shots on goal").

- **Scoreboard:** `site.api.espn.com/apis/site/v2/sports/soccer/<slug>/scoreboard?dates=YYYYMMDD`
  lists one day's matches. Date ranges return nothing for soccer, but each response carries the
  season's `calendar` (every match day), so history walks only real match days.
- **Summary:** `.../summary?event=<id>` has both rosters: per player `starter`, `subbedIn`,
  `subbedOut`, position and formation slot, and stats (`totalShots`, `shotsOnTarget`,
  `totalGoals`, `goalAssists`, fouls, cards, offsides). Player shots add up to the team's box
  (checked Oct 10). Substitution minutes come from `keyEvents` ("63'", "90'+2'"); the first
  participant comes on, the second goes off. Rosters appear with the lineups, about an hour
  before kickoff.
- **History back to 2019-20** for every league we bet (checked Oct 10).

Finished matches are cached as gzipped JSON under data/cache/espn_soccer/ (not committed): a played
match never changes. A summary is about 440 KB as plain JSON, so the worker's cache of this season's matches
helped fill its 500 MB volume (Oct 17); gzipped it's about a tenth. Older plain .json files are still read.
"""

from __future__ import annotations

import gzip
import json
import re
import time

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from betlab import config

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
CACHE = config.DATA_DIR / "cache" / "espn_soccer"
SLUGS = {"epl": "eng.1", "la_liga": "esp.1", "serie_a": "ita.1", "bundesliga": "ger.1", "ligue_1": "fra.1",
         "mls": "usa.1", "ucl": "uefa.champions", "uel": "uefa.europa", "uecl": "uefa.europa.conf"}
UEFA = ("uefa.champions", "uefa.europa", "uefa.europa.conf")   # midweek European matches: congestion
STATS = {"totalShots": "shots", "shotsOnTarget": "sot", "totalGoals": "goals", "goalAssists": "assists",
         "foulsCommitted": "fouls", "yellowCards": "yellow", "redCards": "red", "offsides": "offsides"}
FULL_TIME = 90

_S: requests.Session | None = None


def _session() -> requests.Session:
    global _S
    if _S is None:
        _S = requests.Session()
        _S.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1,
                                                             status_forcelist=(429, 500, 502, 503, 504),
                                                             allowed_methods=("GET",))))
        _S.headers["Accept-Encoding"] = "gzip"
    return _S


def _get(url: str) -> dict:
    r = _session().get(url, timeout=30)
    r.raise_for_status()
    body = r.content
    if body[:2] == b"\x1f\x8b":            # some answers come gzipped without saying so
        body = gzip.decompress(body)
    return json.loads(body.decode("utf-8"))


def scoreboard(slug: str, day) -> dict:
    """One day's matches (and the season's calendar), raw."""
    return _get(f"{BASE}/{slug}/scoreboard?dates={pd.Timestamp(day):%Y%m%d}")


def events(sb: dict) -> list[dict]:
    """The scoreboard's matches: id, kickoff (UTC), home and away names, finished or not."""
    out = []
    for e in sb.get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        teams = {c.get("homeAway"): c.get("team", {}).get("displayName") for c in comp.get("competitors", [])}
        out.append({"event_id": str(e["id"]), "kickoff": pd.Timestamp(e["date"]), "home": teams.get("home"),
                    "away": teams.get("away"), "completed": bool(e.get("status", {}).get("type", {}).get("completed"))})
    return out


def match_days(sb: dict) -> list[pd.Timestamp]:
    """The season's match days from a scoreboard's calendar (dates in UTC midnight-ish)."""
    cal = ((sb.get("leagues") or [{}])[0]).get("calendar") or []
    return sorted({pd.Timestamp(d).tz_convert("America/New_York").normalize().tz_localize(None) for d in cal
                   if isinstance(d, str)})


def summary(slug: str, event_id: str, use_cache: bool = True) -> dict:
    """One match's summary; finished matches come from (and go to) the cache."""
    path, plain = CACHE / slug / f"{event_id}.json.gz", CACHE / slug / f"{event_id}.json"
    for f, read in ((path, lambda f: gzip.decompress(f.read_bytes())),
                    (plain, lambda f: f.read_text(encoding="utf-8"))):   # plain: cached before Oct 20
        if use_cache and f.exists():
            try:
                return json.loads(read(f))
            except (ValueError, OSError, EOFError):
                # Oct 17-18: writes on the worker's full disk left empty files, and every league's history update
                # failed on them until Oct 20 ("Expecting value: line 1 column 1"). A bad file is a miss.
                f.unlink(missing_ok=True)
    s = _get(f"{BASE}/{slug}/summary?event={event_id}")
    status = (((s.get("header") or {}).get("competitions") or [{}])[0].get("status") or {}).get("type") or {}
    if status.get("completed"):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")                     # a full disk leaves a partial .tmp, never a bad cache file
        tmp.write_bytes(gzip.compress(json.dumps(s).encode("utf-8"), compresslevel=6))
        tmp.replace(path)
    return s


def _minute(clock: str | None) -> int | None:
    """"63'" -> 63, "90'+2'" -> 92, "45'+1'" -> 46."""
    if not clock:
        return None
    nums = [int(x) for x in re.findall(r"\d+", str(clock))]
    return sum(nums[:2]) if nums else None


def substitutions(s: dict) -> tuple[dict, dict]:
    """({player on: minute}, {player off: minute}) by athlete id, from the key events."""
    on, off = {}, {}
    for k in s.get("keyEvents") or []:
        if "substitution" not in str((k.get("type") or {}).get("text", "")).lower():
            continue
        m = _minute((k.get("clock") or {}).get("displayValue"))
        parts = [str((p.get("athlete") or {}).get("id")) for p in k.get("participants") or []]
        if len(parts) >= 1 and parts[0] != "None":
            on[parts[0]] = m
        if len(parts) >= 2 and parts[1] != "None":
            off[parts[1]] = m
    return on, off


def box(s: dict, league: str | None = None) -> pd.DataFrame:
    """One row per player who was in a matchday squad: who, for whom, against whom, started or
    came on, minutes, and the stats in STATS. Unused substitutes are kept with minutes 0."""
    rosters = s.get("rosters") or []
    if len(rosters) != 2:
        return pd.DataFrame()
    comp = ((s.get("header") or {}).get("competitions") or [{}])[0]
    kickoff = pd.Timestamp(comp.get("date")) if comp.get("date") else None
    score = {c.get("homeAway"): pd.to_numeric(c.get("score"), errors="coerce") for c in comp.get("competitors", [])}
    on, off = substitutions(s)
    names = [r.get("team", {}).get("displayName") for r in rosters]
    rows = []
    for i, r in enumerate(rosters):
        side = r.get("homeAway")
        for p in r.get("roster") or []:
            a = p.get("athlete") or {}
            pid = str(a.get("id"))
            st = {x.get("name"): x.get("value") for x in p.get("stats") or []}
            starter, came_on = bool(p.get("starter")), bool(p.get("subbedIn"))
            m_in = 0 if starter else on.get(pid)
            m_out = off.get(pid) if p.get("subbedOut") else None
            if starter:
                minutes = m_out if m_out is not None else FULL_TIME
            elif came_on and m_in is not None:
                minutes = max((m_out if m_out is not None else FULL_TIME) - m_in, 1)
            else:
                minutes = 0
            rows.append({"event_id": str((s.get("header") or {}).get("id") or ""), "league": league,
                         "kickoff": kickoff, "team": names[i], "opponent": names[1 - i], "home": side == "home",
                         "player_id": pid, "player": a.get("displayName"),
                         "position": (p.get("position") or {}).get("abbreviation"),
                         "formation_place": pd.to_numeric(p.get("formationPlace"), errors="coerce"),
                         "starter": starter, "came_on": came_on, "minutes": minutes,
                         "team_goals": score.get(side), "opp_goals": score.get("away" if side == "home" else "home"),
                         **{v: st.get(k) for k, v in STATS.items()}})
    return pd.DataFrame(rows)


def lineup(slug: str, event_id: str) -> pd.DataFrame:
    """Tonight's announced squads (about an hour before kickoff), as box rows (player, team,
    opponent, home, starter, position ...; the stats still empty). Empty until the lineups are out."""
    b = box(summary(slug, event_id, use_cache=False))
    return b.assign(event_id=str(event_id)) if len(b) else b


def season_days(slug: str, season_end: int) -> list[pd.Timestamp]:
    """Every match day of the season ending in `season_end` (MLS: the calendar year), from the
    calendar of a scoreboard inside that season."""
    probe = f"{season_end}0701" if slug == "usa.1" else f"{season_end}0115"
    return match_days(scoreboard(slug, probe))


def history(league: str, seasons, pause: float = 0.05, log=print) -> pd.DataFrame:
    """Every finished match's player box for these seasons (season = the year it ends)."""
    slug = SLUGS[league]
    frames = []
    for season in seasons:
        n, failed = 0, 0
        for day in season_days(slug, season):
            if day >= pd.Timestamp.now().normalize():
                break
            try:
                day_events = events(scoreboard(slug, day))
            except requests.RequestException:
                failed += 1
                continue
            for e in day_events:
                if not e["completed"]:
                    continue
                try:                     # one match ESPN can't serve (a lasting 502) never stops a season
                    b = box(summary(slug, e["event_id"]), league)
                except requests.RequestException:
                    failed += 1
                    continue
                if len(b):
                    b["season"] = season
                    frames.append(b)
                    n += 1
            time.sleep(pause)
        log(f"{league} {season}: {n} matches" + (f" ({failed} ESPN couldn't serve)" if failed else ""))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def find_event(league: str, home: str, away: str, kickoff) -> str | None:
    """ESPN's event id for an odds-feed match: the same two clubs (names as in sources/soccer's
    similarity) kicking off within 3 hours, on that Eastern day's scoreboard. ESPN spells some clubs its
    own way ("LAFC", "FC Cologne", "Stade Rennais"; their Oct 11 props went ungraded), so a match at the
    same kickoff (10 minutes) where one club's name agrees (0.9+) counts too."""
    from betlab.sources.soccer import similarity

    k = pd.Timestamp(kickoff)
    best, score = None, 0.0
    for e in events(scoreboard(SLUGS[league], k.tz_convert("America/New_York"))):
        gap = abs((e["kickoff"] - k).total_seconds())
        if gap > 3 * 3600:
            continue
        sh, sa = similarity(home, e["home"] or ""), similarity(away, e["away"] or "")
        s = min(sh, sa)
        if s < 0.6 and gap <= 600 and max(sh, sa) >= 0.9:
            s = 0.6
        if s > score:
            best, score = e["event_id"], s
    return best if score >= 0.6 else None



def final_score(league: str, home: str, away: str, kickoff) -> tuple[int, int] | None:
    """(home goals, away goals) of a finished match, or None (not found or not over). For the fun
    tickets when football-data.co.uk lags (Oct 12: its 2026-27 files stopped at Sep 20)."""
    eid = find_event(league, home, away, kickoff)
    if eid is None:
        return None
    comp = ((summary(SLUGS[league], eid).get("header") or {}).get("competitions") or [{}])[0]
    if not ((comp.get("status") or {}).get("type") or {}).get("completed"):
        return None
    score = {c.get("homeAway"): pd.to_numeric(c.get("score"), errors="coerce") for c in comp.get("competitors", [])}
    if any(pd.isna(score.get(k)) for k in ("home", "away")):
        return None
    return int(score["home"]), int(score["away"])

# letters that don't decompose into a base letter plus an accent ("Højlund", "Ødegaard", "Müller" does)
_TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "Ae", "ß": "ss", "ł": "l", "Ł": "L", "đ": "d",
                           "Đ": "D", "ı": "i", "þ": "th", "ð": "d"})


def _plain(name: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", str(name or "").translate(_TRANSLIT)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z ]", " ", s).split())


def match_player(name: str, squad: pd.DataFrame) -> pd.Series | None:
    """The squad row for a feed name: the same name without accents, else the same last name and
    first initial, else the one squad name containing all of the feed name's words (or the reverse:
    "Alisson de Almeida Santos" vs "Alisson Santos"). None when unsure."""
    if squad is None or squad.empty:
        return None
    plain = squad["player"].map(_plain)
    n = _plain(name)
    hit = squad[plain == n]
    if len(hit) == 1:
        return hit.iloc[0]
    w = n.split()
    if w:
        hit = squad[plain.map(lambda p: bool(p) and p.split()[-1] == w[-1] and p[0] == w[0][0])]
        if len(hit) == 1:
            return hit.iloc[0]
        words = set(w)
        hit = squad[plain.map(lambda p: bool(p) and (set(p.split()) <= words or words <= set(p.split())))]
        if len(hit) == 1:
            return hit.iloc[0]
    return None


HIST = config.DATA_DIR / "history" / "soccer_players"


def load_history(since_season: int | None = None) -> pd.DataFrame:
    """Every league's player history (data/history/soccer_players/<league>.parquet), duplicates from
    ESPN's overlapping 2020 calendars dropped."""
    frames = [pd.read_parquet(f) for f in sorted(HIST.glob("*.parquet"))]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).drop_duplicates(["event_id", "player_id"], keep="first")
    return df[df["season"] >= since_season] if since_season else df


def current_season(league: str, today: pd.Timestamp | None = None) -> int:
    """The season's end year: MLS plays in the calendar year, the big five from August."""
    t = today or pd.Timestamp.now(tz="America/New_York")
    return t.year if league == "mls" or t.month < 7 else t.year + 1


def update_history(league: str, log=print) -> int:
    """Add this season's finished matches since the last one in the league's file (the daily run;
    about one summary call per new match)."""
    path = HIST / f"{league}.parquet"
    old = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    slug, season = SLUGS[league], current_season(league)
    today = pd.Timestamp.now(tz="America/New_York").tz_localize(None).normalize()
    last = pd.to_datetime(old["kickoff"], utc=True, format="ISO8601").max().tz_convert("America/New_York").tz_localize(None).normalize()         if len(old) else pd.Timestamp(f"{season - (0 if league == 'mls' else 1)}-01-01")
    have = set(old["event_id"].astype(str)) if len(old) else set()
    frames = []
    for day in match_days(scoreboard(slug, today)):
        if not (last - pd.Timedelta(days=1) <= day < today):
            continue
        for e in events(scoreboard(slug, day)):
            if e["completed"] and e["event_id"] not in have:
                try:
                    b = box(summary(slug, e["event_id"]), league)
                except requests.RequestException:
                    continue
                if len(b):
                    frames.append(b.assign(season=season))
    if not frames:
        return 0
    new = pd.concat(frames, ignore_index=True)
    pd.concat([old, new], ignore_index=True).to_parquet(path, index=False)
    log(f"{league}: {new['event_id'].nunique()} new matches")
    return int(new["event_id"].nunique())


def player_result(league: str, home: str, away: str, kickoff, player: str) -> tuple[str, pd.Series | None]:
    """A player's line in a finished match: ("ok", box row), ("void", None) when he didn't play (the
    books void those), or ("open", None) until ESPN has the match final."""
    eid = find_event(league, home, away, kickoff)
    if eid is None:
        return "open", None
    s = summary(SLUGS[league], eid)
    done = (((s.get("header") or {}).get("competitions") or [{}])[0].get("status") or {}).get("type", {}).get("completed")
    if not done:
        return "open", None
    p = match_player(player, box(s, league))
    if p is None or not p["minutes"]:
        return "void", None
    return "ok", p
