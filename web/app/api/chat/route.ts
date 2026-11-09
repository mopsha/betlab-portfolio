import Anthropic from "@anthropic-ai/sdk";
import { MAX_CHARS, MAX_TURNS, answer, chatName, chatReady, type ChatTurn } from "@/lib/chat";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

/** Chat with BetLab (lib/chat.ts): the conversation so far in, the next answer out. Signed-in only (proxy.ts). */
export async function POST(req: Request) {
  if (!chatReady()) return Response.json({ error: "Chat is waiting for its key (ANTHROPIC_API_KEY on the web service)." }, { status: 503 });
  let turns: ChatTurn[];
  try {
    const body = await req.json();
    turns = (Array.isArray(body?.messages) ? body.messages : [])
      .filter((t: ChatTurn) => (t.role === "user" || t.role === "assistant") && typeof t.content === "string" && t.content.trim())
      .slice(-MAX_TURNS)
      .map((t: ChatTurn) => ({ role: t.role, content: t.content.slice(0, MAX_CHARS) }));
  } catch {
    return Response.json({ error: "That message didn't arrive whole: try again." }, { status: 400 });
  }
  while (turns.length && turns[0].role !== "user") turns.shift();     // the conversation must open with a question
  if (!turns.length || turns[turns.length - 1].role !== "user") return Response.json({ error: "Ask something first." }, { status: 400 });
  try {
    return Response.json({ answer: await answer(turns, await chatName()) });
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError) return Response.json({ error: "The chat's key was refused: check ANTHROPIC_API_KEY." }, { status: 503 });
    if (e instanceof Anthropic.RateLimitError) return Response.json({ error: "Too many questions at once: try again in a minute." }, { status: 429 });
    if (e instanceof Anthropic.APIError) return Response.json({ error: `Claude answered with an error (${e.status ?? "?"}): try again.` }, { status: 502 });
    return Response.json({ error: "Something went wrong reading your data: try again." }, { status: 500 });
  }
}
