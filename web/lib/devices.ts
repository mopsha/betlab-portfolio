// Signed-in devices (Nov 4): a session's name from its user agent. Pure, so the tests run it. Port: ios/BetLab/Me/DevicesView.swift, fixture
// tests/fixtures/devices.json.
export type DeviceSession = { id: string; created_at: string; last_active: string; user_agent: string | null; ip: string | null; current: boolean };

export function deviceName(ua: string | null | undefined): string {
  const u = ua ?? "";
  if (/^BetLab\//.test(u)) return "BetLab iPhone app";
  if (u === "node") return "Website sign-in";     // went through our server: its IP is the server's, so the card leaves it out
  const os = /iPhone/.test(u) ? "iPhone" : /iPad/.test(u) ? "iPad" : /Android/.test(u) ? "Android" : /Windows/.test(u) ? "Windows" : /Macintosh/.test(u) ? "Mac" : /Linux/.test(u) ? "Linux" : "";
  const browser = /Edg\//.test(u) ? "Edge" : /Firefox\/|FxiOS\//.test(u) ? "Firefox" : /Chrome\/|CriOS\//.test(u) ? "Chrome" : /Safari\//.test(u) ? "Safari" : "";
  return os && browser ? `${browser} on ${os}` : "Unknown device";
}
