import "server-only";
// Chat with BetLab (Mike's W22, rated essential, Oct 24): Claude inside the app, answering from the app's own numbers.
// Read-only tools over the signed-in account's data (the same Supabase client and row-level security as every page):
// open bets with each leg live, today's board, one game's offers and analysis, the record. Claude never places a
// bet; it explains and suggests, and links to the game pages where the Open in FanDuel/DraftKings buttons are.
// Needs ANTHROPIC_API_KEY on the web service (Mike adds it in Railway); without it the chat says it's waiting.
import Anthropic from "@anthropic-ai/sdk";
import { betaTool } from "@anthropic-ai/sdk/helpers/beta/json-schema";
import { bonusSummary, boostSummary, isSettled, profit, record, recordBets, stakeOf, statusOf } from "./bets";
import { allGames, gameData, homeData, myBetsData, openBetNames, socialData } from "./data";
import { betName } from "./gameday";
import { liveBets } from "./live-bets";
import { plain } from "./live";
import { isReal } from "./real";

// Sonnet (Mike, Oct 24: "why don't we use sonnet or haiku"): answering from four read-only tools doesn't need Opus,
// and Sonnet costs half as much; the server-side refusal fallback stays on.
export const MODEL = "claude-sonnet-5-5";
const MAX_TOOL_CHARS = 20_000;   // a tool's answer is cut here (a busy board can run long)
export const MAX_TURNS = 20, MAX_CHARS = 4000;   // what one request may carry

export const chatReady = () => !!process.env.ANTHROPIC_API_KEY;

/** The system prompt for whoever is signed in (Nov 9: it called everyone Mike, so Sam's chat answered to him). */
export const systemFor = (who: string) => `You are BetLab's assistant, inside a personal sports-betting app for FanDuel, DraftKings and Novig in New York.

How BetLab works: it prices each book's lines against the sharp market's no-vig price (Pinnacle and similar), which closing lines show beats our own models in most markets, so most picks are a book's price lagging the sharp one. EV is the edge per unit at the book's price; a pick clears the bar, a lean is close. Parlays (SGP+, "fun" tickets) are priced from the sharp legs' fair chances; a ticket locks shortly before its first game. CLV (closing line value: did the price move our way by the start) is the scorecard. The app counts units, not dollars. Bonus bets pay only the winnings; a profit boost multiplies a win's profit.

Answer from the tools, never from memory: call them for anything about bets, prices, games or results, and quote the app's numbers (price, book, EV, fair chance). You are talking with ${who}, who is learning the betting math: when it helps, show the arithmetic briefly (implied chance from a price, how a parlay's chance multiplies, what a boost does to EV). Be direct and short; lead with the answer. Link a game as markdown, [Bears @ Lions](/games/nfl/<id>), using the url a tool gives; the game page has the Open in FanDuel/DraftKings buttons. You cannot place, change or cancel bets; say so if asked, and point to the game page. Suggestions are ${who}'s to take or leave; don't push volume. New York rules apply: no college player props, no bets on New York colleges or on college games played in New York. If the data doesn't answer the question, say what's missing instead of guessing.`;

const clip = (v: unknown) => {
  const s = JSON.stringify(v);
  return s.length > MAX_TOOL_CHARS ? s.slice(0, MAX_TOOL_CHARS) + `… [cut at ${MAX_TOOL_CHARS} characters]` : s;
};
const gameUrl = (league: string | null | undefined, id: string | null | undefined) => (id ? `/games/${league}/${id}` : null);
const short = (s: string | null | undefined, n = 400) => (s && s.length > n ? s.slice(0, n) + "…" : s ?? null);

const openBets = betaTool({
  name: "my_open_bets",
  description: "The signed-in user's own open bets (not settled yet), each with its price, stake in units, bonus or boost, and every leg's live state from ESPN (score, clock, progress to a prop's target, winning/losing/won/lost).",
  inputSchema: { type: "object", properties: {}, additionalProperties: false },
  run: async () => {
    const [{ bets }, names] = await Promise.all([myBetsData(), openBetNames()]);
    const open = bets.filter((b) => !isSettled(b));
    const live = await liveBets(undefined, new Date(), open).catch(() => null);
    const nameOf = Object.fromEntries(names.map((n) => [n.id, n.name]));
    return clip(open.map((b) => {
      const l = live?.bets[b.bet_id];
      return {
        name: nameOf[b.bet_id], price: b.price, book: b.book, stake_units: stakeOf(b), mode: b.mode, bonus: b.bonus || undefined,
        boost_pct: b.boost ?? undefined, placed_at: b.placed_at, status: l?.status ?? "pending",
        games: l?.games.map((g) => `${g.away.name} ${g.away.score ?? ""} @ ${g.home.name} ${g.home.score ?? ""} (${g.state === "pre" ? g.start : g.detail})`),
        legs: l ? l.legs.map((x) => ({ leg: x.label, status: x.status, now: x.text })) : b.legs ?? [b.label],
      };
    }));
  },
});

const board = betaTool({
  name: "todays_board",
  description: "What's worth betting: the picks (with price, book, EV, fair chance and why), games with something to act on, locked parlay tickets with their legs and fair price, and the next parlay locks. Leans are on each game (use game_details).",
  inputSchema: {
    type: "object",
    properties: {
      day: { type: "string", enum: ["today", "tomorrow", "week"], description: "Which window; default today" },
      sport: { type: "string", description: "Optional league key: nfl, ncaaf, nba, nhl, ufc, epl, la_liga, serie_a, bundesliga, ligue_1, mls, ucl, uel, uecl" },
    },
    additionalProperties: false,
  },
  run: async ({ day, sport }) => {
    const d = await homeData((day ?? "today") as "today" | "tomorrow" | "week", sport ?? null);
    const offer = (o: (typeof d.picks)[number]) => ({ tier: o.tier, label: o.label, matchup: o.matchup, start: o.commence_time, price: o.price,
      book: o.book, ev: o.ev, fair_chance: o.p_final, other_book: o.other_book ?? undefined, other_price: o.other_price ?? undefined,
      why: short(o.why), url: gameUrl(o.league, o.game_id) });
    return clip({
      picks: d.picks.map(offer),
      games: d.items.flatMap((it) => it.kind === "game" ? [{ matchup: it.game.matchup, league: it.game.league, start: it.game.commence_time,
        url: gameUrl(it.game.league, it.game.game_id), offers: it.game.offers.filter((o) => o.tier !== "check").map(offer),
        slips: it.game.tickets.filter((t) => t.kind !== "over").map((t) => ({ kind: t.kind, fair: t.fair_price, book_price: t.naive_price,
          legs: (t.body.legs ?? []).map((l) => l.label) })) }] : []),
      locked_tickets: d.items.flatMap((it) => it.kind === "ticket" ? [{ title: it.slate?.title ?? it.ticket.matchup, kind: it.ticket.kind,
        fair: it.ticket.fair_price, book_price: it.ticket.naive_price, start: it.ticket.commence_time,
        legs: (it.ticket.body.games ?? []).flatMap((g) => g.legs.map((l) => `${l.label} (${g.matchup})`)) }] : []),
      next_locks: d.nextLocks.slice(0, 6),
      quiet_games: d.quiet,
    });
  },
});

const game = betaTool({
  name: "game_details",
  description: "One game's offers at every book (picks and leans with price, EV, fair chance, why), its parlay slips, and the model's analysis, found by a team, player-free name or fighter (e.g. 'Knicks', 'Michigan', 'Arsenal', 'Evloev'). Upcoming games this week only.",
  inputSchema: {
    type: "object",
    properties: { team: { type: "string", description: "A team, club or fighter name as it appears in the matchup" } },
    required: ["team"],
    additionalProperties: false,
  },
  run: async ({ team }) => {
    const want = plain(team);
    const { games } = await allGames(null);
    const hits = games.filter((g) => plain(g.matchup).includes(want)).slice(0, 3);
    if (!hits.length) return `No upcoming game this week matches "${team}".`;
    const out = await Promise.all(hits.map(async (g) => {
      const d = await gameData(g.game_id);
      return d && {
        matchup: g.matchup, league: g.league, start: g.commence_time, url: gameUrl(g.league, g.game_id),
        offers: d.offers.map((o) => ({ tier: o.tier, label: o.label, price: o.price, book: o.book, ev: o.ev, fair_chance: o.p_final,
          model_chance: o.p_model, why: short(o.why, 300) })),
        slips: d.tickets.filter((t) => t.kind !== "over").map((t) => ({ kind: t.kind, fair: t.fair_price, book_price: t.naive_price,
          legs: (t.body.legs ?? []).map((l) => l.label) })),
        analysis: short(JSON.stringify(d.analysis), 4000),
      };
    }));
    return clip(out.filter(Boolean));
  },
});

const myRecord = betaTool({
  name: "my_record",
  description: "The signed-in user's own betting record: units won or lost overall and by market, bonus bets and profit boosts, and their most recent settled bets with their results.",
  inputSchema: { type: "object", properties: {}, additionalProperties: false },
  run: async () => {
    const { bets, settings } = await myBetsData();
    const { counted, useReal } = recordBets(bets, isReal(new Date(), settings.real_from));
    const r = record(counted);
    const settled = counted.filter(isSettled).sort((a, b) => b.placed_at.localeCompare(a.placed_at)).slice(0, 20);
    return clip({
      counting: useReal ? "real-money bets" : "paper bets", total: r.total, by_market: r.lines,
      bonus_bets: bonusSummary(counted), profit_boosts: boostSummary(counted),
      recent: settled.map((b) => ({ name: betName(b), status: statusOf(b), units: profit(b), placed_at: b.placed_at, book: b.book })),
    });
  },
});

export const TOOLS = [openBets, board, game, myRecord];

export type ChatTurn = { role: "user" | "assistant"; content: string };

/** One answer to the conversation so far: Claude with the tools until it's done (at most 8 rounds). */
/** What to call the signed-in account: its profile's first name, else the account's own words for it. */
export async function chatName(): Promise<string> {
  const p = await socialData().then((d) => d.profile).catch(() => null);
  const first = p?.name?.trim().split(/\s+/)[0];
  return first || "the user";
}

export async function answer(turns: ChatTurn[], who = "the user"): Promise<string> {
  const client = new Anthropic();
  const message = await client.beta.messages.toolRunner({
    model: MODEL,
    max_tokens: 16000,
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",              // a declined request is retried on the fallback model in the same call
    output_config: { effort: "low" },     // chat: Sonnet's recalibrated levels start at low
    cache_control: { type: "ephemeral" },
    system: systemFor(who),
    tools: TOOLS,
    messages: turns.map((t) => ({ role: t.role, content: t.content })),
    max_iterations: 8,
  });
  if (message.stop_reason === "refusal") return "I can't help with that one.";
  const text = message.content.flatMap((b) => (b.type === "text" ? [b.text] : [])).join("\n").trim();
  if (message.stop_reason === "max_tokens") return text + "\n\n(cut off: ask me to continue)";
  return text || "I looked but have nothing to add: try asking it another way.";
}
