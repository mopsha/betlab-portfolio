import { redirect } from "next/navigation";
import { cookies, headers } from "next/headers";
import { fixtureMode } from "@/lib/mode";
import { supabaseServer } from "@/lib/supabase/server";
import SignedInWatch from "@/components/app/SignedInWatch";

// The email waiting for its code, kept in a short-lived cookie (never in the URL).
// Codes need Supabase's email template to include {{ .Token }}, which needs a custom SMTP sender; until then
// the email has only a link, so the screen says so (NEXT_PUBLIC_BETLAB_EMAIL_CODE=1 once the template has it).
const CODES = process.env.NEXT_PUBLIC_BETLAB_EMAIL_CODE === "1";
const CODE_EMAIL = "betlab_code_email";

async function signIn(form: FormData) {
  "use server";
  const email = String(form.get("email") ?? "").trim();
  const password = String(form.get("password") ?? "");
  const sb = await supabaseServer();
  if (!password) {
    // Email code (and link): only existing accounts (sign-ups are off). The code is typed back here, so it works in
    // the home-screen app, where a tapped email link opens in another browser (Oct 12: links "expired" that way).
    const origin = (await headers()).get("origin") ?? "";
    const { error } = await sb.auth.signInWithOtp({ email, options: { shouldCreateUser: false, emailRedirectTo: `${origin}/auth/callback` } });
    if (error) redirect(`/login?e=${encodeURIComponent("Couldn't send the email. Check the address (it must be the invited one).")}`);
    (await cookies()).set(CODE_EMAIL, email, { httpOnly: true, secure: true, sameSite: "lax", maxAge: 3600, path: "/login" });
    redirect("/login?sent=1");
  }
  const { error } = await sb.auth.signInWithPassword({ email, password });
  if (error) redirect(`/login?e=${encodeURIComponent("That email and password don't match. Leave the password empty to get a code by email.")}`);
  redirect("/");
}

async function verifyCode(form: FormData) {
  "use server";
  const store = await cookies();
  const email = store.get(CODE_EMAIL)?.value ?? "";
  const token = String(form.get("code") ?? "").replace(/\D/g, "");
  if (!email) redirect(`/login?e=${encodeURIComponent("Send a new code first.")}`);
  const { error } = await (await supabaseServer()).auth.verifyOtp({ email, token, type: "email" });
  if (error) redirect(`/login?sent=1&e=${encodeURIComponent("That code didn't work. Codes last an hour and work once; send a new one.")}`);
  store.delete({ name: CODE_EMAIL, path: "/login" });
  redirect("/");
}

/** Google (and Apple once Mike has an Apple developer account: NEXT_PUBLIC_BETLAB_APPLE=1) through Supabase's
 *  OAuth (Oct 10). Sign-ups stay off, so only invited emails get in; the same email links to the account. Google
 *  always shows its account picker: on Oct 11 it kept choosing a signed-in Google account that wasn't invited. */
async function signInWith(form: FormData) {
  "use server";
  const provider = form.get("provider") === "apple" ? "apple" : "google";
  const origin = (await headers()).get("origin") ?? "";
  const { data, error } = await (await supabaseServer()).auth.signInWithOAuth({
    provider, options: { redirectTo: `${origin}/auth/callback`, queryParams: provider === "google" ? { prompt: "select_account" } : undefined } });
  if (error || !data.url) redirect(`/login?e=${encodeURIComponent(`Couldn't start ${provider === "apple" ? "Apple" : "Google"} sign-in.`)}`);
  redirect(data.url);
}

export default async function Login({ searchParams }: { searchParams: Promise<{ e?: string; sent?: string }> }) {
  if (fixtureMode()) redirect("/");
  const sp = await searchParams;
  const waiting = sp.sent && (await cookies()).get(CODE_EMAIL)?.value;
  return (
    <main className="login">
      <SignedInWatch />
      <h1>Bet<span style={{ color: "var(--accent)" }}>Lab</span></h1>
      <p className="muted">Sign in to see today&apos;s bets, your parlays and your record.</p>
      {waiting ? (
        <form action={verifyCode} style={{ display: "grid", gap: 12 }}>
          <p className="mine">We emailed {waiting} a sign-in link{CODES ? " and a code" : ""}.</p>
          <label className="field" htmlFor="code">Code from the email
            <input id="code" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,10}" required />
          </label>
          <button className="btn" type="submit">Sign in</button>
          <p className="note">{CODES ? "Type the code here, especially in the home-screen app." : "If the email has a code, type it here. Otherwise tap the link on this phone: it signs in Safari, not the home-screen app, so in the app use Google or your password instead."} <a href="/login">Use a different way</a></p>
        </form>
      ) : (
        <>
          <form action={signInWith} style={{ display: "grid", gap: 8, marginBottom: 18 }}>
            <button className="btn" name="provider" value="google" type="submit">Continue with Google</button>
            {process.env.NEXT_PUBLIC_BETLAB_APPLE === "1" &&
              <button className="btn" name="provider" value="apple" type="submit">Continue with Apple</button>}
            <p className="note">Pick the Google account with the email you were invited with. In the home-screen app, Google opens on top: when it closes, this screen moves on by itself.</p>
          </form>
          <p className="note" style={{ textAlign: "center" }}>or with your email</p>
          <form action={signIn} style={{ display: "grid", gap: 12 }}>
            <label className="field" htmlFor="email">Email<input id="email" name="email" type="email" autoComplete="email" required /></label>
            <label className="field" htmlFor="password">Password<input id="password" name="password" type="password" autoComplete="current-password" /></label>
            <button className="btn" type="submit">Sign in</button>
            <p className="note">Leave the password empty to get a sign-in {CODES ? "code" : "link"} by email instead.</p>
          </form>
        </>
      )}
      {sp.e && <p className="err" role="alert">{sp.e}</p>}
    </main>
  );
}
