// The chat's answers as display pieces (Oct 24): paragraphs and "- " lists, with **bold** and [links](/path) inside.
// Pure, so the tests run it. Only app paths and https links become links; anything else stays text.
export type Span = { text: string; bold?: boolean; href?: string };
export type Block = { kind: "p" | "li"; spans: Span[] };

const INLINE = /\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)/g;
const safeHref = (h: string) => (h.startsWith("/") && !h.startsWith("//")) || h.startsWith("https://") ? h : null;

export function spans(line: string): Span[] {
  const out: Span[] = [];
  let last = 0;
  for (const m of line.matchAll(INLINE)) {
    if (m.index! > last) out.push({ text: line.slice(last, m.index) });
    if (m[1] !== undefined) out.push({ text: m[1], bold: true });
    else {
      const href = safeHref(m[3]);
      out.push(href ? { text: m[2], href } : { text: m[0] });
    }
    last = m.index! + m[0].length;
  }
  if (last < line.length) out.push({ text: line.slice(last) });
  return out;
}

export function blocks(text: string): Block[] {
  const out: Block[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) continue;
    const li = /^\s*(?:[-*•]|\d+\.)\s+(.*)$/.exec(line);
    out.push(li ? { kind: "li", spans: spans(li[1]) } : { kind: "p", spans: spans(line.replace(/^#+\s*/, "")) });
  }
  return out;
}
