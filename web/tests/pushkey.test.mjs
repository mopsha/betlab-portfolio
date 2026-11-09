import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { keyBytes, staleKey } = loader()(new URL("../lib/pushkey.ts", import.meta.url));

const OLD = "BOldKeyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const NEW = "BNewKeyBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";
const sub = (k) => ({ options: { applicationServerKey: k === null ? null : keyBytes(k).buffer } });

test("a subscription made with the old VAPID key is stale after the rotation (Oct 23)", () => {
  assert.equal(staleKey(sub(OLD), NEW), true);
  assert.equal(staleKey(sub(NEW), NEW), false);
});

test("a browser that doesn't report its key, or no key deployed, is left alone", () => {
  assert.equal(staleKey(sub(null), NEW), false);
  assert.equal(staleKey({}, NEW), false);
  assert.equal(staleKey(sub(OLD), ""), false);
});
