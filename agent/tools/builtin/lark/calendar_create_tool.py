from __future__ import annotations

from backend.lark_service import run_lark_command

from ...base import ToolExecutionError, ToolSchema
from ._base import LarkBaseTool, _json_data


class LarkCalendarCreateTool(LarkBaseTool):
    name = "lark_calendar_create"
    description = "Create a Feishu/Lark calendar event."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title."},
                    "start": {"type": "string", "description": "Event start as an ISO 8601 datetime with timezone."},
                    "end": {"type": "string", "description": "Event end as an ISO 8601 datetime with timezone."},
                    "description": {"type": "string", "description": "Optional event description."},
                    "attendee_ids": {
                        "type": "string",
                        "description": "Optional comma-separated attendee IDs.",
                    },
                    "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to primary."},
                    "account_id": {
                        "type": "integer",
                        "description": "Optional bound Lark account ID. Defaults to the user's default account.",
                    },
                },
                "required": ["summary", "start", "end"],
            },
        )

    async def execute(
        self,
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        attendee_ids: str | None = None,
        calendar_id: str | None = None,
        account_id: int | None = None,
        current_user_id: int | None = None,
    ) -> str:
        if not summary or not start or not end:
            raise ToolExecutionError(self.name, "summary, start, and end are required")
        try:
            account = await self._get_account(current_user_id, account_id)
            args = [
                "calendar",
                "+create",
                "--as",
                "user",
                "--calendar-id",
                calendar_id or "primary",
                "--summary",
                summary,
                "--start",
                start,
                "--end",
                end,
            ]
            if description:
                args.extend(["--description", description])
            if attendee_ids:
                args.extend(["--attendee-ids", attendee_ids])
            return _json_data(await run_lark_command(account, args, add_format=False))
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._raise_external_error(exc)
