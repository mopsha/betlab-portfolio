-- The theme each account last picked (Oct 25): the apps save it (web Settings, the iPhone's appearance), and the
-- worker's leg alerts speak "diva" to an account on Pink (src/betlab/leg_alerts.py; Mike: "it's for my girlfriend
-- call her diva or something"). Ids as web/lib/looks.ts and ios/BetLab/Theme.swift name them; "system" for none.
alter table user_settings add column if not exists theme text;
