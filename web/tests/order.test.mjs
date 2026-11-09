import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const O = loader()(new URL("../lib/order.ts", import.meta.url));

const tiles = ["nfl:1", "nfl:2", "nba:3", "nhl:4"].map((key) => ({ key }));   // the wall's own order (live first)

test("placed tiles come first in your order, the rest after them in the wall's own order", () => {
  const keys = (o) => O.ordered(tiles, o, (t) => t.key).map((t) => t.key);
  assert.deepEqual(keys([]), ["nfl:1", "nfl:2", "nba:3", "nhl:4"]);
  assert.deepEqual(keys(["nba:3", "nfl:1", "gone:9"]), ["nba:3", "nfl:1", "nfl:2", "nhl:4"]);
});

test("a drop puts the shown tiles where they stood and keeps every other key's place", () => {
  assert.deepEqual(O.placed([], ["c", "a", "b"]), ["c", "a", "b"]);
  assert.deepEqual(O.placed(["x", "a", "y", "b", "z"], ["b", "a"]), ["x", "b", "a", "y", "z"]);
  assert.deepEqual(O.placed(["x", "y"], ["b", "a"]), ["x", "y", "b", "a"]);
  assert.deepEqual(O.placed(["p", "q", "r", "s"], ["s", "r"], 3), ["q", "s", "r"]);
});

test("moving an item", () => {
  assert.deepEqual(O.moved(["a", "b", "c", "d"], 0, 2), ["b", "c", "a", "d"]);
  assert.deepEqual(O.moved(["a", "b", "c", "d"], 3, 0), ["d", "a", "b", "c"]);
});
