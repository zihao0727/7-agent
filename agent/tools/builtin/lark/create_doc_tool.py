from __future__ import annotations

import json

from backend.lark_service import run_lark_command

from ...base import ToolExecutionError, ToolSchema
from ._base import LarkBaseTool, _extract_doc_ref, _looks_like_doc_has_content


class LarkCreateDocTool(LarkBaseTool):
    name = "lark_create_doc"
    description = "Create a Feishu/Lark cloud document and write Markdown content into it."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Document title."},
                    "text": {"type": "string", "description": "Markdown content to write into the document."},
                    "account_id": {
                        "type": "integer",
                        "description": "Optional bound Lark account ID. Defaults to the user's default account.",
                    },
                    "identity": {
                        "type": "string",
                        "enum": ["bot", "user"],
                        "description": "Creator identity. Defaults to bot.",
                        "default": "bot",
                    },
                },
                "required": ["title", "text"],
            },
        )

    async def execute(
        self,
        title: str,
        text: str,
        account_id: int | None = None,
        identity: str = "bot",
        current_user_id: int | None = None,
    ) -> str:
        if not title or not text:
            raise ToolExecutionError(self.name, "title and text are required")
        try:
            account = await self._get_account(current_user_id, account_id)
            exec_identity = self._resolve_identity(identity, "docs")
            # docs +create v2 has no --title/--markdown; title comes from the first
            # "# H1" line inside the markdown content. Strip any pre-existing H1 in
            # `text` to avoid two heading-1 blocks, then prepend our own.
            stripped_text = text.lstrip()
            if stripped_text.startswith("# "):
                first_nl = stripped_text.find("\n")
                stripped_text = stripped_text[first_nl + 1 :] if first_nl != -1 else ""
            content = f"# {title.strip()}\n\n{stripped_text}".rstrip() + "\n"
            created = await run_lark_command(
                account,
                [
                    "docs",
                    "+create",
                    "--api-version",
                    "v2",
                    "--as",
                    exec_identity,
                    "--doc-format",
                    "markdown",
                    "--content",
                    "-",
                ],
                add_format=False,
                stdin=content,
            )
            created_data = created["data"]
            doc_ref = _extract_doc_ref(created_data)
            if not doc_ref:
                raise ToolExecutionError(
                    self.name,
                    f"Could not determine document reference from response: {json.dumps(created_data, ensure_ascii=False)}",
                )

            fetched = await run_lark_command(
                account,
                ["docs", "+fetch", "--api-version", "v2", "--as", exec_identity, "--doc", doc_ref],
                add_format=False,
            )
            fetched_data = fetched["data"]
            repaired_data = None
            if not _looks_like_doc_has_content(fetched_data, title=title, text=text):
                repaired = await run_lark_command(
                    account,
                    [
                        "docs",
                        "+update",
                        "--api-version",
                        "v2",
                        "--as",
                        exec_identity,
                        "--doc",
                        doc_ref,
                        "--command",
                        "append",
                        "--doc-format",
                        "markdown",
                        "--content",
                        "-",
                    ],
                    add_format=False,
                    stdin=text,
                )
                repaired_data = repaired["data"]
                fetched = await run_lark_command(
                    account,
                    ["docs", "+fetch", "--api-version", "v2", "--as", exec_identity, "--doc", doc_ref],
                    add_format=False,
                )
                fetched_data = fetched["data"]
                if not _looks_like_doc_has_content(fetched_data, title=title, text=text):
                    raise ToolExecutionError(
                        self.name,
                        json.dumps(
                            {
                                "message": "Document was created, but post-write repair did not find the expected content.",
                                "doc_ref": doc_ref,
                                "created": created_data,
                                "repair": repaired_data,
                                "fetched": fetched_data,
                            },
                            ensure_ascii=False,
                        ),
                    )
            return json.dumps(
                {
                    "doc_ref": doc_ref,
                    "created": created_data,
                    "verified": True,
                    "repaired": repaired_data is not None,
                    "repair": repaired_data,
                    "fetched": fetched_data,
                },
                ensure_ascii=False,
                indent=2,
            )
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._raise_external_error(exc)
