-- A token for certain kinds of leg (Mike, Nov 9: "there's boosts like td only or first td only"): every leg of the bet must be
-- one of these, in the Build packs' stat names ("tds" is an anytime TD, "first_td" a first TD scorer, "passing_yards", "points",
-- ...). Null for any. The apps check the names (web lib/promos.ts LEG_CHOICES, iPhone Promos.legChoices); the finder tests each
-- candidate leg with them (web builder.marketFits, iPhone Build.marketFits). No check constraint: a new kind is a code change.
alter table promos add column if not exists leg_kinds text[];
