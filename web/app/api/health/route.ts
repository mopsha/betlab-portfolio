import { createClient } from "@supabase/supabase-js";
import { SUPABASE_KEY, SUPABASE_URL } from "@/lib/env";

/** Is the app wired to Supabase? A signed-out read of a shared table must be refused with
 * "permission denied" (the key works and row-level security holds), never "invalid key".
 * Returns no data either way. */
export async function GET() {
  const sb = createClient(SUPABASE_URL, SUPABASE_KEY, { auth: { persistSession: false } });
  const { error } = await sb.from("games").select("game_id").limit(1);
  const key = !error ? "open (signed-out read allowed: check grants)" : error.code === "42501" ? "valid" : "invalid";
  return Response.json({ ok: key === "valid", supabase_key: key }, { status: key === "valid" ? 200 : 500 });
}
