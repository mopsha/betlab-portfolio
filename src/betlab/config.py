"""Paths, settings and secrets."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
# The Railway worker keeps data on a volume (docs/APP_PLAN.md): BETLAB_DATA_DIR / BETLAB_EXPORTS_DIR
# point there; everywhere else they default to the repo's folders.
DATA_DIR = Path(os.environ.get("BETLAB_DATA_DIR") or ROOT / "data")
CACHE_DIR = DATA_DIR / "cache"
EXPORTS_DIR = Path(os.environ.get("BETLAB_EXPORTS_DIR") or ROOT / "exports")


@cache
def settings() -> dict:
    """config/settings.yaml, loaded once per process (key meanings: config/README.md)."""
    return yaml.safe_load((CONFIG_DIR / "settings.yaml").read_text(encoding="utf-8"))


@cache
def ny_restrictions() -> dict:
    """config/ny_restrictions.yaml, loaded once per process."""
    return yaml.safe_load((CONFIG_DIR / "ny_restrictions.yaml").read_text(encoding="utf-8"))


def owner_user_id() -> str | None:
    """The app user whose bets the ledgers follow: OWNER_USER_ID if set, else settings.yaml (app)."""
    return secret("OWNER_USER_ID") or (settings().get("app") or {}).get("owner_user_id")


def secret(name: str) -> str | None:
    """Read a key from the environment (GitHub Secrets in CI) or the local .env file."""
    load_dotenv(ROOT / ".env", override=False)
    return os.environ.get(name) or None
