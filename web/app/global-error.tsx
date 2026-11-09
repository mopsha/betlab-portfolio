"use client";
// The last net: an error in the root layout itself (its settings read) replaces the whole page, so this one brings its
// own <html> and <body> and the app's base styles. Reloading is the retry: the layout has to be read again.
import { useEffect } from "react";
import "./globals.css";
import "./look.css";
import "./kit.css";

export default function GlobalError({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <html lang="en">
      <body>
        <main className="rail" style={{ paddingTop: 48 }}>
          <section className="card empty" role="alert">
            <b>BetLab didn&apos;t load</b>
            <span>A read from the database failed, usually for a moment. Your bets are safe.</span>
            <span><button className="btn" type="button" onClick={() => window.location.reload()}>Try again</button></span>
            {error.digest && <small className="note">Error {error.digest}</small>}
          </section>
        </main>
      </body>
    </html>
  );
}
