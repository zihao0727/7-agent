from __future__ import annotations

import json
from typing import Any

from backend.lark_service import get_lark_account, lark_auth_status, run_lark_command

from ..base import BaseTool, ToolExecutionError, ToolSchema


class LarkCliTool(BaseTool):
    name = "lark_cli"
    description = (
        "通过已绑定的飞书/Lark CLI 账户执行受控飞书操作。"
        "仅支持白名单动作：auth_status、send_message、create_doc、raw_api。"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["auth_status", "send_message", "create_doc", "raw_api"],
                        "description": "要执行的飞书动作。",
                    },
                    "account_id": {
                        "type": "integer",
                        "description": "可选，绑定的飞书账户 ID；不填则使用当前用户默认账户。",
                    },
                    "identity": {
                        "type": "string",
                        "enum": ["bot", "user", "auto"],
                        "description": "调用身份。发消息和机器人自动化优先使用 bot。",
                        "default": "bot",
                    },
                    "chat_id": {
                        "type": "string",
                        "description": "send_message 使用的飞书群聊或会话 ID，如 oc_xxx。",
                    },
                    "text": {
                        "type": "string",
                        "description": "send_message 的文本，或 create_doc 的 Markdown 内容。",
                    },
                    "title": {
                        "type": "string",
                        "description": "create_doc 的文档标题。",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                        "description": "raw_api 的 HTTP 方法。",
                    },
                    "path": {
                        "type": "string",
                        "description": "raw_api 的 OpenAPI 路径，必须以 /open-apis/ 开头。",
                    },
                    "params": {
                        "type": "object",
                        "description": "raw_api 的 URL/query 参数 JSON。",
                    },
                    "data": {
                        "type": "object",
                        "description": "raw_api 的请求体 JSON。",
                    },
                },
                "required": ["action"],
            },
        )

    async def execute(
        self,
        action: str,
        account_id: int | None = None,
        identity: str = "bot",
        chat_id: str | None = None,
        text: str | None = None,
        title: str | None = None,
        method: str | None = None,
        path: str | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        current_user_id: int | None = None,
    ) -> str:
        if not current_user_id:
            raise ToolExecutionError(self.name, "缺少当前登录用户上下文，无法选择飞书账户")

        try:
            account = await get_lark_account(int(current_user_id), account_id)

            if action == "auth_status":
                result = await lark_auth_status(account)
                return json.dumps(result["data"], ensure_ascii=False, indent=2)

            safe_identity = identity if identity in {"bot", "user", "auto"} else "bot"

            if action == "send_message":
                if not chat_id or not text:
                    raise ToolExecutionError(self.name, "send_message 需要 chat_id 和 text")
                result = await run_lark_command(
                    account,
                    [
                        "im",
                        "+messages-send",
                        "--as",
                        safe_identity,
                        "--chat-id",
                        chat_id,
                        "--text",
                        text,
                    ],
                )
                return json.dumps(result["data"], ensure_ascii=False, indent=2)

            if action == "create_doc":
                if not title or not text:
                    raise ToolExecutionError(self.name, "create_doc 需要 title 和 text")
                result = await run_lark_command(
                    account,
                    [
                        "docs",
                        "+create",
                        "--as",
                        safe_identity,
                        "--title",
                        title,
                        "--markdown",
                        text,
                    ],
                )
                return json.dumps(result["data"], ensure_ascii=False, indent=2)

            if action == "raw_api":
                if not method or not path:
                    raise ToolExecutionError(self.name, "raw_api 需要 method 和 path")
                if not path.startswith("/open-apis/"):
                    raise ToolExecutionError(self.name, "raw_api path 必须以 /open-apis/ 开头")
                args = ["api", method.upper(), path, "--as", safe_identity]
                if params:
                    args.extend(["--params", json.dumps(params, ensure_ascii=False)])
                if data:
                    args.extend(["--data", json.dumps(data, ensure_ascii=False)])
                result = await run_lark_command(account, args)
                return json.dumps(result["data"], ensure_ascii=False, indent=2)

            raise ToolExecutionError(self.name, f"不支持的 action: {action}")
        except ToolExecutionError:
            raise
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            if detail is not None:
                raise ToolExecutionError(self.name, json.dumps(detail, ensure_ascii=False)) from exc
            raise ToolExecutionError(self.name, str(exc)) from exc
