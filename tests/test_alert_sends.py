"""One device's error never stops the alert loop (alerts._send, _safe; Nov 9)."""

import sys
import types

import requests

from betlab import alerts
from tests.test_alerts import NOW, db  # noqa: F401 - the fake database fixture


def test_one_devices_error_never_stops_the_loop(db):  # noqa: F811
    """A web device's timeout (requests, not WebPushException) escaped the loop before alerts_sent was written: the
    next tick sent the same picks again to the devices before it, and the ones after it got nothing."""
    db.subs = [("u1", "https://push/a", "k", "s"), ("u1", "https://push/slow", "k", "s"), ("u1", "https://push/b", "k", "s")]
    got = []

    def send(sub, msg, key):
        if sub["endpoint"].endswith("slow"):
            raise requests.Timeout("read timed out")
        got.append(sub["endpoint"])
        return 201

    out = alerts.run(now=NOW, send=send, db_url="postgres://x", private_key="k")
    assert "sent to 2 of 3 device(s)" in out
    assert set(got) == {"https://push/a", "https://push/b"} and db.sent == {"p0", "p1"}


def test_web_push_connection_errors_are_a_failed_send(monkeypatch):
    def webpush(*a, **k):
        raise requests.ConnectionError("reset")
    fake = types.SimpleNamespace(webpush=webpush, WebPushException=type("WebPushException", (Exception,), {}))
    monkeypatch.setitem(sys.modules, "pywebpush", fake)
    assert alerts._send_webpush({"endpoint": "https://push/a", "p256dh": "k", "auth": "s"}, {"tag": "t"}, "key") == 0
