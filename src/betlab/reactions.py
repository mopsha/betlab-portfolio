"""Reaction alerts (Nov 6, supabase 0042): a friend reacts to your bet in the Friends feed, and your phone hears it.

The worker runs `run` every minute with the leg alerts. Each reaction from the last hour that hasn't gone out is sent to the
bet's owner once: "Sam 🔥 your bet", with the bet's name. Keyed in `alerts_sent` by bet, reactor and reaction
("react:<bet>:<user>:<reaction>"), so changing to another one sends again and taking it back and giving it again doesn't.
An account can turn them off (notify.reactions) or hold them through quiet hours (alert_prefs.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from betlab import alert_prefs, leg_alerts

EMOJI = {"fire": "🔥", "money": "💰", "sweat": "😬", "skull": "💀", "pray": "🙏", "goat": "🐐"}   # the apps' REACTIONS

NEW_SQL = """
select r.bet_id::text, r.user_id::text, r.reaction, coalesce(p.name, 'A friend'), b.user_id::text, b.price, b.label, b.legs,
       us.notify
from bet_reactions r join bets b on b.bet_id = r.bet_id
left join profiles p on p.user_id = r.user_id
left join user_settings us on us.user_id = b.user_id
where r.created_at > now() - interval '1 hour'
"""


def key(bet_id: str, user_id: str, reaction: str) -> str:
    return f"react:{bet_id}:{user_id}:{reaction}"


def message(who: str, reaction: str, bet: dict) -> dict:
    """The notification: who and their emoji, then the bet by name (leg_alerts.bet_name)."""
    legs = bet.get("legs") or []
    return {"title": f"{who} {EMOJI.get(reaction, '')} your bet".replace("  ", " "),
            "body": leg_alerts.bet_name(bet, len(legs)),
            "url": "/bets", "tag": f"react-{bet['bet_id']}"}


def pending(rows: list[tuple], sent: set[str]) -> list[tuple[str, str, dict, dict | None]]:
    """(key, owner, message, notify) for each reaction not sent yet."""
    out = []
    for bet_id, user_id, reaction, name, owner, price, label, legs, notify in rows:
        k = key(bet_id, user_id, reaction)
        if k in sent or reaction not in EMOJI or user_id == owner:
            continue
        bet = {"bet_id": bet_id, "price": price, "label": label, "legs": legs or []}
        out.append((k, owner, message(name, reaction, bet), notify))
    return out


def run(send: Callable | None = None, db_url: str | None = None, now: datetime | None = None) -> str:
    """One minute's check; returns a line for the runs log ("" when nothing went out)."""
    from betlab import alerts, config

    send = send or alerts._send
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    if not db_url:
        return ""
    now = now or datetime.now(timezone.utc)
    private_key = config.secret("VAPID_PRIVATE_KEY") or ""
    import psycopg

    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
        rows = c.execute(NEW_SQL).fetchall()
        if not rows:
            return ""
        sent = {r[0] for r in c.execute("select pick_id from alerts_sent where pick_id like 'react:%'").fetchall()}
        lines = []
        for k, owner, msg, notify in pending(rows, sent):
            prefs = alert_prefs.clean(notify)
            delivered = 0
            if not prefs["reactions"]:
                pass
            elif alert_prefs.in_quiet(prefs, now):
                alerts.hold(c, owner, msg, now + timedelta(hours=12))
            else:
                delivered = alerts.deliver(c, owner, msg, send, private_key)[0]
                lines.append(f"{msg['title']}: {msg['body']} -> {delivered} device(s)")
            c.execute("insert into alerts_sent (pick_id, recipients) values (%s, %s) on conflict do nothing", [k, delivered])
    return "\n".join(lines)
