-- A ladder stays at one book the whole way (Mike, Oct 26: "ladder needs to be at one book whole time so I need to be
-- able to signify it"): chosen at the start, every step is suggested, locked and priced at it (web/lib/ladder.ts
-- atBook, ios/BetLab/Ladder.swift, src/betlab/ladders.py). Ladders from before default to FanDuel.
alter table ladders add column if not exists book text not null default 'FanDuel'
  check (book in ('FanDuel', 'DraftKings', 'Novig'));
