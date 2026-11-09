"""Mike's Novig bets from his own account (Oct 22): request signing and turning fills into bets. No network."""

import json
from pathlib import Path

import pandas as pd
import pytest

from betlab import novig_sync as N

VECTORS = json.loads((Path(__file__).parent / "data" / "novig_signing_vectors.json").read_text(encoding="utf-8"))
KEYS = {k_id: k for k_id, k in VECTORS["keypairs"].items()} if isinstance(VECTORS["keypairs"], dict) else \
    {k["id"]: k for k in VECTORS["keypairs"]}


@pytest.mark.parametrize("v", VECTORS["vectors"], ids=[v["id"] for v in VECTORS["vectors"]])
def test_signing_matches_novigs_published_vectors(v):
    i = v["input"]
    body = i["body"].encode() if isinstance(i["body"], str) else json.dumps(i["body"]).encode()
    s = N.string_to_sign(i["timestamp"], i["method"], i["path"], i["query"], body)
    assert s == v["string_to_sign"]
    if v["algorithm"] == "ed25519":                      # deterministic: the exact signature
        assert N.sign(KEYS[v["keypair_id"]]["private_key_pkcs8_pem"], s) == v["signature"]
    else:                                                # P-256 signatures vary: verify ours with the public key
        import base64
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        pub = serialization.load_pem_public_key(KEYS[v["keypair_id"]]["public_key_spki_pem"].encode())
        pub.verify(base64.b64decode(N.sign(KEYS[v["keypair_id"]]["private_key_pkcs8_pem"], s)), s.encode(),
                   ec.ECDSA(hashes.SHA256()))


def test_fills_become_one_bet_per_outcome():
    fills = [{"outcomeId": "o1", "marketId": "m1", "qty": 1000, "cost": 6.25, "ts": 1792700000000},
             {"outcomeId": "o1", "marketId": "m1", "qty": 600, "cost": 3.75, "ts": 1792690000000},
             {"outcomeId": "o2", "marketId": "m2", "qty": 1470, "cost": 5.00, "ts": 1792690000000}]
    bets = {b["outcome_id"]: b for b in N.bets_from_fills(fills)}
    # 16 contracts for $10: 62.5 cents each (-167), placed at the first fill
    assert bets["o1"]["cost"] == 10.0 and bets["o1"]["p"] == pytest.approx(0.625) and bets["o1"]["price"] == -167
    assert bets["o1"]["ts"] == 1792690000000
    assert bets["o2"]["price"] == 194                     # 14.7 contracts for $5: 34 cents


def test_outcome_labels_read_like_the_card():
    m = {"marketType": "MONEYLINE_3_WAY_WIN", "description": "Salzburg MONEYLINE_3_WAY_WIN",
         "outcomes": [{"outcomeId": "y", "name": "Yes"}, {"outcomeId": "n", "name": "No"}]}
    assert N.outcome_label(m, "y") == "Salzburg to win"
    draw = {"marketType": "MONEYLINE_3_WAY_DRAW", "description": "A @ B MONEYLINE_3_WAY_DRAW", "outcomes": [{"outcomeId": "y", "name": "Yes"}]}
    assert N.outcome_label(draw, "y") == "Draw"
    tot = {"marketType": "TOTAL", "description": "A @ B t2.5", "outcomes": [{"outcomeId": "o", "name": "Over 2.5"}]}
    assert N.outcome_label(tot, "o") == "Over 2.5"
    assert N.outcome_label(None, "x") == "Novig position"


def test_without_a_key_the_step_skips(monkeypatch):
    monkeypatch.setattr(N.config, "secret", lambda name: None)
    assert "skipping" in N.run()


def test_a_key_pasted_on_one_line_still_loads():
    """Oct 23: Railway's one-line variable turned the PEM's line breaks into spaces (MalformedFraming)."""
    v = next(x for x in VECTORS["vectors"] if x["algorithm"] == "ed25519")
    pem = KEYS[v["keypair_id"]]["private_key_pkcs8_pem"]
    body = "".join(l for l in pem.strip().splitlines() if not l.startswith("-----"))
    for pasted in (pem.replace("\n", " "), pem.replace("\n", "\\n"), body, f'"{pem.strip()}"'):
        assert N.sign(pasted, v["string_to_sign"]) == v["signature"]


def test_a_management_keys_read_is_unwrapped_from_its_wallet_map():
    """Oct 23: a management key's read is {key id: page}; reading `items` off the map gave 0 fills on every run."""
    calls = []

    class Fake(N.Client):
        def get(self, path, params=None):
            calls.append(params)
            if params.get("after"):
                return {"kid": {"items": [{"fillId": "b"}], "next": None}}
            return {"kid": {"items": [{"fillId": "a"}], "next": "c1"}}

    cl = Fake.__new__(Fake)
    cl.key_id = "kid"
    assert [f["fillId"] for f in cl.pages("/v3/portfolio/fills")] == ["a", "b"]
    assert all(p["keyId"] == "kid" for p in calls)
    assert cl.wallet({"items": [], "next": None}) == {"items": [], "next": None}     # a trading key's bare page
    with pytest.raises(RuntimeError):
        cl.wallet({"other": {"items": []}})


def test_a_maintenance_pause_skips_instead_of_failing(monkeypatch):
    """Oct 27 7 PM: Novig answered 423 SYSTEM_LOCKED and the step failed; it's a skip, the next tick reads it all."""
    class R:
        status_code = 423
        text = '{"code":"SYSTEM_LOCKED","message":"Trading is paused: Maintenance"}'

    class Session:
        def request(self, *a, **k):
            return R()

    cl = N.Client.__new__(N.Client)
    cl.key_id, cl.pem, cl.session = "kid", "pem", Session()
    monkeypatch.setattr(N, "sign", lambda pem, msg: "sig")
    with pytest.raises(N.Paused):
        cl.get("/v3/portfolio/fills")
    monkeypatch.setattr(N, "client", lambda: cl)
    monkeypatch.setattr(N.config, "secret", lambda name: "x")
    monkeypatch.setattr(N.config, "owner_user_id", lambda: "owner")
    out = N.run()
    assert "paused" in out and "skipping" in out


def test_a_post_signs_the_exact_body_it_sends():
    """scripts/novig_read_key.py registers a key with a signed POST: the signature covers the SHA-256 of the sent bytes."""
    import hashlib

    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization

    priv = ed25519.Ed25519PrivateKey.generate()
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()
    seen = {}

    class Session:
        def request(self, method, url, headers, data, timeout):
            seen.update(method=method, url=url, headers=headers, data=data)

            class R:
                status_code = 201
                text = ""

                def json(self):
                    return {"keyId": "new", "fingerprint": "f"}
            return R()

    cl = N.Client("kid", pem, session=Session())
    assert cl.post("/v3/keys", {"name": "x"})["keyId"] == "new"
    h = seen["headers"]
    msg = "\n".join(["NOVIG-V3", h["Novig-Timestamp"], "POST", "/v3/keys", "", hashlib.sha256(seen["data"]).hexdigest()])
    import base64
    priv.public_key().verify(base64.b64decode(h["Novig-Signature"]), msg.encode())     # raises if wrong
    assert seen["method"] == "POST" and h["Content-Type"] == "application/json"


def test_a_synced_bet_reads_like_a_slip_and_carries_its_game():
    """Oct 28 (Mike: "why is auto novig bet doesnt look like our other cool bets"): "TULN -10.5 · Novig $5.00 (auto)"
    with no game; now the leg is in our words and the game has the grader's ref, so My bets tracks it."""
    import pandas as pd

    ms = lambda s: pd.Timestamp(s).timestamp() * 1000
    games = [{"game_id": "ncaaf:401862813", "league": "ncaaf", "matchup": "Tulane @ Charlotte",
              "commence_time": "2026-10-30T23:00:00Z", "odds_event_id": "e1"},
             {"game_id": "nba:7b9e", "league": "nba", "matchup": "New York Knicks @ Chicago Bulls",
              "commence_time": "2026-10-29T00:10:00Z", "odds_event_id": "e2"}]
    spread = {"marketType": "SPREAD", "strike": "10.5", "description": "CHAR +10.5",
              "outcomes": [{"outcomeId": "h", "name": "CHAR +10.5"}, {"outcomeId": "a", "name": "TULN -10.5"}]}
    o = N.ours(spread, {"description": "Tulane @ Charlotte", "startsTs": ms("2026-10-30T23:00:00Z")}, "a", games)
    assert o["label"] == "Tulane -10.5" and o["matchup"] == "Tulane @ Charlotte" and o["odds_event_id"] == "e1"
    assert o["games"] == [{"matchup": "Tulane @ Charlotte", "game_ref": "ncaaf:401862813", "legs": ["Tulane -10.5"]}]
    ev = {"description": "New York Knicks @ Chicago Bulls", "startsTs": ms("2026-10-29T00:10:00Z")}
    ml = {"marketType": "MONEY", "strike": "0", "description": "CHI", "outcomes": [{"outcomeId": "c", "name": "CHI"}, {"outcomeId": "n", "name": "NYK"}]}
    assert N.ours(ml, ev, "n", games)["label"] == "New York Knicks ML"
    pts = {"marketType": "POINTS", "strike": "24.5", "description": "Karl-Anthony Towns 24.5 POINTS",
           "outcomes": [{"outcomeId": "o", "name": "Over 24.5"}, {"outcomeId": "u", "name": "Under 24.5"}]}
    got = N.ours(pts, ev, "u", games)
    assert got["label"] == "Karl-Anthony Towns under 24.5 points"
    assert got["games"][0]["game_ref"] == "nba|CHI|NY|2026-10-29T00:10:00+00:00"        # web lib/slip.ts gameRef
    total = {"marketType": "TOTAL", "strike": "214.5", "description": "NYK @ CHI t214.5",
             "outcomes": [{"outcomeId": "o", "name": "Over 214.5"}, {"outcomeId": "u", "name": "Under 214.5"}]}
    assert N.ours(total, ev, "o", games)["label"] == "Over 214.5 total points"
    # no game of ours (or a start 2 hours off): Novig's own words, no game
    far = N.ours(spread, {"description": "Tulane @ Charlotte", "startsTs": ms("2026-10-31T01:00:00Z")}, "a", games)
    assert far["label"] == "TULN -10.5" and far["games"] is None


def test_an_nhl_goal_bet_finds_a_game_written_in_codes():
    """Oct 28: a Flyers-Capitals goal bet synced as "Over 0.5" with no game: the NHL's games read "PHI @ WSH" and
    Novig's "Philadelphia Flyers @ Washington Capitals", and the fallback dropped the player."""
    import pandas as pd

    games = [{"game_id": "nhl:2026020199", "league": "nhl", "matchup": "PHI @ WSH",
              "commence_time": "2026-10-28T23:30:00Z", "odds_event_id": None}]
    ev = {"description": "Philadelphia Flyers @ Washington Capitals", "startsTs": pd.Timestamp("2026-10-28T23:30:00Z").timestamp() * 1000}
    goals = {"marketType": "PLAYER_GOALS", "strike": "0.5", "description": "Travis Konecny 0.5 PLAYER_GOALS",
             "outcomes": [{"outcomeId": "o", "name": "Over 0.5"}, {"outcomeId": "u", "name": "Under 0.5"}]}
    o = N.ours(goals, ev, "o", games)
    assert o["label"] == "Travis Konecny 1+ goals" and o["matchup"] == "PHI @ WSH"
    assert o["games"] == [{"matchup": "PHI @ WSH", "game_ref": "nhl:2026020199", "legs": ["Travis Konecny 1+ goals"]}]
    assert N.outcome_label(goals, "o") == "Travis Konecny over 0.5 goals"     # no game of ours: still whose goal


def _hand(sgp_id, price, stake, placed, games=None, legs=None):
    return {"sgp_id": sgp_id, "price": price, "stake": stake, "placed_at": pd.Timestamp(placed),
            "games": games, "legs": legs}


def test_a_hand_entry_stands_for_one_novig_fill_only():
    """Nov 9: one hand-entered 1u single swallowed a second, similar 1u single the same day, which then never reached
    My bets. Each entry matches one fill, the closest chance; a parlay entered by hand matches no single; a known game
    must agree."""
    day = "2026-11-07T18:00:00Z"
    ts = int(pd.Timestamp(day).timestamp() * 1000)
    tulane = {"ts": ts, "cost": 5.0, "p": 0.512}          # -105
    ohio = {"ts": ts + 60_000, "cost": 5.0, "p": 0.524}   # -110
    existing = pd.DataFrame([_hand("custom-nv-snap-a", -105, 1.0, day,
                                   games=[{"matchup": "Tulane @ X", "game_ref": "ncaaf:1", "legs": ["Tulane -10.5"]}],
                                   legs=["Tulane -10.5"])])
    used: set = set()
    assert N._duplicate(tulane, existing, 5.0, used, "ncaaf:1") == "custom-nv-snap-a"
    used.add("custom-nv-snap-a")
    assert N._duplicate(ohio, existing, 5.0, used, "ncaaf:2") is None            # used up, and another game anyway
    assert N._duplicate(ohio, existing, 5.0, set(), "ncaaf:2") is None           # a different game is a different bet
    assert N._duplicate(ohio, existing, 5.0, set(), None) == "custom-nv-snap-a"  # no game known: chance and stake decide
    parlay = pd.DataFrame([_hand("custom-nv-b", 272, 2.0, day, legs=["A ML", "B ML"])])
    assert N._duplicate({"ts": ts, "cost": 10.0, "p": 0.27}, parlay, 5.0, set()) is None
    # two entries: the closer chance wins
    two = pd.DataFrame([_hand("x", -105, 1.0, day), _hand("y", -110, 1.0, day)])
    assert N._duplicate(ohio, two, 5.0, set()) == "y"
