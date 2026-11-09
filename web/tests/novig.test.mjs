import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { novigApp } = loader()(new URL("../lib/novig.ts", import.meta.url));

test("an order-slip link becomes Novig's app scheme with the same path (Oct 28)", () => {
  assert.equal(novigApp("https://novig.com/events/01a17ead-b7b2-7a71-aa1a-68515b461ab7/oddsapi/5"),
               "novigapp://events/01a17ead-b7b2-7a71-aa1a-68515b461ab7/oddsapi/5");
  assert.equal(novigApp("https://www.novig.com/events/a,b/oddsapi/5"), "novigapp://events/a,b/oddsapi/5");
});

test("other links have no app link", () => {
  assert.equal(novigApp("https://novig.com/"), null);
  assert.equal(novigApp("https://sportsbook.draftkings.com/?outcomes=1"), null);
});

const { novigQuote, novigSlipLink } = loader()(new URL("../lib/novig.ts", import.meta.url));

test("Novig's pricer answer becomes American odds (Oct 30: /rfq/v2/quote, no largest stake)", () => {
  const q = novigQuote({ price: "0.333", expiresAt: 1793381399956, serverNow: 1793381369957 });
  assert.equal(q.price, 200);
  assert.equal(q.stake_max, null);
  assert.equal(novigQuote({ price: "0.75" }).price, -300);
  assert.equal(novigQuote({ statusCode: 400 }), null);
  assert.equal(novigQuote([{ price: "0.5" }]), null);   // the old route's array
  assert.equal(novigSlipLink(["a", "b"]), "https://novig.com/events/a,b/oddsapi/5");
});
