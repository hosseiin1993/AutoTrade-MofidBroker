from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path

from autotrade.broker.constants import MIN_TOKEN_LEN

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
UNKNOWN_EXP_TTL_S = 3600


def account_fingerprint(username: str) -> str:
    return hashlib.sha256((username or "").strip().encode("utf-8")).hexdigest()[:16]


def jwt_expiry(token: str) -> int | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except Exception:
        return None
    exp = payload.get("exp") if isinstance(payload, dict) else None
    if isinstance(exp, (int, float)):
        return int(exp)
    return None


def save_token(
    token: str,
    path: Path,
    *,
    account_hint: str | None = None,
    now_fn=time.time,
) -> dict:
    token = (token or "").strip()
    if len(token) < MIN_TOKEN_LEN:
        raise ValueError("Refusing to cache a token that is too short.")

    now = int(now_fn())
    exp = jwt_expiry(token)
    record = {
        "version": CACHE_VERSION,
        "token": token,
        "saved_at": now,
        "expires_at": exp if exp is not None else now + UNKNOWN_EXP_TTL_S,
        "expiry_from_claim": exp is not None,
        "account": account_hint,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        try:
            os.chmod(tmp_name, 0o600)
        except OSError:
            pass
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    return {k: v for k, v in record.items() if k != "token"}


def load_token(
    path: Path,
    *,
    min_validity_s: int = 120,
    account_hint: str | None = None,
    now_fn=time.time,
) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("Cached token unreadable (%s) — discarding.", exc)
        clear_token(path)
        return None

    if not isinstance(record, dict):
        clear_token(path)
        return None

    stored = record.get("account")
    if account_hint and stored and stored != account_hint:
        logger.warning("Cached token belongs to another account — discarding.")
        clear_token(path)
        return None

    token = record.get("token")
    if not isinstance(token, str) or len(token) < MIN_TOKEN_LEN:
        clear_token(path)
        return None

    expires_at = record.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        clear_token(path)
        return None

    remaining = float(expires_at) - float(now_fn())
    if remaining < float(min_validity_s):
        logger.info(
            "Cached token has %ds left (need %d) — logging in fresh.",
            int(remaining),
            int(min_validity_s),
        )
        clear_token(path)
        return None
    return token


def describe(path: Path, now_fn=time.time) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
    except (OSError, ValueError):
        return "no cached token"
    if not isinstance(record, dict):
        return "no cached token"
    expires_at = record.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        return "cached token (expiry unknown)"
    remaining = int(float(expires_at) - float(now_fn()))
    if remaining <= 0:
        return "cached token expired"
    minutes, seconds = divmod(remaining, 60)
    return f"cached token valid for {minutes}m{seconds:02d}s"


def clear_token(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("Could not delete token cache: %s", exc)
        return False
