import XCTest
@testable import BetLab

/// web/tests/stats.test.mjs, case for case: Stats, achievements and share cards must read as the web does.
final class StatsTests: XCTestCase {
    private var n = 0
    func bet(_ f: (inout MyBet) -> Void = { _ in }) -> MyBet {
        n += 1
        var b = MyBet(betId: "b\(n)", kind: "custom", mode: "real", price: 100, stake: 1, book: "FanDuel", bonus: false, matchup: "x",
                      placedAt: String(format: "2026-10-%02dT18:00:00Z", 10 + n), ticketStatus: "won", legs: ["A ML"])
        f(&b)
        return b
    }
    func games(_ s: String) -> JSON { try! JSON.plainDecoder.decode(JSON.self, from: Data(s.utf8)) }

    func testBetsFallIntoSportsTypesPriceBandsAndMoneyKinds() {
        let ufc = bet { $0.games = self.games(#"[{"matchup": "a vs b", "game_ref": "ufc:1:2", "legs": ["A ML"]}, {"matchup": "c vs d", "game_ref": "ufc:1:3", "legs": ["C ML"]}]"#); $0.legs = ["A ML", "C ML"] }
        let mixed = bet { $0.games = self.games(#"[{"matchup": "x", "gameRef": "epl|H|A|t", "legs": ["H to win"]}, {"matchup": "y", "gameRef": "ncaaf:9", "legs": ["Y ML"]}]"#) }
        XCTAssertEqual(Stats.sportOf(ufc), "UFC")
        XCTAssertEqual(Stats.sportOf(mixed), "Multi-sport")
        XCTAssertEqual(Stats.sportOf(bet { $0.kind = "pick"; $0.league = "serie_a" }), "Soccer")
        XCTAssertEqual(Stats.sportOf(bet { $0.matchup = "SGP+ Fri Oct 23 · NBA late games"; $0.legs = ["x", "y"] }), "NBA")
        XCTAssertEqual(Stats.sportOf(bet { $0.matchup = "Dallas Cowboys @ Green Bay Packers"; $0.legs = ["Dak Prescott 225+ passing yds"] }), "NFL")
        XCTAssertEqual(Stats.sportOf(bet { $0.matchup = "New York Knicks @ Boston Celtics"; $0.legs = ["New York Knicks ML"] }), "NBA")
        XCTAssertEqual(Stats.sportOf(bet { $0.matchup = "Parlay Fri Oct 23 · college football night"; $0.legs = ["Duke Blue Devils +2.5"] }), "College football")
        XCTAssertEqual(Stats.typeOf(ufc), "Parlay, 2-4 legs")
        XCTAssertEqual(Stats.typeOf(bet { $0.legs = Array(repeating: "x", count: 8) }), "Parlay, 5+ legs")
        XCTAssertEqual(Stats.bandOf(bet { $0.price = -130 }), Stats.bands[0])
        XCTAssertEqual(Stats.bandOf(bet { $0.price = 1128 }), Stats.bands[4])
        XCTAssertEqual(Stats.moneyOf(bet { $0.bonus = true; $0.boost = 30 }), "Bonus bets")
        XCTAssertEqual(Stats.moneyOf(bet { $0.boost = 50 }), "Boosted cash")
    }

    func testUnitsOverTimeStreaksAndExtremesFollowTheSettledOrder() {
        let bets = [bet { $0.price = 200 }, bet { $0.ticketStatus = "lost" }, bet(), bet(), bet { $0.ticketStatus = nil }]
        XCTAssertEqual(Stats.timeline(bets).map(\.units), [2, 1, 2, 3])
        let s = Stats.streaks(bets)
        XCTAssertEqual(s.kind, "won"); XCTAssertEqual(s.n, 2); XCTAssertEqual(s.bestWin, 2)
        let e = Stats.extremes(bets)
        XCTAssertEqual(e.best?.price, 200)
        XCTAssertEqual(e.worst?.ticketStatus, "lost")
    }

    func testAchievementsEarnedOnesCarryTheirBetAndDayLockedOnesTheirProgress() {
        let bets = [bet { $0.price = 1100; $0.bonus = true; $0.legs = Array(repeating: "x", count: 5) }, bet { $0.ticketStatus = "lost" },
                    bet { $0.book = "DraftKings" }]
        let all = Achievements.all(bets)
        let by = Dictionary(uniqueKeysWithValues: all.map { ($0.id, $0) })
        XCTAssertTrue(by["four-figures"]?.earned != nil && by["five-legs"]?.earned != nil && by["free-money"]?.earned != nil && by["line-shopper"]?.earned != nil)
        XCTAssertNil(by["eight-legs"]?.earned)
        XCTAssertEqual(by["hat-trick"]?.progress?.have, 1); XCTAssertEqual(by["hat-trick"]?.progress?.need, 3)
        XCTAssertGreaterThanOrEqual(all[0].earned!, all[1].earned!)                 // newest first
        XCTAssertEqual(all.count, 89)
    }

    // web/tests/achievements.test.mjs, case for case
    func on(_ day: String, _ f: (inout MyBet) -> Void = { _ in }) -> MyBet { bet { $0.placedAt = day + "T18:00:00Z"; f(&$0) } }
    func got(_ bets: [MyBet]) -> Set<String> { Set(Achievements.all(bets).filter { $0.earned != nil }.map(\.id)) }
    func results(_ s: String) -> [LegResult] { try! Models.decoder.decode([LegResult].self, from: Data(s.utf8)) }

    func testLotsOfBadgesEachIdAndIconItsOwnEachInAGroup() {
        let all = Achievements.all([])
        XCTAssertGreaterThanOrEqual(all.count, 80)
        XCTAssertEqual(Set(Achievements.ids).count, all.count)
        XCTAssertEqual(Set(Achievements.icons).count, all.count)
        XCTAssertTrue(all.allSatisfy { Achievements.groups.contains($0.group) })
    }

    func testRunsFiveInARowIsOnFireALossResetsItAVoidDoesnt() {
        let five = [on("2026-10-01"), on("2026-10-02"), on("2026-10-03") { $0.ticketStatus = "void" }, on("2026-10-04"), on("2026-10-05"), on("2026-10-06")]
        XCTAssertTrue(got(five).contains("on-fire"))
        let broken = [on("2026-10-01"), on("2026-10-02"), on("2026-10-03") { $0.ticketStatus = "lost" }, on("2026-10-04"), on("2026-10-05")]
        XCTAssertFalse(got(broken).contains("on-fire"))
        let p = Achievements.all(broken).first { $0.id == "on-fire" }!.progress!
        XCTAssertEqual(p.have, 2); XCTAssertEqual(p.need, 5)
    }

    func testAComebackBackAboveZeroAfterBeingDownFiveUnits() {
        let lose = (1...5).map { i in on("2026-10-0\(i)") { $0.ticketStatus = "lost" } }
        XCTAssertTrue(got(lose + [on("2026-10-08") { $0.price = 600 }]).contains("comeback"))
        XCTAssertFalse(got(lose + [on("2026-10-08") { $0.price = 400 }]).contains("comeback"))     // back to -1u: not yet
    }

    func testLegsCountByTheirLine() {
        let p = { (label: String) in self.on("2026-10-12") {
            $0.legs = [label, "B ML"]; $0.ticketStatus = "lost"
            $0.legResults = self.results(#"[{"leg": "\#(label)", "result": "won", "value": 310}, {"leg": "B ML", "result": "lost"}]"#)
        } }
        XCTAssertTrue(got([p("Jared Goff 300+ passing yds")]).contains("air-raid"))
        XCTAssertFalse(got([p("Jared Goff 250+ passing yds")]).contains("air-raid"))
        XCTAssertTrue(got([p("Jared Goff over 299.5 passing yds")]).contains("air-raid"))
        XCTAssertTrue(got([on("2026-10-12") { $0.label = "Josh Allen anytime TD"; $0.legs = nil }]).contains("td"))   // a single takes the bet's result
    }

    func testTheHeartbreakerA4LegParlayLostByExactlyOneGradedLeg() {
        let legs = ["A", "B", "C", "D"]
        let res = { (lost: [Int]) in self.results("[" + legs.enumerated().map { #"{"leg": "\#($0.element)", "result": "\#(lost.contains($0.offset) ? "lost" : "won")"}"# }.joined(separator: ",") + "]") }
        XCTAssertTrue(got([on("2026-10-12") { $0.legs = legs; $0.legResults = res([2]); $0.ticketStatus = "lost" }]).contains("heartbreak"))
        XCTAssertFalse(got([on("2026-10-12") { $0.legs = legs; $0.legResults = res([1, 2]); $0.ticketStatus = "lost" }]).contains("heartbreak"))
    }

    func testDaysAPerfectDayNeeds3AllWonABigDayIsPlus5() {
        XCTAssertTrue(got([on("2026-10-12"), on("2026-10-12"), on("2026-10-12")]).contains("perfect-day"))
        XCTAssertFalse(got([on("2026-10-12"), on("2026-10-12"), on("2026-10-12") { $0.ticketStatus = "lost" }]).contains("perfect-day"))
        XCTAssertTrue(got([on("2026-10-12") { $0.price = 300 }, on("2026-10-12") { $0.price = 250 }]).contains("big-day"))
    }

    func testNextUpTheLockedBadgesClosestToDone() {
        let bets = (1...9).map { i in on(String(format: "2026-10-%02d", i)) { $0.ticketStatus = i % 2 == 0 ? "lost" : "won" } }
        let next = Achievements.nextUp(Achievements.all(bets), 3)
        XCTAssertEqual(next.count, 3)
        XCTAssertTrue(next.allSatisfy { $0.earned == nil && $0.progress!.have > 0 })
        XCTAssertEqual(next[0].id, "line-shopper")
        XCTAssertEqual(next[1].id, "wins-10")
    }

    func testAShareCardSaysOneLegAwayKeepsRepeatedLegsInOrderAndShowsABoostedPrice() throws {
        let lr = try Models.decoder.decode([LegResult].self, from: Data(#"[{"leg": "Over 2.5 goals", "result": "won", "value": "3-1"}, {"leg": "Lazio to win", "result": "won", "value": "2-1"}, {"leg": "Over 2.5 goals", "result": "lost", "value": "1-1"}]"#.utf8))
        let b = bet { $0.ticketStatus = "lost"; $0.price = 1128; $0.bonus = true; $0.legs = ["Over 2.5 goals", "Lazio to win", "Over 2.5 goals"]; $0.legResults = lr }
        let c = ShareCard.of(b)
        XCTAssertEqual(c.status, "ONE LEG AWAY")
        XCTAssertEqual(c.legs.map(\.result), ["won", "won", "lost"])
        XCTAssertEqual(c.legs.map(\.value), ["3-1", "2-1", "1-1"])
        XCTAssertEqual(c.detail, "2 of 3 hit · 1u bonus bet")
        let boosted = ShareCard.of(bet { $0.ticketStatus = nil; $0.price = 978; $0.boost = 30; $0.legs = ["A ML", "B ML", "C ML", "D ML"] })
        XCTAssertEqual(boosted.status, "OPEN")
        XCTAssertEqual(boosted.price, "+978 → +1271")
        XCTAssertEqual(boosted.headline, "to win 12.71u")
        XCTAssertEqual(boosted.title, "A, B and 2 more")
    }
}

final class ShareRenderTests: XCTestCase {
    @MainActor func testTheShareCardRendersAt1080x1350() throws {
        var b = MyBet(betId: "x", kind: "custom", mode: "real", price: 978, stake: 1, placedAt: "2026-10-24T17:06:00Z")
        b.legs = ["Alexander Volkov ML", "Lone'er Kavanagh ML", "Petr Yan ML", "Movsar Evloev ML"]; b.boost = 30
        let data = try XCTUnwrap(ShareCardView.png(ShareCard.of(b)))
        let img = try XCTUnwrap(UIImage(data: data))
        XCTAssertEqual(img.size.width * img.scale, 1080); XCTAssertEqual(img.size.height * img.scale, 1350)
        try data.write(to: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("betlab-share-test.png"))
    }
}

/// web/tests/slip.test.mjs: the saved row and the slip's Eastern time.
final class SlipTests: XCTestCase {
    func testTheSavedRowUnitsLabelAndLegsGroupedByGame() {
        let legs = [SlipDraft.Leg(label: "Tennessee Volunteers ML", matchup: "Tennessee Volunteers @ South Carolina Gamecocks", sport: "ncaaf",
                                  game_ref: "ncaaf:401856731", start: nil, matched: true),
                    SlipDraft.Leg(label: "Josh Giddey 7+ assists", matchup: "Washington Wizards @ Chicago Bulls", sport: "nba",
                                  game_ref: "nba|CHI|WSH|2026-10-24T23:10:00+00:00", start: nil, matched: true),
                    SlipDraft.Leg(label: "Over 2.5 goals", matchup: "Napoli vs AS Roma", sport: "soccer",
                                  game_ref: "serie_a|Napoli|AS Roma|2026-10-24T16:00:00+00:00", start: nil, matched: true)]
        let d = SlipDraft(book: "FanDuel", price: 978, boost_pct: 30, stake_dollars: 5, bonus: false, placed_at: nil, legs: legs)
        let row = Slip.row(d, unitDollars: 5, placedAt: "2026-10-24T17:06:00.000Z", id: "abcd1234")
        XCTAssertEqual(row["stake"] as? Double, 1)
        XCTAssertEqual(row["sgp_id"] as? String, "custom-fd-snap-abcd1234")
        XCTAssertEqual(row["label"] as? String, "$5 cash, 30% profit boost (+978 -> +1271)")
        XCTAssertEqual(row["matchup"] as? String, "Parlay Sat, Oct 24 · 3 legs")
        let games = row["games"] as! [[String: Any]]
        XCTAssertEqual(games.map { $0["game_ref"] as? String }, ["ncaaf:401856731", "nba|CHI|WSH|2026-10-24T23:10:00+00:00", "serie_a|Napoli|AS Roma|2026-10-24T16:00:00+00:00"])
        XCTAssertEqual(games.map { $0["legs"] as! [String] }, [["Tennessee Volunteers ML"], ["Josh Giddey 7+ assists"], ["Over 2.5 goals"]])
        XCTAssertEqual(games.map { $0["sport"] as? String }, ["ncaaf", "nba", "soccer"])     // a game with no ref grades by it
        var bonus = d; bonus.bonus = true; bonus.boost_pct = nil; bonus.stake_dollars = 10; bonus.book = "DraftKings"
        let b = Slip.row(bonus, unitDollars: 5, placedAt: "2026-10-24T17:06:00.000Z", id: "x")
        XCTAssertEqual(b["label"] as? String, "Bonus bet $10")
        // an odds-on boosted price stays odds-on (Nov 9; web slip.test.mjs)
        var fav = d; fav.price = -200
        XCTAssertEqual(Slip.row(fav, unitDollars: 5, placedAt: "2026-10-24T17:06:00.000Z", id: "y")["label"] as? String,
                       "$5 cash, 30% profit boost (-200 -> -154)")
        // a leg with no game put on the one chosen (web chooseGame)
        let lost = SlipDraft.Leg(label: "Some team ML", matchup: "Nobody @ Nowhere", sport: "nfl", game_ref: nil, start: nil, matched: false)
        let put = Slip.choose(lost, .init(matchup: "Cleveland Browns @ Tennessee Titans", sport: "nfl", game_ref: "2026_07_CLE_TEN",
                                         start: "2026-10-25T17:00:00+00:00", event_id: nil))
        XCTAssertEqual([put.matchup, put.game_ref, put.label], ["Cleveland Browns @ Tennessee Titans", "2026_07_CLE_TEN", "Some team ML"])
        XCTAssertTrue(put.matched)
        XCTAssertEqual(b["stake"] as? Double, 2)
        XCTAssertEqual(b["sgp_id"] as? String, "custom-dk-snap-x")
    }

    func testASlipsEasternTimeBecomesTheRightInstant() {
        XCTAssertEqual(Slip.easternIso("2026-10-24T13:06:00"), "2026-10-24T17:06:00.000Z")   // EDT
        XCTAssertEqual(Slip.easternIso("2026-12-05T20:00:00"), "2026-12-06T01:00:00.000Z")   // EST
        XCTAssertEqual(Slip.easternIso("2026-11-01T06:30:00"), "2026-11-01T11:30:00.000Z")   // clock-change day
    }

    // web/tests/slip.test.mjs (Oct 27): four slips were read at 2-4.6x their legs' own prices multiplied
    func testAReadPriceFarAboveTheLegsMultipliedIsFlagged() throws {
        let legs = try JSONDecoder().decode([SlipDraft.Leg].self, from: Data(#"""
            [{"label": "Justin Jefferson 50+ receiving yds", "matchup": "x", "sport": "nfl", "matched": true, "prices": {"FanDuel": -330, "DraftKings": -300}},
             {"label": "Kyler Murray 175+ passing yds", "matchup": "x", "sport": "nfl", "matched": true, "prices": {"FanDuel": -270}},
             {"label": "Garrett Wilson 3+ receptions", "matchup": "x", "sport": "nfl", "matched": true, "prices": {"FanDuel": -1800}}]
            """#.utf8))
        let bad = try XCTUnwrap(Slip.priceCheck(legs, book: "FanDuel", price: 3038))    // the legs multiply to -113 (1.885)
        XCTAssertTrue(bad.flag); XCTAssertEqual(bad.legsPrice, -113); XCTAssertGreaterThan(bad.ratio, 15)
        XCTAssertEqual(Slip.priceCheck(legs, book: "FanDuel", price: -150)?.flag, false)  // a same-game price under the product
        XCTAssertEqual(Slip.priceCheck(legs, book: "FanDuel", price: 130)?.flag, false)   // a little over: still fits
        XCTAssertNil(Slip.priceCheck(legs, book: "DraftKings", price: 3038))              // Murray has no DraftKings price
        XCTAssertNil(Slip.priceCheck(legs, book: "Novig", price: 3038))
        XCTAssertNil(Slip.priceCheck(legs + [SlipDraft.Leg(label: "Unknown 1+ goals", matchup: "x", sport: "soccer", matched: true)], book: "FanDuel", price: 3038))
    }
}

/// web/tests/stats.test.mjs: player cards.
final class PlayerCardTests: XCTestCase {
    func testPlayerCardsCountEachLegMatchResultsInOrderAndRankTheMostBetFirst() throws {
        let lr = try Models.decoder.decode([LegResult].self, from: Data(#"[{"leg": "Josh Giddey 7+ assists", "result": "lost", "value": 6}, {"leg": "Tre Jones 9+ points", "result": "won", "value": 10}, {"leg": "Miami Heat ML", "result": "won"}]"#.utf8))
        var a = MyBet(betId: "a", kind: "custom", mode: "real", price: 100, stake: 1, placedAt: "2026-10-11T18:00:00Z", ticketStatus: "lost",
                      legs: ["Josh Giddey 7+ assists", "Tre Jones 9+ points", "Miami Heat ML"])
        a.legResults = lr
        let b = MyBet(betId: "b", kind: "custom", mode: "real", price: 100, stake: 1, placedAt: "2026-10-12T18:00:00Z",
                      legs: ["Josh Giddey 7+ assists", "Tre Jones 9+ points"])
        let c = MyBet(betId: "c", kind: "pick", mode: "real", price: -110, stake: 1, label: "Tre Jones over 8.5 points",
                      placedAt: "2026-10-13T18:00:00Z", pickStatus: "won")
        let list = Players.all([a, b, c])
        XCTAssertEqual(list.map(\.name), ["Tre Jones", "Josh Giddey"])
        XCTAssertEqual(list.map { [$0.legs.count, $0.won, $0.lost, $0.open] }, [[3, 2, 0, 1], [2, 0, 1, 1]])
        XCTAssertEqual(list[0].hitRate, 1)
        XCTAssertEqual(list[0].topStat, "points")
        XCTAssertEqual(list[0].bets, 3)
        XCTAssertNil(list[0].tier)                        // 2 graded legs: no tier yet
        XCTAssertEqual(Players.legs(a).count, 2)          // the moneyline is no player's
    }
}

final class TeamCardTests: XCTestCase {
    /// Web tests/cards.test.mjs: game legs count for both teams, each leg keeps its own result, codes read as full names.
    func testGameLegsCountForBothTeamsAndCodesReadAsNames() {
        let r = { (l: String, x: String) in LegResult(leg: l, result: x) }
        let sgp = MyBet(betId: "b1", kind: "custom", mode: "real", price: 300, stake: 1, placedAt: "2026-10-24T20:00:00Z", ticketStatus: "lost",
                        legs: ["Both teams to score", "Over 2.5 goals", "Chelsea to win", "Both teams to score"],
                        legResults: [r("Both teams to score", "won"), r("Over 2.5 goals", "lost"), r("Chelsea to win", "won"), r("Both teams to score", "lost")])
        let nhl = MyBet(betId: "b2", kind: "custom", mode: "real", price: 100, stake: 1, placedAt: "2026-10-24T20:00:00Z", ticketStatus: "won",
                        legs: ["OTT to win"], legResults: [r("OTT to win", "won")])
        let groups: [String: [LiveGroup]] = [
            "b1": [LiveGroup(sport: "soccer", league: "serie_a", matchup: "Venezia @ Genoa", legs: ["Both teams to score", "Over 2.5 goals"]),
                   LiveGroup(sport: "soccer", league: "epl", matchup: "Chelsea vs Arsenal", legs: ["Chelsea to win", "Both teams to score"])],
            "b2": [LiveGroup(sport: "nhl", league: nil, matchup: "NYR @ OTT", legs: ["OTT to win"])],
        ]
        let entries = [sgp, nhl].flatMap { Cards.teamLegs($0, groups[$0.betId]!) }
        let t = Dictionary(uniqueKeysWithValues: Players.tally(entries, min: 1).map { ($0.name, $0) })
        XCTAssertEqual(t["Genoa"].map { [$0.won, $0.lost] }, [1, 1])
        XCTAssertEqual(t["Chelsea"].map { [$0.won, $0.lost] }, [1, 1])
        XCTAssertEqual(t["Arsenal"].map { [$0.won, $0.lost] }, [0, 1])
        XCTAssertEqual(t["Ottawa Senators"]?.won, 1)
        XCTAssertEqual(t["Genoa"]?.legs.first?.game, "Venezia @ Genoa")
    }
}

final class SameTeamTests: XCTestCase {
    /// Web tests/cards.test.mjs: the Knicks card took other New York teams' legs (Oct 25).
    func testATeamNeverMatchesAnotherFromTheSameCity() {
        XCTAssertFalse(Cards.sameTeam("New York City FC", "New York Knicks"))
        XCTAssertFalse(Cards.sameTeam("New York Rangers", "New York Knicks"))
        XCTAssertFalse(Cards.sameTeam("New York Jets", "New York Giants"))
        XCTAssertTrue(Cards.sameTeam("Bournemouth", "AFC Bournemouth"))
        XCTAssertTrue(Cards.sameTeam("Brighton and Hove Albion", "Brighton & Hove Albion"))
        XCTAssertTrue(Cards.sameTeam("New York Knicks", "New York Knicks"))
    }
}
