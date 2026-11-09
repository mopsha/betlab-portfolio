"""UFC cards, results and the sportsbook's prices from ESPN's free API (no key), for UFC (Mike, Oct 23).

- **Calendar:** `site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates=YYYY` carries the year's events
  (`leagues[0].calendar`, 50-57 a year back to 2019).
- **Fight center:** `site.web.api.espn.com/apis/common/v3/sports/mma/ufc/fightcenter/<event id>` has every fight
  by card segment (`cards`: main, prelims1, prelims2) with its start, note ("Flyweight - Main Event - Title
  Fight"), result (`status.result.name`: decision---unanimous, ko/tko, submission, ...; `period`, `clock` in
  seconds into the round), each fighter's `winner` flag and stats, and the sportsbook's prices (`bets`; DraftKings
  in 2026): per fighter the moneyline and method (KO/TKO/DQ, submission, points), per fight total rounds and
  whether it goes the distance. For a finished event these are the last prices ESPN showed, before the fight.

Finished events are cached as gzipped JSON under data/cache/espn_ufc/ (not committed).
"""

from __future__ import annotations

import gzip
import json
import time

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from betlab import config

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
FIGHTCENTER = "https://site.web.api.espn.com/apis/common/v3/sports/mma/ufc/fightcenter"
CACHE = config.DATA_DIR / "cache" / "espn_ufc"
ROUND_SECONDS = 300
METHOD = {"knockout": "ko", "submission": "sub", "points": "dec"}   # ESPN's per-fighter method bets

_S: requests.Session | None = None


def _session() -> requests.Session:
    global _S
    if _S is None:
        _S = requests.Session()
        _S.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1,
                                                             status_forcelist=(429, 500, 502, 503, 504),
                                                             allowed_methods=("GET",))))
        _S.headers["User-Agent"] = "BetLab"
    return _S


def _get(url: str, params: dict | None = None) -> dict:
    r = _session().get(url, params=params, timeout=30)
    r.raise_for_status()
    body = r.content
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return json.loads(body)


def calendar(year: int) -> list[dict]:
    """[{event_id, name, start}] for a year's UFC events."""
    d = _get(SCOREBOARD, {"dates": str(year)})
    out = []
    for c in (d.get("leagues") or [{}])[0].get("calendar", []):
        ref = (c.get("event") or {}).get("$ref", "")
        eid = ref.split("/events/")[-1].split("?")[0] if "/events/" in ref else None
        if eid:
            out.append({"event_id": eid, "name": c.get("label"), "start": c.get("startDate")})
    return out


def event(event_id: str, refresh: bool = False) -> dict:
    """An event's fight center; a finished one is read from the cache."""
    path = CACHE / f"{event_id}.json.gz"
    if path.exists() and not refresh:
        try:
            return json.loads(gzip.decompress(path.read_bytes()))
        except (OSError, ValueError):
            pass                                   # a bad cache file is a miss
    d = _get(f"{FIGHTCENTER}/{event_id}", {"region": "us", "lang": "en"})
    if _finished(d):
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps(d).encode()))
    return d


def _comps(d: dict):
    for seg_key, seg in (d.get("cards") or {}).items():
        for c in seg.get("competitions") or []:
            yield seg_key, c


def _finished(d: dict) -> bool:
    comps = [c for _, c in _comps(d)]
    return bool(comps) and all(((c.get("status") or {}).get("type") or {}).get("completed") for c in comps)


def american(text) -> float | None:
    """'+140', '-166', 'EVEN' -> American odds; anything else None."""
    if text is None:
        return None
    t = str(text).strip().upper()
    if t in ("EVEN", "EV", "PK"):
        return 100.0
    try:
        v = float(t.replace("+", ""))
    except ValueError:
        return None
    return v if abs(v) >= 100 else None


def _bets(obj: dict) -> tuple[str | None, dict]:
    """(provider, {kind: [values]}) from a competition's or a competitor's `bets`."""
    b = obj.get("bets") or {}
    if isinstance(b, list):
        b = b[0] if b else {}
    out = {}
    for o in b.get("odds") or []:
        out[o.get("type") or o.get("displayName")] = o.get("values") or []
    return (b.get("provider") or {}).get("name"), out


STATS = {"sigStrikes": "sig", "totalStrikes": "str", "takedowns": "td", "knockDowns": "kd", "submissions": "subatt",
         "timeInControl": "ctrl"}


def _stats(x: dict) -> dict:
    """A fighter's fight stats: sig/str/td as landed and attempted ("25/44"), kd, submission attempts, control seconds."""
    out = {}
    for st in x.get("stats") or []:
        key = STATS.get(st.get("name"))
        if not key:
            continue
        dv = str(st.get("displayValue") or "")
        if "/" in dv:
            try:
                landed, att = (float(v) for v in dv.split("/"))
            except ValueError:
                continue
            out[key], out[f"{key}_att"] = landed, att
        else:
            try:
                out[key] = float(st.get("value")) if st.get("value") is not None else None
            except (TypeError, ValueError):
                pass
    return out


def _rounds(c: dict) -> int:
    """Scheduled rounds: five for a main event or a title fight, else three (UFC rules)."""
    fmt = ((c.get("format") or {}).get("regulation") or {}).get("periods")
    if fmt:
        return int(fmt)
    note = str(c.get("note") or "").lower()
    return 5 if ("main event" in note or "title" in note) else 3


def fights(d: dict, event_id: str | None = None) -> pd.DataFrame:
    """One row per fight: fighters (a = ESPN's order 1), segment and start, scheduled rounds, result (winner,
    method, round, clock, seconds fought) and the sportsbook's prices."""
    ev = d.get("event") or {}
    rows = []
    for seg, c in _comps(d):
        comp = sorted(c.get("competitors") or [], key=lambda x: x.get("order", 9))
        if len(comp) != 2:
            continue
        st = c.get("status") or {}
        res = (st.get("result") or {}).get("name") or ""
        period = int(st.get("period") or 0)
        try:
            clock = float(st.get("clock") or 0)
        except (TypeError, ValueError):
            clock = 0.0
        done = bool((st.get("type") or {}).get("completed"))
        provider, fight_bets = _bets(c)
        row = {"event_id": event_id or ev.get("id"), "event": ev.get("name"), "fight_id": c.get("id"),
               "segment": seg, "start": c.get("date"), "note": c.get("note"), "rounds": _rounds(c),
               "done": done, "result": res, "period": period, "clock": clock,
               "seconds": (period - 1) * ROUND_SECONDS + clock if done and period else None,
               "provider": provider}
        for side, x in zip(("a", "b"), comp):
            ath = x.get("athlete") or {}
            row[f"{side}_name"] = ath.get("displayName") or ath.get("fullName")
            row[f"{side}_id"] = ath.get("id")
            row[f"{side}_win"] = x.get("winner")
            row.update({f"{side}_{k}": v for k, v in _stats(x).items()})
            flag = ath.get("flag") or {}
            row[f"{side}_info"] = {"record": x.get("displayRecord"), "age": ath.get("age"), "height": ath.get("displayHeight"),
                                   "reach": ath.get("displayReach"), "stance": (ath.get("stance") or {}).get("text")
                                   if isinstance(ath.get("stance"), dict) else ath.get("stance"),
                                   "country": flag.get("alt") or (ath.get("country") or {}).get("name")
                                   if isinstance(ath.get("country"), dict) else flag.get("alt")}
            p, mine = _bets(x)
            provider = provider or p
            for kind, vals in mine.items():
                key = "ml" if kind == "moneyline" else METHOD.get(kind)
                if key and vals:
                    row[f"{side}_{key}"] = american(vals[0].get("odds"))
        row["provider"] = provider
        for kind, vals in fight_bets.items():
            if kind == "total":
                for v in vals:
                    line = str(v.get("line") or "")
                    if line[:1] in ("o", "u"):
                        row["total_line"] = float(line[1:])
                        row["over" if line[0] == "o" else "under"] = american(v.get("odds"))
            elif str(kind).lower().startswith("fight goes the distance") or kind == "distance":
                for v in vals:
                    row["distance_" + str(v.get("line", "")).lower()] = american(v.get("odds"))
        rows.append(row)
    return pd.DataFrame(rows)


def history(years, pause: float = 0.25) -> pd.DataFrame:
    """Every finished fight of these years' events (cached; about 55 events a year)."""
    frames = []
    for y in years:
        for e in calendar(y):
            if pd.Timestamp(e["start"]) > pd.Timestamp.now(tz="UTC"):
                continue
            cached = (CACHE / f"{e['event_id']}.json.gz").exists()
            try:
                df = fights(event(e["event_id"]), e["event_id"])
            except requests.RequestException:
                continue
            if not cached:
                time.sleep(pause)
            frames.append(df.assign(event=e["name"], event_start=e["start"]))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = out.drop(columns=[c for c in ("a_info", "b_info") if c in out])   # profiles: the live card only
    return out[out["done"]] if len(out) else out


def scheduled(day: str) -> pd.DataFrame:
    """A day's UFC fights from the scoreboard (`day` YYYYMMDD, Eastern): fighters, the start of the fight's card
    segment (early prelims, prelims, main card) and its scheduled rounds."""
    d = _get(SCOREBOARD, {"dates": day})
    rows = []
    for e in d.get("events") or []:
        for c in e.get("competitions") or []:
            comp = sorted(c.get("competitors") or [], key=lambda x: x.get("order", 9))
            if len(comp) != 2:
                continue
            names = [(x.get("athlete") or {}).get("displayName") for x in comp]
            rows.append({"espn_event": e.get("id"), "event": e.get("name"), "fight_id": c.get("id"),
                         "start": c.get("date") or c.get("startDate"), "rounds": _rounds(c),
                         "a_name": names[0], "b_name": names[1],
                         "completed": bool(((c.get("status") or {}).get("type") or {}).get("completed"))})
    return pd.DataFrame(rows)


def _last(name) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    t = "".join(ch if ch.isalnum() or ch == " " else " " for ch in t).split()
    return t[-1] if t else ""


def same_fight(a1, b1, a2, b2) -> bool:
    """Two fighter pairs are the same fight: both last names match, in either order (ESPN and the Odds API
    spell first names differently: Ramazan / Ramazonbek Temirov, Alexander / Alex Volkanovski)."""
    return {_last(a1), _last(b1)} == {_last(a2), _last(b2)} and _last(a1) != _last(b1)


def find(fights_df: pd.DataFrame, x, y) -> pd.Series | None:
    """The row of `fights_df` (a_name, b_name) for fighters x and y, if exactly one matches."""
    if fights_df is None or fights_df.empty:
        return None
    m = fights_df[[same_fight(a, b, x, y) for a, b in zip(fights_df["a_name"], fights_df["b_name"])]]
    return m.iloc[0] if len(m) == 1 else None
