import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { BonusCalc, ClvCalc, EvCalc, OddsCalc, ParlayCalc, UnitsCalc, VarianceSim, VigCalc } from "@/components/me/Calculators";

const M = ({ children }: { children: React.ReactNode }) => <span className="mono">{children}</span>;

/** More > Learn: Betting 101, every number in the app explained, each lesson folded with its calculator. */
export default async function Learn() {
  const lessons: { id: string; title: string; body: React.ReactNode }[] = [
    { id: "odds", title: "Reading odds", body: <>
      <p>American odds are built around $100. A minus number is what you risk to win $100; a plus number is what you win when you risk $100. <M>−150</M> means risk $150 to win $100. <M>+150</M> means risk $100 to win $150.</p>
      <p>Every price is also a probability: the win rate you need to break even. That&apos;s the number the model compares against. Implied probability = 1 ÷ decimal odds.</p>
      <OddsCalc /></> },
    { id: "vig", title: "The vig (the book's cut)", body: <>
      <p>A fair coin flip would be <M>+100</M> on both sides. FanDuel usually prices it <M>−110 / −110</M>. Add the two break-even rates and you get 104.8%, not 100%. That extra is the vig.</p>
      <p>Remove it and you get the market&apos;s fair chances: that&apos;s &quot;no-vig&quot; in the app. Books shade long shots more than favorites, so BetLab uses the <em>power</em> method, which takes more of the vig off the underdog.</p>
      <VigCalc /></> },
    { id: "ev", title: "Expected value", body: <>
      <p>Expected value (EV) is what a bet earns on average per $1 staked, if your chance is right: <M>EV = p × (decimal − 1) − (1 − p)</M>. A 55% shot at −110 has EV of +5%.</p>
      <p>A bet is a pick only when its EV clears 3% on game lines, 5% on props and 10% on prop unders, within 36 hours of the start. Smaller edges show as leans. The buffers exist because our chances are estimates.</p>
      <EvCalc /></> },
    { id: "units", title: "Units", body: <>
      <p>A <b>unit</b> is your standard bet, whatever size you choose. BetLab counts everything in units, never dollars: a 1u bet at <M>+120</M> that wins is <M>+1.20u</M>, and &quot;+6 units&quot; means the same whatever your unit is. Only bet money you could lose completely without it touching rent, bills or school.</p>
      <ul>
        <li>Bet flat at first: every pick 1 unit.</li>
        <li>Keep your unit the same size for a month at a time, never bigger after a win or a loss.</li>
        <li>At most 5 units at risk on one day. The one exception is a ladder challenge&apos;s steps (Me › Ladder), which roll the whole stack by design.</li>
        <li>Never chase. Doubling up to get even is how losing streaks get worse.</li>
      </ul>
      <p>The <b>Kelly criterion</b> gives the stake that grows your money fastest <em>if your chances are exactly right</em>. They never are, so BetLab tracks quarter-Kelly, capped at 2 units, for comparison only (taking a unit as about 1% of what you set aside).</p>
      <UnitsCalc /></> },
    { id: "variance", title: "Variance: why 100 bets prove almost nothing", body: <>
      <p>Someone who truly wins 55% of −110 bets (a big edge) is still behind after 100 bets about 3 times in 10. After 1,000 bets that drops to about 1 in 20. That&apos;s why the scorecard is closing line value, not the record.</p>
      <VarianceSim /></> },
    { id: "clv", title: "Closing line value (CLV)", body: <>
      <p>The closing line, the last price before the start, is the sharpest number the market produces. Consistently beating it means you&apos;re very likely a winning bettor, even through losing stretches. CLV becomes meaningful in weeks, where records take years.</p>
      <p>CLV here is your bet&apos;s EV if the no-vig closing price were the truth.</p>
      <ClvCalc /></> },
    { id: "shop", title: "Line shopping", body: <>
      <p>Books disagree, and the difference is pure edge. The same bet at −105 instead of −115 moves your break-even from 53.5% to 51.2%. Winning 52.5% of bets is EV −1.9% at −115 (a slow loser) and +2.5% at −105 (a winner).</p>
      <p>That&apos;s why the plan is FanDuel plus one or two other books.</p></> },
    { id: "parlays", title: "Parlays and same-game parlays", body: <>
      <p>A parlay multiplies the legs&apos; odds, and the book&apos;s edge too. One −110 coin flip costs about 4.5%; four of them pay <M>+1228</M> against a fair <M>+1500</M>, about 17%. Same-game parlays price the correlation with extra margin.</p>
      <p>Picks are straight bets. Parlays live in the fun bucket (the parlay units a month you set in Settings), so they never blur the real record. The Build grade compares FanDuel&apos;s price with what its parlays that size usually pay.</p>
      <ParlayCalc /></> },
    { id: "bonus", title: "Bonus bets and boosts", body: <>
      <p><b>Bonus bets</b> pay the profit but never the stake, so long odds keep more of their value: a $10 bonus bet on a fair +300 is worth about $7.50 in cash on average; on a −110 coin flip, about $4.50.</p>
      <p><b>Profit boosts</b> raise the payout on one bet; many turn a slightly negative bet positive. Run the boosted price through the EV calculator with the no-vig chance.</p>
      <BonusCalc /></> },
    { id: "props", title: "Player props", body: <>
      <p>Props are priced from projections of playing time and usage. Books post hundreds per game, so they&apos;re less sharp than spreads, but they carry more vig, lower limits, and move with game script.</p>
      <p>New York bans college player props, and BetLab never offers them.</p></> },
    { id: "soccer", title: "Soccer markets", body: <ul>
      <li><b>Moneyline is three-way:</b> home, draw or away, settled on 90 minutes plus stoppage time.</li>
      <li><b>Draw no bet:</b> your stake comes back on a draw.</li>
      <li><b>Double chance:</b> two of the three outcomes.</li>
      <li><b>Totals and spreads:</b> usually half-goal lines, so no pushes.</li>
      <li><b>Both teams to score:</b> yes/no on each side scoring.</li>
    </ul> },
    { id: "taxes", title: "Taxes in New York", body: <p>Gambling winnings are income for federal and New York taxes (and New York City tax if you live there), with or without a tax form. Losses are deductible only if you itemize, and from 2026 returns a federal law limits that to 90% of losses. Keep your records (My bets). Check with a tax professional; this isn&apos;t tax advice.</p> },
    { id: "control", title: "Staying in control", body: <>
      <ul>
        <li>Before your first deposit, set a monthly deposit limit in FanDuel equal to what you set aside for betting (Account → Responsible Gaming).</li>
        <li>At most 5 units at risk per day.</li>
        <li>If betting stops being fun, or you catch yourself chasing, take a break. FanDuel&apos;s limits can lock the account for a set time.</li>
      </ul>
      <p className="help"><b>New York HOPEline</b>, free, confidential, 24/7: call <M>1-877-846-7369</M> (1-877-8-HOPENY) or text <M>467369</M> (HOPENY).</p></> },
  ];
  return (
    <main className="rail">
      <BackLink fallback="/more" label="Me" />
      <div className="head"><h1>Learn</h1><span className="stamp">every number in the app, explained</span></div>
      <div className="feed">
        {lessons.map((l) => (
          <details className="card lesson" key={l.id} id={l.id}>
            <summary>{l.title}</summary>
            <div className="prose">{l.body}</div>
          </details>
        ))}
      </div>
    </main>
  );
}
