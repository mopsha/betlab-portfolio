import { SubHead } from "@/components/ui/Kit";
import { BookSwitches } from "@/components/me/BookSwitches";
import { settingsData } from "@/lib/data";

/** Settings > Your books (0043): one switch per book for everything. */
export default async function BooksPage() {
  const s = await settingsData();
  return <main className="rail stg"><SubHead title="Your books" back="/more/settings" backLabel="Settings" /><BookSwitches off={s.books_off ?? []} /></main>;
}
