import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { redirect } from "next/navigation";
import { reviewsData } from "@/lib/data";
import { isOwner } from "@/lib/owner";

/** A review body: paragraphs, "- " bullet blocks, and one-line headings (a short line with no period). */
function Body({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n{2,}/).map((b, i) => {
        const lines = b.split("\n").map((l) => l.trim()).filter(Boolean);
        if (lines.length && lines.every((l) => l.startsWith("- "))) return <ul key={i}>{lines.map((l, j) => <li key={j}>{l.slice(2)}</li>)}</ul>;
        if (lines.length === 1 && lines[0].length < 60 && !/[.:!?]$/.test(lines[0])) return <h3 key={i}>{lines[0]}</h3>;
        return <p key={i}>{b}</p>;
      })}
    </>
  );
}

/** More > Reviews: the Tuesday weekly reviews, newest open, older ones folded. */
export default async function Reviews() {
  if (!(await isOwner())) redirect("/more");          // the owner's weekly reviews (Oct 10)
  const list = await reviewsData();
  return (
    <main className="rail">
      <BackLink fallback="/more" label="Me" />
      <div className="head"><h1>Reviews</h1><span className="stamp">every Tuesday</span></div>
      {!list.length ? <div className="card empty"><span>No reviews yet.</span></div> : (
        <div className="feed">
          {list.map((r, i) => {
            const when = new Date(r.created_at).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "long", day: "numeric", year: "numeric" });
            return (
              <details className="card review" key={r.id} open={i === 0}>
                <summary><span className="faint mono">{when}</span><b>{r.title}</b></summary>
                <div className="prose"><Body text={r.body} /></div>
              </details>
            );
          })}
        </div>
      )}
    </main>
  );
}
