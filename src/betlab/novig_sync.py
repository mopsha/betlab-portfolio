"""Mike's Novig bets into My bets, entered and settled from his own Novig account (Oct 22). Read-only.

Mike adds a Novig key to the worker himself (CLAUDE.md, hard rule 1): `NOVIG_KEY_ID` (the key's UUID) and
`NOVIG_PRIVATE_KEY` (its PKCS#8 PEM). A `management::read` key is enough and can't trade or move money; the
`management` key from Novig's profile works too. Without both secrets the step skips at no cost.

- **Signing** (docs.novig.com/api/signing): NOVIG-V3, the timestamp in ms, method, path, canonical query and the
  body's SHA-256, joined by newlines; Ed25519 signs it as is, P-256 with SHA-256 (DER). Base64 into `Novig-Signature`.
- **Bets:** `GET /v3/portfolio/fills`, grouped by outcome: one bet per outcome bought, stake = its cost in units
  (`odds_api.novig.unit_dollars`, $5 = 1u), price = the average cost per contract as American odds, placed at its
  first fill. Its market and event come from the public catalog, for the label and matchup.
- **Results:** `GET /v3/history/positions`: WIN, LOSS or PUSH settles the bet (its saved parlay's status, which
  my_bets reads); a fair-market-value settlement (a price string) settles it at its payout (`bets.cashout`).
- **Bets already entered by hand** (the same day, price within 2 points of chance, stake within 10%) are left alone.
- **Wallets** (Oct 23): a management key's reads map key id to page; `keyId` = the signing key's own id reads the cash wallet
  (the same for a `management::read` key). Trade-credit bets and app parlays don't appear in fills (Mike's Oct 22 bets:
  only the two cash singles did), so those stay entered by hand.
- Parlays: Novig's API documents only straight-contract fills and positions; how app parlays appear is logged so it can
  be checked against Mike's account (Oct 22: two app parlays that day).
"""

from __future__ import annotations

import base64
import functools
import hashlib
import json
import re
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests

from betlab import config
from betlab import odds_math as om

HOST = "https://api.novig.com"
PUBLIC = HOST + "/v3/public/catalog"
KEY_ID, PRIVATE_KEY = "NOVIG_KEY_ID", "NOVIG_PRIVATE_KEY"
RESULT = {"WIN": "won", "LOSS": "lost", "PUSH": "push"}
_UNRESERVED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _enc(s: str) -> str:
    return "".join(c if c in _UNRESERVED else "".join(f"%{b:02X}" for b in c.encode()) for c in s)


def canonical_query(query: str) -> str:
    """Pairs URI-decoded and re-encoded (unreserved kept, the rest %XX), sorted by name then value. A bare '+' is a
    plus, never a space, so it comes out as %2B (Novig's signing vectors)."""
    if not query:
        return ""
    pairs = []
    for part in query.split("&"):
        name, _, value = part.partition("=")
        pairs.append((_enc(urllib.parse.unquote(name)), _enc(urllib.parse.unquote(value))))
    return "&".join(f"{n}={v}" for n, v in sorted(pairs))


def string_to_sign(ts_ms: int, method: str, path: str, query: str = "", body: bytes = b"") -> str:
    return "\n".join(["NOVIG-V3", str(ts_ms), method.upper(), path, canonical_query(query), hashlib.sha256(body).hexdigest()])


def normalize_pem(text: str) -> str:
    """A PKCS#8 PEM from however it was pasted into a one-line variable (Oct 23: Railway turned its line breaks into
    spaces, MalformedFraming): literal '\\n's, spaces for newlines, or the base64 body alone."""
    import re

    t = text.replace("\\n", "\n").strip().strip('"').strip("'")
    m = re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", t, flags=re.S)
    label, body = (m.group(1), m.group(2)) if m else ("PRIVATE KEY", t)
    body = re.sub(r"\s+", "", body)
    return f"-----BEGIN {label}-----\n" + "\n".join(body[i:i + 64] for i in range(0, len(body), 64)) + f"\n-----END {label}-----\n"


def sign(private_pem: str, message: str) -> str:
    """Base64 signature: Ed25519 over the message, or P-256 ECDSA with SHA-256 (DER)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519

    key = serialization.load_pem_private_key(normalize_pem(private_pem).encode(), password=None)
    data = message.encode()
    if isinstance(key, ed25519.Ed25519PrivateKey):
        sig = key.sign(data)
    elif isinstance(key, ec.EllipticCurvePrivateKey):
        sig = key.sign(data, ec.ECDSA(hashes.SHA256()))
    else:
        raise ValueError("Novig keys are Ed25519 or P-256")
    return base64.b64encode(sig).decode()


class Paused(RuntimeError):
    """Novig's 423 SYSTEM_LOCKED ("Trading is paused: Maintenance", Oct 27 7 PM): nothing to read, try next tick."""


class Client:
    def __init__(self, key_id: str, private_pem: str, session=None):
        self.key_id, self.pem = key_id.strip(), normalize_pem(private_pem)
        self.session = session or requests.Session()

    def call(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        query = urllib.parse.urlencode(params or {})
        data = json.dumps(body).encode() if body is not None else b""
        ts = int(time.time() * 1000)
        headers = {"Novig-Key-Id": self.key_id, "Novig-Timestamp": str(ts),
                   "Novig-Signature": sign(self.pem, string_to_sign(ts, method, path, query, data)), "User-Agent": "BetLab"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        r = self.session.request(method, f"{HOST}{path}" + (f"?{query}" if query else ""), headers=headers,
                                 data=data or None, timeout=30)
        if r.status_code == 423:
            raise Paused(f"Novig {path}: paused ({r.text[:120]})")
        if r.status_code >= 400:     # never echo the request: no secret is in it, but keep errors short
            raise RuntimeError(f"Novig {path}: HTTP {r.status_code} {r.text[:160]}")
        return r.json()

    def get(self, path: str, params: dict | None = None) -> dict:
        return self.call("GET", path, params)

    def post(self, path: str, body: dict) -> dict:
        return self.call("POST", path, body=body)

    def wallet(self, body: dict) -> dict:
        """The primary wallet's page. A trading key's read is the bare page; a management key's is a map of key id to
        page (PerWalletResponse), so reading `items` off it found nothing (Oct 23: every run said 0 fills)."""
        if "items" in body:
            return body
        if self.key_id in body:
            return body[self.key_id]
        raise RuntimeError(f"Novig answered no page for this key's wallet (wallets: {len(body)})")

    def pages(self, path: str, params: dict | None = None) -> list[dict]:
        """Every page of a personal listing, from the primary wallet (keyId = the management key's own id)."""
        out, after = [], None
        while True:
            body = self.get(path, {**(params or {}), "keyId": self.key_id, "limit": 5000, **({"after": after} if after else {})})
            page = self.wallet(body)
            out += page.get("items", [])
            after = page.get("next")
            if not after:
                return out


def client() -> Client | None:
    key_id, pem = config.secret(KEY_ID), config.secret(PRIVATE_KEY)
    return Client(key_id, pem) if key_id and pem else None


def _public(path: str) -> dict | None:
    try:
        r = requests.get(f"{PUBLIC}/{path}", headers={"User-Agent": "BetLab"}, timeout=30)
        return r.json() if r.ok else None
    except requests.RequestException:
        return None


def unit_dollars() -> float:
    return float((config.settings()["odds_api"].get("novig") or {}).get("unit_dollars", 5))


def outcome_label(market: dict | None, outcome_id: str) -> str:
    """'Salzburg to win', 'Draw', 'Over 2.5' or the outcome's own name with its market."""
    if not market:
        return "Novig position"
    oc = next((o for o in market.get("outcomes") or [] if o.get("outcomeId") == outcome_id), {})
    name, kind = str(oc.get("name", "")), str(market.get("marketType", ""))
    desc = str(market.get("description", "")).replace(kind, "").strip()
    if kind == "MONEYLINE_3_WAY_WIN":
        return f"{desc} to win" if name.lower() == "yes" else f"{desc} not to win"
    if kind == "MONEYLINE_3_WAY_DRAW":
        return "Draw" if name.lower() == "yes" else "No draw"
    if name.lower() in ("yes", "no"):
        return f"{desc} {name}"
    player = _player(market)
    if player and name.split()[:1] in (["Over"], ["Under"]):         # "Over 0.5" alone hid whose goal it was (Oct 28)
        return f"{player} {name.lower()} {STAT.get(kind, kind.replace('PLAYER_', '').replace('_', ' ').lower())}"
    return name or desc or "Novig position"


def _player(market: dict) -> str:
    """The player in a prop market's description ("Travis Konecny 0.5 PLAYER_GOALS"); empty for a game market."""
    if not str(market.get("marketType", "")).startswith("PLAYER_") and market.get("marketType") not in STAT:
        return ""
    return re.sub(r"\s+-?\d+(\.\d+)?\s+[A-Z_]+$|\s+[A-Z_]+$", "", str(market.get("description", ""))).strip()


# ------------------------------------------------------------------ our game and our wording (Oct 28)
# Mike: "why is auto novig bet doesnt look like our other cool bets in my bets?" A synced bet read "TULN -10.5 · Novig
# $5.00 (auto)" with Novig's short matchup and no game, so My bets had nothing to track, no logos and no scoreboard.
# Now each one is matched to the app's game (both teams, start within 15 minutes) and written as a slip's bet is: the
# leg in our words ("Tulane -10.5", "Jack Hughes 1+ goals"), the game's matchup, and `games` with its grader ref
# (web lib/slip.ts gameRef). Unmatched, it keeps Novig's own words.
STAT = {"POINTS": "points", "REBOUNDS": "rebounds", "ASSISTS": "assists", "THREE_POINTERS_MADE": "threes",
        "POINTS_REBOUNDS_ASSISTS": "pts + reb + ast", "POINTS_REBOUNDS": "pts + reb", "POINTS_ASSISTS": "pts + ast",
        "REBOUNDS_ASSISTS": "reb + ast", "STEALS": "steals", "BLOCKS": "blocks", "SHOTS_ON_GOAL": "shots on goal",
        "SAVES": "saves", "RECEPTIONS": "receptions", "RECEIVING_YARDS": "receiving yds", "RUSHING_YARDS": "rushing yds",
        "PASSING_YARDS": "passing yds", "RUSHING_AND_RECEIVING_YARDS": "rush + rec yds", "SHOTS_ON_TARGET": "shots on target"}


def _sides(matchup: str) -> tuple[str, str] | None:
    """(away, home) from "Away @ Home"."""
    return tuple(x.strip() for x in matchup.split(" @ ", 1)) if " @ " in str(matchup) else None


def _full(team: str, league: str | None) -> str:
    """A team code in the app's games ("PHI", the NHL's matchups) as its full name ("Philadelphia Flyers"), from
    teams.json; anything else as it is."""
    for t in _TEAMS().get(league or "", []):
        if team.upper() in t.get("abbr", []):
            return t["name"]
    return team


@functools.cache
def _TEAMS() -> dict:
    return json.loads((Path(__file__).parent / "teams.json").read_text())


def our_game(ev: dict | None, games: list[dict]) -> dict | None:
    """The app's game (a `games` row) for a Novig event: both teams and a start within 15 minutes. Oct 28: the NHL's
    games are written in codes ("PHI @ WSH"), so a code counts as its full name."""
    from betlab.sources import novig

    same = lambda nv, ours, g: novig._same_team(nv, ours) or novig._same_team(nv, _full(ours, g.get("league")))
    t = _sides((ev or {}).get("description", ""))
    if not t or not ev.get("startsTs"):
        return None
    start = float(ev["startsTs"]) / 1000
    hits = [g for g in games if (s := _sides(g.get("matchup") or "")) and g.get("commence_time") is not None
            and abs(pd.Timestamp(g["commence_time"]).timestamp() - start) <= 15 * 60
            and same(t[0], s[0], g) and same(t[1], s[1], g)]
    return hits[0] if len(hits) == 1 else None


def game_ref(g: dict) -> str | None:
    """The grader's ref for an app game (web lib/slip.ts gameRef): NFL's nflverse id, "ncaaf:<id>", "nhl:<id>",
    "nba|HOME|AWAY|<start>"; None where the sport's ref needs more (soccer's league, a UFC fight)."""
    from betlab import bans
    from betlab.sources.nba import NBA_TEAMS

    gid = str(g["game_id"]).split(":", 1)[-1] if ":" in str(g["game_id"]) else str(g["game_id"])
    league = g.get("league")
    if league == "nfl":
        return gid if re.match(r"^\d{4}_\d{2}_", gid) else None
    if league in ("ncaaf", "ncaab", "nhl"):
        return f"{league}:{gid}"
    if league == "nba":
        s = _sides(g.get("matchup") or "")
        code = lambda name: next((a for t in bans.teams().get("nba", []) if t["name"] == name for a in t["abbr"] if a in NBA_TEAMS), None)
        h, a = (code(s[1]), code(s[0])) if s else (None, None)
        start = pd.Timestamp(g["commence_time"]).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S+00:00")
        return f"nba|{h}|{a}|{start}" if h and a else None
    return None


def our_label(market: dict | None, outcome_id: str, g: dict | None) -> str | None:
    """A Novig outcome in the app's own wording, given its game; None when it isn't one BetLab writes."""
    if not market or not g:
        return None
    oc = market.get("outcomes") or []
    idx = next((i for i, o in enumerate(oc) if o.get("outcomeId") == outcome_id), None)
    s = _sides(g.get("matchup") or "")
    if idx is None or not s:
        return None
    kind, name = str(market.get("marketType", "")), str(oc[idx].get("name", ""))
    strike = float(market.get("strike") or 0)
    team = s[1] if idx == 0 else s[0]                       # Novig lists the home side first
    soccer_or_hockey = g.get("league") in ("soccer", "nhl")
    if kind == "MONEY":
        return f"{team} ML"
    if kind == "SPREAD":
        num = re.search(r"([-+]\d+(?:\.\d+)?)\s*$", name)
        return f"{team} {num.group(1)}" if num else None
    if kind == "TOTAL" and name.split()[0] in ("Over", "Under"):
        return f"{name.split()[0]} {strike:g} {'goals' if soccer_or_hockey else 'total points'}"
    if kind == "MONEYLINE_3_WAY_DRAW" and name.lower() == "yes":
        return "Draw"
    if kind == "MONEYLINE_3_WAY_WIN" and name.lower() == "yes":
        desc = str(market.get("description", "")).replace(kind, "").strip()
        from betlab.sources import novig
        return f"{s[1] if novig._same_team(desc, s[1]) else s[0]} to win"
    if kind == "BOTH_TEAMS_TO_SCORE":
        return "Both teams to score" if name.lower() == "yes" else None
    player = re.sub(r"\s+-?\d+(\.\d+)?\s+[A-Z_]+$|\s+[A-Z_]+$", "", str(market.get("description", ""))).strip()
    over = name.lower().startswith("over")
    if kind == "PLAYER_GOALS" and over:
        return f"{player} {int(strike + 0.5)}+ goals"
    if kind == "ANYTIME_TOUCHDOWN_SCORER" and name.lower() == "yes":
        return f"{player} anytime TD"
    if kind == "DOUBLE_DOUBLE" and name.lower() == "yes":
        return f"{player} double-double"
    if kind in STAT and name.split()[0] in ("Over", "Under"):
        return f"{player} {'over' if over else 'under'} {strike:g} {STAT[kind]}"
    return None


def ours(market: dict | None, ev: dict | None, outcome_id: str, games: list[dict]) -> dict:
    """The bet's label, matchup, legs, games and odds event as the app writes a slip's, falling back to Novig's words."""
    g = our_game(ev, games)
    label = our_label(market, outcome_id, g)
    if g is None or label is None:
        label = outcome_label(market, outcome_id)
        return {"label": label, "matchup": (ev or {}).get("description") or "Novig", "legs": [label], "games": None,
                "odds_event_id": None}
    ref = game_ref(g)
    return {"label": label, "matchup": g["matchup"], "legs": [label],
            "games": [{"matchup": g["matchup"], **({"game_ref": ref} if ref else {}), "legs": [label]}],
            "odds_event_id": g.get("odds_event_id")}


def bets_from_fills(fills: list[dict]) -> list[dict]:
    """One bet per outcome bought: cost and contracts summed, first fill time, average price."""
    by = defaultdict(lambda: {"cost": 0.0, "qty": 0.0, "ts": None, "market": None})
    for f in fills:
        b = by[f["outcomeId"]]
        b["cost"] += float(f.get("cost") or 0)
        b["qty"] += float(f.get("qty") or 0)
        b["ts"] = min(b["ts"], int(f["ts"])) if b["ts"] else int(f["ts"])
        b["market"] = f.get("marketId")
    out = []
    for oid, b in by.items():
        if b["qty"] <= 0 or b["cost"] <= 0:
            continue
        p = 100 * b["cost"] / b["qty"]           # docs: price = 100 x cost / qty
        if not 0.005 < p < 0.995:
            continue
        out.append({"outcome_id": oid, "market_id": b["market"], "cost": round(b["cost"], 2), "p": p,
                    "price": float(round(om.prob_to_american(p))), "ts": b["ts"]})
    return out


def _json_list(v) -> list:
    """A jsonb column as a list (psycopg gives lists; a test or an old row may give its text)."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    return v if isinstance(v, list) else []


def _duplicate(bet: dict, existing: pd.DataFrame, unit: float, used: set, ref: str | None = None) -> str | None:
    """The Novig bet Mike entered by hand that this fill is: the same ET day, chance within 2 points, stake within 10%,
    a single (a parlay entered by hand is never one fill), on the same game when both know theirs (`ref`: the fill's
    game ref). Each hand entry stands for one fill only (`used`, Nov 9: one entry swallowed two similar 1u singles that
    day, and the second never reached My bets). The closest chance wins. Returns the entry's sgp_id, or None."""
    if existing.empty:
        return None
    day = pd.Timestamp(bet["ts"], unit="ms", tz="UTC").tz_convert("America/New_York").date()
    stake = bet["cost"] / unit
    best, gap = None, None
    for r in existing.itertuples():
        if r.sgp_id in used or pd.Timestamp(r.placed_at).tz_convert("America/New_York").date() != day:
            continue
        if r.price is None or pd.isna(r.price) or r.stake is None or pd.isna(r.stake):
            continue
        legs, games = _json_list(getattr(r, "legs", None)), _json_list(r.games)
        if len(legs) > 1 or len(games) > 1:
            continue
        refs = {g.get("game_ref") for g in games if isinstance(g, dict) and g.get("game_ref")}
        if ref and refs and ref not in refs:
            continue
        d = abs(om.implied_prob(float(r.price)) - bet["p"])
        if d <= 0.02 and abs(float(r.stake) - stake) <= 0.1 * stake and (gap is None or d < gap):
            best, gap = r.sgp_id, d
    return best


def run() -> str:
    """Enter new Novig bets and settle finished ones; returns one line for the runs log."""
    cl = client()
    if cl is None:
        return "novig-sync: no Novig key set (NOVIG_KEY_ID, NOVIG_PRIVATE_KEY): skipping"
    url, owner = config.secret("SUPABASE_DB_URL"), config.owner_user_id()
    if not url or not owner:
        return "novig-sync: SUPABASE_DB_URL or OWNER_USER_ID not set, skipping"
    import psycopg

    try:
        fills = cl.pages("/v3/portfolio/fills")
        positions = cl.pages("/v3/history/positions")
    except Paused as e:                  # maintenance isn't a failure: the next tick reads it all
        return f"novig-sync: {e}, skipping"
    unit = unit_dollars()
    new = bets_from_fills(fills)
    settled = {p["outcomeId"]: p for p in positions if p.get("result") not in (None, "TBD")}
    added = settled_n = dupes = 0
    with psycopg.connect(url, prepare_threshold=None, autocommit=True) as conn:
        rows = conn.execute("select sgp_id, price, stake, placed_at, games, legs from bets where user_id = %s and book = 'Novig'",
                            [owner]).fetchall()
        existing = pd.DataFrame(rows, columns=["sgp_id", "price", "stake", "placed_at", "games", "legs"])
        by_hand = existing[~existing["sgp_id"].fillna("").str.startswith("novig-")]
        used: set = set()              # hand entries already standing for a fill this run
        mine = set(existing["sgp_id"].dropna())
        bare = set(existing[existing["games"].isna() & existing["sgp_id"].fillna("").str.startswith("novig-")]["sgp_id"])
        games = [dict(zip(("game_id", "league", "matchup", "commence_time", "odds_event_id"), r)) for r in conn.execute(
            "select game_id, league, matchup, commence_time, odds_event_id from games "
            "where commence_time > now() - interval '30 days'").fetchall()]
        markets, events = {}, {}
        for b in sorted(new, key=lambda x: x["ts"]):       # oldest first: the same fill claims the same entry every tick
            sid = f"novig-{b['outcome_id']}"
            if sid not in mine or sid in bare:
                m = markets.setdefault(b["market_id"], _public(f"markets/{b['market_id']}") if b["market_id"] else None)
                ev = events.setdefault(m.get("eventId"), _public(f"events/{m['eventId']}")) if m and m.get("eventId") else None
                o = ours(m, ev, b["outcome_id"], games)
                if sid not in mine:
                    ref = next((g.get("game_ref") for g in o["games"] or [] if g.get("game_ref")), None)
                    hit = _duplicate(b, by_hand, unit, used, ref)
                    if hit:
                        used.add(hit)
                        dupes += 1
                        continue
                if sid in bare:                  # entered before Oct 28 in Novig's words: rewritten once matched
                    if o["games"]:
                        conn.execute("update bets set label = %s, matchup = %s, legs = %s, games = %s, odds_event_id = %s "
                                     "where user_id = %s and sgp_id = %s",
                                     [o["label"], o["matchup"], json.dumps(o["legs"]), json.dumps(o["games"]),
                                      o["odds_event_id"], owner, sid])
                        conn.execute("update custom_parlays set legs = %s, matchup = %s where user_id = %s and sgp_id = %s",
                                     [json.dumps(o["legs"]), o["matchup"], owner, sid])
                        bare.discard(sid)
                else:
                    placed = pd.Timestamp(b["ts"], unit="ms", tz="UTC").to_pydatetime()
                    conn.execute(
                        "insert into bets (user_id, kind, mode, book, price, stake, bonus, label, matchup, sgp_id, legs, games, "
                        "odds_event_id, placed_at) values (%s, 'custom', 'real', 'Novig', %s, %s, false, %s, %s, %s, %s, %s, %s, %s)",
                        [owner, b["price"], round(b["cost"] / unit, 3), o["label"], o["matchup"], sid, json.dumps(o["legs"]),
                         json.dumps(o["games"]) if o["games"] else None, o["odds_event_id"], placed])
                    conn.execute(
                        "insert into custom_parlays (user_id, sgp_id, price, legs, matchup, n_legs, quoted_at) "
                        "values (%s, %s, %s, %s, %s, 1, %s) on conflict (user_id, sgp_id) do nothing",
                        [owner, sid, b["price"], json.dumps(o["legs"]), o["matchup"], placed])
                    mine.add(sid)
                    added += 1
            pos = settled.get(b["outcome_id"])
            if pos is None:
                continue
            status = RESULT.get(str(pos["result"]).upper())
            if status:
                cur = conn.execute("update custom_parlays set status = %s, graded_at = now() where user_id = %s and sgp_id = %s "
                                   "and status is distinct from %s", [status, owner, sid, status])
            else:                                  # settled at fair market value: what it paid back
                cur = conn.execute("update bets set cashout = %s where user_id = %s and sgp_id = %s and cashout is distinct from %s",
                                   [round(float(pos.get("payout") or 0) / unit, 3), owner, sid, round(float(pos.get("payout") or 0) / unit, 3)])
            settled_n += cur.rowcount or 0
    return (f"novig-sync: {len(fills)} fills, {len(positions)} positions ({len(settled)} settled); "
            f"{added} new bet(s), {settled_n} settled, {dupes} already entered by hand")
