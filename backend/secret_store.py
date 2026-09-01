from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from backend.config import get_settings


_PREFIX = "enc:v1:"


def _fernet() -> Fernet | None:
    settings = get_settings()
    key = settings.credential_encryption_key.strip()
    if not key:
        if settings.app_env.lower() in {"production", "prod"}:
            raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is required in production")
        return None
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_secret(value: str) -> str:
    text = str(value or "")
    if text.startswith(_PREFIX):
        return text
    fernet = _fernet()
    if fernet is None:
        return text
    token = fernet.encrypt(text.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_secret(value: str) -> str:
    text = str(value or "")
    if not text.startswith(_PREFIX):
        return text
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError("Encrypted credentials require CREDENTIAL_ENCRYPTION_KEY")
    try:
        return fernet.decrypt(text[len(_PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("Unable to decrypt stored credential") from exc
