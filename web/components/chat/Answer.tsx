// One of BetLab's answers in the chat (the overhaul's look, Nov 5): plain text on the page, not a bubble. The answer's
// own markdown (lib/chat-format.ts: paragraphs, lists, bold, links) is drawn as type; a link to a game page becomes a
// tappable card with the two teams' logos when the page knows the game, never a raw link.
import Link from "next/link";
import type { ReactNode } from "react";
import { blocks, type Block, type Span } from "@/lib/chat-format";
import { Art, type ArtOf } from "@/components/ui/Art";

/** A game the chat can draw: its teams' pictures and when it starts, keyed by its page's path. */
export type GameRef = { title: string; when: string; away: ArtOf; home: ArtOf };
export type GameRefs = Record<string, GameRef>;

const GAME = /^\/games\/([^/?#]+)\/([^/?#]+)/;
const isGame = (s: Span) => !!s.href && GAME.test(s.href);
const pathOf = (href: string) => href.split(/[?#]/)[0];

function Pair({ href, games, size }: { href: string; games: GameRefs; size: number }) {
  const g = games[pathOf(href)];
  if (!g) return <Art kind="league" name={GAME.exec(href)?.[1] ?? ""} size={size} className="disc" />;   // the league's logo when the game isn't on the page
  return <span className="artstack" style={{ ["--art" as string]: `${size}px` }}><Art {...g.away} size={size} className="disc" /><Art {...g.home} size={size} className="disc" /></span>;
}

function inline(s: Span, j: number, games: GameRefs): ReactNode {
  if (isGame(s)) return <Link key={j} href={s.href!} className="cx-pill"><Pair href={s.href!} games={games} size={22} /><span>{s.text}</span></Link>;
  if (s.href) return s.href.startsWith("/") ? <Link key={j} href={s.href}>{s.text}</Link> : <a key={j} href={s.href} target="_blank" rel="noreferrer">{s.text}</a>;
  return s.bold ? <b key={j}>{s.text}</b> : <span key={j}>{s.text}</span>;
}

const CARD_MAX = 150;    // a game card carries at most this much text beside its title; longer stays a sentence

/** A block that leads with its one game link reads as a card: the logos, the game, the rest of the line under it. */
function asCard(b: Block): { link: Span; rest: Span[] } | null {
  const real = b.spans.filter((s) => s.text.trim());
  if (!real.length || !isGame(real[0]) || real.filter(isGame).length !== 1) return null;
  const rest = real.slice(1);
  if (rest.some((s) => s.href)) return null;                // a card is one link; another link inside it couldn't be tapped
  if (rest.length) rest[0] = { ...rest[0], text: rest[0].text.replace(/^\s*[:\-–—,.·]\s*/, "") };
  if (rest.reduce((n, s) => n + s.text.length, 0) > CARD_MAX) return null;
  return { link: real[0], rest: rest.filter((s) => s.text.trim()) };
}

export function Answer({ text, games }: { text: string; games: GameRefs }) {
  const out: ReactNode[] = [];
  let list: ReactNode[] = [], cards: ReactNode[] = [];
  const flush = () => {
    if (list.length) { out.push(<ul key={`u${out.length}`}>{list}</ul>); list = []; }
    if (cards.length) { out.push(<div key={`c${out.length}`} className="cx-games">{cards}</div>); cards = []; }
  };
  blocks(text).forEach((b, i) => {
    const card = asCard(b);
    if (card) {
      if (list.length) flush();
      const g = games[pathOf(card.link.href!)];
      cards.push(
        <Link key={i} href={card.link.href!} className="cx-game">
          <Pair href={card.link.href!} games={games} size={34} />
          <span className="cx-game-what">
            <b>{card.link.text}</b>
            {card.rest.length > 0 && <span className="sub">{card.rest.map((s, j) => (s.bold ? <b key={j}>{s.text}</b> : <span key={j}>{s.text}</span>))}</span>}
            {!card.rest.length && g?.when && <span className="sub">{g.when}</span>}
          </span>
          <span className="chev" aria-hidden>›</span>
        </Link>);
      return;
    }
    if (cards.length) flush();
    const inner = b.spans.map((s, j) => inline(s, j, games));
    if (b.kind === "li") list.push(<li key={i}>{inner}</li>);
    else { flush(); out.push(<p key={i}>{inner}</p>); }
  });
  flush();
  return <>{out}</>;
}
