import { NextResponse, type NextRequest } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { supabaseServer } from "@/lib/supabase/server";

/** The email link once the Supabase email templates point here ({{ .SiteURL }}/auth/confirm?token_hash=
 *  {{ .TokenHash }}&type=email): verified on the server with no PKCE cookie, so it signs in whichever browser
 *  opens it, unlike /auth/callback's code, which needs the browser that asked (Oct 12). */
export async function GET(request: NextRequest) {
  const tokenHash = request.nextUrl.searchParams.get("token_hash");
  const type = (request.nextUrl.searchParams.get("type") ?? "email") as EmailOtpType;
  if (tokenHash) {
    const { error } = await (await supabaseServer()).auth.verifyOtp({ token_hash: tokenHash, type });
    if (!error) return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.redirect(new URL("/login?e=" + encodeURIComponent("That link expired or was used already. Get a new code by email."), request.url));
}
