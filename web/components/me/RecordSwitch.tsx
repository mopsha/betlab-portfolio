import Link from "next/link";
import { SubHead } from "@/components/ui/Kit";

const TABS = [["record", "Record"], ["stats", "Stats"], ["prices", "Prices"]] as const;

/** Record, Stats and Prices as one place (the Me reorganization, Nov 5): the same header and one switch on all three
 *  pages, so Me needs a single way in. */
export function RecordSwitch({ on }: { on: (typeof TABS)[number][0] }) {
  return (
    <>
      <SubHead title="Record and stats" />
      <nav className="segx me-switch" aria-label="Record and stats">
        {TABS.map(([k, l]) => <Link key={k} href={`/more/${k}`} aria-current={k === on ? "page" : undefined} replace>{l}</Link>)}
      </nav>
    </>
  );
}
