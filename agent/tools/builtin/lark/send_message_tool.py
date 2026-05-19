from __future__ import annotations

from backend.lark_service import run_lark_command

from ...base import ToolExecutionError, ToolSchema
from ._base import LarkBaseTool, _json_data


class LarkSendMessageTool(LarkBaseTool):
    name = "lark_send_message"
    description = "Send a text message through Feishu/Lark to a chat or direct conversation."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "chat_id": {"type": "string", "description": "Chat or conversation ID, such as oc_xxx."},
                    "text": {"type": "string", "description": "Message text to send."},
                    "account_id": {
                        "type": "integer",
                        "description": "Optional bound Lark account ID. Defaults to the user's default account.",
                    },
                    "identity": {
                        "type": "string",
                        "enum": ["bot", "user"],
                        "description": "Sender identity. Defaults to bot.",
                        "default": "bot",
                    },
                },
                "required": ["chat_id", "text"],
            },
        )

    async def execute(
        self,
        chat_id: str,
        text: str,
        account_id: int | None = None,
        identity: str = "bot",
        current_user_id: int | None = None,
    ) -> str:
        if not chat_id or not text:
            raise ToolExecutionError(self.name, "chat_id and text are required")
        try:
            account = await self._get_account(current_user_id, account_id)
            exec_identity = self._resolve_identity(identity, "im")
            # `im +messages-send` does NOT accept --format (it only has --jq for
            # output shaping). Forcing --format json via run_lark_command's
            # default add_format=True makes the CLI exit with
            # `unknown flag: --format` and the message never gets sent.
            result = await run_lark_command(
                account,
                ["im", "+messages-send", "--as", exec_identity, "--chat-id", chat_id, "--text", text],
                add_format=False,
            )
            return _json_data(result)
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._raise_external_error(exc)
