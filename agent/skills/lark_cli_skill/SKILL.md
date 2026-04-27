# Lark CLI Skill

Use this skill when the user asks to operate Feishu/Lark resources through their bound bot or app.

Rules:

- Use the `lark_cli` tool only after the user has bound a Lark account in the app.
- Prefer `identity="bot"` for bot automation such as sending group messages, creating bot-owned docs, or calling tenant APIs.
- Use `identity="user"` only when the task clearly needs the user's personal data, such as personal calendar, mail, or tasks.
- Never ask for or reveal App Secret, access token, refresh token, or CLI credential output.
- For destructive or broad operations, explain the intended action first and ask the user to confirm.
- Use these actions first:
  - `auth_status` to check whether the bound account is usable.
  - `send_message` for IM text messages.
  - `create_doc` for Markdown document creation.
  - `raw_api` only when the shortcut actions do not cover the required Feishu OpenAPI.

When using `raw_api`, the path must start with `/open-apis/`, and parameters must be supplied as structured JSON.
