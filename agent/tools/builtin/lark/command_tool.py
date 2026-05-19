from __future__ import annotations

import shlex

from backend.lark_service import run_lark_command

from ...base import ToolExecutionError, ToolSchema
from ._base import LarkBaseTool, USER_IDENTITY_DOMAINS, _json_data


# lark-cli commands that do NOT accept --format. Adding --format json to these
# makes the CLI exit with "unknown flag: --format" and the call fails completely.
# Verified against installed lark-cli help output (see audit notes).
NO_FORMAT_SHORTCUTS = {
    # docs v2 write/read shortcuts use --jq only
    ("docs", "+create"),
    ("docs", "+update"),
    ("docs", "+fetch"),
    ("docs", "+media-upload"),
    ("docs", "+media-download"),
    ("docs", "+media-insert"),
    ("docs", "+media-preview"),
    ("docs", "+whiteboard-update"),
    # IM messaging
    ("im", "+messages-send"),
    # Sheets (most write shortcuts only have --jq)
    ("sheets", "+create"),
    # Auth maintenance commands (none accept --format)
    ("auth", "status"),
    ("auth", "login"),
    ("auth", "logout"),
    ("auth", "list"),
    ("auth", "check"),
    ("auth", "scopes"),
}


class LarkCommandTool(LarkBaseTool):
    name = "lark_command"
    description = "Run an arbitrary lark-cli command through a bound account as a fallback."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Full lark-cli command arguments without the lark-cli binary/profile, e.g. ['docs', '+search', '--query', 'budget'].",
                    },
                    "account_id": {
                        "type": "integer",
                        "description": "Optional bound Lark account ID. Defaults to the user's default account.",
                    },
                    "identity": {
                        "type": "string",
                        "enum": ["bot", "user", "auto"],
                        "description": "Caller identity to append when --as is absent. Auto uses user for personal-data domains.",
                        "default": "auto",
                    },
                    "add_format": {
                        "type": "boolean",
                        "description": "Whether to append --format json when missing.",
                        "default": True,
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(
        self,
        command: list[str] | str,
        account_id: int | None = None,
        identity: str = "auto",
        add_format: bool = True,
        current_user_id: int | None = None,
    ) -> str:
        if isinstance(command, str):
            cli_args = [item.strip() for item in shlex.split(command, posix=False) if item.strip()]
        else:
            cli_args = [str(item).strip() for item in (command or []) if str(item).strip()]
        if cli_args and cli_args[0] in {"lark-cli", "lark-cli.cmd"}:
            cli_args = cli_args[1:]
        if "--profile" in cli_args:
            idx = cli_args.index("--profile")
            del cli_args[idx : min(idx + 2, len(cli_args))]
        if not cli_args:
            raise ToolExecutionError(self.name, "command must be a non-empty array")
        try:
            account = await self._get_account(current_user_id, account_id)
            if "--as" not in cli_args:
                if identity in {"bot", "user"}:
                    cli_args.extend(["--as", identity])
                elif cli_args[0] in USER_IDENTITY_DOMAINS:
                    cli_args.extend(["--as", "user"])
            supports_format = tuple(cli_args[:2]) not in NO_FORMAT_SHORTCUTS
            if add_format and supports_format and "--format" not in cli_args:
                cli_args.extend(["--format", "json"])
            return _json_data(await run_lark_command(account, cli_args, add_format=False))
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._raise_external_error(exc)
