import XCTest
@testable import BetLab

/// web/tests/live.test.mjs, case for case: the live tracker must judge every leg exactly as the web app does.
final class LiveTests: XCTestCase {
    func side(_ name: String, _ abbr: String, _ score: Double? = nil) -> LiveSide { LiveSide(name: name, abbr: abbr, score: score) }
    func game(_ state: String, _ home: LiveSide, _ away: LiveSide, _ sport: String = "nfl", detail: String = "Q3 4:12") -> GameLive {
        GameLive(key: "\(sport):1", sport: sport, espnId: "1", state: state, detail: detail, start: "2026-10-23T20:00:00Z", home: home, away: away)
    }
    func decode(_ s: String) throws -> JSON { try JSON.plainDecoder.decode(JSON.self, from: Data(s.utf8)) }

    func testLegLabelsFromEverySportParse() {
        XCTAssertEqual(Live.parseLeg("A.J. Brown 60+ receiving yds"), .prop(player: "A.J. Brown", stat: "receiving yds", side: "over", need: 60, point: 59.5))
        guard case .prop(_, _, _, let need, _) = Live.parseLeg("Joel Embiid over 7.5 rebounds") else { return XCTFail() }
        XCTAssertEqual(need, 8)
        guard case .prop(_, let s1, _, _, _) = Live.parseLeg("Derrick White over 7.5 reb + ast") else { return XCTFail() }
        XCTAssertEqual(s1, "reb + ast")
        guard case .prop(_, let s2, _, _, _) = Live.parseLeg("Rolando Mandragora 1+ shots on target") else { return XCTFail() }
        XCTAssertEqual(s2, "shots on target")
        XCTAssertEqual(Live.parseLeg("Over 2.5 goals"), .total(side: "over", point: 2.5))
        XCTAssertEqual(Live.parseLeg("Under 47.5 total points"), .total(side: "under", point: 47.5))
        XCTAssertEqual(Live.parseLeg("CBJ to win"), .ml(team: "CBJ"))
        XCTAssertEqual(Live.parseLeg("Virginia Tech Hokies -3.5"), .spread(team: "Virginia Tech Hokies", point: -3.5))
        XCTAssertEqual(Live.parseLeg("Both teams to score"), .btts)
        XCTAssertEqual(Live.parseLeg("Drake Maye first TD scorer"), .td(player: "Drake Maye", first: true))
    }

    func testTeamsMatchByAbbreviationAliasNicknameOrNameAccentsAside() {
        XCTAssertTrue(Live.isTeam("NJD", side("New Jersey Devils", "NJ")))
        XCTAssertTrue(Live.isTeam("Chicago Bears", side("Chicago Bears", "CHI")))
        XCTAssertTrue(Live.isTeam("Viktoria Plzeň", side("Viktoria Plzen", "PLZ")))
        XCTAssertTrue(Live.isTeam("Borussia Monchengladbach", side("Borussia Mönchengladbach", "BMG")))
        XCTAssertFalse(Live.isTeam("Celta Vigo", side("Celtic", "CEL")))          // same ESPN abbreviation, different clubs
        XCTAssertTrue(Live.isTeam("Celtic", side("Celtic", "CEL")))
        let games = [game("in", side("Celtic", "CEL", 1), side("Celta Vigo", "CEL", 0), "soccer")]
        XCTAssertEqual(Live.findGame(games, "Celta Vigo @ Celtic")?.key, "soccer:1")
        XCTAssertNil(Live.findGame(games, "Rangers @ Celtic"))
        // Oct 24: "State" is in both pairs; the live Sacramento State game must not take Boise State's leg
        var sac = game("in", side("Ball State Cardinals", "BALL", 0), side("Sacramento State Hornets", "SAC", 3), "ncaaf"); sac.key = "ncaaf:sac"
        var boise = game("pre", side("Washington State Cougars", "WSU"), side("Boise State Broncos", "BSU"), "ncaaf"); boise.key = "ncaaf:bsu"
        XCTAssertEqual(Live.findGame([sac, boise], "Boise State Broncos @ Washington State Cougars")?.key, "ncaaf:bsu")
    }

    func testPlayersMatchDespiteCaseSuffixesAndInitials() {
        let box: LiveBox = ["demario douglas": ["receivingYards": 23], "paul reed": ["points": 9], "aj brown": ["receivingYards": 48]]
        XCTAssertEqual(Live.findPlayer(box, "Demario Douglas")?["receivingYards"], 23)
        XCTAssertEqual(Live.findPlayer(box, "Paul Reed Jr")?["points"], 9)
        XCTAssertEqual(Live.findPlayer(box, "A.J. Brown")?["receivingYards"], 48)
    }

    func testBoxScoresParseMadeAttemptedAndCompAttColumns() throws {
        let s = try decode("""
        {"boxscore": {"players": [{"statistics": [
          {"keys": ["minutes", "points", "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "rebounds"],
           "athletes": [{"athlete": {"displayName": "Tyler Herro"}, "stats": ["20", "18", "3-7", "4"]}]},
          {"keys": ["completions/passingAttempts", "passingYards"], "athletes": [{"athlete": {"displayName": "Drake Maye"}, "stats": ["24/31", "321"]}]}]}]}}
        """)
        let box = Live.parseBox(s, sport: "nba")
        // both halves of "3-7" (Nov 6): made and attempted
        XCTAssertEqual(box["tyler herro"], ["minutes": 20, "points": 18, "threePointFieldGoalsMade": 3, "threePointFieldGoalsAttempted": 7, "rebounds": 4])
        XCTAssertEqual(box["drake maye"]?["passingYards"], 321)
    }

    func testPropsAnOverClinchesAsSoonAsItsHitAnUnderBustsWhenPassed() {
        let live = game("in", side("Chicago Bears", "CHI", 21), side("New England Patriots", "NE", 17))
        let box: LiveBox = ["drake maye": ["passingYards": 205], "cole kmet": ["receptions": 2]]
        XCTAssertEqual(Live.judge("Drake Maye 200+ passing yds", live, box).status, .won)
        XCTAssertEqual(Live.judge("Cole Kmet under 1.5 receptions", live, box).status, .lost)
        let going = Live.judge("Rome Odunze 40+ receiving yds", live, box)          // not in the box yet: 0 so far
        XCTAssertEqual(going.status, .live); XCTAssertEqual(going.current, 0); XCTAssertEqual(going.target, 40); XCTAssertEqual(going.text, "40 to go")
        var post = live; post.state = "post"
        let fin = Live.judge("Rome Odunze 40+ receiving yds", post, ["rome odunze": ["receivingYards": 38]])
        XCTAssertEqual(fin.status, .lost); XCTAssertEqual(fin.text, "Missed by 2")
    }

    func testGameLinesMoneylineSpreadTotalsSoccerDrawsAndBothTeamsToScore() {
        let g = game("in", side("Alaves", "ALA", 0), side("Malaga", "MCF", 1), "soccer")
        XCTAssertEqual(Live.judge("Alavés to win", g, nil).status, .losing)
        var draw = g; draw.state = "post"; draw.home = side("Alaves", "ALA", 1)
        XCTAssertEqual(Live.judge("Alavés to win", draw, nil).status, .lost)            // 1-1: a draw loses a 3-way bet
        XCTAssertEqual(Live.judge("Over 2.5 goals", g, nil).status, .live)
        var three = g; three.home = side("Alaves", "ALA", 2); three.away = side("Malaga", "MCF", 1)
        XCTAssertEqual(Live.judge("Over 2.5 goals", three, nil).status, .won)
        var nil0 = g; nil0.state = "post"
        XCTAssertEqual(Live.judge("Both teams to score", nil0, nil).status, .lost)
        let nfl = game("post", side("Chicago Bears", "CHI", 30), side("New England Patriots", "NE", 24))
        XCTAssertEqual(Live.judge("Chicago Bears -3.5", nfl, nil).status, .won)
        XCTAssertEqual(Live.judge("New England Patriots +6", nfl, nil).status, .void)    // a push
        XCTAssertEqual(Live.judge("Under 47.5 total points", nfl, nil).status, .lost)
    }

    func testUfcLiveWhileTheFightRunsThenItsWinner() {
        let f = game("in", side("Movsar Evloev", "evloev"), side("Alexander Volkanovski", "volkanovski"), "ufc", detail: "R2 3:10")
        XCTAssertEqual(Live.judge("Alex Volkanovski ML", f, nil).status, .live)
        var done = f; done.state = "post"; done.winner = "away"; done.result = "Decision - Unanimous"
        XCTAssertEqual(Live.judge("Alex Volkanovski ML", done, nil).status, .won)
    }

    func testAParlayRollsUpLostOnAnyLostLegWonWhenEveryLegIsIn() {
        let legs = { (ss: [LegStatus]) in ss.map { LegLive(label: "", status: $0, gameKey: nil) } }
        let g = [game("in", side("A", "A"), side("B", "B"))]
        XCTAssertEqual(Live.rollup(legs([.won, .live]), g).status, "live")
        XCTAssertEqual(Live.rollup(legs([.won, .lost, .live]), g).status, "lost")
        let r = Live.rollup(legs([.won, .void]), g)
        XCTAssertEqual(r.status, "won"); XCTAssertEqual(r.hit, 1)
    }

    func testBetsSplitIntoTheirGamesSavedParlaysTicketsAndSinglePicks() throws {
        XCTAssertTrue(Live.refSport("nhl:2026020162") == ("nhl", nil))
        XCTAssertTrue(Live.refSport("2026_07_NE_CHI") == ("nfl", nil))
        XCTAssertTrue(Live.refSport("epl|Ipswich Town|Nottingham Forest|2026-10-23T19:00:00+00:00") == ("soccer", "epl"))
        let custom = LiveBetRow(bet_id: "c", games: try decode(#"[{"matchup": "Minnesota Wild @ Calgary Flames", "game_ref": "nhl:1", "legs": ["MIN to win"]}]"#))
        XCTAssertEqual(Live.groups(custom, tickets: [:]), [LiveGroup(sport: "nhl", league: nil, matchup: "Minnesota Wild @ Calgary Flames", legs: ["MIN to win"], ref: "nhl:1")])
        let ticket = LiveBetRow(bet_id: "t", kind: "parlay", sgp_id: "t1", legs: ["x"])
        let body = try decode(#"{"games": [{"matchup": "Málaga @ Alavés", "game_ref": "la_liga|Alavés|Málaga|t", "legs": [{"label": "Alavés to win"}], "commence_time": "t"}]}"#)
        let g = Live.groups(ticket, tickets: ["t1": body])
        XCTAssertEqual(g[0].sport, "soccer"); XCTAssertEqual(g[0].league, "la_liga"); XCTAssertEqual(g[0].legs, ["Alavés to win"])
        let pick = LiveBetRow(bet_id: "p", kind: "pick", label: "Milwaukee Bucks ML", matchup: "Chicago Bulls @ Milwaukee Bucks", league: "nba")
        XCTAssertEqual(Live.groups(pick, tickets: [:])[0].sport, "nba"); XCTAssertEqual(Live.groups(pick, tickets: [:])[0].legs, ["Milwaukee Bucks ML"])
    }

    func testABetSettlesFromItsLiveStateAnyLostLegOrEveryLegWonOutright() {
        let legs = { (ss: [LegStatus]) in ss.map { LegLive(label: "", status: $0, gameKey: nil) } }
        let g = [game("in", side("A", "A"), side("B", "B"))], done = [game("post", side("A", "A"), side("B", "B"))]
        XCTAssertEqual(Live.rollup(legs([.won, .lost, .live]), g).settle, "lost")
        XCTAssertEqual(Live.rollup(legs([.won, .won]), done).settle, "won")
        XCTAssertNil(Live.rollup(legs([.won, .void]), done).settle)        // a void's reduced price: the grader's
        XCTAssertNil(Live.rollup(legs([.won, .live]), g).settle)
    }

    func testLiveSettledBetsReadAsSettledWithTheirProfitFlaggedNotGraded() {
        let settled = ["a": "lost", "b": "won"]
        let bets = [MyBet(betId: "a", price: 150, stake: 2, pickStatus: "open"), MyBet(betId: "b", price: 300, stake: 1),
                    MyBet(betId: "c", price: 100, stake: 1, ticketStatus: "won")]
        let out = Live.markLiveSettled(bets, settled)
        XCTAssertEqual(BetMath.status(out[0]), "lost"); XCTAssertEqual(BetMath.profit(out[0]), -2); XCTAssertEqual(out[0].liveSettled, "lost")
        XCTAssertEqual(BetMath.status(out[1]), "won"); XCTAssertEqual(BetMath.profit(out[1]), 3); XCTAssertEqual(out[1].liveSettled, "won")
        XCTAssertNil(out[2].liveSettled)                                   // already graded: untouched
    }

    func testASettledBetsGamesAreLookedUpOnTheirOwnDays() {
        let b = LiveBetRow(bet_id: "x", placed_at: "2026-10-22T23:05:00Z")
        let g = { (ref: String?, start: String?) in LiveGroup(sport: nil, league: nil, matchup: "", legs: [], start: start, ref: ref) }
        XCTAssertEqual(Live.daysOf(b, g("2026_07_NE_CHI", nil)), ["20261022", "20261023"])           // placed Thu 7:05 PM ET
        XCTAssertEqual(Live.daysOf(b, g("epl|Ipswich Town|Nottingham Forest|2026-10-23T19:00:00+00:00", nil)), ["20261023", "20261024"])
        XCTAssertEqual(Live.daysOf(b, g(nil, "2026-10-25T00:30:00Z")), ["20261024", "20261025"])     // 8:30 PM ET Oct 24
        XCTAssertEqual(Live.days(Models.date("2026-11-02T04:30:00Z")!), ["20261031", "20261101"])    // 11:30 PM on the 25-hour day
        XCTAssertEqual(Live.days(Models.date("2027-03-15T04:30:00Z")!), ["20270314", "20270315"])    // just after the 23-hour day
    }

    func testTeamColorsReadOnBothThemes() {           // Oct 23: the score strip's underline
        XCTAssertEqual(Live.teamColor("0b162a", "c83803"), "#0b162a")       // Bears navy (linear luminance 0.083) still reads
        XCTAssertEqual(Live.teamColor("111111", "c83803"), "#c83803")       // near black: the alternate
        XCTAssertEqual(Live.teamColor("ffffff", "eee1c6"), nil)             // near white twice: none
        XCTAssertEqual(Live.teamColor("ce1141", "000000"), "#ce1141")       // a primary that reads stays
        XCTAssertNil(Live.teamColor(nil, "zz"))
    }

    func testHeadshotsFromTheBoxScoreOrBySoccerPlayerId() throws {
        let nfl = try decode("""
        {"boxscore": {"players": [{"statistics": [{"keys": ["receptions"], "athletes": [
          {"athlete": {"displayName": "Cole Kmet", "headshot": {"href": "https://x/kmet.png"}}, "stats": ["3"]},
          {"athlete": {"displayName": "D'Andre Swift"}, "stats": ["1"]}]}]}]}}
        """)
        XCTAssertEqual(Live.parseHeads(nfl, sport: "nfl"), ["cole kmet": "https://x/kmet.png"])
        let soc = try decode(#"{"rosters": [{"roster": [{"athlete": {"id": "123", "displayName": "Angelo Stiller"}, "stats": []}]}]}"#)
        XCTAssertEqual(Live.parseHeads(soc, sport: "soccer")["angelo stiller"], "https://a.espncdn.com/i/headshots/soccer/players/full/123.png")
    }

    func testALegCarriesItsPlayersHeadshotOrItsTeamsLogo() {
        var g = game("in", side("Chicago Bears", "CHI", 21), side("New England Patriots", "NE", 17))
        g.home.logo = "chi.png"; g.away.logo = "ne.png"
        XCTAssertEqual(Live.judge("Chicago Bears -3.5", g, nil).img, "chi.png")
        XCTAssertEqual(Live.judge("New England Patriots ML", g, nil).img, "ne.png")
        XCTAssertEqual(Live.judge("Cole Kmet over 1.5 receptions", g, [:], ["cole kmet": "kmet.png"]).img, "kmet.png")
        XCTAssertEqual(Live.judge("C. Kmet 25+ receiving yds", g, [:], ["cole kmet": "kmet.png"]).img, "kmet.png")   // initial + last name
        XCTAssertNil(Live.judge("Over 47.5 total points", g, nil).img)
    }

    func testScoreboardsReadTeamsScoresAndUfcFights() throws {     // the iPhone's own ESPN read (the web's scoreboard())
        let nba = try decode("""
        {"events": [{"id": "401", "date": "2026-10-23T23:10Z", "competitions": [{"id": "401", "competitors": [
          {"homeAway": "home", "score": "88", "team": {"displayName": "Milwaukee Bucks", "abbreviation": "MIL"}},
          {"homeAway": "away", "score": "91", "team": {"displayName": "Chicago Bulls", "abbreviation": "CHI"}}],
          "status": {"type": {"state": "in", "shortDetail": "2:32 - 4th"}}}]}]}
        """)
        let g = Live.parseBoard(nba, sport: "nba")
        XCTAssertEqual(g.count, 1)
        XCTAssertEqual(g[0].key, "nba:401"); XCTAssertEqual(g[0].state, "in"); XCTAssertEqual(g[0].detail, "2:32 - 4th")
        XCTAssertEqual(g[0].away.score, 91); XCTAssertEqual(g[0].home.abbr, "MIL")
        XCTAssertEqual(Live.findGame(g, "Chicago Bulls @ Milwaukee Bucks")?.key, "nba:401")
        let ufc = try decode("""
        {"events": [{"id": "600", "competitions": [
          {"id": "f1", "date": "2026-10-24T14:00Z", "status": {"type": {"state": "post", "shortDetail": "Final"}, "result": {"displayName": "KO/TKO"}},
           "competitors": [{"athlete": {"displayName": "Kody Steele"}, "winner": true}, {"athlete": {"displayName": "Noah Gugnon"}, "winner": false}]},
          {"id": "f2", "status": {"type": {"state": "pre"}}, "competitors": [{"id": "3949584", "athlete": {"displayName": "Bolaji Oki"}}, {"athlete": {"displayName": "Daniel Santos"}}]}]}]}
        """)
        let f = Live.parseBoard(ufc, sport: "ufc")
        XCTAssertEqual(f.map(\.key), ["ufc:f1", "ufc:f2"])
        XCTAssertEqual(f[0].home.abbr, "steele"); XCTAssertEqual(f[0].winner, "home"); XCTAssertEqual(f[0].result, "KO/TKO")
        XCTAssertEqual(f[1].home.logo, "https://a.espncdn.com/i/headshots/mma/players/full/3949584.png")   // the id is the competitor's (Oct 24)
        XCTAssertEqual(Live.judge("Kody Steele ML", Live.findGame(f, "Kody Steele vs Noah Gugnon"), nil).status, .won)
    }

    // MARK: the shared fixture (tests/fixtures/live_legs.json): web, Python and iPhone must read every case alike

    private func fixture() throws -> JSON {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/live_legs.json")
        return try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
    }

    /// A parsed leg as the fixture writes it.
    private func asJSON(_ p: Live.Parsed?) -> JSON {
        func o(_ d: [String: JSON]) -> JSON { .object(d) }
        switch p {
        case nil: return .null
        case .ml(let t)?: return o(["kind": .string("ml"), "team": .string(t)])
        case .spread(let t, let pt)?: return o(["kind": .string("spread"), "team": .string(t), "point": .number(pt)])
        case .total(let side, let pt)?: return o(["kind": .string("total"), "side": .string(side), "point": .number(pt)])
        case .btts?: return o(["kind": .string("btts")])
        case .bttsNo?: return o(["kind": .string("btts_no")])
        case .draw?: return o(["kind": .string("draw")])
        case .drawOr(let t)?: return o(["kind": .string("draw_or"), "team": .string(t)])
        case .noDraw?: return o(["kind": .string("no_draw")])
        case .notWin(let t)?: return o(["kind": .string("not_win"), "team": .string(t)])
        case .prop(let pl, let st, let side, let need, let pt)?:
            return o(["kind": .string("prop"), "player": .string(pl), "stat": .string(st), "side": .string(side), "need": .number(need), "point": .number(pt)])
        case .td(let pl, let first)?: return o(["kind": .string("td"), "player": .string(pl), "first": .bool(first)])
        case .goalOrAssist(let pl)?: return o(["kind": .string("goal_or_assist"), "player": .string(pl)])
        case .double(let pl, let n)?: return o(["kind": .string("double"), "player": .string(pl), "n": .number(Double(n))])
        case .leader(let pl, let st)?: return o(["kind": .string("leader"), "player": .string(pl), "stat": .string(st)])
        case .card(let pl)?: return o(["kind": .string("card"), "player": .string(pl)])
        case .first(let pl, let what)?: return o(["kind": .string("first"), "player": .string(pl), "what": .string(what)])
        }
    }

    func testTheSharedFixtureParsesEveryLabelAlike() throws {
        let cases = try fixture()["parse"].array
        XCTAssertGreaterThan(cases.count, 10)
        for c in cases {
            let label = c["label"].string ?? ""
            XCTAssertEqual(asJSON(Live.parseLeg(label)), c["expect"], label)
        }
    }

    func testTheSharedFixtureJudgesEveryLegAlike() throws {      // the Tigers and Akron cases are Oct 24's fixes
        let cases = try fixture()["judge"].array
        XCTAssertGreaterThan(cases.count, 10)
        for c in cases {
            let label = c["label"].string ?? "", g = c["game"]
            let sd = { (x: JSON) in LiveSide(name: x[0].string ?? "", abbr: x[1].string ?? "", score: x[2].double) }
            var game = GameLive(key: "x:1", sport: g["sport"].string ?? "", espnId: "1", state: g["state"].string ?? "pre",
                                detail: "", start: "", home: sd(g["home"]), away: sd(g["away"]))
            game.winner = g["winner"].string
            let box: LiveBox? = c["box"].isNull ? nil : c["box"].object.mapValues { $0.object.compactMapValues(\.double) }
            let leg = Live.judge(label, game, box)
            let e = c["expect"]
            XCTAssertEqual(leg.status.rawValue, e["status"].string, label)
            if let cur = e["current"].double { XCTAssertEqual(leg.current, cur, label) }
            if let text = e["text"].string { XCTAssertEqual(leg.text, text, label) }
            if let heat = e["deadHeat"].bool { XCTAssertEqual(leg.deadHeat ?? false, heat, label) }
        }
    }

    func testTheSharedFixtureLooksForEachBetsGameOnItsOwnDays() throws {   // Nov 9: open bets looked only at yesterday and today
        let cases = try fixture()["days"].array
        XCTAssertGreaterThan(cases.count, 3)
        for c in cases {
            let b = c["bet"]
            let row = LiveBetRow(bet_id: "x", pick_commence_time: b["pick_commence_time"].string, placed_at: b["placed_at"].string,
                                 game_start: b["game_start"].string)
            let grp = LiveGroup(sport: nil, league: nil, matchup: "", legs: [], start: c["group"]["start"].string, ref: c["group"]["ref"].string)
            XCTAssertEqual(Live.searchDays(row, grp, open: c["open"].bool ?? false, now: Models.date(c["now"].string)!, single: c["single"].bool ?? true),
                           c["expect"].array.compactMap(\.string), c["why"].string ?? "")
        }
    }

    func testADeadHeatNeverSettlesLiveAtTheFullPrice() {
        let done = [game("post", side("A", "A"), side("B", "B"))]
        var heat = LegLive(label: "", status: .won, gameKey: nil); heat.deadHeat = true
        XCTAssertNil(Live.rollup([LegLive(label: "", status: .won, gameKey: nil), heat], done).settle)
        XCTAssertEqual(Live.rollup([LegLive(label: "", status: .won, gameKey: nil), heat], done).status, "won")
    }

    func testTheSharedPlayByPlayGivesTheSameStats() throws {
        for c in try fixture()["plays"].array {
            let got = Live.parseBox(c["summary"], sport: c["sport"].string ?? "")
            let want = c["expect"].object.mapValues { $0.object.mapValues { $0.double ?? 0 } }
            XCTAssertEqual(got, want, c["sport"].string ?? "")
        }
    }
}

final class ESPNCacheTests: XCTestCase {
    final class Fake: @unchecked Sendable {
        var now = Date(timeIntervalSince1970: 0), calls = 0, fail = false
        func espn() -> ESPN {
            ESPN(fetch: { [self] _ in calls += 1; return fail ? nil : .number(Double(calls)) }, clock: { [self] in now })
        }
    }

    /// Nov 1: the Games list's 6-hour copy of today's board froze every live tracker until the app was closed.
    func testALongLivedCopyDoesNotAnswerALiveCaller() async {
        let f = Fake(), e = f.espn()
        _ = await e.get("board", ttl: ESPN.doneTTL)
        f.now += 16
        _ = await e.get("board")
        XCTAssertEqual(f.calls, 2)
    }
    func testALiveCopyGoesStaleForALongLivedCaller() async {
        let f = Fake(), e = f.espn()
        _ = await e.get("summary")                  // the box score while the game was on
        f.now += 16
        _ = await e.get("summary", ttl: ESPN.doneTTL)   // the game's over: not the old box for 6 hours
        XCTAssertEqual(f.calls, 2)
    }
    func testACopyAnswersWhileYoung() async {
        let f = Fake(), e = f.espn()
        _ = await e.get("board")
        f.now += 10
        _ = await e.get("board")
        XCTAssertEqual(f.calls, 1)
        _ = await e.get("logos", ttl: ESPN.doneTTL)
        f.now += 3600
        _ = await e.get("logos", ttl: ESPN.doneTTL)
        XCTAssertEqual(f.calls, 2)
    }
    func testAFailedFetchIsNotKept() async {
        let f = Fake(), e = f.espn()
        f.fail = true
        _ = await e.get("board", ttl: ESPN.doneTTL)
        f.fail = false
        _ = await e.get("board", ttl: ESPN.doneTTL)
        XCTAssertEqual(f.calls, 2)
    }
}

final class SoccerClubsTests: XCTestCase {
    func testEveryNameFormFindsItsClub() throws {   // Oct 24: the names that missed before the aliases
        let dir = try JSON.plainDecoder.decode(JSON.self, from: Data(#"""
        {"sports": [{"leagues": [{"teams": [
          {"team": {"displayName": "FC Cologne", "abbreviation": "KOE", "color": "e32219", "logos": [{"href": "koe.png"}]}},
          {"team": {"displayName": "Athletic Club", "abbreviation": "ATH", "color": "ee2523", "logos": [{"href": "ath.png"}]}},
          {"team": {"displayName": "Brighton & Hove Albion", "abbreviation": "BHA", "color": "0057b8", "logos": [{"href": "bha.png"}]}},
          {"team": {"displayName": "F.C. København", "abbreviation": "FCK", "color": "1b3a8c", "logos": [{"href": "fck.png"}]}},
          {"team": {"displayName": "Bodø/Glimt", "abbreviation": "BOD", "color": "ffe000", "logos": [{"href": "bod.png"}]}},
          {"team": {"displayName": "Internazionale", "abbreviation": "INT", "color": "0068a8", "logos": [{"href": "int.png"}]}},
          {"team": {"displayName": "Atalanta", "abbreviation": "ATA", "color": "1e71b8", "logos": [{"href": "ata.png"}]}},
          {"team": {"displayName": "1. FC Union Berlin", "abbreviation": "FCU", "color": "da0308", "logos": [{"href": "fcu.png"}]}}]}]}]}
        """#.utf8))
        let ix = SoccerClubs.index([dir])
        for (ours, logo) in [("1. FC Köln", "koe.png"), ("Athletic Bilbao", "ath.png"), ("Brighton and Hove Albion", "bha.png"),
                             ("FC Copenhagen", "fck.png"), ("Bodø/Glimt", "bod.png"), ("Inter Milan", "int.png"),
                             ("Atalanta BC", "ata.png"), ("Union Berlin", "fcu.png")] {
            XCTAssertEqual(SoccerClubs.find(ours, in: ix)?.logo, logo, ours)
        }
        XCTAssertNil(SoccerClubs.find("Celtic", in: ix))
    }

    // Oct 25: who has the ball and the red zone (football), who's on the floor (basketball): web tests/live.test.mjs
    func testFootballBallRedZoneAndBasketballOnCourt() throws {
        func board(_ sit: String) throws -> JSON {
            try JSON.plainDecoder.decode(JSON.self, from: Data(#"{"events":[{"id":"9","competitions":[{"id":"9","date":"2026-10-25T17:00:00Z","status":{"type":{"state":"in","shortDetail":"Q2 1:15"}},"situation":\#(sit),"competitors":[{"homeAway":"home","score":"7","team":{"id":"1","displayName":"Atlanta Falcons","abbreviation":"ATL"}},{"homeAway":"away","score":"3","team":{"id":"25","displayName":"San Francisco 49ers","abbreviation":"SF"}}]}]}]}"#.utf8))
        }
        let g = Live.parseBoard(try board(#"{"possession":"25","isRedZone":true,"downDistanceText":"3rd & Goal at ATL 1"}"#), sport: "nfl")[0]
        XCTAssertEqual(g.ball, "away"); XCTAssertTrue(g.redZone); XCTAssertEqual(g.down, "3rd & Goal at ATL 1")
        let between = Live.parseBoard(try board(#"{"possession":null,"isRedZone":true}"#), sport: "nfl")[0]
        XCTAssertNil(between.ball); XCTAssertFalse(between.redZone)
        let summary = try JSON.plainDecoder.decode(JSON.self, from: Data(#"{"boxscore":{"players":[{"statistics":[{"athletes":[{"active":true,"athlete":{"displayName":"Bam Adebayo"}},{"active":false,"athlete":{"displayName":"Klay Thompson"}}]}]}]}}"#.utf8))
        XCTAssertEqual(Live.parseOnCourt(summary), ["bam adebayo"])
        let nba = GameLive(key: "nba:1", sport: "nba", espnId: "1", state: "in", detail: "Q3", start: "2026-10-25T23:00:00Z",
                           home: LiveSide(name: "Miami Heat", abbr: "MIA", score: 50), away: LiveSide(name: "Charlotte Hornets", abbr: "CHA", score: 48))
        XCTAssertEqual(Live.judge("Bam Adebayo 10+ rebounds", nba, ["bam adebayo": ["rebounds": 6]], nil, ["bam adebayo"]).onCourt, true)
        XCTAssertEqual(Live.judge("Klay Thompson 2+ threes", nba, ["klay thompson": [:]], nil, ["bam adebayo"]).onCourt, false)
        XCTAssertNil(Live.judge("Bam Adebayo 10+ rebounds", nba, ["bam adebayo": ["rebounds": 6]], nil, nil).onCourt)
    }

}
