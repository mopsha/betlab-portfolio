-- Books on and off (Mike, Nov 6: "I need the ability to turn on or off different books for EVERYTHING", "like one universal
-- off switch for novig"). Each account turns off any of FanDuel, DraftKings and Novig, never all three: the apps then show
-- each pick at the best book you have on (or not at all), price parlays, Build, promos and ladders at your books only,
-- hide what only a book that's off has (Novig challenges), and the worker's alerts follow the same switches.
alter table user_settings add column if not exists books_off text[] not null default '{}'
  check (books_off <@ array['FanDuel', 'DraftKings', 'Novig']::text[] and cardinality(books_off) < 3);

-- Every book's own read of a card bet (books.per_book): its line, price, EV, the tier and units it earns as if it were the
-- only book, and its link, so an account with the chosen book off sees the bet at another of its books.
alter table offers add column if not exists books jsonb;
