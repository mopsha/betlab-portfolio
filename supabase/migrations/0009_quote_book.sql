-- 0009: the book a typed parlay price is from (DraftKings day 4, Oct 12). A DraftKings quote is saved under the slip's
-- id + "~dk" (so one slip can hold both books' prices without changing the key); the fun ledger grades it from
-- DraftKings' own legs and its quote model learns DraftKings' parlay pricing apart from FanDuel's.
alter table quotes add column if not exists book text not null default 'FanDuel';
