from __future__ import annotations

from backend.lark_service import lark_auth_status

from ...base import ToolExecutionError, ToolSchema
from ._base import LarkBaseTool, _json_data


class LarkAuthTool(LarkBaseTool):
    name = "lark_auth"
    description = "Check the authentication status of a bound Feishu/Lark account."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "integer",
                        "description": "Optional bound Lark account ID. Defaults to the user's default account.",
                    },
                },
            },
        )

    async def execute(
        self,
        account_id: int | None = None,
        current_user_id: int | None = None,
    ) -> str:
        try:
            account = await self._get_account(current_user_id, account_id)
            return _json_data(await lark_auth_status(account))
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._raise_external_error(exc)
