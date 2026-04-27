from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

import bcrypt

AUTH_TOKEN_TTL_DAYS = 14
REGISTER_CODE_TTL_MINUTES = 10


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def generate_numeric_code(length: int = 6) -> str:
    digits = "".join(secrets.choice("0123456789") for _ in range(length))
    return digits


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def verify_code(raw_code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(raw_code), code_hash)


def new_token_pair() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, token_hash


def utcnow() -> datetime:
    return datetime.now()


def auth_token_expires_at() -> datetime:
    return utcnow() + timedelta(days=AUTH_TOKEN_TTL_DAYS)


def register_code_expires_at() -> datetime:
    return utcnow() + timedelta(minutes=REGISTER_CODE_TTL_MINUTES)
