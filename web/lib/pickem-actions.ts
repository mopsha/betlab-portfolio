"use server";

import { revalidatePath } from "next/cache";
import { supabaseServer } from "./supabase/server";

/** Your pick on a pick'em game from the app (after editing it in FanDuel), or none. */
export async function setPickemPick(id: string, pick: "home" | "away" | null): Promise<{ error?: string }> {
  const sb = await supabaseServer();
  const { error } = await sb.from("pickem").update({ pick }).eq("pick_id", id);
  revalidatePath("/more/pickem");
  return error ? { error: "Couldn't save that. Try again." } : {};
}

/** The week's outcome once FanDuel grades it: the partners' best score and what it paid. */
export async function setPickemWeek(week: string, partnerBest: number | null, reward: string | null): Promise<{ error?: string }> {
  const sb = await supabaseServer();
  const { error } = await sb.from("pickem_weeks").upsert({ week, partner_best: partnerBest, reward }, { onConflict: "user_id,week" });
  revalidatePath("/more/pickem");
  return error ? { error: "Couldn't save that. Try again." } : {};
}

/** Take a game off the entry (a misread). */
export async function removePickemRow(id: string): Promise<{ error?: string }> {
  const sb = await supabaseServer();
  const { error } = await sb.from("pickem").delete().eq("pick_id", id);
  revalidatePath("/more/pickem");
  return error ? { error: "Couldn't remove it. Try again." } : {};
}
