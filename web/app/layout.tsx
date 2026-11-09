import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import { Archivo, Inter, JetBrains_Mono, Manrope, Nunito, Public_Sans } from "next/font/google";
import { Nav, TabBar } from "@/components/app/Nav";
import { CardProvider } from "@/components/games/Cards";
import { InstallProvider } from "@/components/app/InstallApp";
import { NavTracker } from "@/components/ui/BackLink";
import { LivePulse } from "@/components/app/LivePulse";
import { RealFromProvider } from "@/components/app/RealFrom";
import { MyBooksProvider } from "@/components/app/MyBooks";
import { settingsData } from "@/lib/data";
import { realStart } from "@/lib/real";
import { THEMES, fontOf, themeOf } from "@/lib/looks";
import "./globals.css";
import "./look.css";
import "./kit.css";
import "./screens.css";
import "./social.css";
import "./settings.css";
import "./wallet.css";
import "./build.css";
import "./me.css";

const display = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-display" });
const body = Public_Sans({ subsets: ["latin"], variable: "--font-public" });
// the other body fonts (More > Settings > Font); only the chosen one downloads
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", preload: false });
const nunito = Nunito({ subsets: ["latin"], variable: "--font-nunito", preload: false });
const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", preload: false });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "BetLab",
  description: "What's worth betting now, every game on one page.",
  appleWebApp: { capable: true, title: "BetLab", statusBarStyle: "default" },
  icons: { icon: "/icon.svg", apple: "/icons/apple-touch-icon.png" },
};
export async function generateViewport(): Promise<Viewport> {
  const theme = themeOf((await cookies()).get("theme")?.value);      // the status bar follows the chosen theme
  const bg = THEMES.find((t) => t.id === theme)?.bg;
  return {
    width: "device-width", initialScale: 1, viewportFit: "cover",
    themeColor: bg ? bg : [{ media: "(prefers-color-scheme: light)", color: "#f4f5f7" }, { media: "(prefers-color-scheme: dark)", color: "#0d0f13" }],
  };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const jar = await cookies();
  const theme = themeOf(jar.get("theme")?.value), font = fontOf(jar.get("font")?.value);
  const settings = await settingsData().catch(() => null);      // signed out: the defaults
  const start = realStart(settings?.real_from);
  const days = Math.ceil((start.getTime() - Date.now()) / 864e5);
  const startLabel = start.toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
  return (
    <html lang="en" className={[display, body, mono, inter, nunito, manrope].map((f) => f.variable).join(" ")}
          data-theme={theme} data-font={font}>
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <NavTracker />
        <LivePulse />
        <Nav phase={days > 0 ? `paper · ${days}d to ${startLabel}` : "live · real money"} />
        <RealFromProvider value={settings?.real_from ?? null}><MyBooksProvider off={settings?.books_off ?? []}><InstallProvider><CardProvider><div id="main" tabIndex={-1}>{children}</div></CardProvider></InstallProvider></MyBooksProvider></RealFromProvider>
        <TabBar />
      </body>
    </html>
  );
}
