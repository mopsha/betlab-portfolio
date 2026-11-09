// Local preview with no sign-in: the app reads web/fixtures/today.json (scripts/dump_web_fixture.py).
// Development only; fixtureMode() can never be on in a production build.
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const web = fileURLToPath(new URL("..", import.meta.url));   // runs from anywhere

const port = process.argv[2] || "3001";
const file = process.argv[3] || "fixtures/today.json";       // fixtures/mine.json: with the owner's bets (--mine)
const real = process.argv[4] === "real";                     // try real-money marking before Oct 18
const child = spawn(process.execPath, [web + "node_modules/next/dist/bin/next", "dev", "-p", port], {
  cwd: web,
  stdio: "inherit",
  env: { ...process.env, BETLAB_FIXTURE: file, ...(real ? { NEXT_PUBLIC_BETLAB_PREVIEW_REAL: "1" } : {}) },
});
child.on("exit", (code) => process.exit(code ?? 0));
