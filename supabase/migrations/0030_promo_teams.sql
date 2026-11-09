-- A token for some games only (Mike, Oct 31: "there's also boosts for specific games"): the teams it names, as typed or
-- read from the book's screen ("Knicks", "Ohio State"). The finder searches only games with one of them on a side
-- (web lib/promos.ts teamFits, iPhone Promos.teamFits); null: any game.
alter table promos add column if not exists teams text[];
