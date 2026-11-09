import { SearchBox } from "@/components/games/SearchBox";

export const metadata = { title: "Search · BetLab" };

export default function Search() {
  return (
    <main className="rail">
      <div className="head"><h1>Search</h1></div>
      <SearchBox />
    </main>
  );
}
