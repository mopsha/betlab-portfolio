-- The native iPhone app's push alerts (2026-10-14). An iPhone registers with Apple (APNs), not Web Push: its row in
-- push_subscriptions has endpoint 'apns:<environment>:<device token>' (sandbox for builds installed from Xcode,
-- production for TestFlight and the App Store) and no Web Push keys. alerts.py sends those rows through APNs.

alter table push_subscriptions drop constraint push_subscriptions_endpoint_check;
alter table push_subscriptions add constraint push_subscriptions_endpoint_check
  check (endpoint like 'https://%' or endpoint ~ '^apns:(sandbox|production):[0-9a-f]{32,200}$');

alter table push_subscriptions alter column p256dh drop not null;
alter table push_subscriptions alter column auth drop not null;
alter table push_subscriptions add constraint push_subscriptions_keys_check
  check (endpoint like 'apns:%' or (p256dh is not null and auth is not null));
