"""Telegram WebApp initData validation."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException, status


def _compute_hash(data_check_string: str, bot_token: str) -> str:
    """Compute HMAC-SHA256 of data_check_string."""
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(init_data: str, bot_token: str, max_age_sec: int = 24 * 3600) -> dict:
    """
    Validate Telegram WebApp initData.

    Steps:
    - parse key=value pairs
    - build data_check_string sorted by key excluding 'hash'
    - compute HMAC-SHA256 with secret key = HMAC("WebAppData", bot_token)
    - compare with provided hash
    - check auth_date not older than max_age_sec
    """
    # Parse init data
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    provided_hash = parsed.pop("hash", None)
    if not provided_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="hash missing in init data")

    # Build data_check_string
    data_check_items = [f"{k}={v}" for k, v in sorted(parsed.items())]
    data_check_string = "\n".join(data_check_items)

    # Compute expected hash
    expected_hash = _compute_hash(data_check_string, bot_token)
    if not hmac.compare_digest(provided_hash, expected_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid init data hash")

    # Check auth_date
    auth_date = int(parsed.get("auth_date", "0"))
    if auth_date and time.time() - auth_date > max_age_sec:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="init data expired")

    # Decode user json if present
    if "user" in parsed:
        try:
            parsed["user"] = json.loads(parsed["user"])
        except json.JSONDecodeError:
            pass

    return parsed

