-- Your own order of the wall's tiles (Mike, Oct 25: drag them into place on the web; web/lib/order.ts): ESPN game keys
-- ("nfl:401772...", lib/live.ts). Tiles not in the list follow in the wall's own order. Per account, like the ban list.
alter table user_settings add column if not exists wall_order jsonb not null default '[]'::jsonb;
