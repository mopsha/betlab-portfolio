"""Mike's sportsbooks (Oct 12: FanDuel and DraftKings) and how the card chooses between them.

Each game-line evaluator prices every book in `odds_api.target_books` against the same sharp no-vig market
(neither book is ever the other's market: market.reference_books). `select` then applies the rules of
docs/DRAFTKINGS_PLAN.md:
- One offer per bet: a bet is a league, game, market, side and player (the pick id, ledger.pick_id), so the same
  side at both books, at the same number or different ones, is one offer.
- The higher EV wins. At different numbers that's a different bet with a different chance, each priced at its own
  number (rule 1); at the same number it's the better price (rule 2). A tie goes to FanDuel (Mike, Oct 12).
- The other book's line, price and EV ride along (`other_book`, `other_point`, `other_price`, `other_ev`), so the
  app and alerts show both prices (Mike, Oct 12).
- Player names differ by book ("A.J. Brown" / "AJ Brown", accents, "Jr."): a bet's player is matched across books
  by `player_key` when the evaluator sets one (a roster id), else by players.normalize plus the alias file, and the
  chosen offer takes FanDuel's spelling when FanDuel posts the bet, so pick ids from before DraftKings hold (rule 8).
The ledger logs a pick once at the first book it qualified at (ledger.add_picks keeps the first pick id), so a
better price later elsewhere never rewrites the paper record (rule 4).

Novig (Oct 22), the CFTC sports exchange, is a third book for game lines only (`odds_api.prop_books` keeps props and
parlays at the sportsbooks). Its prices carry no vig, and each comes with a bet limit, the dollars available at it:
`price_all` attaches it from the snapshot (`bet_limit`), and `select` never lets a Novig price with less than
`odds_api.novig.min_limit` behind it (or none found) win the best-book choice; the sportsbooks' price stands instead.
"""

from __future__ import annotations

import inspect

import pandas as pd

from betlab import config

NAME = {"fanduel": "FanDuel", "draftkings": "DraftKings", "novig": "Novig"}
KEY = ["league", "event_id", "market", "side", "player"]          # one bet, as ledger.pick_id


def targets(kind: str = "lines") -> list[str]:
    """The books Mike bets at, FanDuel first (the tie-break order): every one for game lines; `prop_books` (the
    sportsbooks) for props."""
    s = config.settings()["odds_api"]
    books = list(s.get("target_books") or [s.get("target_book", "fanduel")])
    return [b for b in books if b in s["prop_books"]] if kind == "props" and s.get("prop_books") else books


def min_limit() -> float:
    return float((config.settings()["odds_api"].get("novig") or {}).get("min_limit", 0))


EXCHANGES = ("novig",)       # books whose prices come with a bet limit


def name(book: str | None) -> str:
    return NAME.get(str(book or "fanduel"), str(book).title())


def price_all(evaluate, *args, kind: str = "lines", **kwargs) -> pd.DataFrame:
    """An evaluator run once per book (`kind` "props": the sportsbooks only), rows stacked (an evaluator without a
    `book` argument prices FanDuel only). Every evaluator takes the snapshot first: an exchange's offers get their
    bet limits from it."""
    if "book" not in inspect.signature(evaluate).parameters:
        return evaluate(*args, **kwargs)
    frames = [evaluate(*args, **kwargs, book=b) for b in targets(kind)]
    frames = [f for f in frames if f is not None and len(f)]
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(out) and args and isinstance(args[0], pd.DataFrame):
        out = attach_limits(out, args[0])
    return out


def attach_limits(offers: pd.DataFrame, snap: pd.DataFrame) -> pd.DataFrame:
    """Each exchange offer's bet limit: its snapshot row's (same game, market, price, number and side, matched as
    the betslip links are, links.Matcher). NaN where none matches exactly once."""
    from betlab import links

    if "book" not in offers or "bet_limit" not in snap:
        return offers
    out = offers.copy()
    if "bet_limit" not in out:
        out["bet_limit"] = float("nan")
    for book in EXCHANGES:
        rows = snap[(snap["bookmaker"] == book) & snap["bet_limit"].notna()]
        mine = out.index[out["book"] == book]
        if rows.empty or not len(mine):
            continue
        by_event = {str(e): g for e, g in rows.groupby("event_id")}
        for i in mine:
            r = out.loc[i]
            g = by_event.get(str(r.get("event_id")))
            if g is None:
                continue
            g = g[g["market"].isin(links.CARD_MARKETS.get(r.get("market"), (r.get("market"),)))]
            g = g[(g["price"].astype(float) - float(r["price"])).abs() < 0.5]
            hit = links.Matcher._rows(g, r.get("point"), r.get("player"), r.get("side"), r.get("label")) if len(g) else None
            if hit is not None and len(hit) == 1:
                out.at[i, "bet_limit"] = float(hit["bet_limit"].iloc[0])
    return out


def player_key(df: pd.DataFrame) -> pd.Series:
    """The same player at every book: the evaluator's `player_key` (a roster id) where set, else the normalized
    name through config/player_aliases.yaml ('' for game lines)."""
    from betlab import players

    al = players.aliases()
    names = df["player"].fillna("").astype(str) if "player" in df else pd.Series("", index=df.index)
    norm = names.map(lambda n: al.get(players.normalize(n), players.normalize(n)) if n else "")
    if "player_key" in df:
        given = df["player_key"].astype(object).where(df["player_key"].notna(), None)
        return pd.Series([f"id:{g}" if g is not None and str(g) != "" else n for g, n in zip(given, norm)], index=df.index)
    return norm


def select(offers: pd.DataFrame) -> pd.DataFrame:
    """One row per bet: the book with the higher EV (ties to the first book in targets(), FanDuel), with the
    other book's line, price and EV attached. Rows without a book column pass through."""
    if offers is None or offers.empty or "book" not in offers:
        return offers
    order = {b: i for i, b in enumerate(targets())}
    df = offers.copy()
    if "bet_limit" in df or df["book"].isin(EXCHANGES).any():
        # an exchange price with too little behind it (or none found) isn't a bet: the sportsbooks' price stands
        lim = df["bet_limit"] if "bet_limit" in df else pd.Series(float("nan"), index=df.index)
        df = df[~df["book"].isin(EXCHANGES) | (lim.fillna(0) >= min_limit())]
        if df.empty:
            return df
    df["_rank"] = df["book"].map(order).fillna(len(order))
    df["_player"] = player_key(df)
    key = [k if k != "player" else "_player" for k in KEY if k in df or k == "player"]
    df = df.sort_values(["ev", "_rank"], ascending=[False, True], kind="mergesort")
    best = df.drop_duplicates(key, keep="first").copy()
    if "player" in df:                       # FanDuel's spelling when it posts the bet (stable pick ids)
        first = targets()[0]
        fd = df[df["book"] == first].drop_duplicates(key).set_index(key)["player"]
        for i, r in best[best["book"] != first].iterrows():
            k = tuple(r[c] for c in key)
            if k in fd.index and isinstance(fd.loc[k], str) and fd.loc[k] != r["player"]:
                old, new = str(r["player"]), fd.loc[k]
                best.at[i, "player"] = new
                if isinstance(r.get("label"), str):
                    best.at[i, "label"] = r["label"].replace(old, new)
    rest = df.drop(best.index)
    rest = rest.drop_duplicates(key, keep="first").set_index(key)
    other = {c: [] for c in ("other_book", "other_point", "other_price", "other_ev")}
    for _, r in best.iterrows():
        k = tuple(r[c] for c in key)
        o = rest.loc[k] if k in rest.index else None
        other["other_book"].append(None if o is None else o["book"])
        other["other_point"].append(None if o is None else o.get("point"))
        other["other_price"].append(None if o is None else o["price"])
        other["other_ev"].append(None if o is None else o["ev"])
    for c, v in other.items():
        best[c] = v
    return best.drop(columns=["_rank", "_player"]).sort_index()


def _keys(df: pd.DataFrame) -> list[tuple]:
    pk = player_key(df)
    cols = [c for c in KEY if c != "player" and c in df]
    return [tuple(r[c] for c in cols) + (p,) for (_, r), p in zip(df.iterrows(), pk)]


def per_book(offers: pd.DataFrame, chosen: pd.DataFrame, read) -> list[list[dict]]:
    """Each book's own read of every chosen bet (Mike, Nov 6: "turn on or off different books for EVERYTHING"): its line,
    price and EV, and the tier and units it earns as if it were the only book, by the same rules (`read`: classify and
    stake, run on that book's offers alone, so a Novig price under the limit is no bet there either). The apps show a
    bet at the best book an account has on, and drop it when none of them makes it a bet; the card itself is unchanged.
    One list per row of `chosen`, in the targets() order."""
    if offers is None or offers.empty or "book" not in offers or chosen is None or chosen.empty:
        return [[] for _ in range(0 if chosen is None else len(chosen))]
    order = targets()
    reads: dict[tuple, list[dict]] = {}
    for b in sorted(offers["book"].dropna().unique(), key=lambda x: order.index(x) if x in order else len(order)):
        mine = select(offers[offers["book"] == b])
        if mine is None or mine.empty:
            continue
        r = read(mine.drop(columns=[c for c in mine if c.startswith("other_")]))
        for k, (_, row) in zip(_keys(r), r.iterrows()):
            reads.setdefault(k, []).append({
                "book": name(b), "price": _num(row.get("price")), "point": _num(row.get("point")), "ev": _num(row.get("ev")),
                "tier": row.get("tier") or None, "units_tier": _num(row.get("units_tier")), "bet_limit": _num(row.get("bet_limit"))})
    return [reads.get(k, []) for k in _keys(chosen)]


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


# ---------------------------------------------------------------------------------- books on and off (Nov 6, 0043)
SHOWN = ("FanDuel", "DraftKings", "Novig")       # the apps' names, the tie-break order


def on_books(off) -> list[str]:
    """The books an account has on (user_settings.books_off): never none, so all three off reads as none off."""
    off = set(off or [])
    on = [b for b in SHOWN if b not in off]
    return on or list(SHOWN)


def _best(entries: list[dict], on: list[str], need_tier: bool, skip: str | None = None) -> dict | None:
    best = None
    for e in entries:
        if e.get("book") not in on or e.get("book") == skip or e.get("price") is None or (need_tier and not e.get("tier")):
            continue
        if best is None or (e.get("ev") or 0) > (best.get("ev") or 0):
            best = e
    return best


def at_books(offer: dict, off) -> dict | None:
    """A published card bet (an `offers` row) as an account with `off` books sees it: at its own book while that's on,
    else at the best book on that makes it a bet by itself (books.per_book's tier, so a pick can show as a lean), or
    None (hidden). The other price shown is the best other book on. The web's atBooks and the iPhone's BooksOff.atBooks
    do the same on tests/fixtures/books_off.json."""
    on = on_books(off)
    if len(on) == len(SHOWN):
        return dict(offer)
    entries = offer.get("books") or []
    out = dict(offer)
    if offer.get("book") not in on:
        e = _best(entries, on, need_tier=True)
        if e is None:
            return None
        out.update(tier=e.get("tier"), book=e["book"], price=e.get("price"), point=e.get("point"), ev=e.get("ev"),
                   units_tier=e.get("units_tier"), bet_limit=e.get("bet_limit"), fd_url=e.get("link"),
                   link_main=e.get("link_main"))
    elif offer.get("other_book") in on:
        return out
    o = _best(entries, on, need_tier=False, skip=out["book"])
    out.update(other_book=o and o["book"], other_point=o and o.get("point"), other_price=o and o.get("price"),
               other_ev=o and o.get("ev"))
    return out
