-- The ban list (Mike, Oct 25): players and teams BetLab never gives bets on. Games and players stay visible; the
-- worker leaves banned legs out of tickets, slips and pick alerts, and the apps leave banned bets out of what they
-- suggest. Entries are {"kind": "player" | "team", "name": "..."}; matched by src/betlab/bans.py, web/lib/bans.ts and
-- ios/BetLab/Bans.swift against tests/fixtures/bans.json.
alter table user_settings add column if not exists bans jsonb not null default '[]'::jsonb;
