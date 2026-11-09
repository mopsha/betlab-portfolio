"""The iPhone app's alerts through Apple (apns.py): the signed token, the endpoint format, the payload, gone devices,
and the routing in alerts.py. No network: a throwaway key and a fake HTTP client."""

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from betlab import alerts, apns

TOKEN = "ab" * 32


@pytest.fixture
def key():
    return ec.generate_private_key(ec.SECP256R1())


def _p8(key) -> str:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@pytest.mark.parametrize("form", ["pem", "escaped", "bare"])
def test_the_token_is_es256_signed_with_the_key(key, form):
    pem = _p8(key)
    text = {"pem": pem, "escaped": pem.replace("\n", "\\n"),
            "bare": "".join(pem.splitlines()[1:-1])}[form]          # how a key might be pasted into Railway
    jwt = apns.make_jwt(text, "KEY1234567", "YOUR_TEAM_ID", now=1_800_000_000)
    head, claims, sig = jwt.split(".")
    assert json.loads(_unb64(head)) == {"alg": "ES256", "kid": "KEY1234567"}
    assert json.loads(_unb64(claims)) == {"iss": "YOUR_TEAM_ID", "iat": 1_800_000_000}
    raw = _unb64(sig)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    key.public_key().verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))   # raises if wrong


def test_endpoints_and_payload():
    assert apns.parse(f"apns:sandbox:{TOKEN}") == ("sandbox", TOKEN)
    assert apns.parse(f"apns:production:{TOKEN}") == ("production", TOKEN)
    assert apns.parse(f"apns:staging:{TOKEN}") is None and apns.parse("https://push/a") is None
    p = apns.payload({"title": "NHL pick", "body": "MTL ML +108", "url": "/", "tag": "p1"})
    assert p == {"aps": {"alert": {"title": "NHL pick", "body": "MTL ML +108"}, "sound": "default", "thread-id": "betlab"}, "url": "/"}


class _Resp:
    def __init__(self, status, reason=""):
        self.status_code, self._reason = status, reason

    def json(self):
        return {"reason": self._reason}


class _Client:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def post(self, url, headers, content):
        self.calls.append((url, headers, json.loads(content)))
        return self.resp


@pytest.fixture
def keys(monkeypatch, key):
    vals = {"APNS_KEY_P8": _p8(key), "APNS_KEY_ID": "KEY1234567", "APNS_TEAM_ID": "YOUR_TEAM_ID"}
    monkeypatch.setattr(apns.config, "secret", lambda name: vals.get(name))
    monkeypatch.setattr(apns, "_token", None)


def test_send_posts_to_the_right_host_and_maps_gone_devices(keys):
    ok = _Client(_Resp(200))
    msg = {"title": "t", "body": "b", "tag": "p1"}
    assert apns.send({"endpoint": f"apns:sandbox:{TOKEN}"}, msg, client=ok) == 200
    url, headers, body = ok.calls[0]
    assert url == f"https://api.sandbox.push.apple.com/3/device/{TOKEN}"
    assert headers["apns-topic"] == "com.mopsha.betlab" and headers["apns-push-type"] == "alert"
    assert headers["authorization"].startswith("bearer ") and headers["apns-collapse-id"] == "p1"
    prod = _Client(_Resp(200))
    apns.send({"endpoint": f"apns:production:{TOKEN}"}, msg, client=prod)
    assert prod.calls[0][0].startswith("https://api.push.apple.com/")
    assert apns.send({"endpoint": f"apns:sandbox:{TOKEN}"}, msg, client=_Client(_Resp(410, "Unregistered"))) == 410
    assert apns.send({"endpoint": f"apns:sandbox:{TOKEN}"}, msg, client=_Client(_Resp(400, "BadDeviceToken"))) == 410
    assert apns.send({"endpoint": f"apns:sandbox:{TOKEN}"}, msg, client=_Client(_Resp(403, "ExpiredProviderToken"))) == 403


def test_no_keys_sends_nothing(monkeypatch):
    monkeypatch.setattr(apns.config, "secret", lambda name: None)
    assert apns.send({"endpoint": f"apns:sandbox:{TOKEN}"}, {"title": "t", "body": "b"}, client=_Client(_Resp(200))) == 0


def test_alerts_route_iphones_to_apple_and_browsers_to_web_push(monkeypatch):
    got = []
    monkeypatch.setattr(apns, "send", lambda sub, msg: got.append(("apns", sub["endpoint"])) or 200)
    monkeypatch.setattr(alerts, "_send_webpush", lambda sub, msg, key: got.append(("web", sub["endpoint"])) or 201)
    assert alerts._send({"endpoint": f"apns:sandbox:{TOKEN}"}, {}, "k") == 200
    assert alerts._send({"endpoint": "https://push/a", "p256dh": "k", "auth": "s"}, {}, "k") == 201
    assert got == [("apns", f"apns:sandbox:{TOKEN}"), ("web", "https://push/a")]
