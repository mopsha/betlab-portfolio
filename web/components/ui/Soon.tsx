import Link from "next/link";

/** A place that arrives in Phase 4 (docs/APP_PLAN.md), with where to find it until then. */
export function Soon({ title, what, meanwhile }: { title: string; what: string; meanwhile: string }) {
  return (
    <main className="rail">
      <div className="card soon" style={{ marginTop: 24 }}>
        <h1>{title}</h1>
        <p className="muted">{what}</p>
        <p className="note">Until then: {meanwhile} <Link href="/">Back to Today</Link></p>
      </div>
    </main>
  );
}
