import { NextResponse, type NextRequest } from "next/server";
import { supabaseServer } from "@/lib/supabase/server";

/** Where the email sign-in link and Google / Apple sign-in land: trade the one-time code for a session,
 *  then go home. An email that wasn't invited comes back with an error (sign-ups are off). */
export async function GET(request: NextRequest) {
  const desc = request.nextUrl.searchParams.get("error_description");
  if (desc) {
    const msg = /signup|sign.?ups? (are )?(not allowed|disabled)/i.test(desc)
      ? "That Google account isn't invited to BetLab. Try again and pick the account with your invited email, or get a code by email." : "Sign-in didn't finish. Try again.";
    return NextResponse.redirect(new URL("/login?e=" + encodeURIComponent(msg), request.url));
  }
  const code = request.nextUrl.searchParams.get("code");
  if (code) {
    const sb = await supabaseServer();
    const { error } = await sb.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.redirect(new URL("/login?e=" + encodeURIComponent("That link didn't finish signing in (it was used already, or opened in a different browser than the one you asked from). Get a code by email and type it in instead."), request.url));
}
