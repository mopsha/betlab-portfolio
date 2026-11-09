import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const box = { self: { addEventListener() {}, location: { origin: "https://b.test" } }, caches: {}, URL, Response: class {} };
vm.runInNewContext(readFileSync(new URL("../public/sw.js", import.meta.url), "utf8"), box);
const how = (path, method = "GET", mode = "navigate", origin = "https://b.test") =>
  box.policy(new URL(path, origin), method, mode, "https://b.test");

test("a page's last copy is kept for going offline, but never live data or sign-in", () => {
  assert.equal(how("/"), "page");
  assert.equal(how("/bets?view=settled"), "page");
  assert.equal(how("/_next/static/chunks/a.js", "GET", "no-cors"), "static");
  assert.equal(how("/api/live", "GET", "cors"), null);
  assert.equal(how("/api/live"), null);
  assert.equal(how("/login"), null);
  assert.equal(how("/auth/callback"), null);
  assert.equal(how("/", "POST"), null);                 // a server action
  assert.equal(how("/?_rsc=abc", "GET", "cors"), null); // a refresh's data
  assert.equal(how("/x", "GET", "navigate", "https://other.test"), null);
});

test("a local preview caches nothing: the dev server's file names aren't content-hashed", () => {
  const local = (path, mode = "navigate") => box.policy(new URL(path, "http://localhost:3012"), "GET", mode, "http://localhost:3012");
  assert.equal(local("/_next/static/chunks/app.css", "no-cors"), null);
  assert.equal(local("/"), null);
});
