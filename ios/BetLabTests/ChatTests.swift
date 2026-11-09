import XCTest
@testable import BetLab

/// web/tests/chat.test.mjs: answers keep bold, app links and lists; other links stay text.
final class ChatTests: XCTestCase {
    typealias S = ChatFormat.Span
    func testAnswersKeepBoldAppLinksAndListsOtherLinksStayText() {
        XCTAssertEqual(ChatFormat.spans("Take **Akron +2.5** on [Akron @ Kent](/games/ncaaf/401866446)."), [
            S(text: "Take "), S(text: "Akron +2.5", bold: true), S(text: " on "), S(text: "Akron @ Kent", href: "/games/ncaaf/401866446"), S(text: ".")])
        XCTAssertEqual(ChatFormat.spans("[x](javascript:alert(1))"), [S(text: "[x](javascript:alert(1)"), S(text: ")")])
        XCTAssertEqual(ChatFormat.spans("[evil](//evil.com)"), [S(text: "[evil](//evil.com)")])
        let b = ChatFormat.blocks("## Tonight\n\n- One\n2. Two\nDone")
        XCTAssertEqual(b.map(\.kind), ["p", "li", "li", "p"])
        XCTAssertEqual(b[0].spans[0].text, "Tonight")
    }
}

final class SiriTests: XCTestCase {
    func testAnswersAreSpokenPlain() {
        XCTAssertEqual(Ask.spoken("**3 of 4** hit.\n- [Zion](/games/nba/1): 1 to go\n## Next"), "3 of 4 hit. Zion: 1 to go Next")
    }
}
