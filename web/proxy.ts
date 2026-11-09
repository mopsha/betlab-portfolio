import { createServerClient } from "@supabase/ssr";
import { SUPABASE_KEY, SUPABASE_URL } from "@/lib/env";
import { NextResponse, type NextRequest } from "next/server";
import { fixtureMode } from "@/lib/mode";

// Every route the iPhone app calls with its bearer token (Nov 9: /api/promos, /api/challenges and /api/pickem were missing, so
// the app's promo, challenge and Pick'em screenshots were sent to /login and every read failed). A new route the app calls goes here.
const BEARER_PATHS = ["/api/chat", "/api/slip", "/api/promos", "/api/challenges", "/api/pickem"];

// Refreshes the Supabase session cookie on every request and sends signed-out visitors to
// /login. The real authorization is row-level security in the database, not this check.
export async function proxy(request: NextRequest) {
  if (fixtureMode()) return NextResponse.next();
  // the iPhone app asks the chat and reads slips with its Supabase access token (it has no web cookie): a valid token goes through, the
  // route then reads as that user (lib/supabase/server.ts)
  const bearer = /^Bearer\s+(\S+)$/i.exec(request.headers.get("authorization") ?? "")?.[1];
  if (bearer && BEARER_PATHS.includes(request.nextUrl.pathname)) {   // /api/slip too (Oct 25: 292d1ca6 listed it, never used it)
    const sb = createServerClient(SUPABASE_URL, SUPABASE_KEY, { cookies: { getAll: () => [], setAll: () => {} } });
    const { data } = await sb.auth.getClaims(bearer);
    return data?.claims ? NextResponse.next() : NextResponse.json({ error: "Sign in again." }, { status: 401 });
  }
  let response = NextResponse.next({ request });
  const supabase = createServerClient(SUPABASE_URL, SUPABASE_KEY, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet) => {
        toSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        toSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });
  const { data } = await supabase.auth.getClaims();
  const path = request.nextUrl.pathname;
  if (!data?.claims && !path.startsWith("/login") && !path.startsWith("/auth") && path !== "/api/health") {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico$|icon\\.svg$|icons/|manifest\\.webmanifest$|sw\\.js$|fd\\.html$).*)"],
};
