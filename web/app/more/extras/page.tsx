import { redirect } from "next/navigation";

/** Extras was its own page for a day (Nov 4). Its places are chips on Me now (the Me reorganization, Nov 5); old links
 *  land there. */
export default function Extras() {
  redirect("/more");
}
