from __future__ import annotations

import json
from typing import Any

from backend.lark_service import run_lark_command

from ...base import ToolExecutionError, ToolSchema
from ._base import LarkBaseTool, _json_data


class LarkApiTool(LarkBaseTool):
    name = "lark_api"
    description = "Call a raw Feishu/Lark OpenAPI endpoint through the bound CLI account."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                        "description": "HTTP method.",
                    },
                    "path": {
                        "type": "string",
                        "description": "OpenAPI path. Must start with /open-apis/.",
                    },
                    "params": {"type": "object", "description": "Optional query parameters."},
                    "data": {"type": "object", "description": "Optional JSON request body."},
                    "account_id": {
                        "type": "integer",
                        "description": "Optional bound Lark account ID. Defaults to the user's default account.",
                    },
                    "identity": {
                        "type": "string",
                        "enum": ["bot", "user", "auto"],
                        "description": "Caller identity. Auto uses user for calendar APIs and bot otherwise.",
                        "default": "auto",
                    },
                },
                "required": ["method", "path"],
            },
        )

    async def execute(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        account_id: int | None = None,
        identity: str = "auto",
        current_user_id: int | None = None,
    ) -> str:
        if not method or not path:
            raise ToolExecutionError(self.name, "method and path are required")
        if not path.startswith("/open-apis/"):
            raise ToolExecutionError(self.name, "path must start with /open-apis/")
        try:
            account = await self._get_account(current_user_id, account_id)
            domain = "calendar" if path.startswith("/open-apis/calendar/") else None
            args = ["api", method.upper(), path, "--as", self._resolve_identity(identity, domain)]
            if params:
                args.extend(["--params", json.dumps(params, ensure_ascii=False)])
            if data:
                args.extend(["--data", json.dumps(data, ensure_ascii=False)])
            return _json_data(await run_lark_command(account, args))
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._raise_external_error(exc)
