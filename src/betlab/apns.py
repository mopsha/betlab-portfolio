"""Pick alerts to the native iPhone app, through Apple's push service (APNs), 2026-10-14.

The app saves its device token in `push_subscriptions` as endpoint 'apns:<environment>:<token>' (sandbox for builds
installed from Xcode, production for TestFlight and the App Store; migration 0011). alerts.py sends those rows here and
every other row through Web Push, so new picks, locked tickets, problems and the test alert all reach the iPhone too.

Keys (Mike made the key in the Apple Developer site and pasted these into Railway; never print them): APNS_KEY_P8 (the
.p8 file's text), APNS_KEY_ID, APNS_TEAM_ID. Each request carries a short token signed with the key (ES256), reused for
up to 45 minutes as Apple asks. Apple speaks HTTP/2 only (httpx with h2).
"""

from __future__ import annotations

import base64
import json
import time

from betlab import config

TOPIC = "com.mopsha.betlab"            # the app's bundle id
HOSTS = {"sandbox": "https://api.sandbox.push.apple.com", "production": "https://api.push.apple.com"}
TOKEN_TTL = 45 * 60
GONE = {"BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"}   # the device is gone: drop its row

_token: tuple[str, float] | None = None
_client = None


def configured() -> bool:
    return all(config.secret(k) for k in ("APNS_KEY_P8", "APNS_KEY_ID", "APNS_TEAM_ID"))


def is_apns(endpoint: str) -> bool:
    return str(endpoint).startswith("apns:")


def parse(endpoint: str) -> tuple[str, str] | None:
    """'apns:sandbox:<hex token>' -> ('sandbox', token)."""
    parts = str(endpoint).split(":")
    return (parts[1], parts[2]) if len(parts) == 3 and parts[0] == "apns" and parts[1] in HOSTS and parts[2] else None


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _pem(p8: str) -> bytes:
    """The key as PEM, whether pasted whole, with literal \\n, or as the bare base64 body."""
    text = p8.strip().replace("\\n", "\n")
    if "BEGIN" not in text:
        body = "".join(text.split())
        text = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(body[i:i + 64] for i in range(0, len(body), 64)) + "\n-----END PRIVATE KEY-----"
    return text.encode()


def make_jwt(p8: str, key_id: str, team_id: str, now: float | None = None) -> str:
    """The provider token APNs wants: ES256 over {alg, kid}.{iss, iat}, the signature as raw r||s."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    key = serialization.load_pem_private_key(_pem(p8), password=None)
    head = _b64(json.dumps({"alg": "ES256", "kid": key_id}, separators=(",", ":")).encode())
    claims = _b64(json.dumps({"iss": team_id, "iat": int(now or time.time())}, separators=(",", ":")).encode())
    r, s = decode_dss_signature(key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"{head}.{claims}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def _jwt() -> str:
    global _token
    if _token is None or time.time() - _token[1] > TOKEN_TTL:
        _token = (make_jwt(config.secret("APNS_KEY_P8"), config.secret("APNS_KEY_ID"), config.secret("APNS_TEAM_ID")), time.time())
    return _token[0]


def payload(msg: dict) -> dict:
    """A web alert ({title, body, url, tag}) as an APNs notification."""
    return {"aps": {"alert": {"title": msg["title"], "body": msg["body"]}, "sound": "default", "thread-id": "betlab"},
            "url": msg.get("url", "/")}


def send(sub: dict, msg: dict, client=None) -> int:
    """Send one alert; returns the HTTP status like Web Push does: 200 on success, 410 when the device is gone
    (alerts.py then removes its row), 0 when it couldn't be sent at all."""
    p = parse(sub.get("endpoint", ""))
    if not p or not configured():
        return 0
    env, token = p
    headers = {"apns-topic": TOPIC, "apns-push-type": "alert", "apns-priority": "10",
               "apns-expiration": str(int(time.time()) + 3600)}
    if msg.get("tag"):
        headers["apns-collapse-id"] = str(msg["tag"])[:64]
    return post(env, token, headers, payload(msg), client)


def post(env: str, token: str, headers: dict, body: dict, client=None) -> int:
    """One push to one device token (alerts here, Live Activities from live_activity.py): 200, 410 when the token is
    gone, another status Apple answered, or 0 when it couldn't be sent at all."""
    global _client
    if env not in HOSTS or not configured():
        return 0
    try:
        if client is None:
            import httpx

            _client = _client or httpx.Client(http2=True, timeout=15)
            client = _client
        r = client.post(f"{HOSTS[env]}/3/device/{token}", headers={"authorization": f"bearer {_jwt()}", **headers},
                        content=json.dumps(body, separators=(",", ":")))
    except Exception as e:                     # network trouble: report it, keep the device
        print(f"apns: send failed ({type(e).__name__})")
        return 0
    if r.status_code == 200:
        return 200
    try:
        reason = r.json().get("reason", "")
    except Exception:
        reason = ""
    print(f"apns: {r.status_code} {reason}".strip())
    return 410 if r.status_code == 410 or reason in GONE else r.status_code
