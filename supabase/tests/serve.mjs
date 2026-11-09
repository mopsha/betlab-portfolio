// A throwaway Postgres with the BetLab schema, for testing `betlab publish` and
// `sync-personal` locally: node serve.mjs [port], then connect to
// postgresql://postgres@127.0.0.1:<port>/postgres (one connection at a time).
import { PGlite } from "@electric-sql/pglite";
import { PGLiteSocketServer } from "@electric-sql/pglite-socket";
import { readFileSync, readdirSync } from "node:fs";

const here = new URL(".", import.meta.url);
const db = new PGlite();
await db.exec(readFileSync(new URL("auth_stub.sql", here), "utf8"));
const dir = new URL("../migrations/", here);
for (const f of readdirSync(dir).filter((f) => f.endsWith(".sql")).sort()) {
  await db.exec(readFileSync(new URL(f, dir), "utf8"));
}
const port = Number(process.argv[2] || 54329);
const server = new PGLiteSocketServer({ db, port, host: "127.0.0.1" });
await server.start();
console.log(`BetLab test database on postgresql://postgres@127.0.0.1:${port}/postgres`);
