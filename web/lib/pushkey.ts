/** The VAPID public key as bytes, from its base64url text. */
export function keyBytes(b64url: string): Uint8Array {
  const b64 = (b64url + "=".repeat((4 - (b64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

/** True when the browser's subscription was made with a different server key than `key` (Oct 23: after the VAPID
 *  rotation the old subscriptions still read "on" while every push to them failed). A browser that doesn't report
 *  the key it used is left alone. */
export function staleKey(sub: { options?: { applicationServerKey?: ArrayBuffer | null } }, key: string): boolean {
  const used = sub.options?.applicationServerKey;
  if (!used || !key) return false;
  const a = new Uint8Array(used), b = keyBytes(key);
  return a.length !== b.length || a.some((x, i) => x !== b[i]);
}
