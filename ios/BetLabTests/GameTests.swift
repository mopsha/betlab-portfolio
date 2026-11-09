import XCTest
@testable import BetLab

/// Refresh / Grade now rules (web/lib/jobs.ts) and the game page's analysis lines (web/components/games/Analysis.tsx).
final class GameTests: XCTestCase {
    func req(_ status: String, minutesAgo: Double) -> JobRequest {
        let f = ISO8601DateFormatter()
        return JobRequest(id: 1, status: status, requestedAt: f.string(from: Date().addingTimeInterval(-minutesAgo * 60)), finishedAt: nil)
    }

    func testJobsAskOnlyWhenActiveIdleAndCooledDown() {
        XCTAssertEqual(JobState.mode(fromStep: "started"), "active")
        XCTAssertEqual(JobState.mode(fromStep: "started (shadow)"), "shadow")
        XCTAssertEqual(JobState.mode(fromStep: nil), "unknown")
        XCTAssertTrue(JobState(mode: "active", request: nil).canAsk)
        XCTAssertFalse(JobState(mode: "shadow", request: nil).canAsk)
        XCTAssertFalse(JobState(mode: "active", request: req("running", minutesAgo: 40)).canAsk)    // pending
        XCTAssertFalse(JobState(mode: "active", request: req("done", minutesAgo: 10)).canAsk)       // cooling down
        XCTAssertTrue(JobState(mode: "active", request: req("done", minutesAgo: 31)).canAsk)
        XCTAssertEqual(JobState(mode: "active", request: req("queued", minutesAgo: 0)).message(.grade), "Grading queued. You can keep browsing.")
        XCTAssertEqual(JobState(mode: "shadow").message(.reprice), "On-demand refresh is not enabled yet. Scheduled updates continue.")
    }

    func analysis(_ kind: String, _ json: String) throws -> [String: JSON] {
        [kind: try JSON.plainDecoder.decode(JSON.self, from: Data(json.utf8))]
    }

    func testNflMetaAndBadges() throws {
        let an = try analysis("nfl_preview", #"""
        {"home":"BUF","away":"NYJ","market":{"spread_home":-7.5,"total":44.5,"away_points":18.4,"home_points":25.9},
         "ours":{"margin":6.2},"teams":[{"team":"NYJ","name":"New York Jets","qb":{"name":"T. Boyle","change":true}},
         {"team":"BUF","name":"Buffalo Bills","qb":{"name":"J. Allen"}}],
         "injuries":{"NYJ":[{"name":"A. Player","status":"Out","position":"WR","snap_share":0.82}],"BUF":[]},
         "script":"Buffalo controls it.","matchups":[{"text":"BUF pass offense vs NYJ secondary","size":1.4}]}
        """#)
        XCTAssertEqual(GameAnalysis.meta(an), ["New York Jets \u{2212}7.5 · total 44.5", "Market NYJ 18, BUF 26", "Our ratings: BUF by 6.2"])
        XCTAssertEqual(GameAnalysis.badges(an), ["New QB: T. Boyle"])
        XCTAssertEqual(GameAnalysis.sections(an).folds.map(\.key), ["story", "tape", "hurt"])
        XCTAssertEqual(GameAnalysis.sections(an).folds.first { $0.key == "hurt" }?.n, 1)
        XCTAssertTrue(GameAnalysis.sections(an).top.isEmpty)        // no lines that fit the script in this sample
    }

    func testNhlAndSoccerMeta() throws {
        let nhl = try analysis("nhl", #"""
        {"home":"NYR","away":"BOS","line":{"ml_home":-140,"ml_away":120,"total":6,"p_home":0.57},"model":{"p_home":0.55,"exp_total":6.1},
         "teams":[{"team":"BOS","goalie_status":"expected","b2b":true},{"team":"NYR","goalie_status":"confirmed"}]}
        """#)
        XCTAssertEqual(GameAnalysis.meta(nhl), ["NYR \u{2212}140 · total 6", "Our model: NYR 55% to win, 6.1 goals"])
        XCTAssertEqual(GameAnalysis.badges(nhl), ["BOS goalie expected", "BOS on a back-to-back"])
        let soc = try analysis("soccer", #"""
        {"competition":"Champions League","lines":[{"side":"Draw","p_market":0.3},{"side":"FC Copenhagen","p_market":0.41},{"side":"SC Braga","p_market":0.29}],
         "analysis":{"lineup":"expected","teams":[{"team":"FCK","shots":13.2,"rotation":{"changes":5}},{"team":"Braga","shots":9.6}],"script":"Tight."}}
        """#)
        XCTAssertEqual(GameAnalysis.meta(soc), ["Champions League", "FC Copenhagen 41% to win", "Shots projected 13–10"])
        XCTAssertEqual(GameAnalysis.badges(soc), ["Lineups not out yet: last XIs shown", "FCK: 5 changes"])
        XCTAssertEqual(GameAnalysis.sections(soc).top.map(\.key), ["books"])
        XCTAssertEqual(GameAnalysis.sections(soc).folds.map(\.key), ["story", "tape"])
    }

    func testSoccerMoneylineReadFollowsTheStoryOrStandsAlone() throws {
        let ml = #"""
        "moneyline":{"summary":"The market has Arsenal at 52%.","lineup":"confirmed","lineup_record":{"n":12,"log_loss":0.98,"log_loss_mkt":0.97},
         "sides":[{"side":"Arsenal","p_market":0.52,"p_first":0.48,"move":0.04,"best_book":"draftkings","best_price":-105,"best_ev":0.012,"p_lineup":0.55},
                  {"side":"Draw","p_market":0.25,"p_first":0.27,"move":-0.02,"best_book":"fanduel","best_price":270,"best_ev":-0.03,"p_lineup":null},
                  {"side":"Chelsea","p_market":0.23,"p_first":0.25,"move":-0.02,"best_book":"fanduel","best_price":null,"best_ev":null,"p_lineup":0.2}]}
        """#
        let full = try analysis("soccer", #"{"analysis":{"lineup":"confirmed","script":"Tight.","teams":[{"team":"ARS"},{"team":"CHE"}],"# + ml + "}}")
        XCTAssertEqual(GameAnalysis.sections(full).folds.map(\.key), ["story", "moneyline", "tape"])
        let only = try analysis("soccer", #"{"analysis":{"# + ml + "}}")      // no ESPN match yet: no teams
        XCTAssertEqual(GameAnalysis.sections(only).folds.map(\.key), ["moneyline"])
        let none = try analysis("soccer", #"{"analysis":{"script":"Tight.","teams":[{"team":"ARS"},{"team":"CHE"}]}}"#)
        XCTAssertEqual(GameAnalysis.sections(none).folds.map(\.key), ["story", "tape"])
    }

    func testStatFormats() {
        XCTAssertEqual(Stat.ord(1), "1st"); XCTAssertEqual(Stat.ord(12), "12th"); XCTAssertEqual(Stat.ord(23), "23rd")
        XCTAssertEqual(Stat.epa(-0.051), "\u{2212}0.05")
        XCTAssertEqual(Stat.pts(0.064), "+6 pts")
        XCTAssertEqual(Stat.pts(-2.5, 1, scale: 1), "\u{2212}2.5 pts")
        XCTAssertEqual(Stat.pctOdds(0.41), "41% (+144)")
        XCTAssertEqual(Stat.bookCell(nil, 0.1).text, "—")
        XCTAssertEqual(Stat.bookCell(-110, 0.031).sub, "+3.1%")
    }

    func testNbaReadAndNhlLines() throws {
        let nba = try analysis("nba", #"""
        {"home":"NYK","away":"BOS","spread_home":-4.5,"total":221.5,
         "model":{"margin":-2.0,"total":224.1,"ranks":{"BOS":{"off_ortg":3,"def_ortg":10,"pace":20},"NYK":{"off_ortg":5,"def_ortg":2,"pace":25}},
                  "out":{"home":[{"name":"J. Brunson","minutes":35.2}],"away":[]}}}
        """#)
        let s = GameAnalysis.sections(nba)
        XCTAssertEqual(s.top.map(\.key), ["read"])
        XCTAssertEqual(s.folds.map(\.key), ["tape", "lines"])
        let nhl = try analysis("nhl", #"""
        {"home":"NYR","away":"BOS","book":"FanDuel","line":{"ml_home":-140,"ml_away":120,"total":6,"p_home":0.57,"p_over":0.5,"over":-110,"under":-110},
         "model":{"p_home":0.55,"p_over":0.52},"teams":[{"team":"BOS"},{"team":"NYR"}],
         "fanduel":[{"label":"NYR ML","price":-140,"ev":0.01,"p_market":0.57,"source":"pinnacle"}],
         "props":[{"player":"A","stat":"shots","line":2.5,"fd_over":-120,"p_market":0.5,"p_model":0.6,"ev_over":0.04,"ev_under":-0.08,"read":true}]}
        """#)
        let h = GameAnalysis.sections(nhl)
        XCTAssertEqual(h.top.map(\.key), ["books"])
        XCTAssertEqual(h.folds.map(\.key), ["tape", "lines", "props"])
    }

    func testJsonKeepsItsOwnKeys() throws {
        let j = try JSON.plainDecoder.decode(JSON.self, from: Data(#"{"spread_home":-3,"x":[1,"a",null]}"#.utf8))
        XCTAssertEqual(j["spread_home"].double, -3)
        XCTAssertEqual(j["x"][1].string, "a")
        XCTAssertTrue(j["x"][2].isNull)
        XCTAssertNil(j["missing"]["deeper"].double)
    }

    func testUfcFightPage() throws {       // Oct 23: a UFC 333 prelim as published, books empty until the card's odds pull
        let body = """
        {"segment": "Prelims", "weight_class": "Middleweight", "rounds": 3, "title": false, "books": [],
         "story": "DraftKings makes Abusupyian Magomedov the favorite at 53%.",
         "dk": {"ml": {"a": -125, "b": 105, "p_a": 0.5346}, "total": {"line": 1.5, "over": -180, "under": 140, "p_over": 0.6165},
                "method": {"a_ko": {"p": 0.2182, "price": 275}, "b_ko": {"p": 0.1705, "price": 380}, "a_dec": {"p": 0.1819, "price": 350},
                           "a_sub": {"p": 0.1488, "price": 450}, "b_dec": {"p": 0.1637, "price": 400}, "b_sub": {"p": 0.1169, "price": 600}},
                "distance": {"no": -200, "yes": 150, "p_yes": 0.3621}, "method_margin": 0.222},
         "model": {"p_a": 0.3968, "p_dist": 0.3929, "debut_a": false, "debut_b": true},
         "fighters": [{"name": "Abusupyian Magomedov", "record": "29-7-1", "age": 36,
                       "form": {"fights": 8, "wins": {"ko": 1, "dec": 2, "sub": 2}, "losses": {"ko": 1}, "distance": 0.375,
                                "last": [{"date": "2026-06-27", "round": 1, "method": "Submission", "result": "W", "opponent": "Michal Oleksiejczuk"}]}},
                      {"name": "Cam Rowston", "form": {"fights": 0}}],
         "same_fight": [{"p": 0.1772, "dk_ev": -0.2026, "label": "Abusupyian Magomedov wins by decision", "dk_price": 350, "fair_price": 464}],
         "class_rates": {"n": 365, "ko": 0.403, "sub": 0.203, "distance": 0.373}}
        """
        let an = try analysis("ufc", body)
        XCTAssertEqual(GameAnalysis.meta(an), ["Prelims", "Middleweight", "3 rounds"])
        let s = GameAnalysis.sections(an)
        XCTAssertEqual(s.top.map(\.key), ["method"])                    // no moneyline table while books is empty
        XCTAssertEqual(s.folds.map(\.key), ["story", "model", "sgp", "tape", "last", "class"])
        XCTAssertEqual(s.folds.first { $0.key == "class" }?.title, "Middleweight 3-rounders")
        XCTAssertEqual(s.folds.first { $0.key == "sgp" }?.n, 1)
        var title = an
        title["ufc"] = try analysis("ufc", #"{"segment": "Main card", "weight_class": "Featherweight", "rounds": 5, "title": true}"#)["ufc"]
        XCTAssertEqual(GameAnalysis.meta(title), ["Main card", "Featherweight title fight", "5 rounds"])
        let books = try analysis("ufc", #"{"books": [{"label": "A ML", "p_market": 0.6, "source": "pinnacle", "novig": {"price": -140, "ev": 0.01}}], "fighters": []}"#)
        XCTAssertEqual(GameAnalysis.sections(books).top.map(\.key), ["books"])
        XCTAssertTrue(GameAnalysis.sections(books).folds.isEmpty)       // no fighters, no folds
    }
}
