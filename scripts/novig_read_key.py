"""Make a read-only Novig key for the worker's sync, to replace the management key in Railway (Oct 23).

The sync (`betlab.novig_sync`) only reads fills and positions, so it needs `management::read`: it can't trade, open
subaccounts, move money or make keys. Mike runs this once, signed by the management key now in Railway:

    railway run --service worker python scripts/novig_read_key.py

(`railway run` puts the worker's NOVIG_KEY_ID and NOVIG_PRIVATE_KEY in the environment for this one command; a local
.env with both works too.) It makes an Ed25519 keypair on this PC, registers the public half with POST /v3/keys (which
always issues `management::read`), checks the new key can read the cash wallet's fills, and writes the private half to
a file in your home folder, never the repo. It prints only the new key's id (not a secret) and the file's path.

Then, by hand:
1. Railway, worker service: NOVIG_KEY_ID = the printed id; NOVIG_PRIVATE_KEY = the file's whole contents. Redeploy.
2. After the next pregame tick's runs row says 'novig-sync: N fills', revoke the management key in Novig's profile
   and delete the file.

Usage: python scripts/novig_read_key.py [--name "BetLab read"] [--out PATH]
"""

import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from betlab import novig_sync as N  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", default="BetLab read")
    ap.add_argument("--out", default=str(Path.home() / "novig_betlab_read_key.pem"))
    args = ap.parse_args()

    mgmt = N.client()
    if mgmt is None:
        print("NOVIG_KEY_ID / NOVIG_PRIVATE_KEY not set: run it under `railway run --service worker`.")
        return 1
    out = Path(args.out)
    if out.exists():
        print(f"{out} already exists: move it or pass --out.")
        return 1

    key = ed25519.Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    made = mgmt.post("/v3/keys", {"name": args.name, "publicKey": public, "algorithm": "Ed25519"})
    key_id = made["keyId"]

    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", newline="\n") as f:
        f.write(private)

    fills = N.Client(key_id, private).pages("/v3/portfolio/fills")
    print(f"New management::read key: {key_id} (it reads {len(fills)} fills from the cash wallet)")
    print(f"Its private key is in {out}")
    print("Railway, worker: NOVIG_KEY_ID = that id, NOVIG_PRIVATE_KEY = the file's contents; redeploy. "
          "Once the next 'novig-sync' runs row reads fills, revoke the management key in Novig and delete the file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
