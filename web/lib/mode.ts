/**
 * Fixture mode: local development only. The app reads a JSON snapshot of the database
 * (web/fixtures/today.json, written by `python scripts/dump_web_fixture.py`, never committed)
 * instead of Supabase, with no sign-in, so Claude can build and check screens without anyone's
 * password. It can never turn on in a production build.
 */
export function fixtureMode(): boolean {
  return process.env.NODE_ENV !== "production" && !!process.env.BETLAB_FIXTURE;
}
