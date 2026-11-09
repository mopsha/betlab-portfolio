from betlab import ny_rules


def test_pro_leagues_unaffected():
    assert ny_rules.allowed("nfl", "Buffalo Bills", "New York Jets")[0]
    assert ny_rules.allowed("nba", "New York Knicks", "Brooklyn Nets", player="Jalen Brunson")[0]


def test_college_player_props_banned():
    ok, reason = ny_rules.allowed("ncaaf", "Alabama", "Georgia", player="Some QB")
    assert not ok and "player props" in reason


def test_ny_schools_banned_by_either_naming_style():
    assert not ny_rules.allowed("ncaaf", "Syracuse", "Clemson")[0]                     # CFBD style
    assert not ny_rules.allowed("ncaaf", "Clemson Tigers", "Syracuse Orange")[0]       # FanDuel style
    assert not ny_rules.allowed("ncaab", "St. John's Red Storm", "Villanova Wildcats")[0]
    assert not ny_rules.allowed("ncaaf", "Army Black Knights", "Navy Midshipmen")[0]


def test_games_played_in_ny_banned():
    ok, reason = ny_rules.allowed("ncaab", "Duke", "Kansas", venue_state="NY")  # e.g. at Madison Square Garden
    assert not ok and "played in New York" in reason


def test_ordinary_college_game_allowed():
    assert ny_rules.allowed("ncaaf", "Ohio State Buckeyes", "Michigan Wolverines") == (True, "")
