"use server";

import { revalidatePath } from "next/cache";
import { supabaseServer } from "./supabase/server";

/** A challenge's status from the app: placed (done), skipped, or back to open (the worker solves it again). */
export async function setChallenge(id: string, status: "done" | "skipped" | "open"): Promise<{ error?: string }> {
  const sb = await supabaseServer();
  const { error } = await sb.from("challenges").update(status === "open" ? { status, pick: null } : { status }).eq("challenge_id", id);
  revalidatePath("/more/challenges");
  return error ? { error: "Couldn't save that. Try again." } : {};
}
