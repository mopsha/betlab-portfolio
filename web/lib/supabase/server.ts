import { createServerClient } from "@supabase/ssr";
import { SUPABASE_KEY, SUPABASE_URL } from "@/lib/env";
import { cookies, headers } from "next/headers";

/** The iPhone app's sign-in: "Authorization: Bearer <Supabase access token>" (Oct 24, for /api/chat; proxy.ts checks it). */
export async function bearerToken(): Promise<string | null> {
  const m = /^Bearer\s+(\S+)$/i.exec((await headers()).get("authorization") ?? "");
  return m ? m[1] : null;
}

/** A Supabase client acting as the signed-in user: row-level security decides what it sees. */
export async function supabaseServer() {
  // the app's bearer token, when it sent one: the same user and row-level security as the web's cookie session
  const token = await bearerToken();
  if (token) {
    return createServerClient(SUPABASE_URL, SUPABASE_KEY, {
      cookies: { getAll: () => [], setAll: () => {} },
      global: { headers: { Authorization: `Bearer ${token}` } },
    });
  }
  const store = await cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_KEY, {
    cookies: {
      getAll: () => store.getAll(),
      setAll: (toSet) => {
        try {
          toSet.forEach(({ name, value, options }) => store.set(name, value, options));
        } catch {
          // Called from a Server Component, which can't set cookies; proxy.ts refreshes the session.
        }
      },
    },
  });
}
