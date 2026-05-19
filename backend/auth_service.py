from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from pymysql.cursors import DictCursor

from backend.auth_db import get_auth_conn
from backend.auth_mail import EmailDeliveryError, send_register_code
from backend.auth_security import (
    auth_token_expires_at,
    generate_numeric_code,
    hash_code,
    hash_password,
    new_token_pair,
    normalize_email,
    register_code_expires_at,
    utcnow,
    verify_code,
    verify_password,
)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


async def send_register_email_code(email: str, client_ip: str | None = None) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    now = utcnow()
    if "@" not in normalized_email:
        raise _bad_request("邮箱格式不正确")

    async with get_auth_conn() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "SELECT id FROM users WHERE email=%s LIMIT 1",
                (normalized_email,),
            )
            existing_user = await cursor.fetchone()
            if existing_user:
                raise HTTPException(status_code=409, detail="该邮箱已注册")

            await cursor.execute(
                """
                DELETE FROM email_verification_codes
                WHERE email=%s
                  AND purpose='register'
                  AND (expires_at < created_at OR expires_at < %s)
                """,
                (normalized_email, now),
            )

            await cursor.execute(
                """
                SELECT created_at
                FROM email_verification_codes
                WHERE email=%s AND purpose='register'
                ORDER BY id DESC
                LIMIT 1
                """,
                (normalized_email,),
            )
            latest_code = await cursor.fetchone()
            if latest_code and latest_code["created_at"]:
                if now - latest_code["created_at"] < timedelta(seconds=60):
                    raise HTTPException(status_code=429, detail="验证码发送过于频繁，请稍后再试")

            code = generate_numeric_code()
            await cursor.execute(
                """
                INSERT INTO email_verification_codes (email, purpose, code_hash, expires_at, request_ip)
                VALUES (%s, 'register', %s, %s, %s)
                """,
                (normalized_email, hash_code(code), register_code_expires_at(), client_ip),
            )

        try:
            await send_register_code(normalized_email, code)
        except EmailDeliveryError as exc:
            raise HTTPException(
                status_code=502,
                detail="Register code email delivery failed. Please check SMTP settings or try again later.",
            ) from exc

    return {"ok": True}


async def register_user(
    email: str,
    password: str,
    code: str,
    display_name: str | None,
    user_agent: str | None,
    client_ip: str | None,
) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    clean_name = (display_name or "").strip() or None

    if "@" not in normalized_email:
        raise _bad_request("邮箱格式不正确")
    if len(password or "") < 8:
        raise _bad_request("密码至少需要 8 位")
    if not code or len(code.strip()) != 6:
        raise _bad_request("验证码格式不正确")

    async with get_auth_conn() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "SELECT id FROM users WHERE email=%s LIMIT 1",
                (normalized_email,),
            )
            existing_user = await cursor.fetchone()
            if existing_user:
                raise HTTPException(status_code=409, detail="该邮箱已注册")

            await cursor.execute(
                """
                SELECT id, code_hash, expires_at, used_at
                FROM email_verification_codes
                WHERE email=%s AND purpose='register'
                ORDER BY id DESC
                LIMIT 1
                """,
                (normalized_email,),
            )
            verification_row = await cursor.fetchone()
            if not verification_row:
                raise HTTPException(status_code=404, detail="请先发送注册验证码")
            if verification_row["used_at"] is not None:
                raise _bad_request("验证码已使用，请重新获取")
            if verification_row["expires_at"] < utcnow():
                raise _bad_request("验证码已过期，请重新获取")
            if not verify_code(code.strip(), verification_row["code_hash"]):
                raise _bad_request("验证码不正确")

            password_hash = hash_password(password)
            now = utcnow()
            await cursor.execute(
                """
                INSERT INTO users (email, display_name, password_hash, email_verified_at, last_login_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (normalized_email, clean_name, password_hash, now, now),
            )
            user_id = cursor.lastrowid
            await cursor.execute(
                "UPDATE email_verification_codes SET used_at=%s WHERE id=%s",
                (now, verification_row["id"]),
            )

            raw_token, token_hash = new_token_pair()
            expires_at = auth_token_expires_at()
            await cursor.execute(
                """
                INSERT INTO auth_tokens (user_id, token_hash, user_agent, client_ip, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, token_hash, user_agent, client_ip, expires_at),
            )

    return {
        "access_token": raw_token,
        "token_type": "bearer",
        "user": {
            "id": int(user_id),
            "email": normalized_email,
            "display_name": clean_name,
            "avatar_url": None,
        },
    }


async def login_user(
    email: str,
    password: str,
    user_agent: str | None,
    client_ip: str | None,
) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    if "@" not in normalized_email:
        raise _bad_request("邮箱格式不正确")

    async with get_auth_conn() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT id, email, display_name, avatar_url, password_hash, is_active
                FROM users
                WHERE email=%s
                LIMIT 1
                """,
                (normalized_email,),
            )
            user = await cursor.fetchone()
            if not user or not verify_password(password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="邮箱或密码错误")
            if not user["is_active"]:
                raise HTTPException(status_code=403, detail="该账户已被停用")

            raw_token, token_hash = new_token_pair()
            expires_at = auth_token_expires_at()
            now = utcnow()
            await cursor.execute(
                """
                INSERT INTO auth_tokens (user_id, token_hash, user_agent, client_ip, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user["id"], token_hash, user_agent, client_ip, expires_at),
            )
            await cursor.execute(
                "UPDATE users SET last_login_at=%s WHERE id=%s",
                (now, user["id"]),
            )

    return {
        "access_token": raw_token,
        "token_type": "bearer",
        "user": {
            "id": int(user["id"]),
            "email": user["email"],
            "display_name": user["display_name"],
            "avatar_url": user.get("avatar_url"),
        },
    }


async def get_user_by_token(access_token: str) -> dict[str, Any] | None:
    token = (access_token or "").strip()
    if not token:
        return None

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    async with get_auth_conn() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                  users.id,
                  users.email,
                  users.display_name,
                  users.avatar_url,
                  users.is_active,
                  auth_tokens.id AS auth_token_id,
                  auth_tokens.expires_at,
                  auth_tokens.revoked_at
                FROM auth_tokens
                INNER JOIN users ON users.id = auth_tokens.user_id
                WHERE auth_tokens.token_hash=%s
                LIMIT 1
                """,
                (token_hash,),
            )
            row = await cursor.fetchone()

            if not row:
                return None
            if row["revoked_at"] is not None or row["expires_at"] < utcnow():
                return None
            if not row["is_active"]:
                return None
            return {
                "id": int(row["id"]),
                "email": row["email"],
                "display_name": row["display_name"],
                "avatar_url": row.get("avatar_url"),
                "auth_token_id": int(row["auth_token_id"]),
            }


async def update_user_avatar(user_id: int, avatar_url: str | None) -> dict[str, Any]:
    clean_avatar = (avatar_url or "").strip() or None
    if clean_avatar is not None:
        if not clean_avatar.startswith("data:image/"):
            raise _bad_request("Avatar must be an image data URL")
        if len(clean_avatar) > 2_800_000:
            raise _bad_request("Avatar image is too large")

    async with get_auth_conn() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "UPDATE users SET avatar_url=%s WHERE id=%s",
                (clean_avatar, user_id),
            )
            await cursor.execute(
                "SELECT id, email, display_name, avatar_url FROM users WHERE id=%s LIMIT 1",
                (user_id,),
            )
            user = await cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": int(user["id"]),
        "email": user["email"],
        "display_name": user["display_name"],
        "avatar_url": user.get("avatar_url"),
    }


async def logout_user(access_token: str) -> None:
    token = (access_token or "").strip()
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    async with get_auth_conn() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE auth_tokens SET revoked_at=%s WHERE token_hash=%s AND revoked_at IS NULL",
                (utcnow(), token_hash),
            )
