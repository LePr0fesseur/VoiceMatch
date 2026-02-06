"""Admin authentication module."""

import hashlib
import hmac
import secrets
import time

from .config import ADMIN_SECRET_KEY, ADMIN_SESSION_MAX_AGE


def hash_password(password: str) -> str:
    """Hash a password with a random salt using PBKDF2."""
    salt = secrets.token_hex(16)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    )
    return f"{salt}:{hash_bytes.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt, hash_hex = stored_hash.split(":", 1)
        hash_bytes = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 100_000
        )
        return hmac.compare_digest(hash_bytes.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def create_session_token() -> str:
    """Create a signed session token with timestamp."""
    timestamp = str(int(time.time()))
    token = secrets.token_hex(32)
    payload = f"{timestamp}:{token}"
    signature = hmac.new(
        ADMIN_SECRET_KEY.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}:{signature}"


def verify_session_token(session: str) -> bool:
    """Verify a session token is valid and not expired."""
    try:
        parts = session.split(":")
        if len(parts) != 3:
            return False
        timestamp, token, signature = parts
        payload = f"{timestamp}:{token}"
        expected = hmac.new(
            ADMIN_SECRET_KEY.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        if time.time() - int(timestamp) > ADMIN_SESSION_MAX_AGE:
            return False
        return True
    except Exception:
        return False
