"use client";
// A screen whose server read failed (a Supabase 5xx or timeout during a publish): say so and offer a retry, in place of
// Next's blank "Application error" page. The home-screen app has no reload button, so this is the only way back.
import { useEffect, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ScreenHead } from "@/components/ui/Kit";

export default function ScreenError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const router = useRouter();
  const [busy, start] = useTransition();
  useEffect(() => { console.error(error); }, [error]);
  const retry = () => start(() => { router.refresh(); reset(); });
  return (
    <main className="rail">
      <ScreenHead title="BetLab" search={false} />
      <section className="card empty" role="alert">
        <b>This screen didn&apos;t load</b>
        <span>A read from the database failed, usually for a moment. Your bets are safe.</span>
        <span><button className="btn" type="button" onClick={retry} disabled={busy}>{busy ? "Trying…" : "Try again"}</button></span>
        {error.digest && <small className="note">Error {error.digest}</small>}
      </section>
    </main>
  );
}
