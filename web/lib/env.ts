/** The Supabase URL and public (anon / publishable) key. Values pasted with quotes or spaces
 * around them (easy to do in .env.local or the Railway dashboard) are cleaned, so a stray quote
 * never turns into "Invalid API key". */
const clean = (v: string | undefined) => (v ?? "").trim().replace(/^["']|["']$/g, "").trim();

export const SUPABASE_URL = clean(process.env.NEXT_PUBLIC_SUPABASE_URL).replace(/\/$/, "");
export const SUPABASE_KEY = clean(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
