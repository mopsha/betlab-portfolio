// The first-run welcome (Nov 5, idea #60), the same words as the iPhone's WelcomeView (web/tests/welcome.test.mjs holds them together).
export const WELCOME: { title: string; lines: string[] }[] = [
  { title: "BetLab finds the prices that lag",
    lines: ["It compares each book's price with the sharp market's no-vig price. When your book is behind, that's a pick.",
            "Picks are suggestions. You decide, and you place every bet yourself."] },
  { title: "Three words you'll see",
    lines: ["EV: what a price is worth against the fair chance. Above zero is good.",
            "Units: a bet is 1u, and 5u a day at most. The apps count units, never money.",
            "CLV: did you beat the closing price? Over time it's the best sign you're betting well."] },
  { title: "Where things are",
    lines: ["Today: the picks and parlays.", "Live: your open bets, updating as they play.",
            "Build: your own parlay, a slip to check, or a promo to use.", "Games: every game and its page.", "Me: your record, friends and settings."] },
];
export const WELCOME_UNIT = { title: "What's one unit to you?", line: "Pick an amount you could lose every day and not mind. You can change it in Settings.",
  help: "If betting stops being fun, help is free and private: 1-877-8-HOPENY." };
