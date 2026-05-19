from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pymysql.cursors import DictCursor

from backend.auth_db import get_auth_conn
from backend.config import get_settings

PROFILE_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")
SECRET_KEYS = {"app_secret", "access_token", "refresh_token", "token"}
LARK_SHORTCUT_COMMANDS: dict[str, set[str]] = {
    "base": {
        "advperm-disable",
        "advperm-enable",
        "base-copy",
        "base-create",
        "base-get",
        "dashboard-arrange",
        "dashboard-block-create",
        "dashboard-block-delete",
        "dashboard-block-get",
        "dashboard-block-list",
        "dashboard-block-update",
        "dashboard-create",
        "dashboard-delete",
        "dashboard-get",
        "dashboard-list",
        "dashboard-update",
        "data-query",
        "field-create",
        "field-delete",
        "field-get",
        "field-list",
        "field-search-options",
        "field-update",
        "form-create",
        "form-delete",
        "form-get",
        "form-list",
        "form-questions-create",
        "form-questions-delete",
        "form-questions-list",
        "form-questions-update",
        "form-update",
        "record-batch-create",
        "record-batch-update",
        "record-delete",
        "record-get",
        "record-history-list",
        "record-list",
        "record-search",
        "record-share-link-create",
        "record-upload-attachment",
        "record-upsert",
        "role-create",
        "role-delete",
        "role-get",
        "role-list",
        "role-update",
        "table-create",
        "table-delete",
        "table-get",
        "table-list",
        "table-update",
        "view-create",
        "view-delete",
        "view-get",
        "view-list",
        "view-rename",
        "workflow-create",
        "workflow-disable",
        "workflow-enable",
        "workflow-get",
        "workflow-list",
        "workflow-update",
    },
    "calendar": {"agenda", "create", "freebusy", "rsvp", "suggestion"},
    "contact": {"get-user", "search-user"},
    "docs": {
        "create",
        "fetch",
        "media-download",
        "media-insert",
        "media-preview",
        "media-upload",
        "search",
        "update",
        "whiteboard-update",
    },
    "drive": {
        "add-comment",
        "apply-permission",
        "create-folder",
        "create-shortcut",
        "delete",
        "download",
        "export",
        "export-download",
        "import",
        "move",
        "task_result",
        "upload",
    },
    "mail": {
        "decline-receipt",
        "draft-create",
        "draft-edit",
        "forward",
        "message",
        "messages",
        "reply",
        "reply-all",
        "send",
        "send-receipt",
        "signature",
        "thread",
        "triage",
        "watch",
    },
    "minutes": {"download", "search"},
    "sheets": {
        "append",
        "create",
        "export",
        "find",
        "info",
        "read",
        "replace",
        "write",
    },
    "task": {
        "assign",
        "comment",
        "complete",
        "create",
        "followers",
        "get-my-tasks",
        "get-related-tasks",
        "reminder",
        "reopen",
        "search",
        "set-ancestor",
        "subscribe-event",
        "tasklist-create",
        "tasklist-members",
        "tasklist-search",
        "tasklist-task-add",
        "update",
    },
    "vc": {"notes", "recording", "search"},
    "wiki": {"delete-space", "move", "node-create"},
}


@dataclass(frozen=True)
class LarkAccount:
    id: int
    user_id: int
    name: str
    app_id: str
    app_secret: str
    brand: str
    profile_name: str
    is_default: bool


def _safe_profile_name(user_id: int, name: str) -> str:
    clean_name = PROFILE_SAFE_RE.sub("_", name.strip().lower()).strip("_")
    return f"sevnx_u{user_id}_{clean_name or 'default'}"[:120]


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in SECRET_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _parse_json_or_text(stdout: str, stderr: str) -> Any:
    text = stdout.strip()
    if text:
        try:
            return _redact(json.loads(text))
        except json.JSONDecodeError:
            return text
    return stderr.strip()


def _redact_text(text: str, account: LarkAccount | None) -> str:
    if not account or not text:
        return text
    return text.replace(account.app_secret, "***")


def _config_dir(user_id: int | None = None) -> Path:
    settings = get_settings()
    configured = os.getenv("LARKSUITE_CLI_CONFIG_DIR") or settings.lark_cli_config_dir
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        return path if user_id is None else path / f"user_{int(user_id)}"
    root = Path.home() / ".lark-cli"
    return root if user_id is None else root / f"user_{int(user_id)}"


def _load_multi_app_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"apps": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"apps": []}
    if not isinstance(data, dict):
        return {"apps": []}
    apps = data.get("apps")
    if not isinstance(apps, list):
        data["apps"] = []
    return data


def normalize_lark_command_args(args: list[str]) -> list[str]:
    normalized = [str(item).strip() for item in args if str(item).strip()]
    if len(normalized) >= 2:
        domain = normalized[0]
        subcommand = normalized[1]
        if (
            not subcommand.startswith(("+", "-"))
            and subcommand in LARK_SHORTCUT_COMMANDS.get(domain, set())
        ):
            normalized[1] = f"+{subcommand}"
    return normalized


def _save_profile_with_file_secret(
    account: LarkAccount,
    *,
    users: list[Any] | None = None,
) -> dict[str, Any]:
    config_dir = _config_dir(account.user_id)
    secrets_dir = config_dir / "secrets"
    config_dir.mkdir(parents=True, exist_ok=True)
    secrets_dir.mkdir(parents=True, exist_ok=True)

    secret_path = secrets_dir / f"{account.profile_name}.secret"
    secret_path.write_text(account.app_secret, encoding="utf-8")

    config_path = config_dir / "config.json"
    config = _load_multi_app_config(config_path)
    apps = config.setdefault("apps", [])
    profile = {
        "name": account.profile_name,
        "appId": account.app_id,
        "appSecret": {"source": "file", "id": str(secret_path)},
        "brand": account.brand,
        "lang": "zh",
        "users": users or [],
    }

    replaced = False
    for idx, app in enumerate(apps):
        if isinstance(app, dict) and (
            app.get("name") == account.profile_name or app.get("appId") == account.profile_name
        ):
            existing_users = app.get("users") if app.get("appId") == account.app_id else []
            if not users:
                profile["users"] = existing_users if isinstance(existing_users, list) else []
            apps[idx] = profile
            replaced = True
            break
    if not replaced:
        apps.append(profile)

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "fallback": "file-secret-reference",
        "config_path": str(config_path),
        "profile": account.profile_name,
        "appId": account.app_id,
        "brand": account.brand,
    }


def _find_profile(config: dict[str, Any], account: LarkAccount) -> dict[str, Any] | None:
    for app in config.get("apps", []):
        if not isinstance(app, dict):
            continue
        if app.get("name") == account.profile_name or app.get("appId") == account.app_id:
            return app
    return None


def ensure_lark_cli_profile(account: LarkAccount) -> None:
    user_config_dir = _config_dir(account.user_id)
    user_config_path = user_config_dir / "config.json"
    user_config = _load_multi_app_config(user_config_path)
    if _find_profile(user_config, account):
        return

    root_config_path = _config_dir(None) / "config.json"
    root_profile = None
    if root_config_path.resolve() != user_config_path.resolve():
        root_profile = _find_profile(_load_multi_app_config(root_config_path), account)

    users = root_profile.get("users") if isinstance(root_profile, dict) else None
    _save_profile_with_file_secret(account, users=users if isinstance(users, list) else None)


async def _run_lark_cli(
    args: list[str],
    *,
    account: LarkAccount | None = None,
    stdin: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    env = os.environ.copy()
    env["LARKSUITE_CLI_CONFIG_DIR"] = str(_config_dir(account.user_id if account else None))
    env["LARK_CLI_NO_PROXY"] = "1"
    command = settings.lark_cli_binary
    exec_args = [command, *args]
    if os.name == "nt" and command.lower().endswith((".cmd", ".bat")):
        exec_args = ["cmd", "/c", command, *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *exec_args,
            env=env,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(stdin.encode("utf-8") if stdin is not None else None),
            timeout=timeout or settings.lark_cli_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise HTTPException(status_code=504, detail="lark-cli 执行超时") from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="未找到 lark-cli，请先安装 @larksuite/cli 或配置 LARK_CLI_BINARY",
        ) from exc

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    stdout = _redact_text(stdout, account)
    stderr = _redact_text(stderr, account)
    payload = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "data": _parse_json_or_text(stdout, stderr),
    }
    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=payload)
    return payload


def account_public(row: dict[str, Any] | LarkAccount) -> dict[str, Any]:
    if isinstance(row, LarkAccount):
        return {
            "id": row.id,
            "name": row.name,
            "app_id": row.app_id,
            "brand": row.brand,
            "profile_name": row.profile_name,
            "is_default": row.is_default,
        }
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "app_id": row["app_id"],
        "brand": row["brand"],
        "profile_name": row["profile_name"],
        "is_default": bool(row["is_default"]),
    }


async def list_lark_accounts(user_id: int) -> list[dict[str, Any]]:
    async with get_auth_conn() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT id, name, app_id, brand, profile_name, is_default
                FROM lark_accounts
                WHERE user_id=%s
                ORDER BY is_default DESC, id ASC
                """,
                (user_id,),
            )
            return [account_public(row) for row in await cursor.fetchall()]


async def get_lark_account(user_id: int, account_id: int | None = None) -> LarkAccount:
    where = "user_id=%s AND id=%s" if account_id is not None else "user_id=%s AND is_default=1"
    params: tuple[Any, ...] = (user_id, account_id) if account_id is not None else (user_id,)
    async with get_auth_conn() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                f"""
                SELECT id, user_id, name, app_id, app_secret, brand, profile_name, is_default
                FROM lark_accounts
                WHERE {where}
                ORDER BY id ASC
                LIMIT 1
                """,
                params,
            )
            row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="未找到飞书账户，请先绑定飞书机器人")
    return LarkAccount(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        name=row["name"],
        app_id=row["app_id"],
        app_secret=row["app_secret"],
        brand=row["brand"],
        profile_name=row["profile_name"],
        is_default=bool(row["is_default"]),
    )


async def upsert_lark_account(
    *,
    user_id: int,
    name: str,
    app_id: str,
    app_secret: str,
    brand: str,
    make_default: bool,
) -> dict[str, Any]:
    clean_name = name.strip() or "default"
    clean_brand = brand.strip().lower() or "feishu"
    if clean_brand not in {"feishu", "lark"}:
        raise HTTPException(status_code=400, detail="brand 只能是 feishu 或 lark")
    if not app_id.strip() or not app_secret.strip():
        raise HTTPException(status_code=400, detail="app_id 和 app_secret 不能为空")
    profile_name = _safe_profile_name(user_id, clean_name)

    async with get_auth_conn() as conn:
        async with conn.cursor(DictCursor) as cursor:
            if make_default:
                await cursor.execute(
                    "UPDATE lark_accounts SET is_default=0 WHERE user_id=%s",
                    (user_id,),
                )
            await cursor.execute(
                """
                INSERT INTO lark_accounts
                  (user_id, name, app_id, app_secret, brand, profile_name, is_default)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  app_id=VALUES(app_id),
                  app_secret=VALUES(app_secret),
                  brand=VALUES(brand),
                  profile_name=VALUES(profile_name),
                  is_default=VALUES(is_default)
                """,
                (
                    user_id,
                    clean_name,
                    app_id.strip(),
                    app_secret.strip(),
                    clean_brand,
                    profile_name,
                    1 if make_default else 0,
                ),
            )
            await cursor.execute(
                """
                SELECT id, name, app_id, brand, profile_name, is_default
                FROM lark_accounts
                WHERE user_id=%s AND name=%s
                LIMIT 1
                """,
                (user_id, clean_name),
            )
            row = await cursor.fetchone()
    return account_public(row)


async def delete_lark_account(user_id: int, account_id: int) -> None:
    async with get_auth_conn() as conn:
        async with conn.cursor() as cursor:
            deleted = await cursor.execute(
                "DELETE FROM lark_accounts WHERE user_id=%s AND id=%s",
                (user_id, account_id),
            )
    if not deleted:
        raise HTTPException(status_code=404, detail="未找到飞书账户")


def account_cli_prefix(account: LarkAccount) -> list[str]:
    return ["--profile", account.profile_name]


async def configure_lark_cli(account: LarkAccount) -> dict[str, Any]:
    args = [
        "--profile",
        account.profile_name,
        "config",
        "init",
        "--name",
        account.profile_name,
        "--app-id",
        account.app_id,
        "--app-secret-stdin",
    ]
    if account.brand == "lark":
        args.extend(["--brand", "lark"])
    try:
        return await _run_lark_cli(args, account=account, stdin=account.app_secret)
    except (PermissionError, OSError) as exc:
        return {
            "ok": True,
            "warning": f"当前环境无法通过子进程 stdin 写入 keychain（{exc}），已按 lark-cli 官方 file secret reference 方式写入 profile。",
            "data": _save_profile_with_file_secret(account),
        }
    except HTTPException as exc:
        detail_text = json.dumps(exc.detail, ensure_ascii=False)
        if "keychain unavailable" not in detail_text:
            raise
        return {
            "ok": True,
            "warning": "系统 keychain 不可用，已按 lark-cli 官方 file secret reference 方式写入 profile。",
            "data": _save_profile_with_file_secret(account),
        }


async def lark_auth_login(
    account: LarkAccount,
    *,
    recommend: bool = True,
    domains: list[str] | None = None,
    scopes: list[str] | None = None,
    no_wait: bool = True,
) -> dict[str, Any]:
    ensure_lark_cli_profile(account)
    args = [*account_cli_prefix(account), "auth", "login"]
    if recommend:
        args.append("--recommend")
    if domains:
        args.extend(["--domain", ",".join(domains)])
    if scopes:
        args.extend(["--scope", " ".join(scopes)])
    if no_wait:
        args.append("--no-wait")
    return await _run_lark_cli(args, account=account, timeout=120)


async def lark_auth_complete(account: LarkAccount, device_code: str) -> dict[str, Any]:
    code = (device_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="device_code 不能为空")
    ensure_lark_cli_profile(account)
    return await _run_lark_cli(
        [*account_cli_prefix(account), "auth", "login", "--device-code", code, "--json"],
        account=account,
        timeout=190,
    )


async def lark_auth_status(account: LarkAccount) -> dict[str, Any]:
    ensure_lark_cli_profile(account)
    return await _run_lark_cli(
        [*account_cli_prefix(account), "auth", "status"],
        account=account,
    )


async def run_lark_command(
    account: LarkAccount,
    args: list[str],
    *,
    add_format: bool = True,
    stdin: str | None = None,
) -> dict[str, Any]:
    ensure_lark_cli_profile(account)
    cli_args = [*account_cli_prefix(account), *normalize_lark_command_args(args)]
    if add_format:
        cli_args.extend(["--format", "json"])
    return await _run_lark_cli(
        cli_args,
        account=account,
        stdin=stdin,
    )
