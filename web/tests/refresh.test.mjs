import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { workerMode, refreshWait, pendingRefresh, refreshMessage } = loader()(new URL("../lib/jobs.ts", import.meta.url));
const at = Date.parse("2026-10-02T16:00:00Z");
const request = (status = "done") => ({ id: 1, status, requested_at: new Date(at).toISOString(), finished_at: null });

test("only a recognized live worker start enables refresh", () => {
  assert.equal(workerMode("started"), "active");
  assert.equal(workerMode("started (shadow)"), "shadow");
  for (const step of [undefined, "(shadow) would run", "anything else"]) assert.equal(workerMode(step), "unknown");
});
test("refresh cooldown survives navigation and expires after 30 minutes", () => {
  assert.equal(refreshWait(request(), at + 10 * 60_000), 20 * 60_000);
  assert.equal(refreshWait(request(), at + 30 * 60_000), 0);
  assert.equal(refreshWait(null, at), 0);
  assert.equal(refreshWait({ ...request(), requested_at: "invalid" }, at), 0);
});
test("queued and running states stay pending; terminal states have honest feedback", () => {
  for (const status of ["queued", "running"]) assert.equal(pendingRefresh(request(status)), true);
  for (const status of ["done", "failed", "refused"]) {
    assert.equal(pendingRefresh(request(status)), false);
    assert.ok(refreshMessage({ mode: "active", request: request(status) }).length);
  }
  assert.match(refreshMessage({ mode: "shadow", request: null }), /not enabled/);
  assert.match(refreshMessage({ mode: "active", request: request() }), /Check the priced time/);
});

function actionHarness(state, fail = false) {
  const inserts = [];
  const load = loader({
    "./refresh": { refreshData: async () => state },
    "./supabase/server": { supabaseServer: async () => ({ from(table) {
      assert.equal(table, "job_requests");
      return { insert(row) {
        inserts.push(row);
        return { select(columns) {
          assert.equal(columns.includes("note"), false);
          return { single: async () => ({ data: request("queued"), error: fail ? { message: "private details" } : null }) };
        } };
      } };
    } }) },
  });
  return { actions: load(new URL("../lib/refresh-actions.ts", import.meta.url)), inserts };
}
test("shadow, unknown, and preview never enqueue live jobs", async () => {
  for (const mode of ["shadow", "unknown", "preview"]) {
    const h = actionHarness({ mode, request: null });
    await h.actions.requestRefresh();
    assert.equal(h.inserts.length, 0);
  }
});
test("repeat taps reuse pending requests and recent requests enforce cooldown", async () => {
  for (const status of ["queued", "running", "done"]) {
    const h = actionHarness({ mode: "active", request: { ...request(status), requested_at: new Date().toISOString() } });
    await h.actions.requestRefresh();
    assert.equal(h.inserts.length, 0);
  }
});
test("an eligible request queues only reprice and returns safe status fields", async () => {
  const h = actionHarness({ mode: "active", request: null });
  const result = await h.actions.requestRefresh();
  assert.deepEqual(h.inserts, [{ job: "reprice", status: "queued" }]);
  assert.equal(result.state.request.status, "queued");
});
test("database failures do not expose backend error text", async () => {
  const h = actionHarness({ mode: "active", request: null }, true);
  const result = await h.actions.requestRefresh();
  assert.match(result.error, /Couldn't queue/);
  assert.equal(result.error.includes("private details"), false);
});
test("grade queues only the grade job and refuses names outside the allow-list", async () => {
  const h = actionHarness({ mode: "active", request: null });
  await h.actions.requestRefresh("grade");
  assert.deepEqual(h.inserts, [{ job: "grade", status: "queued" }]);
  const bad = await h.actions.requestRefresh("daily");
  assert.equal(h.inserts.length, 1);
  assert.match(bad.error, /Couldn't queue/);
});
test("grade has its own honest messages", () => {
  assert.match(refreshMessage({ mode: "active", request: null }, "grade"), /9:55/);
  assert.match(refreshMessage({ mode: "active", request: request("done") }, "grade"), /Grading finished/);
  assert.match(refreshMessage({ mode: "shadow", request: null }, "grade"), /not enabled/);
});
