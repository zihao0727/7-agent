from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pymysql
from dotenv import dotenv_values

_initialized = False
_DOTENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")


def _config_value(key: str, default: str) -> str:
    value = _DOTENV.get(key)
    if value not in (None, ""):
        return str(value)
    return os.getenv(key, default)


def _mysql_config(include_db: bool = True) -> dict[str, Any]:
    config: dict[str, Any] = {
        "host": _config_value("MYSQL_HOST", "localhost"),
        "port": int(_config_value("MYSQL_PORT", "3306")),
        "user": _config_value("MYSQL_USER", "root"),
        "password": _config_value("MYSQL_PASSWORD", ""),
        "charset": "utf8mb4",
        "autocommit": False,
        "cursorclass": pymysql.cursors.Cursor,
    }
    if include_db:
        config["database"] = _config_value("MYSQL_DATABASE", "sevnx_agent")
    return config


class AsyncCursor:
    def __init__(self, cursor: pymysql.cursors.Cursor):
        self._cursor = cursor

    @property
    def lastrowid(self) -> int:
        return int(self._cursor.lastrowid or 0)

    async def execute(self, query: str, params: Any = None) -> int:
        return await asyncio.to_thread(self._cursor.execute, query, params)

    async def fetchone(self) -> Any:
        return await asyncio.to_thread(self._cursor.fetchone)

    async def fetchall(self) -> Any:
        return await asyncio.to_thread(self._cursor.fetchall)

    async def __aenter__(self) -> "AsyncCursor":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await asyncio.to_thread(self._cursor.close)


class AsyncConnection:
    def __init__(self, connection: pymysql.connections.Connection):
        self._connection = connection

    def cursor(self, cursor_class: type[pymysql.cursors.Cursor] | None = None) -> AsyncCursor:
        if cursor_class is None:
            raw_cursor = self._connection.cursor()
        else:
            raw_cursor = self._connection.cursor(cursor=cursor_class)
        return AsyncCursor(raw_cursor)

    async def commit(self) -> None:
        await asyncio.to_thread(self._connection.commit)

    async def rollback(self) -> None:
        await asyncio.to_thread(self._connection.rollback)

    async def close(self) -> None:
        await asyncio.to_thread(self._connection.close)


async def connect_auth_db() -> None:
    global _initialized
    if _initialized:
        return

    try:
        connection = await asyncio.to_thread(pymysql.connect, **_mysql_config())
        await asyncio.to_thread(connection.close)
    except pymysql.err.OperationalError as exc:
        if not exc.args or int(exc.args[0]) != 1049:
            raise
        db_name = _config_value("MYSQL_DATABASE", "sevnx_agent")
        bootstrap = await asyncio.to_thread(
            pymysql.connect,
            **_mysql_config(include_db=False),
        )
        try:
            def _bootstrap_create() -> None:
                with bootstrap.cursor() as cursor:
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                bootstrap.commit()

            await asyncio.to_thread(_bootstrap_create)
        finally:
            await asyncio.to_thread(bootstrap.close)

    await initialize_auth_tables()
    _initialized = True


async def initialize_auth_tables() -> None:
    create_users = """
    CREATE TABLE IF NOT EXISTS users (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      email VARCHAR(255) NOT NULL,
      display_name VARCHAR(80) NULL,
      avatar_url MEDIUMTEXT NULL,
      password_hash VARCHAR(255) NOT NULL,
      is_active TINYINT(1) NOT NULL DEFAULT 1,
      email_verified_at DATETIME NULL,
      last_login_at DATETIME NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY uq_users_email (email)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """

    create_codes = """
    CREATE TABLE IF NOT EXISTS email_verification_codes (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      email VARCHAR(255) NOT NULL,
      purpose VARCHAR(32) NOT NULL,
      code_hash CHAR(64) NOT NULL,
      expires_at DATETIME NOT NULL,
      used_at DATETIME NULL,
      request_ip VARCHAR(64) NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_codes_email_purpose_created (email, purpose, created_at),
      INDEX idx_codes_expires_at (expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """

    create_tokens = """
    CREATE TABLE IF NOT EXISTS auth_tokens (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      user_id BIGINT UNSIGNED NOT NULL,
      token_hash CHAR(64) NOT NULL,
      user_agent VARCHAR(255) NULL,
      client_ip VARCHAR(64) NULL,
      expires_at DATETIME NOT NULL,
      revoked_at DATETIME NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY uq_auth_tokens_token_hash (token_hash),
      INDEX idx_auth_tokens_user_id (user_id),
      INDEX idx_auth_tokens_expires_at (expires_at),
      CONSTRAINT fk_auth_tokens_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """

    create_lark_accounts = """
    CREATE TABLE IF NOT EXISTS lark_accounts (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      user_id BIGINT UNSIGNED NOT NULL,
      name VARCHAR(80) NOT NULL,
      app_id VARCHAR(128) NOT NULL,
      app_secret TEXT NOT NULL,
      brand VARCHAR(16) NOT NULL DEFAULT 'feishu',
      profile_name VARCHAR(128) NOT NULL,
      is_default TINYINT(1) NOT NULL DEFAULT 0,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY uq_lark_accounts_user_name (user_id, name),
      UNIQUE KEY uq_lark_accounts_user_profile (user_id, profile_name),
      INDEX idx_lark_accounts_user_id (user_id),
      CONSTRAINT fk_lark_accounts_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """

    async with get_auth_conn() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(create_users)
            await cursor.execute(create_codes)
            await cursor.execute(create_tokens)
            await cursor.execute(create_lark_accounts)
            try:
                await cursor.execute("ALTER TABLE users ADD COLUMN avatar_url MEDIUMTEXT NULL AFTER display_name")
            except Exception as exc:
                if "Duplicate column name" not in str(exc):
                    raise


async def disconnect_auth_db() -> None:
    global _initialized
    _initialized = False


def get_auth_pool() -> None:
    return None


@asynccontextmanager
async def get_auth_conn():
    connection = await asyncio.to_thread(pymysql.connect, **_mysql_config())
    wrapper = AsyncConnection(connection)
    try:
        yield wrapper
        await wrapper.commit()
    except Exception:
        await wrapper.rollback()
        raise
    finally:
        await wrapper.close()
