// The owner's account (Mike): the app user the Python ledgers follow (settings.yaml app.owner_user_id,
// config.owner_user_id). Plan and Reviews are his work with Claude, so other accounts don't see them
// (Oct 10: a second account for his girlfriend).
import "server-only";
import { fixtureMode } from "./mode";
import { supabaseServer } from "./supabase/server";

export const OWNER_USER_ID = "00000000-0000-4000-8000-000000000001";

/** Whether the signed-in user is the owner (the local preview counts as the owner). */
export async function isOwner(): Promise<boolean> {
  if (fixtureMode()) return true;
  const { data } = await (await supabaseServer()).auth.getUser();
  return data.user?.id === OWNER_USER_ID;
}
