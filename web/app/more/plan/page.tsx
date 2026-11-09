import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { PlanList } from "@/components/me/PlanList";
import { redirect } from "next/navigation";
import { todosData } from "@/lib/data";
import { isOwner } from "@/lib/owner";

/** More > Plan: the to-do list Mike and Claude share (the owner's only, Oct 10). */
export default async function Plan() {
  if (!(await isOwner())) redirect("/more");
  const todos = await todosData();
  return (
    <main className="wide">
      <BackLink fallback="/more" label="Me" />
      <div className="head"><h1>Plan</h1><span className="stamp">what each of us owes next</span></div>
      <PlanList todos={todos} />
    </main>
  );
}
