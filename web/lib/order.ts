// Your own order of the wall's tiles (Mike, Oct 25: drag them into place), saved per account in
// user_settings.wall_order: a list of ESPN game keys ("nfl:401772..."). Pure, so the tests run it.

/** Items in your order: those you placed first, as placed; the rest after them in the order they came (the wall's own:
 *  live, then upcoming by start), like a game you bet after you last dragged. */
export function ordered<T>(items: T[], order: string[], key: (x: T) => string): T[] {
  const rank = new Map(order.map((k, i) => [k, i]));
  const at = (x: T) => rank.get(key(x)) ?? Infinity;
  return [...items].sort((a, b) => at(a) - at(b));      // stable: unplaced items keep their own order
}

/** The saved list after a drop: `shown` is the tiles on the wall in their new order. They take the place of the first
 *  of them in the old list, so keys not on the wall now keep theirs; at most `cap` keys are kept (the newest: old games
 *  fall off the front). */
export function placed(order: string[], shown: string[], cap = 400): string[] {
  const moving = new Set(shown);
  const firstAt = order.findIndex((k) => moving.has(k));
  const rest = order.filter((k) => !moving.has(k));
  const at = firstAt < 0 ? rest.length : order.slice(0, firstAt).filter((k) => !moving.has(k)).length;
  const out = [...rest.slice(0, at), ...shown, ...rest.slice(at)];
  return out.slice(Math.max(0, out.length - cap));
}

/** The list with the item at `from` moved to `to` (a drag's result). */
export function moved<T>(list: T[], from: number, to: number): T[] {
  const out = [...list];
  const [x] = out.splice(from, 1);
  out.splice(Math.max(0, Math.min(to, out.length)), 0, x);
  return out;
}
