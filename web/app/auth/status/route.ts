import { supabaseServer } from "@/lib/supabase/server";

/** Is this browser signed in? The login screen asks when it comes back into view: in the iPhone home-screen app,
 *  Google sign-in runs in a sheet over the app and finishes there (the session cookie is saved), but closing the
 *  sheet leaves the app on the old login screen (Oct 12: the callback succeeded, the app never loaded "/"). */
export async function GET() {
  const { data } = await (await supabaseServer()).auth.getClaims();
  return Response.json({ signedIn: !!data?.claims }, { headers: { "Cache-Control": "no-store" } });
}
