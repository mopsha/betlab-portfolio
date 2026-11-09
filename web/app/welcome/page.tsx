import { WelcomeSteps } from "@/components/me/WelcomeSteps";
import { settingsData } from "@/lib/data";

export const dynamic = "force-dynamic";

/** The first-run welcome (Nov 5, idea #60): Today sends a new account here once; Me > Extras > Intro shows it again. */
export default async function WelcomePage({ searchParams }: { searchParams: Promise<{ again?: string }> }) {
  const [{ again }, s] = await Promise.all([searchParams, settingsData()]);
  return <main className="rail"><WelcomeSteps again={!!again} unit={s.unit_dollars ?? 5} /></main>;
}
