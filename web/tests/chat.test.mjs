import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const F = loader()(new URL("../lib/chat-format.ts", import.meta.url));

test("answers keep bold, app links and lists; other links stay text", () => {
  assert.deepEqual(F.spans("Take **Akron +2.5** on [Akron @ Kent](/games/ncaaf/401866446)."), [
    { text: "Take " }, { text: "Akron +2.5", bold: true }, { text: " on " }, { text: "Akron @ Kent", href: "/games/ncaaf/401866446" }, { text: "." }]);
  assert.deepEqual(F.spans("[x](javascript:alert(1))"), [{ text: "[x](javascript:alert(1)" }, { text: ")" }]);
  assert.deepEqual(F.spans("[evil](//evil.com)"), [{ text: "[evil](//evil.com)" }]);
  const b = F.blocks("## Tonight\n\n- One\n2. Two\nDone");
  assert.deepEqual(b.map((x) => x.kind), ["p", "li", "li", "p"]);
  assert.equal(b[0].spans[0].text, "Tonight");
});
