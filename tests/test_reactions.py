"""Reaction alerts (reactions.py, Nov 6, supabase 0042): a friend's reaction to your bet, sent to you once."""

from betlab import alert_prefs as ap, reactions as rx

BET, OWNER, G = "b1", "mike", "sam"


def _row(reaction="fire", who=G, name="Sam", legs=("Devin Booker 2+ threes", "Phoenix Suns ML")):
    return (BET, who, reaction, name, OWNER, 940.0, None, list(legs), None)


def test_a_reaction_goes_to_the_bets_owner_once_by_name():
    out = rx.pending([_row()], set())
    assert len(out) == 1
    k, owner, msg, _ = out[0]
    assert (k, owner) == ("react:b1:sam:fire", OWNER)
    assert msg["title"] == "Sam 🔥 your bet"
    assert msg["body"].endswith("(+940)") and msg["url"] == "/bets" and len(msg["tag"]) <= 64
    assert rx.pending([_row()], {k}) == []                                   # sent already


def test_a_new_reaction_sends_again_and_an_unknown_or_your_own_never():
    sent = {rx.key(BET, G, "fire")}
    assert [o[0] for o in rx.pending([_row("goat")], sent)] == ["react:b1:sam:goat"]
    assert rx.pending([_row("clap")], set()) == []
    assert rx.pending([_row(who=OWNER)], set()) == []


def test_reactions_are_on_unless_turned_off():
    assert ap.clean(None)["reactions"] is True
    assert ap.clean({"reactions": False})["reactions"] is False


def test_the_emoji_match_the_apps_and_the_database():
    import json, pathlib, re
    fx = json.loads((pathlib.Path(__file__).parent / "fixtures" / "reactions.json").read_text())
    assert set(rx.EMOJI) == {c["reaction"] for c in fx["tally"][1]["want"]} | {"money", "skull", "pray"}
    sql = (pathlib.Path(__file__).parents[1] / "supabase" / "migrations" / "0042_reactions.sql").read_text()
    assert set(re.search(r"reaction in \(([^)]*)\)", sql)[1].replace("'", "").replace(" ", "").split(",")) == set(rx.EMOJI)
