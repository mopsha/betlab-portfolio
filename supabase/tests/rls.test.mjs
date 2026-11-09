// Database tests for supabase/migrations on a real Postgres (PGlite, in process):
// the migration loads, row-level security keeps each user to their own rows, signed-in users
// can read but never write shared tables, and paper picks are history.
// Run: cd supabase/tests && npm install && npm test
import { PGlite } from "@electric-sql/pglite";
import { readFileSync, readdirSync } from "node:fs";
import assert from "node:assert/strict";

const here = new URL(".", import.meta.url);
const db = new PGlite();
await db.exec(readFileSync(new URL("auth_stub.sql", here), "utf8"));
const dir = new URL("../migrations/", here);
for (const f of readdirSync(dir).filter((f) => f.endsWith(".sql")).sort()) {
  await db.exec(readFileSync(new URL(f, dir), "utf8"));
}

const A = "00000000-0000-0000-0000-00000000000a", B = "00000000-0000-0000-0000-00000000000b";
await db.exec(`insert into auth.users values ('${A}'), ('${B}')`);

// As a signed-in user: role authenticated with that user's id in the JWT claim.
async function as(user, fn) {
  await db.exec(`set role authenticated; select set_config('request.jwt.claim.sub', '${user}', false)`);
  try { return await fn(); } finally { await db.exec("reset role; select set_config('request.jwt.claim.sub', '', false)"); }
}
async function fails(fn, re) {
  try { await fn(); } catch (e) { if (re) assert.match(e.message, re); return; }
  assert.fail("expected an error");
}
let passed = 0;
async function test(name, fn) { await fn(); passed++; console.log("ok -", name); }

// shared data, written by the service (the superuser here, as the worker's service key)
await db.exec(`
  insert into games (game_id, league, commence_time) values ('nfl:2026_04_PIT_CLE', 'nfl', now());
  insert into paper_picks (pick_id, tier, created_at, price, point, label) values ('p1', 'pick', now(), 120, 0.5, 'Under 0.5'), ('p1', 'lean', now(), 125, 0.5, 'Under 0.5');
`);

await test("each user sees and writes only their own bets", async () => {
  await as(A, () => db.query(`insert into bets (kind, pick_id, price) values ('pick', 'p1', 120)`));
  await as(B, () => db.query(`insert into bets (kind, sgp_id, price) values ('parlay', 's9', 900)`));
  const a = await as(A, () => db.query("select pick_id, sgp_id from bets"));
  const b = await as(B, () => db.query("select pick_id, sgp_id from bets"));
  assert.deepEqual(a.rows, [{ pick_id: "p1", sgp_id: null }]);
  assert.deepEqual(b.rows, [{ pick_id: null, sgp_id: "s9" }]);
});

await test("a user can't write a row for someone else", async () => {
  await fails(() => as(A, () => db.query(`insert into bets (user_id, kind, pick_id) values ('${B}', 'pick', 'p1')`)), /row-level security/);
  const changed = await as(A, () => db.query(`update bets set price = 1 where user_id = '${B}'`));
  assert.equal(changed.affectedRows ?? 0, 0);
  const del = await as(B, () => db.query(`delete from bets where pick_id = 'p1'`));
  assert.equal(del.affectedRows ?? 0, 0);
});

await test("every personal table is fenced the same way", async () => {
  for (const [table, row] of [["quotes", "(sgp_id, price) values ('s1', 250)"],
                              ["custom_parlays", "(sgp_id, legs) values ('custom-1', '[]')"],
                              ["user_settings", "(bankroll) values (100)"],
                              ["todos", "(owner, title) values ('you', 'Sign up')"]]) {
    await as(A, () => db.query(`insert into ${table} ${row}`));
    const seenByB = await as(B, () => db.query(`select count(*)::int as n from ${table}`));
    assert.equal(seenByB.rows[0].n, 0, `${table} leaked to another user`);
  }
});

await test("my_bets shows each user only their own record", async () => {
  const a = await as(A, () => db.query("select pick_id, label from my_bets"));
  assert.equal(a.rows.length, 1);
  const b = await as(B, () => db.query("select sgp_id from my_bets"));
  assert.deepEqual(b.rows, [{ sgp_id: "s9" }]);
});

await test("signed-in users read shared tables but can't write them", async () => {
  const g = await as(A, () => db.query("select game_id from games"));
  assert.equal(g.rows.length, 1);
  await fails(() => as(A, () => db.query(`insert into games (game_id, league) values ('nfl:x', 'nfl')`)), /permission denied/);
  await fails(() => as(A, () => db.query(`update offers set active = false`)), /permission denied/);
  await fails(() => as(A, () => db.query(`delete from paper_picks`)), /permission denied/);
});

await test("signed-out visitors can't read any table", async () => {
  await db.exec("set role anon");
  try {
    for (const t of ["games", "bets", "paper_picks", "todos"]) {
      await fails(() => db.query(`select count(*)::int as n from ${t}`), /permission denied/);
    }
  } finally { await db.exec("reset role"); }
});

await test("job requests: queue your own, never mark them done", async () => {
  await as(A, () => db.query(`insert into job_requests (job) values ('refresh_free')`));
  await as(A, () => db.query(`insert into job_requests (job) values ('test_alert')`));   // Settings > Pick alerts
  await fails(() => as(A, () => db.query(`insert into job_requests (job) values ('drop_everything')`)), /check constraint/);
  await fails(() => as(A, () => db.query(`insert into job_requests (job, status) values ('reprice', 'done')`)), /row-level security/);
  await fails(() => as(A, () => db.query(`update job_requests set status = 'done'`)), /permission denied/);
});

await test("reprice requests are private and cannot impersonate another user", async () => {
  const inserted = await as(A, () => db.query(`insert into job_requests (job) values ('reprice') returning user_id, status`));
  assert.deepEqual(inserted.rows, [{ user_id: A, status: "queued" }]);
  const other = await as(B, () => db.query(`select id from job_requests where job = 'reprice'`));
  assert.equal(other.rows.length, 0);
  await fails(() => as(A, () => db.query(`insert into job_requests (user_id, job) values ('${B}', 'reprice')`)), /row-level security/);
  await fails(() => as(A, () => db.query(`insert into job_requests (job) values ('shell')`)), /check constraint/);
  await fails(() => as(A, () => db.query(`delete from job_requests`)), /permission denied/);
});

await test("paper picks are history: grading changes, the price never does", async () => {
  await db.query(`update paper_picks set status = 'lost', clv = -0.05 where pick_id = 'p1'`);
  await fails(() => db.query(`update paper_picks set price = 150 where pick_id = 'p1'`), /history/);
  await fails(() => db.query(`update paper_picks set point = 1.5 where pick_id = 'p1'`), /history/);
  await fails(() => db.query(`delete from paper_picks where pick_id = 'p1'`), /history/);
});

await test("nobody but the owner can truncate, reference or add triggers", async () => {
  const r = await db.query(`
    select count(*)::int as n from information_schema.role_table_grants
    where table_schema = 'public' and grantee in ('anon', 'authenticated')
      and privilege_type in ('TRUNCATE', 'REFERENCES', 'TRIGGER')`);
  assert.equal(r.rows[0].n, 0);
  const anon = await db.query(`select count(*)::int as n from information_schema.role_table_grants
                               where table_schema = 'public' and grantee = 'anon'`);
  assert.equal(anon.rows[0].n, 0);
});

await test("my_bets: a saved parlay's result reaches only its owner, and generated tickets grade from the shared table", async () => {
  await as(A, () => db.query(`insert into custom_parlays (sgp_id, legs) values ('custom-x', '["a"]')`));
  await as(A, () => db.query(`insert into bets (kind, sgp_id, price) values ('custom', 'custom-x', 400)`));
  await db.exec(`update custom_parlays set status = 'won', profit_1u = 4 where sgp_id = 'custom-x';
                 insert into fun_tickets (sgp_id, kind, sport, body, status, profit_1u, active)
                 values ('s9', 'sgp', 'nfl', '{}', 'lost', -1, false);`);
  const a = await as(A, () => db.query(`select sgp_id, ticket_status, profit_1u from my_bets where sgp_id is not null`));
  assert.deepEqual(a.rows, [{ sgp_id: "custom-x", ticket_status: "won", profit_1u: "4" }]);
  const b = await as(B, () => db.query(`select sgp_id, ticket_status from my_bets where sgp_id is not null`));
  assert.deepEqual(b.rows, [{ sgp_id: "s9", ticket_status: "lost" }]);
  const peek = await as(B, () => db.query(`select count(*)::int as n from custom_parlays`));
  assert.equal(peek.rows[0].n, 0);
});

await test("personal CLV exposes original prices and closing pushes without leaking bets", async () => {
  await db.exec(`
    insert into paper_picks (pick_id, tier, created_at, price, point, league, market, kind, status, clv, close_push)
    values ('clv-new', 'pick', now(), 120, -3, 'nfl', 'spreads', 'game', 'won', 0.09, 0.1),
           ('clv-old', 'pick', now(), 120, -3, 'nfl', 'spreads', 'game', 'won', 0.09, null),
           ('clv-half', 'lean', now(), 120, -3.5, 'nfl', 'spreads', 'game', 'won', 0.1, null),
           ('clv-prop', 'pick', now(), 120, 3, 'nfl', 'player_receptions', 'prop', 'won', 0.3, null);
  `);
  await as(A, () => db.exec(`
    insert into bets (kind, pick_id, price) values ('pick', 'clv-new', 150), ('pick', 'clv-old', 150),
      ('lean', 'clv-half', -125), ('pick', 'clv-prop', 150);
  `));
  const a = await as(A, () => db.query(`select pick_id, price, logged_price, close_push from my_bets
                                      where pick_id like 'clv-%' order by pick_id`));
  assert.deepEqual(a.rows, [
    { pick_id: "clv-half", price: "-125", logged_price: "120", close_push: "0" },
    { pick_id: "clv-new", price: "150", logged_price: "120", close_push: "0.1" },
    { pick_id: "clv-old", price: "150", logged_price: "120", close_push: null },
    { pick_id: "clv-prop", price: "150", logged_price: "120", close_push: "0" },
  ]);
  const b = await as(B, () => db.query(`select pick_id from my_bets where pick_id like 'clv-%'`));
  assert.equal(b.rows.length, 0);
  await fails(() => db.query(`update paper_picks set close_push = 1.1 where pick_id = 'clv-new'`), /check constraint/);
  await fails(() => as(A, () => db.query(`update paper_picks set close_push = 0 where pick_id = 'clv-new'`)), /permission denied/);
});

await test("push subscriptions are personal; the alert log is the worker's alone", async () => {
  await as(A, () => db.query(`insert into push_subscriptions (endpoint, p256dh, auth) values ('https://push.example/a', 'k', 's')`));
  assert.equal((await as(B, () => db.query("select * from push_subscriptions"))).rows.length, 0);
  await fails(() => as(B, () => db.query(`insert into push_subscriptions (user_id, endpoint, p256dh, auth) values ('${A}', 'https://push.example/b', 'k', 's')`)), /row-level security/);
  await fails(() => as(A, () => db.query(`insert into push_subscriptions (endpoint, p256dh, auth) values ('http://insecure', 'k', 's')`)), /check/);
  await fails(() => as(A, () => db.query("select * from alerts_sent")), /permission denied/);
  await fails(() => as(A, () => db.query("select * from alerts_held")), /permission denied/);
  const gone = await as(A, () => db.query("delete from push_subscriptions"));
  assert.equal(gone.affectedRows, 1);
});

await test("an iPhone (APNs) device saves without Web Push keys; a browser still needs them", async () => {
  const tok = "ab".repeat(32);
  await as(A, () => db.query(`insert into push_subscriptions (endpoint, device) values ('apns:sandbox:${tok}', 'iPhone app')`));
  assert.equal((await as(A, () => db.query("select * from push_subscriptions"))).rows.length, 1);
  await fails(() => as(A, () => db.query(`insert into push_subscriptions (endpoint) values ('https://push.example/nokeys')`)), /check/);
  await fails(() => as(A, () => db.query(`insert into push_subscriptions (endpoint) values ('apns:staging:${tok}')`)), /check/);
  await fails(() => as(A, () => db.query(`insert into push_subscriptions (endpoint) values ('apns:production:not-hex')`)), /check/);
  await as(A, () => db.query("delete from push_subscriptions"));
});

await test("bonus bets: the flag defaults to cash, can be set by the owner and reaches my_bets", async () => {
  await as(A, () => db.query(`insert into bets (kind, sgp_id, price, stake) values ('custom', 'custom-bonus', 329, 1.94)`));
  await as(A, () => db.query(`update bets set bonus = true where sgp_id = 'custom-bonus'`));
  const a = await as(A, () => db.query(`select sgp_id, bonus, stake from my_bets where sgp_id = 'custom-bonus'`));
  assert.deepEqual(a.rows, [{ sgp_id: "custom-bonus", bonus: true, stake: "1.94" }]);
  const cash = await as(A, () => db.query(`select bonus from my_bets where pick_id = 'clv-new'`));
  assert.ok(cash.rows.every((r) => r.bonus === false));
  const b = await as(B, () => db.query(`select count(*)::int as n from my_bets where sgp_id = 'custom-bonus'`));
  assert.equal(b.rows[0].n, 0);
});

await test("ladders: owner only, a step must be the owner's own ladder, and my_bets carries ladder_id", async () => {
  const [{ ladder_id: la }] = (await as(A, () => db.query(`insert into ladders (start_units, target_units) values (1, 100) returning ladder_id`))).rows;
  const [{ ladder_id: lb }] = (await as(B, () => db.query(`insert into ladders (start_units, target_units) values (1, 10) returning ladder_id`))).rows;
  assert.equal((await as(A, () => db.query("select * from ladders"))).rows.length, 1);
  await as(A, () => db.query(`insert into bets (kind, sgp_id, price, stake, ladder_id) values ('custom', 'custom-ladder1', 110, 1, '${la}')`));
  const mine = await as(A, () => db.query(`select ladder_id from my_bets where sgp_id = 'custom-ladder1'`));
  assert.equal(mine.rows[0].ladder_id, la);
  // A can't hang a bet on B's ladder, and can't see or stop it
  await fails(() => as(A, () => db.query(`insert into bets (kind, sgp_id, ladder_id) values ('custom', 'custom-ladder2', '${lb}')`)), /foreign key|violates/);
  const stop = await as(A, () => db.query(`update ladders set status = 'stopped' where ladder_id = '${lb}'`));
  assert.equal(stop.affectedRows ?? 0, 0);
  await fails(() => as(A, () => db.query(`insert into ladders (start_units, target_units) values (5, 2)`)), /check/);
  // deleting a ladder keeps its bets, unhooked
  await as(A, () => db.query(`delete from ladders where ladder_id = '${la}'`));
  const kept = await as(A, () => db.query(`select ladder_id from bets where sgp_id = 'custom-ladder1'`));
  assert.deepEqual(kept.rows, [{ ladder_id: null }]);
  await as(A, () => db.query(`delete from bets where sgp_id = 'custom-ladder1'`));
});

await test("a ladder holds its chosen game, turned-down offers and the worker's locked step (0021)", async () => {
  const [{ ladder_id: la, skipped }] = (await as(A, () => db.query(`insert into ladders (start_units, target_units) values (1, 100) returning ladder_id, skipped`))).rows;
  assert.deepEqual(skipped, []);
  await as(A, () => db.query(`update ladders set game_id = 'nfl:2026_07_DAL_PHI', skipped = '["o1"]'::jsonb where ladder_id = '${la}'`));
  // the worker (the service role) locks the step; the owner reads it and clears it when placing
  await db.query(`update ladders set locked = '{"offer_id":"o2","stake":1}'::jsonb, locked_at = now() where ladder_id = '${la}'`);
  const r = await as(A, () => db.query(`select game_id, skipped, locked->>'offer_id' as o from ladders where ladder_id = '${la}'`));
  assert.deepEqual(r.rows, [{ game_id: "nfl:2026_07_DAL_PHI", skipped: ["o1"], o: "o2" }]);
  await as(A, () => db.query(`update ladders set locked = null, notice = null where ladder_id = '${la}'`));
  assert.equal((await as(B, () => db.query(`select count(*)::int as n from ladders where ladder_id = '${la}'`))).rows[0].n, 0);
  await as(A, () => db.query(`delete from ladders where ladder_id = '${la}'`));
});

await test("a ladder has one book, FanDuel unless chosen (0022)", async () => {
  const [{ ladder_id: la, book }] = (await as(A, () => db.query(`insert into ladders (start_units, target_units) values (1, 10) returning ladder_id, book`))).rows;
  assert.equal(book, "FanDuel");
  await fails(() => as(A, () => db.query(`update ladders set book = 'Bovada' where ladder_id = '${la}'`)), /check/);
  await as(A, () => db.query(`update ladders set book = 'DraftKings' where ladder_id = '${la}'`));
  await as(A, () => db.query(`delete from ladders where ladder_id = '${la}'`));
});

await test("friends: a request, accepted only by the one invited; friends see each other's shared bets (0024)", async () => {
  const C = "00000000-0000-0000-0000-00000000000c";
  await db.exec(`insert into auth.users values ('${C}', 'c@example.com'); update auth.users set email = 'b@example.com' where id = '${B}'`);
  await as(A, () => db.query(`insert into profiles (name, handle) values ('Mike', 'mike')`));
  await as(B, () => db.query(`insert into profiles (name, handle) values ('Sam', 'sam')`));
  await as(C, () => db.query(`insert into profiles (name, handle) values ('Cal', 'cal')`));
  await fails(() => as(A, () => db.query(`insert into profiles (user_id, name, handle) values ('${C}', 'X', 'xx_x')`)), /row-level security/);
  await fails(() => as(B, () => db.query(`update profiles set handle = 'Bad Handle' where user_id = '${B}'`)), /check/);
  // strangers: no profile, no browsing; found only by exact handle or email
  assert.equal((await as(A, () => db.query("select count(*)::int as n from profiles"))).rows[0].n, 1);
  assert.deepEqual((await as(A, () => db.query("select handle from find_person('@Sam')"))).rows, [{ handle: "sam" }]);
  assert.deepEqual((await as(A, () => db.query("select handle from find_person('B@example.com')"))).rows, [{ handle: "sam" }]);
  assert.equal((await as(A, () => db.query("select * from find_person('gian')"))).rows.length, 0);
  assert.equal((await as(A, () => db.query("select * from find_person('mike')"))).rows.length, 0);          // never yourself
  // A asks B; A can't accept it, B can; a second request for the pair is refused
  await as(A, () => db.query(`insert into friendships (addressee) values ('${B}')`));
  await fails(() => as(A, () => db.query(`insert into friendships (addressee, status) values ('${C}', 'accepted')`)), /row-level security/);
  await fails(() => as(B, () => db.query(`insert into friendships (addressee) values ('${A}')`)), /duplicate key/);
  await fails(() => as(B, () => db.query(`update friendships set status = 'accepted'`)), /permission denied/);
  assert.equal((await as(A, () => db.query(`select accept_friend('${B}') as ok`))).rows[0].ok, null);
  assert.equal((await as(B, () => db.query("select count(*)::int as n from profiles"))).rows[0].n, 2);       // a request shows the name
  assert.equal((await as(A, () => db.query("select count(*)::int as n from friend_bets()"))).rows[0].n, 0);  // pending: no bets
  assert.equal((await as(B, () => db.query(`select accept_friend('${A}') as ok`))).rows[0].ok, true);
  // friends see each other's bets through my_bets; C sees neither; the bets table itself stays fenced
  await as(B, () => db.query(`insert into bets (kind, sgp_id, price, stake) values ('custom', 'custom-b1', 450, 1)`));
  const seen = await as(A, () => db.query("select user_id, sgp_id from friend_bets()"));
  assert.ok(seen.rows.some((r) => r.sgp_id === "custom-b1"));
  assert.ok(seen.rows.every((r) => r.user_id === B));
  assert.equal((await as(A, () => db.query(`select count(*)::int as n from friend_bets('${C}')`))).rows[0].n, 0);
  assert.equal((await as(C, () => db.query("select count(*)::int as n from friend_bets()"))).rows[0].n, 0);
  assert.equal((await as(A, () => db.query("select count(*)::int as n from bets where user_id <> auth.uid()"))).rows[0].n, 0);
  // sharing off hides them; either side can end the friendship
  await as(B, () => db.query("insert into user_settings (share_bets) values (false) on conflict (user_id) do update set share_bets = false"));
  assert.equal((await as(A, () => db.query("select count(*)::int as n from friend_bets()"))).rows[0].n, 0);
  await as(B, () => db.query("update user_settings set share_bets = true"));
  assert.ok((await as(A, () => db.query("select count(*)::int as n from friend_bets()"))).rows[0].n > 0);
  await as(B, () => db.query("delete from friendships"));
  assert.equal((await as(A, () => db.query("select count(*)::int as n from friend_bets()"))).rows[0].n, 0);
  await as(B, () => db.query("delete from bets where sgp_id = 'custom-b1'"));
});

await test("Live Activity tokens are personal, a start token has no bet, and the worker's state is its own (0025)", async () => {
  const tok = "cd".repeat(32);
  await as(A, () => db.query(`insert into live_activity_tokens (token, env, kind, device) values ('${tok}', 'production', 'start', 'd1')`));
  await as(A, () => db.query(`insert into live_activity_tokens (token, env, kind, bet_id) values ('${"ef".repeat(32)}', 'sandbox', 'update', 'bet-1')`));
  assert.equal((await as(B, () => db.query("select * from live_activity_tokens"))).rows.length, 0);
  await fails(() => as(B, () => db.query(`insert into live_activity_tokens (user_id, token, env, kind) values ('${A}', '${"aa".repeat(32)}', 'sandbox', 'start')`)), /row-level security/);
  await fails(() => as(A, () => db.query(`insert into live_activity_tokens (token, env, kind, bet_id) values ('${"bb".repeat(32)}', 'sandbox', 'start', 'bet-1')`)), /check/);
  await fails(() => as(A, () => db.query(`insert into live_activity_tokens (token, env, kind) values ('${"bb".repeat(32)}', 'sandbox', 'update')`)), /check/);
  await fails(() => as(A, () => db.query(`insert into live_activity_tokens (token, env, kind) values ('nothex', 'sandbox', 'start')`)), /check/);
  await fails(() => as(A, () => db.query("select * from live_activity_state")), /permission denied/);
  const gone = await as(A, () => db.query("delete from live_activity_tokens where device = 'd1' and kind = 'start'"));
  assert.equal(gone.affectedRows, 1);
  await as(A, () => db.query("delete from live_activity_tokens"));
});

await test("live CLV is readable by the bet's owner only, and only the worker writes it (0028)", async () => {
  const [{ bet_id }] = (await as(A, () => db.query(`insert into bets (kind, pick_id, price) values ('pick', 'pclv', 110) returning bet_id`))).rows;
  await db.exec(`insert into bet_clv (bet_id, user_id, p_now, clv) values ('${bet_id}', '${A}', 0.5, 0.05)`);
  assert.equal((await as(A, () => db.query("select count(*)::int as n from bet_clv"))).rows[0].n, 1);
  assert.equal((await as(B, () => db.query("select count(*)::int as n from bet_clv"))).rows[0].n, 0);
  await fails(() => as(A, () => db.query(`update bet_clv set clv = 0.5`)), /permission denied/);
});

await test("a Novig challenge is its owner's, once a day per wording (0027)", async () => {
  const text = "Place a straight trade on CFB (Min. $5)";
  await as(A, () => db.query(`insert into challenges (day, text) values ('2026-10-28', '${text}')`));
  await fails(() => as(A, () => db.query(`insert into challenges (day, text) values ('2026-10-28', '${text}')`)), /unique|duplicate/);
  assert.equal((await as(B, () => db.query("select count(*)::int as n from challenges"))).rows[0].n, 0);
  await fails(() => as(A, () => db.query("update challenges set status = 'won'")), /check/);
  await as(A, () => db.query("update challenges set status = 'done'"));
});

await test("the CFB pick'em entry is its owner's, one row per game a week, and its job can be queued (0044)", async () => {
  await as(A, () => db.query("insert into pickem (week, n, away, home, home_line, pick) values ('2026-11-07', 1, 'Iowa', 'Northwestern', -2.5, 'home')"));
  await fails(() => as(A, () => db.query("insert into pickem (week, n, away, home, home_line) values ('2026-11-07', 1, 'Iowa', 'Northwestern', -2.5)")), /unique|duplicate/);
  await fails(() => as(A, () => db.query("update pickem set pick = 'over'")), /check/);
  await fails(() => as(A, () => db.query("update pickem set result = 'won'")), /check/);
  await as(A, () => db.query("update pickem set result = 'away', ours = 'away'"));
  assert.equal((await as(B, () => db.query("select count(*)::int as n from pickem"))).rows[0].n, 0);
  await as(A, () => db.query("insert into pickem_weeks (week, partner_best, reward) values ('2026-11-07', 6, '25% boost')"));
  assert.equal((await as(B, () => db.query("select count(*)::int as n from pickem_weeks"))).rows[0].n, 0);
  await as(A, () => db.query("insert into job_requests (job, status) values ('pickem', 'queued')"));
});

await test("promos: owner only, a bet takes a token and gives it back, and my_bets and friends carry the new columns (0029)", async () => {
  const [{ promo_id: pa }] = (await as(A, () => db.query(`insert into promos (kind, book, amount_dollars, expires_at) values ('bonus', 'FanDuel', 50, now() + interval '2 days') returning promo_id`))).rows;
  const [{ promo_id: pb }] = (await as(B, () => db.query(`insert into promos (kind, pct, max_extra_dollars) values ('boost', 30, 25) returning promo_id`))).rows;
  assert.equal((await as(A, () => db.query("select count(*)::int as n from promos"))).rows[0].n, 1);
  await fails(() => as(A, () => db.query(`insert into promos (kind) values ('boost')`)), /check/);        // a boost needs its size
  await fails(() => as(A, () => db.query(`insert into bets (kind, sgp_id, promo_id) values ('custom', 'custom-promo2', '${pb}')`)), /foreign key|violates/);
  await as(A, () => db.query(`insert into bets (kind, sgp_id, price, stake, bonus, boost_cap, promo_id, promo_ev, lock_id)
                              values ('custom', 'custom-promo1', 150, 10, true, null, '${pa}', 3.1, gen_random_uuid())`));
  assert.equal((await as(A, () => db.query(`select status from promos where promo_id = '${pa}'`))).rows[0].status, "used");
  const mine = await as(A, () => db.query(`select promo_id, promo_ev, boost_cap from my_bets where sgp_id = 'custom-promo1'`));
  assert.equal(mine.rows[0].promo_id, pa);
  await fails(() => as(A, () => db.query(`update bets set boost_cap = -1 where sgp_id = 'custom-promo1'`)), /check/);
  await as(A, () => db.query(`delete from bets where sgp_id = 'custom-promo1'`));
  assert.equal((await as(A, () => db.query(`select status from promos where promo_id = '${pa}'`))).rows[0].status, "open");
  await fails(() => as(A, () => db.query(`update user_settings set unit_dollars = 0`)), /check/);
  await as(A, () => db.query(`delete from promos where promo_id = '${pa}'`));
});

await test("a bet reset: a lost bet's stake comes back once as a bonus bet, and a changed grade takes it back (0031)", async () => {
  await as(A, () => db.query(`update user_settings set unit_dollars = 5`));
  await as(A, () => db.query(`insert into user_settings (unit_dollars) select 5 where not exists (select 1 from user_settings)`));
  await as(A, () => db.query(`insert into custom_parlays (sgp_id, legs, games, status) values ('custom-reset1', '[]', '[]', 'open')`));
  await as(A, () => db.query(`insert into bets (kind, sgp_id, mode, price, stake, book, reset) values ('custom', 'custom-reset1', 'real', 127, 20, 'FanDuel', true)`));
  const tokens = async () => (await as(A, () => db.query(`select amount_dollars::float as d, kind, book, status from promos where from_bet is not null`))).rows;
  const grade = (s) => db.query(`update custom_parlays set status = '${s}' where sgp_id = 'custom-reset1'`);
  assert.equal((await db.query("select issue_resets() as n")).rows[0].n, 0);                 // still open: nothing
  await grade("lost");
  assert.equal((await db.query("select issue_resets() as n")).rows[0].n, 1);
  assert.equal((await db.query("select issue_resets() as n")).rows[0].n, 0);                 // once
  assert.deepEqual(await tokens(), [{ d: 100, kind: "bonus", book: "FanDuel", status: "open" }]);
  await fails(() => as(A, () => db.query("select issue_resets()")), /permission/);           // the worker's alone
  await grade("won");
  await db.query("select issue_resets()");
  assert.deepEqual(await tokens(), []);                                                      // the grade changed
  await grade("lost");
  await db.query("select issue_resets()");
  assert.equal((await tokens()).length, 1);
  await as(A, () => db.query(`delete from bets where sgp_id = 'custom-reset1'`));            // undo the bet: no token
  assert.deepEqual(await tokens(), []);
});

await test("live updates: a change pulses its owner and friends, and each sees only theirs and the card's (0033)", async () => {
  const at = async (key) => (await db.query("select at from app_pulse where key = $1", [key])).rows[0]?.at;
  await db.exec("delete from friendships; delete from app_pulse where key like 'u:%'");
  await as(A, () => db.query(`insert into bets (kind, sgp_id, price) values ('parlay', 'pulse1', 120)`));
  assert.ok(await at(`u:${A}`));
  assert.equal(await at(`u:${B}`), undefined);                                                // not friends yet
  await db.exec(`insert into friendships (requester, addressee, status) values ('${A}', '${B}', 'accepted')`);
  await db.exec(`delete from app_pulse where key = 'u:${B}'`);
  await as(A, () => db.query(`delete from bets where sgp_id = 'pulse1'`));
  assert.ok(await at(`u:${B}`));                                                              // a friend's feed hears it
  const seen = await as(B, () => db.query("select key from app_pulse order by key"));
  assert.deepEqual(seen.rows.map((r) => r.key), ["card", `u:${B}`]);
  await fails(() => as(A, () => db.query("update app_pulse set at = now() where key = 'card'")));
  await fails(() => as(A, () => db.query(`select pulse_user('${B}')`)), /permission/);
  await db.exec("delete from friendships");
});

await test("the bet change log: every change with before, after and who, seen by its owner, and no one can rewrite it (0034)", async () => {
  await as(A, () => db.query(`insert into bets (kind, sgp_id, price, stake) values ('parlay', 'hist1', 120, 1)`));
  await as(A, () => db.query(`update bets set stake = 2 where sgp_id = 'hist1'`));
  await as(A, () => db.query(`update bets set stake = 2 where sgp_id = 'hist1'`));          // nothing changed: no line
  await as(A, () => db.query(`delete from bets where sgp_id = 'hist1'`));
  const rows = (await as(A, () => db.query(`select op, by_user, before->>'stake' b, after->>'stake' a from bet_history
                                            where coalesce(after, before)->>'sgp_id' = 'hist1' order by id`))).rows;
  assert.deepEqual(rows.map((r) => [r.op, r.b, r.a]), [["insert", null, "1"], ["update", "1", "2"], ["delete", "2", null]]);
  assert.equal(rows[0].by_user, A);
  const other = await as(B, () => db.query(`select 1 from bet_history where coalesce(after, before)->>'sgp_id' = 'hist1'`));
  assert.equal(other.rows.length, 0);
  await fails(() => as(A, () => db.query("delete from bet_history")));
  await fails(() => as(A, () => db.query("update bet_history set op = 'insert'")));
  await fails(() => as(A, () => db.query(`insert into bet_history (bet_id, user_id, op) values (gen_random_uuid(), '${A}', 'insert')`)));
});

await test("the calendar: shared and read-only, counted by Eastern day (0035)", async () => {
  await db.exec(`insert into schedule_games (id, league, sport, start, matchup) values
    ('nhl:1', 'nhl', 'nhl', '2026-11-05T03:30:00Z', 'A @ B'), ('epl:2', 'epl', 'soccer', '2026-11-05T15:00:00Z', 'C @ D')`);
  const days = await as(B, () => db.query("select day, sport, games from calendar_days order by day"));
  assert.deepEqual(days.rows, [{ day: "2026-11-04", sport: "nhl", games: 1 }, { day: "2026-11-05", sport: "soccer", games: 1 }]);
  await fails(() => as(A, () => db.query("delete from schedule_games")));
  await fails(() => as(A, () => db.query("insert into schedule_games (id, league, sport, start, matchup) values ('x', 'x', 'x', now(), 'x')")));
});

await test("search: games, fights and players for the signed-in, and a % is only a character (0036)", async () => {
  await db.exec(`insert into schedule_games (id, league, sport, start, matchup) values ('nhl:s1', 'nhl', 'nhl', now() + interval '1 day', 'Search Blues @ Search Rangers');
    insert into games (game_id, league, commence_time, matchup) values ('ufc:s2', 'ufc', now() + interval '1 day', 'Search Fighter vs Other');
    insert into leg_packs (pack_key, sport, commence_time, body) values ('s3', 'nba', now() + interval '1 day',
      '{"legs": [{"player": "Search Player", "label": "Search Player 3+ threes"}, {"player": "", "label": "Search to win"}, {"player": "game side", "label": "x"}]}')`);
  const hits = async (q) => (await as(A, () => db.query("select kind, title from search_app($1) order by kind, title", [q]))).rows.map((r) => `${r.kind}:${r.title}`);
  assert.deepEqual(await hits("search"), ["game:Search Blues @ Search Rangers", "game:Search Fighter vs Other", "player:Search Player"]);
  assert.deepEqual(await hits("RANGERS"), ["game:Search Blues @ Search Rangers"]);
  assert.deepEqual(await hits("%"), []);
  assert.deepEqual(await hits("s"), []);                                                     // too short
  await db.exec("reset role");
});

await test("signed-in devices: your own only, ending another's does nothing, and you can't end the one you're on (0037)", async () => {
  const ids = ["1", "2", "3"].map((n) => `00000000-0000-0000-0000-00000000000${n}`), other = "00000000-0000-0000-0000-000000000009";
  await db.exec(`delete from auth.sessions;
    insert into auth.sessions (id, user_id, user_agent, ip) values ('${ids[0]}', '${A}', 'phone', '1.2.3.4'), ('${ids[1]}', '${A}', 'pc', '1.2.3.5'), ('${ids[2]}', '${A}', 'old', '1.2.3.6'), ('${other}', '${B}', 'theirs', '1.2.3.7');
    insert into auth.sessions (id, user_id, not_after) values ('00000000-0000-0000-0000-000000000004', '${A}', now() - interval '1 day')`);
  const onPhone = async (fn) => { await db.exec(`select set_config('request.jwt.claim.session_id', '${ids[0]}', false)`); try { return await as(A, fn); } finally { await db.exec("select set_config('request.jwt.claim.session_id', '', false)"); } };
  const mine = (await onPhone(() => db.query("select user_agent, current, ip from my_sessions() order by user_agent"))).rows;
  assert.deepEqual(mine.map((r) => [r.user_agent, r.current]), [["old", false], ["pc", false], ["phone", true]]);       // no expired, no B's
  assert.equal(mine[0].ip, "1.2.3.6");
  const ended = async (id) => (await onPhone(() => db.query("select end_sessions($1::uuid) n", [id]))).rows[0].n;
  assert.equal(await ended(other), 0);                                                       // someone else's
  assert.equal(await ended(ids[0]), 0);                                                      // the one you're on
  assert.equal(await ended(ids[2]), 1);
  assert.equal((await onPhone(() => db.query("select end_sessions() n"))).rows[0].n, 2);      // pc and the expired one
  assert.deepEqual((await db.query("select user_agent from auth.sessions order by user_agent")).rows.map((r) => r.user_agent), ["phone", "theirs"]);
  await fails(() => as(A, () => db.query("select * from auth.sessions")));
  await fails(() => as(A, () => db.query("select end_sessions()")), /sign in first/);        // no session in the token
});

await test("reactions: a friend's shared bet only, one per person, names only between friends (0042)", async () => {
  const C = "00000000-0000-0000-0000-00000000000c";
  await as(A, () => db.query(`insert into friendships (addressee) values ('${B}')`));
  await as(B, () => db.query(`select accept_friend('${A}')`));
  await as(C, () => db.query(`insert into friendships (addressee) values ('${B}')`));
  await as(B, () => db.query(`select accept_friend('${C}')`));
  const [{ bet_id: bet }] = (await as(B, () => db.query(`insert into bets (kind, sgp_id, price, stake) values ('custom', 'custom-r1', 300, 1) returning bet_id`))).rows;
  const [{ bet_id: own }] = (await as(A, () => db.query(`insert into bets (kind, sgp_id, price, stake) values ('custom', 'custom-r2', 200, 1) returning bet_id`))).rows;
  await as(A, () => db.query(`insert into bet_reactions (bet_id, reaction) values ('${bet}', 'fire')`));
  await fails(() => as(A, () => db.query(`insert into bet_reactions (bet_id, reaction) values ('${own}', 'fire')`)), /row-level security/);   // your own
  await fails(() => as(A, () => db.query(`insert into bet_reactions (bet_id, user_id, reaction) values ('${bet}', '${C}', 'goat')`)), /row-level security/);
  await fails(() => as(C, () => db.query(`insert into bet_reactions (bet_id, reaction) values ('${bet}', 'clap')`)), /check/);
  await fails(() => as(A, () => db.query(`insert into bet_reactions (bet_id, reaction) values ('${bet}', 'goat')`)), /duplicate key/);   // one each
  await as(A, () => db.query(`insert into bet_reactions (bet_id, reaction) values ('${bet}', 'goat') on conflict (bet_id, user_id) do update set reaction = excluded.reaction`));
  await as(C, () => db.query(`insert into bet_reactions (bet_id, reaction) values ('${bet}', 'sweat')`));
  const seen = async (who) => (await as(who, () => db.query(`select name, reaction from bet_reactions_for(array['${bet}']::uuid[]) order by reaction`))).rows;
  assert.deepEqual(await seen(B), [{ name: "Mike", reaction: "goat" }, { name: "Cal", reaction: "sweat" }]);        // the owner sees both
  assert.deepEqual(await seen(A), [{ name: "Mike", reaction: "goat" }, { name: null, reaction: "sweat" }]);         // C isn't A's friend
  assert.equal((await as(A, () => db.query("select count(*)::int as n from bet_reactions"))).rows[0].n, 1);         // the table: your own
  // sharing off or the friendship ended: no reacting, nothing to see
  await as(B, () => db.query("update user_settings set share_bets = false"));
  assert.deepEqual(await seen(A), []);
  await fails(() => as(A, () => db.query(`update bet_reactions set reaction = 'fire' where bet_id = '${bet}'`)), /row-level security/);
  await as(B, () => db.query("update user_settings set share_bets = true"));
  await as(A, () => db.query(`delete from bet_reactions where bet_id = '${bet}'`));
  assert.deepEqual((await seen(B)).map((r) => r.reaction), ["sweat"]);
  assert.ok((await db.query(`select 1 from app_pulse where key = 'u:${B}'`)).rows.length);
  await as(B, () => db.query("delete from bets where sgp_id = 'custom-r1'"));
  assert.equal((await db.query("select count(*)::int as n from bet_reactions")).rows[0].n, 0);                      // gone with the bet
  await as(A, () => db.query("delete from bets where sgp_id = 'custom-r2'"));
  await as(B, () => db.query("delete from friendships"));
});

await test("0046 copies a Build slip's saved games onto a bet without them, once, and touches nothing else", async () => {
  const g = (m) => JSON.stringify([{ matchup: m, game_ref: "nfl:1", legs: ["X ML"] }]);
  await as(A, () => db.query(`insert into custom_parlays (sgp_id, legs, games) values
    ('custom-g1', '[]', '${g("A @ B")}'), ('custom-g2', '[]', '${g("C @ D")}'), ('custom-g3', '[]', '[]'), ('custom-g4', '[]', '${g("E @ F")}')`));
  await as(A, () => db.query(`insert into bets (kind, sgp_id, price, games) values
    ('custom', 'custom-g1', 300, null), ('custom', 'custom-g2', 300, '[]'), ('custom', 'custom-g3', 300, null),
    ('custom', 'custom-g4', 300, '${g("Mine @ Kept")}')`));
  await as(B, () => db.query(`insert into bets (kind, sgp_id, price) values ('custom', 'custom-g1', 300)`));   // B's own, no slip
  const run = () => db.exec(readFileSync(new URL("0046_bet_games_backfill.sql", dir), "utf8"));
  await run();
  await run();                                                                                        // again: no change
  const rows = (await db.query(`select user_id::text, sgp_id, games->0->>'matchup' as m from bets where sgp_id like 'custom-g%' order by sgp_id, user_id`)).rows;
  assert.deepEqual(rows.map((r) => [r.user_id === A ? "A" : "B", r.sgp_id, r.m]),
    [["A", "custom-g1", "A @ B"], ["B", "custom-g1", null], ["A", "custom-g2", "C @ D"], ["A", "custom-g3", null], ["A", "custom-g4", "Mine @ Kept"]]);
  const logged = (await db.query(`select count(*)::int as n from bet_history h join bets b using (bet_id) where h.op = 'update' and b.sgp_id like 'custom-g%'`)).rows[0].n;
  assert.equal(logged, 2);                                                                            // each backfill is in the log, once
  await as(A, () => db.query(`delete from bets where sgp_id like 'custom-g%'`));
  await as(B, () => db.query(`delete from bets where sgp_id like 'custom-g%'`));
  await as(A, () => db.query(`delete from custom_parlays where sgp_id like 'custom-g%'`));
});

console.log(`\n${passed} database tests passed`);
await db.close();
