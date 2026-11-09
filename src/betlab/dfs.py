"""The DFS optimizer (Nov 5, idea #38): DraftKings classic lineups from what the betting market expects of each player.

Salaries, positions and who's out come from DraftKings' own "export to CSV" link, free and with no sign-in. A player's
projection is his fantasy points at the market's expected stats: Novig's free catalog for every game on the slate, and
our own pulled props where a game has had its pull (a sharp book first). A player with no lines falls back to his average
on DraftKings, marked as such. The best lineups under the cap come from an integer program, three of them, each at least
two players apart; an NFL lineup stacks its quarterback with one of his receivers (they score together).

What it is not: a pick. A DFS contest is against other players with a rake of about 15%, and the most projected points
isn't the most money: nothing here knows who else is playing whom. `scripts/dfs_projection_study.py` tested the
projections against box scores; salaries from the past aren't kept anywhere free, so the lineups themselves have no
backtest. Every lock logs them and every player's projection to `data/ledger/dfs_*.csv`, and `grade` fills in what they
scored, so the record builds from here. Mike decides, and enters a lineup himself.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
from scipy import optimize, sparse
from scipy.stats import norm

from betlab import players

ET = ZoneInfo("America/New_York")
LOBBY = "https://www.draftkings.com/lobby/getcontests"
CSV_URL = "https://www.draftkings.com/lineup/getavailableplayerscsv"
LEAGUES = {"nba": "NBA", "nfl": "NFL"}
SPORT_KEY = {"nba": "basketball_nba", "nfl": "americanfootball_nfl"}
CAP = 50000
LINEUPS = 3
DIFFER_BY = 2
ROSTERS = {"nba": ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"],
           "nfl": ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]}
OUT = {"O", "OUT", "IR", "SUSP", "NA", "D", "DOUBTFUL"}

# How far a stat's result runs around its mean: a standard deviation of k * sqrt(mean). NBA: measured on this season's box
# scores (Nov 5). NFL: rough, from weekly stats; only the small step from a line near even to its mean depends on it.
SPREAD = {"points": 1.6, "rebounds": 1.05, "assists": 1.0, "threes": 1.0, "steals": 1.0, "blocks": 1.0,
          "pass_yards": 7.5, "rush_yards": 4.4, "rec_yards": 5.2, "receptions": 1.15, "pass_tds": 0.95, "ints": 0.95}

# (book's market -> stat) for pulled props and Novig's catalog
ODDS_MARKETS = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists",
                "player_threes": "threes", "player_steals": "steals", "player_blocks": "blocks",
                "player_pass_yds": "pass_yards", "player_rush_yds": "rush_yards", "player_reception_yds": "rec_yards",
                "player_receptions": "receptions", "player_pass_tds": "pass_tds", "player_pass_interceptions": "ints"}
NOVIG_MARKETS = {"POINTS": "points", "REBOUNDS": "rebounds", "ASSISTS": "assists", "THREE_POINTERS_MADE": "threes",
                 "STEALS": "steals", "BLOCKS": "blocks"}   # NBA; its NFL games list no props yet (Nov 5)
SHARP = ("pinnacle", "lowvig", "betonlineag")


def dk_nba(s: dict) -> float:
    """DraftKings NBA points for a line of (expected or real) stats; dd / td are double- and triple-double chances."""
    g = s.get
    return (g("points", 0) + 0.5 * g("threes", 0) + 1.25 * g("rebounds", 0) + 1.5 * g("assists", 0) + 2 * g("steals", 0)
            + 2 * g("blocks", 0) - 0.5 * g("turnovers", 0) + 1.5 * g("dd", 0) + 3 * g("td", 0))


def dk_nfl(s: dict) -> float:
    """DraftKings NFL points; `tds` are rushing and receiving touchdowns, the yardage bonuses are not expected here."""
    g = s.get
    return (0.04 * g("pass_yards", 0) + 4 * g("pass_tds", 0) - g("ints", 0) + 0.1 * g("rush_yards", 0)
            + 0.1 * g("rec_yards", 0) + g("receptions", 0) + 6 * g("tds", 0))


SCORE = {"nba": dk_nba, "nfl": dk_nfl}


def mean_from_line(stat: str, point: float, p_over: float) -> float:
    """The expected stat, from the line nearest even: its number moved by how far the over is from 50%."""
    p = min(max(p_over, 0.03), 0.97)
    return float(max(point + SPREAD[stat] * np.sqrt(max(point, 0.5)) * float(norm.ppf(p)), 0.0))


def best_means(quotes: list[tuple[str, str, float, float, int]]) -> dict[str, dict[str, float]]:
    """{player: {stat: expected}} from (player, stat, point, p_over, source rank) rows: the best-ranked source (lower is
    better), and its line nearest even. An anytime touchdown's chance is a Poisson's: expected TDs = -ln(1 - p)."""
    best: dict[tuple[str, str], tuple[int, float, float, float]] = {}
    for name, stat, point, p, rank in quotes:
        key = (players.normalize(name), stat)
        score = (rank, abs(p - 0.5), point, p)
        if key not in best or score < best[key]:
            best[key] = score
    out: dict[str, dict[str, float]] = {}
    for (name, stat), (_, _, point, p) in best.items():
        if stat == "td":
            out.setdefault(name, {})["tds"] = float(-np.log(max(1 - p, 0.02)))
        elif stat in SPREAD:
            out.setdefault(name, {})[stat] = mean_from_line(stat, point, p)
    return out


@dataclass
class Player:
    id: str
    name: str
    team: str
    game: str
    start: datetime | None
    positions: list[str]
    salary: int
    average: float
    status: str = ""
    proj: float = 0.0
    basis: str = "average"
    stats: dict = field(default_factory=dict)


def parse_csv(text: str) -> list[Player]:
    """DraftKings' export. Game Info reads "MIA@GSW 11/05/2026 10:00PM ET"."""
    out = []
    for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        info = (r.get("Game Info") or "").split(" ", 1)
        start = None
        if len(info) == 2:
            try:
                start = datetime.strptime(info[1].replace(" ET", ""), "%m/%d/%Y %I:%M%p").replace(tzinfo=ET)
            except ValueError:
                pass
        try:
            out.append(Player(id=r["ID"], name=r["Name"].strip(), team=r["TeamAbbrev"], game=info[0], start=start,
                              positions=[p for p in r["Roster Position"].split("/") if p], salary=int(r["Salary"]),
                              average=float(r.get("AvgPointsPerGame") or 0), status=(r.get("Status") or "").strip()))
        except (KeyError, ValueError):
            continue
    return out


def project(pool: list[Player], league: str, means: dict[str, dict[str, float]], extras: dict[str, dict[str, float]] | None = None) -> None:
    """Each player's projection in place. `extras` holds season averages of what the market has no line for (an NBA player's
    steals, blocks and turnovers). A player without his main line stays on his DraftKings average: half a stat line would
    understate him. Main lines: an NBA player's points; an NFL player's yards at his position; a DST never has one."""
    score = SCORE[league]
    for p in pool:
        m = means.get(players.normalize(p.name)) or {}
        main = {"nba": ("points",), "nfl": ("pass_yards", "rush_yards", "rec_yards", "receptions")}[league]
        if not any(k in m for k in main) or "DST" in p.positions:
            p.proj, p.basis, p.stats = round(p.average, 2), "average", {}
            continue
        s = {**(extras or {}).get(players.normalize(p.name), {}), **m}
        p.proj, p.basis, p.stats = round(score(s), 2), "market", {k: round(v, 2) for k, v in m.items()}


def _eligible(pool: list[Player]) -> list[Player]:
    return [p for p in pool if p.status.upper() not in OUT and p.salary > 0 and p.proj > 0]


def optimize_lineups(pool: list[Player], league: str, n: int = LINEUPS, cap: int = CAP, roster: list[str] | None = None,
                     differ_by: int = DIFFER_BY, time_limit: float = 20.0) -> list[list[tuple[str, Player]]]:
    """The n best legal lineups, each at least `differ_by` players from the ones before it. Rules: the cap, every slot filled by
    a player its slot takes, nobody twice, players from at least two games; in the NFL the quarterback's team has a WR or TE
    with him. A slot's name is in the player's Roster Position list, which is how DraftKings says who fits where."""
    roster = roster or ROSTERS[league]
    pool = _eligible(pool)
    cols = [(i, s) for i, p in enumerate(pool) for s, slot in enumerate(roster) if slot in p.positions]
    if not cols:
        return []
    v = len(cols)
    by_player = [[] for _ in pool]
    by_slot = [[] for _ in roster]
    for c, (i, s) in enumerate(cols):
        by_player[i].append(c)
        by_slot[s].append(c)
    cost = -np.array([pool[i].proj for i, _ in cols])
    games = sorted({p.game for p in pool})
    rows: list[tuple[list[int], list[float], float, float]] = []
    for s in range(len(roster)):
        rows.append((by_slot[s], [1.0] * len(by_slot[s]), 1, 1))
    for cs in by_player:
        if cs:
            rows.append((cs, [1.0] * len(cs), 0, 1))
    rows.append((list(range(v)), [float(pool[i].salary) for i, _ in cols], 0, cap))
    if len(games) >= 2:                                    # no more than a full lineup less one from any one game
        for g in games:
            cs = [c for c, (i, _) in enumerate(cols) if pool[i].game == g]
            rows.append((cs, [1.0] * len(cs), 0, len(roster) - 1))
    if league == "nfl" and "QB" in roster:                 # a QB's team has a receiver with him
        qb = roster.index("QB")
        for c in by_slot[qb]:
            team = pool[cols[c][0]].team
            mates = [m for m, (i, _) in enumerate(cols) if pool[i].team == team and {"WR", "TE"} & set(pool[i].positions)]
            rows.append((mates + [c], [1.0] * len(mates) + [-1.0], 0, np.inf))
    found: list[list[tuple[str, Player]]] = []
    for _ in range(n):
        idx_r, idx_c, vals, lo, hi = [], [], [], [], []
        for r, (cs, ws, a, b) in enumerate(rows):
            idx_r += [r] * len(cs)
            idx_c += cs
            vals += ws
            lo.append(a)
            hi.append(b)
        A = sparse.csr_array((vals, (idx_r, idx_c)), shape=(len(rows), v))
        res = optimize.milp(cost, integrality=np.ones(v), bounds=optimize.Bounds(0, 1),
                            constraints=optimize.LinearConstraint(A, lo, hi), options={"time_limit": time_limit})
        if res.x is None or res.status not in (0, 1):
            break
        chosen = [c for c in range(v) if res.x[c] > 0.5]
        picked = sorted(chosen, key=lambda c: cols[c][1])
        found.append([(roster[cols[c][1]], pool[cols[c][0]]) for c in picked])
        them = sorted({cols[c][0] for c in chosen})
        cs = [c for i in them for c in by_player[i]]      # the next one shares at most (size - differ_by) of these players
        rows.append((cs, [1.0] * len(cs), 0, len(roster) - differ_by))
    return found


def lineup_doc(lineup: list[tuple[str, Player]]) -> dict:
    return {"salary": sum(p.salary for _, p in lineup), "proj": round(sum(p.proj for _, p in lineup), 1),
            "players": [{"slot": s, "id": p.id, "name": p.name, "team": p.team, "game": p.game, "salary": p.salary,
                         "proj": round(p.proj, 1), "basis": p.basis, "status": p.status} for s, p in lineup]}


# ---- reading the feeds -----------------------------------------------------------------------------------------------


def _slates(league: str, today: str, session) -> list[dict]:
    """Today's featured classic slates. A row of the lobby's DraftGroups: "Classic" is told by its game type's name."""
    resp = session.get(LOBBY, params={"sport": LEAGUES[league]}, timeout=20)
    resp.raise_for_status()
    d = resp.json()
    classic = {t["GameTypeId"] for t in d.get("GameTypes") or [] if t.get("Name") == "Classic"}
    out = []
    for g in d.get("DraftGroups") or []:
        if g.get("GameTypeId") not in classic or g.get("DraftGroupTag") != "Featured":
            continue
        if not str(g.get("StartDateEst") or "").startswith(today):
            continue
        out.append({"draft_group": g["DraftGroupId"], "contest_type": g.get("ContestTypeId"), "games": g.get("GameCount"),
                    "label": (g.get("ContestStartTimeSuffix") or "").strip(" ()") or "Main"})
    return out


def salaries(s: dict, session) -> list[Player]:
    resp = session.get(CSV_URL, params={"contestTypeId": s["contest_type"], "draftGroupId": s["draft_group"]}, timeout=30)
    resp.raise_for_status()
    return parse_csv(resp.text)


def odds_quotes(league: str, today: str) -> list[tuple]:
    """(player, stat, point, p_over, source rank) from today's pulled props: sharp books rank 0, the rest 2."""
    import glob

    import pandas as pd

    from betlab import config

    rows = []
    frames = []
    for f in sorted(glob.glob(str(config.DATA_DIR / "odds" / SPORT_KEY[league] / today / "*_props.parquet"))):
        try:
            frames.append(pd.read_parquet(f))
        except (OSError, ValueError):
            continue
    if not frames:
        return rows
    df = pd.concat(frames)
    df = df[df["market"].isin(ODDS_MARKETS) & df["price"].abs().le(10000)]
    df = df.sort_values("snapshot_ts").groupby(["event_id", "bookmaker", "market", "player", "point", "outcome"]).tail(1)
    for (book, market, player, point), g in df.groupby(["bookmaker", "market", "player", "point"]):
        sides = dict(zip(g["outcome"], g["price"]))
        if "Over" not in sides or "Under" not in sides:
            continue
        over, under = _implied(sides["Over"]), _implied(sides["Under"])
        rows.append((player, ODDS_MARKETS[market], float(point), over / (over + under), 0 if book in SHARP else 2))
    return rows


def _implied(american: float) -> float:
    a = float(american)
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def novig_quotes(league: str, within_hours: int = 24) -> tuple[list[tuple], int]:
    """(player, stat, point, p_over, rank 1) from Novig's free catalog; each market's bids on both sides give its middle.
    Also how many events it read. A market needs both bids: one side alone isn't a price."""
    from betlab.sources import novig

    now = datetime.now(timezone.utc)
    rows, n = [], 0
    for e in novig.open_events():
        if e.get("league") != LEAGUES[league]:
            continue
        start = datetime.fromtimestamp(float(e.get("startsTs") or 0) / 1000, timezone.utc)
        if not now < start < now + timedelta(hours=within_hours):
            continue
        n += 1
        for m in novig.markets(e["eventId"]):
            stat = NOVIG_MARKETS.get(m.get("marketType"))
            if not stat:
                continue
            q = novig_row(m, stat)
            if q:
                rows.append(q)
    return rows, n


def novig_row(m: dict, stat: str) -> tuple | None:
    """A market reads "Jalen Brunson 24.5 POINTS" with outcomes Over and Under; an anytime touchdown, Yes and No."""
    out = m.get("outcomes") or []
    if len(out) != 2:
        return None
    bids = [(o.get("bid") or {}).get("price") for o in out]
    if None in bids:
        return None
    a, b = float(bids[0]), float(bids[1])
    if not 0 < a < 1 or not 0 < b < 1:
        return None
    p = (a + (1 - b)) / 2                                  # the middle of the first outcome's bid and its ask
    if str(out[0].get("name", "")).lower().startswith(("under", "no")):
        p = 1 - p
    desc = str(m.get("description") or "")
    point = float(m.get("strike") or 0)
    name = re.sub(r"\s+-?\d+(\.\d+)?\s+[A-Z_]+$", "", desc)
    name = re.sub(r"\s+[A-Z_]{3,}$", "", name).strip()
    return (name, stat, point, p, 1) if name else None


def nba_extras(session_season=None) -> dict[str, dict[str, float]]:
    """Season averages of steals, blocks, turnovers and the double- and triple-double rates, which no line prices here."""
    from betlab.sources import nba

    box = nba.load_player_box([session_season or nba.current_season()], max_age_hours=24)
    return extras_from_box(box)


def extras_from_box(box) -> dict[str, dict[str, float]]:
    import pandas as pd

    box = box[box["did_not_play"] != True]  # noqa: E712
    cols = ["points", "rebounds", "assists", "steals", "blocks", "turnovers", "three_point_field_goals_made"]
    box = box.assign(**{c: pd.to_numeric(box[c], errors="coerce").fillna(0) for c in cols})
    box = box.assign(_cats=(box[["points", "rebounds", "assists", "steals", "blocks"]] >= 10).sum(axis=1))
    out = {}
    for name, g in box.groupby("athlete_display_name"):
        out[players.normalize(name)] = {"steals": float(g["steals"].mean()), "blocks": float(g["blocks"].mean()),
                                        "turnovers": float(g["turnovers"].mean()), "dd": float((g["_cats"] >= 2).mean()),
                                        "td": float((g["_cats"] >= 3).mean()), "threes": float(g["three_point_field_goals_made"].mean()),
                                        "rebounds": float(g["rebounds"].mean()), "assists": float(g["assists"].mean())}
    return out


# ---- the worker's step ----------------------------------------------------------------------------------------------

LINEUP_COLUMNS = ["slate", "league", "label", "lock_at", "lineup", "player_ids", "salary", "proj", "actual", "graded_at"]
PLAYER_COLUMNS = ["slate", "league", "lock_at", "player_id", "name", "team", "salary", "basis", "proj", "average", "actual", "graded_at"]


def _ledger(name: str):
    from betlab import config

    return config.DATA_DIR / "ledger" / name


def log_slate(slate_id: str, league: str, label: str, lock: datetime, lineups: list[dict], pool: list[Player]) -> None:
    """What this slate's latest build said. A later build before the lock replaces it; after the lock it's history, and
    `grade` only fills the result columns. Kept: lineups, and every player priced by the market or in a lineup."""
    import pandas as pd

    used = {x["id"] for lu in lineups for x in lu["players"]}
    lock_at = lock.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    a = pd.DataFrame([{"slate": slate_id, "league": league, "label": label, "lock_at": lock_at, "lineup": i + 1,
                       "player_ids": " ".join(x["id"] for x in lu["players"]), "salary": lu["salary"], "proj": lu["proj"]}
                      for i, lu in enumerate(lineups)], columns=LINEUP_COLUMNS)
    b = pd.DataFrame([{"slate": slate_id, "league": league, "lock_at": lock_at, "player_id": p.id, "name": p.name, "team": p.team,
                       "salary": p.salary, "basis": p.basis, "proj": p.proj, "average": p.average}
                      for p in pool if p.basis == "market" or p.id in used], columns=PLAYER_COLUMNS)
    for name, new, cols in (("dfs_lineups.csv", a, LINEUP_COLUMNS), ("dfs_projections.csv", b, PLAYER_COLUMNS)):
        p = _ledger(name)
        old = pd.read_csv(p, dtype={"slate": str, "player_id": str}) if p.exists() else pd.DataFrame(columns=cols)
        old = old[old["slate"].astype(str) != slate_id]
        pd.concat([df for df in (old, new) if len(df)], ignore_index=True)[cols].to_csv(p, index=False)


def build(league: str, today: str, session, bans_list=None, extras=None, means=None) -> tuple[list[dict], int, int]:
    """Every unlocked slate of a league today, as documents for the apps. Also ([docs], players priced, players in all)."""
    from betlab import bans as B

    docs, priced, total = [], 0, 0
    now = datetime.now(timezone.utc)
    for s in _slates(league, today, session):
        pool = salaries(s, session)
        starts = [p.start for p in pool if p.start]
        if not pool or not starts:
            continue
        lock = min(starts)
        if lock <= now:
            continue                                            # locked: the last build before it stands
        project(pool, league, means or {}, extras)
        keep = [p for p in pool if not B.banned(bans_list or [], p.name, league, p.name) and not B.banned(bans_list or [], p.team, league)]
        lineups = [lineup_doc(lu) for lu in optimize_lineups(keep, league)]
        live = [p for p in pool if p.status.upper() not in OUT]
        n = sum(p.basis == "market" for p in live)
        priced, total = priced + n, total + len(live)
        slate_id = f"{league}:{s['draft_group']}"
        log_slate(slate_id, league, s["label"], lock, lineups, pool)
        docs.append({"slate_id": slate_id, "league": league, "label": s["label"], "lock_at": lock.astimezone(timezone.utc).isoformat(),
                     "games": s.get("games") or len({p.game for p in pool}), "priced": n, "players": len(live), "lineups": lineups})
    return docs, priced, total


def run(db_url: str | None = None, now: datetime | None = None) -> str:
    """Each pregame tick; free. Nothing to do with no slate today. The last line carries "N of M players priced" (the watchdog)."""
    import json

    import psycopg
    import requests

    from betlab import bans as B
    from betlab import config

    now = now or datetime.now(ET)
    today = now.astimezone(ET).strftime("%Y-%m-%d")
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    session = requests.Session()
    docs, priced, total, notes = [], 0, 0, []
    try:
        ban_list = B.use(B.owner_bans())
    except Exception:                                           # noqa: BLE001  (a ban list we can't read: build for no one)
        return "dfs: skipped, the ban list couldn't be read"
    for league in LEAGUES:
        try:
            if not _slates(league, today, session):
                continue
            quotes = sorted(odds_quotes(league, today), key=lambda q: q[4])
            if league == "nba":
                nq, _ = novig_quotes(league)
                quotes += nq
            extras = nba_extras() if league == "nba" else None
            d, p, t = build(league, today, session, ban_list, extras, best_means(quotes))
            docs += d
            priced, total = priced + p, total + t
        except Exception as e:                                  # noqa: BLE001  (a league's feed failing stops only that league)
            code = getattr(getattr(e, "response", None), "status_code", None)     # the code, never the URL
            notes.append(f"dfs: {league} failed ({type(e).__name__}{f' {code}' if code else ''})")
    if docs and db_url:
        with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15) as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.executemany("insert into dfs_slates (slate_id, league, label, lock_at, games, priced, players, lineups, built_at) "
                                "values (%s, %s, %s, %s, %s, %s, %s, %s, now()) on conflict (slate_id) do update set label = excluded.label, "
                                "lock_at = excluded.lock_at, games = excluded.games, priced = excluded.priced, players = excluded.players, "
                                "lineups = excluded.lineups, built_at = now()",
                                [(d["slate_id"], d["league"], d["label"], d["lock_at"], d["games"], d["priced"], d["players"],
                                  json.dumps(d["lineups"])) for d in docs])
                cur.execute("delete from dfs_slates where lock_at < now() - interval '2 days'")
    line = f"dfs: {priced} of {total} players priced, {len(docs)} slate(s)"
    return "\n".join([*notes, line])


def actual_points(league: str, days: list[str]) -> dict[tuple[str, str], float]:
    """{(day, player): real DraftKings points} from the box scores the graders use."""
    import pandas as pd

    out: dict[tuple[str, str], float] = {}
    if league == "nba":
        from betlab.sources import nba

        box = nba.load_player_box([nba.current_season()], max_age_hours=6)
        box = box[box["game_date"].astype(str).isin(days)]
        cols = ["points", "rebounds", "assists", "steals", "blocks", "turnovers", "three_point_field_goals_made"]
        box = box.assign(**{c: pd.to_numeric(box[c], errors="coerce").fillna(0) for c in cols})
        for r in box.itertuples():
            c = sum(getattr(r, k) >= 10 for k in ("points", "rebounds", "assists", "steals", "blocks"))
            out[(str(r.game_date), players.normalize(r.athlete_display_name))] = dk_nba(
                {"points": r.points, "threes": r.three_point_field_goals_made, "rebounds": r.rebounds, "assists": r.assists,
                 "steals": r.steals, "blocks": r.blocks, "turnovers": r.turnovers, "dd": float(c >= 2), "td": float(c >= 3)})
    return out


def grade(now: datetime | None = None) -> str:
    """In the daily: what each locked slate's players and lineups really scored, for players the box scores know. NBA only so
    far (Nov 5): an NFL slate waits for its first Sunday's stats and says so."""
    import pandas as pd

    now = now or datetime.now(ET)
    p, l = _ledger("dfs_projections.csv"), _ledger("dfs_lineups.csv")
    if not p.exists() or not l.exists():
        return "dfs grade: nothing logged yet"
    players_df = pd.read_csv(p, dtype={"slate": str, "player_id": str, "graded_at": object})
    lineups = pd.read_csv(l, dtype={"slate": str, "graded_at": object})
    players_df["day"] = pd.to_datetime(players_df["lock_at"], format="ISO8601", utc=True).dt.tz_convert(ET).dt.strftime("%Y-%m-%d")
    today = now.astimezone(ET).strftime("%Y-%m-%d")
    todo = players_df[players_df["actual"].isna() & (players_df["day"] < today) & (players_df["league"] == "nba")]
    if todo.empty:
        return "dfs grade: 0 of 0 players graded"
    scores = actual_points("nba", sorted(todo["day"].unique()))
    done = 0
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # a player the box score doesn't list by the day after his game didn't play: zero points, as a contest would score him
    for i, r in todo.iterrows():
        players_df.loc[i, "actual"] = scores.get((r["day"], players.normalize(r["name"])), 0.0)
        players_df.loc[i, "graded_at"] = stamp
        done += 1
    by = players_df.dropna(subset=["actual"]).set_index(["slate", "player_id"])["actual"].to_dict()
    for i, r in lineups[lineups["actual"].isna()].iterrows():
        got = [by.get((r["slate"], x)) for x in str(r["player_ids"]).split()]
        if all(x is not None for x in got):
            lineups.loc[i, "actual"] = round(sum(got), 2)
            lineups.loc[i, "graded_at"] = stamp
    players_df[PLAYER_COLUMNS].to_csv(p, index=False)
    lineups[LINEUP_COLUMNS].to_csv(l, index=False)
    return f"dfs grade: {done} of {len(todo)} players graded"
