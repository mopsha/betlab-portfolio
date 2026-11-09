-- 0008: the other book's line, price and EV on each offer (DraftKings day 1, Oct 12: books.select attaches them and
-- publish._offer sends them). Day 1 shipped without this migration, so every publish failed from 2:02 PM ET Oct 12
-- until it ran (the MNF fun ticket locked and alerted but never reached the app).
alter table offers add column if not exists other_book text;
alter table offers add column if not exists other_point numeric;
alter table offers add column if not exists other_price numeric;
alter table offers add column if not exists other_ev numeric;
