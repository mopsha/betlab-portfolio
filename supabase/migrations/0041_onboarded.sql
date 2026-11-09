-- First-run welcome (Nov 5, idea #60): a new account sees it once. Everyone here today has been using the apps, so they're done.
alter table user_settings add column if not exists onboarded_at timestamptz;
update user_settings set onboarded_at = now() where onboarded_at is null;
