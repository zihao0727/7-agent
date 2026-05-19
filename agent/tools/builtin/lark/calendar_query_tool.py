from __future__ import annotations

from backend.lark_service import run_lark_command

from ...base import ToolExecutionError, ToolSchema
from ._base import LarkBaseTool, _json_data


class LarkCalendarQueryTool(LarkBaseTool):
    name = "lark_calendar_query"
    description = "Query Feishu/Lark calendar events for a date or time range."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "start": {
                        "type": "string",
                        "description": "Optional ISO 8601 range start. Omit with end to query today's agenda.",
                    },
                    "end": {
                        "type": "string",
                        "description": "Optional ISO 8601 range end. Omit with start to query today's agenda.",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar ID. Defaults to primary.",
                    },
                    "account_id": {
                        "type": "integer",
                        "description": "Optional bound Lark account ID. Defaults to the user's default account.",
                    },
                },
            },
        )

    async def execute(
        self,
        start: str | None = None,
        end: str | None = None,
        calendar_id: str | None = None,
        account_id: int | None = None,
        current_user_id: int | None = None,
    ) -> str:
        try:
            account = await self._get_account(current_user_id, account_id)
            args = ["calendar", "+agenda", "--as", "user", "--calendar-id", calendar_id or "primary"]
            if start:
                args.extend(["--start", start])
            if end:
                args.extend(["--end", end])
            return _json_data(await run_lark_command(account, args))
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._raise_external_error(exc)
