from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

COOKIE_NAME = "investai_session"


def _b64_encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")



def _b64_decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii")).decode("utf-8")



def _sign(payload: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()



def build_session_cookie(username: str, secret_key: str, max_age_seconds: int) -> str:
    payload: dict[str, Any] = {
        "username": username,
        "exp": int(time.time()) + max_age_seconds,
    }
    encoded = _b64_encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    signature = _sign(encoded, secret_key)
    return f"{encoded}.{signature}"



def parse_session_cookie(cookie_value: str | None, secret_key: str) -> dict[str, Any] | None:
    if not cookie_value or "." not in cookie_value:
        return None
    encoded, signature = cookie_value.rsplit(".", 1)
    expected = _sign(encoded, secret_key)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64_decode(encoded))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload
