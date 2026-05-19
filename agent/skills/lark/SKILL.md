# Feishu/Lark Skill

Use this skill when the user asks to operate Feishu/Lark resources through a bound account.

Tool selection:

- Check account authentication: `lark_auth`
- Send a message to a chat or person: `lark_send_message`
- Create a cloud document from Markdown: `lark_create_doc`
- Query calendar agenda/events: `lark_calendar_query`
- Create a calendar event: `lark_calendar_create`
- Query tasks assigned to me (with completion status): `lark_my_tasks`
- Query tasks related to me — created/followed (with completion status): `lark_related_tasks`
- Call a raw OpenAPI endpoint: `lark_api`
- Run other lark-cli shortcuts or domains: `lark_command`

Rules:

- Use these focused `lark_*` tools for all Feishu/Lark work.
- Never ask for or reveal App Secret, access token, refresh token, or CLI credential output.
- Ask for confirmation before destructive, broad, or external write operations unless the user already gave clear permission.
- Prefer bot identity for bot automation such as sending group messages, bot-owned docs, or tenant APIs.
- Prefer user identity for personal data such as calendar, mail, tasks, contacts, minutes, and video meetings.
- For today's calendar agenda, call `lark_calendar_query` without `start` and `end`; the CLI default avoids calendar API time edge cases.
- For custom calendar ranges, pass full ISO 8601 datetimes with timezone, for example `2026-04-29T00:00:00+08:00`.
- For `lark_api`, `path` must start with `/open-apis/`, and `params`/`data` must be structured JSON objects.
- For `lark_command`, pass the command as an array without the `lark-cli` binary or profile, for example `["docs", "+search", "--query", "budget"]`.

Task queries — IMPORTANT:

- **Always call `current_time` BEFORE the first `lark_my_tasks` / `lark_related_tasks` call in a conversation.** This anchors the "now" you reason about, so when the user says "today" / "overdue" / "this week", you (and the user reading the trace) know exactly which day you mean. Skip this only if you have already called `current_time` earlier in the same conversation and no day boundary has passed since.
- When the user asks about Feishu task completion / completion time / overdue status, ALWAYS call `lark_my_tasks` (or `lark_related_tasks`), never `lark_command` with `+get-my-tasks` / `+get-related-tasks`. The raw list endpoints omit `status` and `completed_at`, which leads to wrong "no completion time" answers.
- `lark_my_tasks` returns each task with `status`, `is_completed`, `completed_at`, `created_at`, `due_at`, `overdue` — all timestamps formatted as Beijing-time strings (`YYYY-MM-DD HH:MM:SS`). Quote these fields directly; do not infer completion from missing fields.
- Use `completed: "done" | "todo" | "all"` to filter; only set `include_detail: false` when the user explicitly asks for a faster, status-less listing.
- Use `lark_my_tasks` for "my tasks / tasks assigned to me", and `lark_related_tasks` for "tasks I created / tasks I follow / tasks related to me". Note that `lark_related_tasks` with `completed: "done"` performs a client-side filter (the CLI does not support a "done only" flag), which can be slower for very large lists.
- The tool response includes a `query_time` field at the top level showing the Beijing-time anchor the backend used to resolve relative windows — quote that when explaining "today/this-week" to the user, to remove any ambiguity about which day "today" refers to.

Relative date filters on `lark_my_tasks` and `lark_related_tasks`:

- Both tools accept the same `due` / `due_start` / `due_end` parameters. The shape and semantics are identical; the only difference is where the filter runs:
  - `lark_my_tasks` pushes `--due-start` / `--due-end` to lark-cli (which currently applies them client-side as well, but the surface is unified).
  - `lark_related_tasks` always filters in Python after fetching, because lark-cli `+get-related-tasks` has no native due flags. This means setting a narrow `due` window does NOT shrink what the CLI fetches — but it still keeps the response focused, faster to read, and consistent with `lark_my_tasks`.
- Never compute timestamps yourself. The tool resolves Beijing-time windows on the backend so the LLM only needs to pick a keyword.
- Map natural-language due windows to the `due` parameter:
  - "今天 / today" → `due="today"`
  - "明天 / tomorrow" → `due="tomorrow"`
  - "昨天 / yesterday" → `due="yesterday"`
  - "本周 / this week" → `due="this_week"`  *(ISO week, Monday–Sunday)*
  - "下周 / next week" → `due="next_week"`
  - "上周 / last week" → `due="last_week"`
  - "本月 / this month" → `due="this_month"`
  - "未来 7 天 / next 7 days / 一周内到期" → `due="upcoming_7d"`
  - "已逾期 / overdue" → `due="overdue"` *(implicitly forces `completed="todo"`; do not also pass `completed="done"`)*
- For arbitrary ranges, use `due_start` / `due_end` (they override `due`):
  - Absolute: `"2026-05-21"` or full ISO 8601 `"2026-05-21T08:00:00+08:00"`
  - Offsets: `"+3d"`, `"-1w"`, `"0m"` (relative to "now" in Beijing time)
  - Millisecond timestamps: `"1779033600000"`
- The returned `filter.due_window` echoes back the resolved Beijing-time bounds — quote those when explaining to the user what was queried.
