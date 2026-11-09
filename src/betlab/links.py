"""Betslip links for the app's "Open in FanDuel" / "Open in DraftKings" buttons (Mike, 2026-09-30; DraftKings Oct 12).

The Odds API returns, per FanDuel outcome, a link like
`https://sportsbook.fanduel.com/addToBetslip?marketId=42.6101&selectionId=25589` (requested with
`includeLinks`, free; saved in each snapshot's `link` column). Our picks and parlay legs don't
carry which FanDuel outcome they came from, so `attach` matches each one to a FanDuel row of the
same game in the latest snapshots: same price, same number, same player (props), and the side
(Over / Under / the team). An ambiguous or missing match gets no link, never a wrong one.

The page puts single bets' links on a button and combines a parlay's legs into one link
(`marketId[0]=..&selectionId[0]=..&marketId[1]=..`), the format betslip-sharing apps use. Bets
are only added to the betslip; Mike reviews and places them himself.

DraftKings (docs/DRAFTKINGS_PLAN.md, day 3): the feed gives every DraftKings outcome a link like
`https://sportsbook.draftkings.com/?outcomes=0ML84695534_3`, one per outcome, matched the same way. A card row
gets the link of the book it's priced at (`book_rows(book)`, `attach_card`). Parlay legs stay FanDuel's until
parlays are built per book (day 4).
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from betlab import config
from betlab.sgp_plus import TICKETS


# FanDuel reads the state from a two-letter subdomain, then a saved region cookie, and otherwise
# shows "pick your state" (checked in its web bundle, 2026-10-01; Mike's request). The feed's links
# use the bare host, so they're moved to New York's.
FD_HOST = "https://ny.sportsbook.fanduel.com"


def ny_link(url: str) -> str:
    """A FanDuel link on the New York host, so it skips the state picker."""
    return re.sub(r"^https?://(?:[a-z]{2}\.)?sportsbook\.fanduel\.com", FD_HOST, url)


def _plain(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace(".", "").split())


def book_rows(book: str = "fanduel", max_age_hours: float = 36.0) -> pd.DataFrame:
    """A book's rows with links (FanDuel's by default) from every sport's latest pick and props snapshots."""
    frames = []
    now = pd.Timestamp.now(tz="UTC")
    for sport_dir in (config.DATA_DIR / "odds").iterdir():
        if not sport_dir.is_dir():
            continue
        for kind in ("pick", "props", "goals"):
            files = sorted(sport_dir.glob(f"*/*_{kind}.parquet"))
            if not files:
                continue
            df = pd.read_parquet(files[-1])
            if "link" not in df or df.empty:
                continue
            if now - pd.to_datetime(df["snapshot_ts"], utc=True).max() > pd.Timedelta(hours=max_age_hours):
                continue
            frames.append(df[(df["bookmaker"] == book) & df["link"].notna()])
    if not frames:
        return pd.DataFrame(columns=["event_id", "market", "outcome", "player", "point", "price", "link"])
    return pd.concat(frames, ignore_index=True)


fanduel_rows = book_rows                     # the name before DraftKings


def book_link(url: str) -> str:
    """A link as the app should open it: FanDuel's on the New York host; DraftKings' as the feed gives it
    (one host for every state: it reads the state from the location check); Novig's with its `{wager}` placeholder
    filled in (Oct 22: novig.com/events/<outcome>/oddsapi/10 opens Novig's order slip with that outcome at $10)."""
    url = str(url)
    if "fanduel.com" in url:
        return ny_link(url)
    if "novig.com" in url and "{wager}" in url:
        wager = (config.settings()["odds_api"].get("novig") or {}).get("default_wager", 5)
        return url.replace("{wager}", f"{wager:g}")
    return url


_CODES: dict | None = None


def _same_side(outcome: str, label: str) -> bool:
    """Does a feed outcome ("Columbus Blue Jackets") name the side in our label ("CBJ ML",
    "Columbus Blue Jackets +1.5")? Full names by text; NHL abbreviations through the NHL's names."""
    o, lab = _plain(outcome), _plain(label)
    if o and o in lab:
        return True
    code = str(label).split()[0] if label else ""
    if code.isupper() and 2 <= len(code) <= 4:
        global _CODES
        if _CODES is None:
            try:
                from betlab.sources import nhl
                _CODES = nhl.team_codes()
            except Exception:
                _CODES = {}
        from betlab.sources.nhl import code_for
        return bool(_CODES) and code_for(outcome, _CODES) == code
    return False


def _alt(markets: pd.Series) -> pd.Series:
    m = markets.astype(str)
    return m.str.endswith("_alternate") | m.str.startswith("alternate_")


class Matcher:
    def __init__(self, rows: pd.DataFrame):
        self.by_event = {str(e): g for e, g in rows.groupby("event_id")} if len(rows) else {}
        # links into a main market with a number: the market keeps its id when its line moves, so the slip gets the
        # new number (Oct 30, Brunson 1.5 -> 2.5). Legs with only such a link carry `link_main` and the apps say to
        # check the line (Mike: "Keep, flag them"); a moneyline or yes/no market has no number to move
        main = rows[~_alt(rows["market"]) & rows["point"].notna() & rows["link"].notna()] \
            if len(rows) and {"market", "point", "link"} <= set(rows.columns) else rows.iloc[:0]
        self.main_links = {book_link(str(u)) for u in main["link"]}

    def find(self, event_id, price, point=None, player=None, side=None, label: str | None = None,
             any_price: bool = False, markets: tuple | None = None) -> str | None:
        """The one FanDuel link for this bet, or None when nothing (or more than one) matches. A straight bet
        needs FanDuel's price unchanged (a moved price may have no edge left); a parlay leg (`any_price`)
        only needs the same selection, since FanDuel prices the parlay as a whole (a soccer goals leg has
        no price at all: the bulk feed lacks FanDuel's goals lines). `markets` keeps only those feed markets."""
        g = self.by_event.get(str(event_id))
        if g is not None and markets:
            g = g[g["market"].isin(markets)] if "market" in g else g.iloc[:0]
        no_price = price is None or pd.isna(price)
        if g is None or g.empty or (no_price and not any_price):
            return None
        if not no_price:
            exact = self._narrow(g[(g["price"].astype(float) - float(price)).abs() < 0.5], point, player, side, label)
            if exact is not None or not any_price:
                return exact
        # A parlay leg whose price moved since the slip was built (a morning ticket, a later pull): the link
        # names the selection, not the price, so the same side and number still match, if exactly one does.
        return self._narrow(g, point, player, side, label)

    def row(self, event_id, point=None, player=None, side=None, label: str | None = None,
            markets: tuple | None = None) -> dict | None:
        """The one outcome row (price, link, point) for a selection at this matcher's book, whatever its price:
        DraftKings' side of a parlay leg (day 4). None when nothing (or more than one) matches."""
        g = self.by_event.get(str(event_id))
        if g is not None and markets:
            g = g[g["market"].isin(markets)] if "market" in g else g.iloc[:0]
        if g is None or g.empty:
            return None
        hit = self._rows(g, point, player, side, label)
        if hit is None or hit["link"].dropna().nunique() != 1:
            return None
        r = hit.dropna(subset=["link"]).iloc[0]
        return {"price": float(r["price"]), "link": book_link(str(r["link"]))}

    @staticmethod
    def _narrow(g: pd.DataFrame, point, player, side, label) -> str | None:
        hit = Matcher._rows(g, point, player, side, label)
        if hit is None:
            return None
        links = hit["link"].dropna().unique()
        return book_link(str(links[0])) if len(links) == 1 else None

    @staticmethod
    def _rows(g: pd.DataFrame, point, player, side, label) -> pd.DataFrame | None:
        if player:
            g = g[g["player"].map(_plain) == _plain(player)]
        if point is not None and not pd.isna(point):     # even for one row: a lone price match isn't enough
            pts = g["point"].astype(float)
            # a moneyline has no number in the feed: a leg's "0" matches a blank; so does a yes/no market's (anytime
            # TD: our leg says 0.5, FanDuel's outcome has no number; Oct 12, every MNF TD leg had no link)
            # (only a 0.5 leg: on Oct 12 a 224.5 passing-yards leg the book had no rung for matched the player's anytime TD)
            yes_no = g["outcome"].astype(str).str.lower().isin(["yes", "no"]) & (abs(float(point) - 0.5) < 0.01)
            g = g[((pts - float(point)).abs() < 0.01) | (pts.isna() & ((float(point) == 0) | yes_no))]
        s = str(side or "").lower()
        if len(g) > 1 and s in ("over", "under"):
            g = g[g["outcome"].str.lower() == s]
        if len(g) > 1 and s in ("yes", "no") and set(g["outcome"].str.lower()) <= {"yes", "no"}:
            g = g[g["outcome"].str.lower() == s]           # soccer's both teams to score
        if len(g) > 1 and label:                 # team-named outcomes: which side does the label name?
            team_rows = ~g["outcome"].str.lower().isin(["over", "under", "yes", "no"])
            if s not in ("over", "under") and team_rows.any():
                g = g[team_rows & g["outcome"].map(lambda o: _same_side(o, label))]
        if len(g) > 1 and "market" in g:
            # the same rung in the main market and the alternate ladder: always the ladder's. A main market keeps its
            # id when its line moves, so its link follows the line (Oct 30: Brunson's main threes line was 1.5 at the
            # 6:45 pull and 2.5 by 6:52, and the ticket's "over 1.5" link put Over 2.5 on Mike's slip); each ladder
            # rung is its own market, fixed to its number
            alt = _alt(g["market"])
            if alt.any():
                g = g[alt]
        return g


GAME_STATS = {"moneyline", "spread", "total", "puck line", "goals", "draw", "double chance", "btts", "total points"}
# Legs whose side ("yes") can't tell feed markets apart: only these markets may match (soccer). A
# double chance has none in our pulls, so it gets no link rather than another market's.
# Every game-line leg matches only its own markets, never a player's prop (Oct 12: soccer tickets' "Over 2.5
# goals" also matched players' "over 2.5 shots" and got no link, "RB Leipzig to win" -190 matched a player's
# shots line priced -190, and "Inter Milan to win" matched both-teams-to-score Yes).
_TOTALS, _SPREADS = ("totals", "alternate_totals"), ("spreads", "alternate_spreads")
LEG_MARKETS = {"btts": ("btts",), "double chance": ("double_chance",), "draw": ("h2h",), "moneyline": ("h2h",),
               "spread": _SPREADS, "puck line": _SPREADS, "total": _TOTALS, "goals": _TOTALS, "total points": _TOTALS}


# A player leg's stat -> the feed markets it may come from (main line and ladder), across sports (Oct 12: a leg must
# never match another market of the same player, like his anytime TD)
STAT_MARKETS = {
    "receptions": ("player_receptions", "player_receptions_alternate"),
    "receiving_yards": ("player_reception_yds", "player_reception_yds_alternate"),
    "rushing_yards": ("player_rush_yds", "player_rush_yds_alternate"),
    "passing_yards": ("player_pass_yds", "player_pass_yds_alternate"),
    "tds": ("player_anytime_td",),
    "points": ("player_points", "player_points_alternate"), "rebounds": ("player_rebounds", "player_rebounds_alternate"),
    "assists": ("player_assists", "player_assists_alternate"), "threes": ("player_threes", "player_threes_alternate"),
    "pra": ("player_points_rebounds_assists",), "pr": ("player_points_rebounds",), "pa": ("player_points_assists",),
    "ra": ("player_rebounds_assists",),
    "shots": ("player_shots_on_goal", "player_shots"), "sot": ("player_shots_on_target",),
    "saves": ("player_total_saves",), "scorer": ("player_goal_scorer_anytime",),
}


def _markets_for(leg: dict) -> tuple | None:
    """The feed markets a leg may match: its game line's, or its player stat's (None: unknown stat, no filter)."""
    if leg.get("stat") in GAME_STATS:
        return LEG_MARKETS.get(leg.get("stat"))
    return STAT_MARKETS.get(leg.get("stat"))


def _leg(m: Matcher, leg: dict, event_id) -> None:
    if leg.get("link"):
        return
    # game-line legs carry a placeholder player ("game side"): only props match on the player
    player = None if leg.get("stat") in GAME_STATS else leg.get("player")
    link = m.find(event_id, leg.get("price"), leg.get("point"), player, leg.get("side"), leg.get("label"), any_price=True,
                  markets=_markets_for(leg))
    if link:
        leg["link"] = link
        if link in m.main_links:
            leg["link_main"] = True


# A card row's market -> the feed markets its link may come from (game lines only; props match on the player)
CARD_MARKETS = {"h2h": ("h2h",), "spreads": _SPREADS, "totals": _TOTALS, "btts": ("btts",)}


def attach_card(card: dict, m) -> int:
    """Links on the card's picks and leans (app/card), each from the book it's priced at. `m`: one Matcher for
    FanDuel, or {book: Matcher}."""
    n = 0
    matchers = m if isinstance(m, dict) else {"fanduel": m}
    for row in (card.get("picks") or []) + (card.get("leans") or []):
        mb = matchers.get(str(row.get("book") or "fanduel").lower())
        if mb is None:
            continue
        link = mb.find(row.get("event_id"), row.get("price"), row.get("point"), row.get("player"), row.get("side"),
                      row.get("label"), markets=CARD_MARKETS.get(row.get("market")))
        if link:
            row["link"] = link
            if link in mb.main_links:
                row["link_main"] = True
            n += 1
        for e in row.get("books") or []:        # each book's own read (books.per_book) gets that book's link
            mx = matchers.get(str(e.get("book") or "").lower())
            if mx is None or e.get("price") is None:
                continue
            same = str(e.get("book")).lower() == str(row.get("book") or "").lower() and e.get("price") == row.get("price")
            got = row.get("link") if same else mx.find(row.get("event_id"), e.get("price"), e.get("point"), row.get("player"),
                                                         row.get("side"), row.get("label"), markets=CARD_MARKETS.get(row.get("market")))
            if got:
                e["link"] = got
                if got in mx.main_links:
                    e["link_main"] = True
    return n


def attach_fun(doc: dict, m: Matcher) -> int:
    """Links on every leg in the fun document: game slips, SGP+ tickets, overs and builder packs."""
    n = 0

    def legs_of(items, event_id):
        nonlocal n
        for leg in items or []:
            _leg(m, leg, event_id)
            n += bool(leg.get("link"))

    for g in doc.get("games") or []:
        for s in g.get("sgps") or []:
            legs_of(s.get("legs"), g.get("event_id"))
        legs_of((g.get("pack") or {}).get("legs"), g.get("event_id"))
    for sl in doc.get("slates") or []:
        for s in sl.get("sgps") or []:            # a lone NBA game's own slips (Oct 19)
            legs_of(s.get("legs"), s.get("event_id"))
        for t in (sl.get(k) for k in TICKETS):
            for g in (t or {}).get("games") or []:
                legs_of(g.get("legs"), g.get("event_id"))
            if t and t.get("legs"):               # the flat copy of the same legs (after a JSON round trip)
                copy_flat_links(t)
        for o in sl.get("overs") or []:
            _leg(m, o, o.get("event_id"))
            n += bool(o.get("link"))
        for pk in sl.get("packs") or []:
            legs_of(pk.get("legs"), pk.get("event_id"))
    return n


def copy_flat_links(t: dict) -> None:
    """A ticket's flat `legs` are its games' legs in order, and "Open in FanDuel" builds the betslip from
    them: each takes its own game's link. By position when the flat list is that concatenation; else only
    labels that occur once, since soccer's "Over 2.5 goals" and "Both teams to score" repeat in every match
    (Oct 12: matched by label alone, legs took another match's link or none). A flat leg with no matching
    game leg keeps nothing rather than a guess."""
    per_game = [l for g in t.get("games") or [] for l in g.get("legs") or []]
    flat = t.get("legs") or []
    if [l.get("label") for l in per_game] == [l.get("label") for l in flat]:
        for f, l in zip(flat, per_game):
            f.pop("link", None)
            f.pop("link_main", None)
            if l.get("link"):
                f["link"] = l["link"]
                if l.get("link_main"):
                    f["link_main"] = True
        return
    counts: dict = {}
    for l in per_game:
        counts[l.get("label")] = counts.get(l.get("label"), 0) + 1
    by_label = {l.get("label"): l for l in per_game if counts[l.get("label")] == 1}
    for f in flat:
        f.pop("link", None)
        f.pop("link_main", None)
        l = by_label.get(f.get("label")) or {}
        if l.get("link"):
            f["link"] = l["link"]
            if l.get("link_main"):
                f["link_main"] = True


# ------------------------------------------------------------------ DraftKings' side of every parlay (day 4, Oct 12)
def _dk_leg(m: Matcher, leg: dict, event_id) -> bool:
    """DraftKings' price and link for one leg (dk_price, dk_link), found by the selection, not the price. A player
    over DraftKings doesn't hang at our number gets its nearest rung instead (plan rule 11; Mike, Oct 12: "DK would
    have either 220 or 230"): the one whose chance is closest to the leg's fair chance, within 20% of the number
    (at least 1) and 10 points of chance, with dk_point and dk_label saying which, and dk_moved."""
    if not isinstance(leg, dict):                  # a bare label (some stored tickets): nothing to match on
        return False
    for k in ("dk_price", "dk_link", "dk_point", "dk_label", "dk_moved", "dk_link_main"):
        leg.pop(k, None)
    player = None if leg.get("stat") in GAME_STATS else leg.get("player")
    r = m.row(event_id, leg.get("point"), player, leg.get("side"), leg.get("label"), markets=_markets_for(leg))
    if r is None and player and str(leg.get("side")).lower() == "over" and leg.get("point") is not None:
        r = _nearest_rung(m, leg, event_id)
    if r is None:
        return False
    leg["dk_price"], leg["dk_link"] = r["price"], r["link"]
    if r["link"] in m.main_links:
        leg["dk_link_main"] = True
    if r.get("point") is not None:
        leg["dk_point"], leg["dk_label"], leg["dk_moved"] = r["point"], r["label"], True
    return True


def _nearest_rung(m: Matcher, leg: dict, event_id) -> dict | None:
    from betlab import odds_math as om

    g = m.by_event.get(str(event_id))
    markets = _markets_for(leg)
    if g is None or not markets:
        return None
    g = g[g["market"].isin(markets) & (g["outcome"].str.lower() == "over")
          & (g["player"].map(_plain) == _plain(leg.get("player"))) & g["link"].notna()]
    point = float(leg["point"])
    g = g[(g["point"].astype(float) - point).abs() <= max(1.0, 0.2 * abs(point))]
    if g.empty:
        return None
    p = leg.get("p_fair")
    if p is None and leg.get("price") is not None:
        p = om.implied_prob(float(leg["price"]))
    if p is None:
        return None
    g = g.assign(gap=(g["price"].astype(float).map(om.implied_prob) - float(p)).abs()).sort_values(["gap", "point"])
    g = g[g["gap"] <= 0.10]                    # never a very different bet
    if g.empty:
        return None
    r = g.iloc[0]
    new = float(r["point"])
    old_txt, new_txt = f"{point + 0.5:g}+", f"{new + 0.5:g}+"
    label = str(leg.get("label") or "")
    label = label.replace(old_txt, new_txt) if old_txt in label else label.replace(f"{point:g}", f"{new:g}")
    return {"price": float(r["price"]), "link": book_link(str(r["link"])), "point": new, "label": label}


def _dk_summary(t: dict, legs: list[dict], qm: dict | None, stand_in: bool) -> None:
    """A ticket's DraftKings side: whether DraftKings posts every leg, its legs' product and a likely quote."""
    from betlab import fun_ledger
    from betlab import odds_math as om

    legs = [l if isinstance(l, dict) else {"label": l} for l in legs]
    have = [l for l in legs if l.get("dk_price") is not None]
    out = {"legs": len(have), "of": len(legs), "moved": sum(1 for l in legs if l.get("dk_moved"))}
    if legs and len(have) == len(legs):
        dec = 1.0
        for l in legs:
            dec *= om.american_to_decimal(float(l["dk_price"]))
        naive = int(round(om.prob_to_american(1 / dec))) if dec > 1 else None
        out["naive_price"] = naive
        out["likely_price"] = fun_ledger.likely_price(qm, t.get("fair_price"), naive, len(legs),
                                                      str(t.get("sgp_id", "")).startswith("plus-")) if qm else None
        out["stand_in"] = stand_in                      # FanDuel's quote pattern until DraftKings has its own
    t["dk"] = out


def attach_dk(doc: dict, m: Matcher, qm: dict | None = None, stand_in: bool = True) -> int:
    """DraftKings' side of the fun document (Mike, Oct 12: both books side by side): every leg's DraftKings price
    and link, and each slip's and ticket's DraftKings summary (`dk`). The slips are built once, from FanDuel's
    prices and our fair odds; DraftKings gets the same selections, so a slip DraftKings doesn't fully post says how
    many legs it has. Returns legs matched."""
    n = 0

    def legs_of(items, event_id):
        nonlocal n
        for leg in items or []:
            n += _dk_leg(m, leg, event_id)

    for g in doc.get("games") or []:
        for s in g.get("sgps") or []:
            legs_of(s.get("legs"), g.get("event_id"))
            _dk_summary(s, s.get("legs") or [], qm, stand_in)
        legs_of((g.get("pack") or {}).get("legs"), g.get("event_id"))
    for sl in doc.get("slates") or []:
        for s in sl.get("sgps") or []:            # a lone NBA game's own slips (Oct 19)
            legs_of(s.get("legs"), s.get("event_id"))
            _dk_summary(s, s.get("legs") or [], qm, stand_in)
        for t in (sl.get(k) for k in TICKETS):
            if not t:
                continue
            for g in t.get("games") or []:
                legs_of(g.get("legs"), g.get("event_id"))
            flat = [l for g in t.get("games") or [] for l in g.get("legs") or []]
            for f, l in zip(t.get("legs") or [], flat):      # the flat copy, in order
                if f.get("label") == l.get("label"):
                    for k in ("dk_price", "dk_link"):
                        if k in l:
                            f[k] = l[k]
            _dk_summary(t, flat or t.get("legs") or [], qm, stand_in)
        for o in sl.get("overs") or []:
            n += _dk_leg(m, o, o.get("event_id"))
        for pk in sl.get("packs") or []:
            legs_of(pk.get("legs"), pk.get("event_id"))
    return n
