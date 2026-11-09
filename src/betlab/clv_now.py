"""Live CLV on open bets (Mike, Oct 28: idea #2): how the sharp price has moved since you bet, at every publish.

CLV is your price against the sharp no-vig chance: decimal odds x the sharp chance - 1. The graders measure it at the
close; this measures it now, so you learn within hours whether you got a good number. At each publish (`cmd_publish`),
every open bet whose game hasn't started gets its current value in `bet_clv` (migration 0028), and both apps show it on
the bet. A started game's value stays as it was at the last publish before it: the last look before the close.

- **A single** (a pick, a lean, or one leg entered by hand or synced from Novig): the current sharp chance of that side,
  from the card's offer (same pick id) or else the game's builder pack, the same leg in the same game (`label_forms`:
  "over 2.5" = "3+").
- **An app parlay** (a fun slip or SGP+ ticket): its fair chance at placement (`bets.p_fair`) moved by each leg's change
  since the ticket was priced (now / then, from the ticket's own legs), which keeps the correlation it was priced with.
- **A slip parlay** with every leg in a different game: the legs' current chances multiplied (exact across games). A
  same-game slip has no correlation to start from, so it gets none.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from betlab import odds_math as om


def _norm(s) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\.(?!\d)", "", str(s or "").lower().replace("yards", "yds"))).strip()


_TEAM_LINE = re.compile(r"^(.+?) (ml|to win|[-+]\d+(?:\.\d+)?)$")       # "tulane -10.5", "new york knicks ml", "nyr to win"


def label_forms(label: str) -> set[str]:
    """The ways a pack can write the same leg (web lib/slip.ts labelForms): "over 2.5 receptions" is "3+ receptions"."""
    n = _norm(label)
    out = {n}
    if m := re.match(r"^(.+) over (\d+)\.5 (.+)$", n):
        out.add(f"{m.group(1)} {int(m.group(2)) + 1}+ {m.group(3)}")
    if (m := re.match(r"^(.+) (\d+)\+ (.+)$", n)) and int(m.group(2)) > 0:
        out.add(f"{m.group(1)} over {int(m.group(2)) - 1}.5 {m.group(3)}")
    return out


def _same_team(a: str, b: str) -> bool:
    """Nov 4: the NHL's packs are written in codes ("NYR to win", "STL @ NYR") and slips in full names, so a code counts
    as its full name."""
    from betlab.novig_sync import _full
    from betlab.sources import novig

    return novig._same_team(a, b) or novig._same_team(_full(a, "nhl"), _full(b, "nhl"))


def _same_price_kind(a: str, b: str) -> bool:
    """A moneyline is "ml" on a slip and "to win" in a pack; a spread must be the same number."""
    return a == b or {a, b} == {"ml", "to win"}


def _same_game(a: str, b: str) -> bool:
    sa = [x.strip() for x in re.split(r" @ | vs\.? ", str(a or ""))]
    sb = [x.strip() for x in re.split(r" @ | vs\.? ", str(b or ""))]
    return len(sa) == 2 and len(sb) == 2 and all(any(_same_team(x, y) for y in sb) for x in sa)


class Market:
    """The current sharp chances the publish knows: the card's offers and every game's builder pack."""

    def __init__(self, card: dict, packs: list[dict]):
        self.offers = {o["pick_id"]: o for k in ("picks", "leans") for o in card.get(k) or [] if o.get("pick_id")}
        self.packs = [{"event_id": str(p.get("event_id")), "matchup": p.get("matchup"), "start": p.get("commence_time"),
                       "legs": {f: float(l["p"]) for l in p.get("legs") or [] if l.get("p") is not None
                                for f in label_forms(l["label"])}} for p in packs]

    def leg(self, label: str, event_id=None, matchup=None) -> tuple[float, str] | None:
        """(the leg's current sharp chance, its game's start), from the pack of its game (by event id, else matchup). A
        team's line matches on the team ("Tulane -10.5" is the pack's "Tulane Green Wave -10.5", "New York Rangers ML" the
        pack's "NYR to win") and the same number."""
        forms = label_forms(label)
        team = _TEAM_LINE.match(_norm(label))
        for p in self.packs:
            if (event_id and p["event_id"] == str(event_id)) or (not event_id and matchup and _same_game(p["matchup"], matchup)):
                hit = next((p["legs"][f] for f in forms if f in p["legs"]), None)
                if hit is None and team:
                    hit = next((q for f, q in p["legs"].items() if (t := _TEAM_LINE.match(f)) and _same_price_kind(t.group(2), team.group(2))
                                and _same_team(t.group(1), team.group(1))), None)
                if hit is not None:
                    return hit, p["start"]
        return None


def _clv(price, p) -> float | None:
    return round(om.american_to_decimal(float(price)) * float(p) - 1, 4) if price is not None and p else None


def estimate(bet: dict, m: Market, tickets: dict[str, dict]) -> dict | None:
    """{p_now, clv, start} for one open bet, or None when BetLab can't price it now."""
    price = bet.get("price")
    if price is None:
        return None
    legs = bet.get("legs") or []
    if isinstance(legs, str):
        legs = json.loads(legs)
    if bet.get("pick_id") and bet["pick_id"] in m.offers:                      # a pick or lean still on the card
        o = m.offers[bet["pick_id"]]
        return {"p_now": round(float(o["p_market"]), 4), "clv": _clv(price, o["p_market"]), "start": o.get("commence_time")}
    games = bet.get("games") or []
    if isinstance(games, str):
        games = json.loads(games)
    t = tickets.get(str(bet.get("sgp_id") or ""))
    if t and bet.get("p_fair"):                                                 # an app parlay: move its fair chance
        ratio, starts = 1.0, []
        for g in t["games"]:
            for leg in g["legs"]:
                now = m.leg(leg["label"], g.get("event_id"))
                if now is None or not leg.get("p_fair"):
                    return None
                ratio *= now[0] / float(leg["p_fair"])
                starts.append(now[1])
        p = min(float(bet["p_fair"]) * ratio, 1.0)
        return {"p_now": round(p, 4), "clv": _clv(price, p), "start": min(starts) if starts else None}
    if games:                                                                   # entered by hand, from a slip or Novig
        found = []
        for g in games:
            for label in g.get("legs") or []:
                now = m.leg(label, None, g.get("matchup"))
                if now is None:
                    return None
                found.append((g.get("matchup"), now))
        if len({mu for mu, _ in found}) != len(found):
            return None                                                         # two legs in one game: no correlation
        p = 1.0
        for _, (q, _) in found:
            p *= q
        return {"p_now": round(p, 4), "clv": _clv(price, p), "start": min(s for _, (_, s) in found)}
    if len(legs) == 1 and bet.get("matchup"):
        now = m.leg(legs[0], bet.get("odds_event_id"), bet.get("matchup"))
        return {"p_now": round(now[0], 4), "clv": _clv(price, now[0]), "start": now[1]} if now else None
    return None


def tickets_of(products: dict) -> dict[str, dict]:
    """Every fun slip and SGP+ ticket in the products: {sgp_id: {games: [{event_id, legs}]}} with each leg's p_fair."""
    from betlab.sgp_plus import TICKETS

    out = {}
    for doc in (products.get("fun") or {}, products.get("fun_nba") or {}):
        for g in doc.get("games") or []:
            for s in g.get("sgps") or []:
                out[s["sgp_id"]] = {"games": [{"event_id": g.get("event_id"), "legs": [l for l in s.get("legs") or [] if isinstance(l, dict)]}]}
        for sl in doc.get("slates") or []:
            for s in sl.get("sgps") or []:
                out[s["sgp_id"]] = {"games": [{"event_id": s.get("event_id"), "legs": [l for l in s.get("legs") or [] if isinstance(l, dict)]}]}
            for t in (sl.get(k) for k in TICKETS):
                if t and t.get("games"):
                    out[t["sgp_id"]] = {"games": [{"event_id": g.get("event_id"), "legs": [l for l in g.get("legs") or [] if isinstance(l, dict)]}
                                                  for g in t["games"]]}
    return out


def run(conn, products: dict, packs: list[dict], now: pd.Timestamp | None = None) -> str:
    """Write `bet_clv` for every open bet whose games haven't started."""
    now = now or pd.Timestamp.now(tz="UTC")
    m, tickets = Market(products.get("card") or {}, packs), tickets_of(products)
    cur = conn.cursor()
    cur.execute("select bet_id, user_id, kind, pick_id, sgp_id, price, p_fair, legs, games, matchup, odds_event_id, "
                "coalesce(pick_status, ticket_status, 'open') as status from my_bets where mode = 'real'")
    cols = [d[0] for d in cur.description]
    written = n_open = 0
    for row in cur.fetchall():
        b = dict(zip(cols, row))
        if b["status"] != "open":
            continue
        n_open += 1
        try:
            e = estimate(b, m, tickets)
        except (TypeError, ValueError, KeyError, ZeroDivisionError):
            continue
        if not e or e["clv"] is None or (e.get("start") and pd.Timestamp(e["start"]) <= now):
            continue
        conn.execute("insert into bet_clv (bet_id, user_id, p_now, clv, updated_at) values (%s, %s, %s, %s, %s) "
                     "on conflict (bet_id) do update set p_now = excluded.p_now, clv = excluded.clv, updated_at = excluded.updated_at",
                     [b["bet_id"], b["user_id"], e["p_now"], e["clv"], now.to_pydatetime()])
        written += 1
    return f"live CLV: {written} of {n_open} open bet(s) priced"   # the watchdog reads "N of M"
