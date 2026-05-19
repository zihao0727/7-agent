from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.lark_service import run_lark_command

from ...base import ToolExecutionError, ToolSchema
from ._base import LarkBaseTool
from ._tasks_common import (
    build_tasks_payload,
    extract_task_items,
    fetch_and_merge_tasks,
    resolve_due_window,
    summarize_task,
)

_CN_TZ = timezone(timedelta(hours=8))


class LarkMyTasksTool(LarkBaseTool):
    """
    查询当前用户被分配的飞书任务。

    解决 `+get-my-tasks` 列表接口缺失 `status` / `completed_at` 的问题：
    内部先调列表，再并发对每条任务调用 `task tasks get` 拉详情补齐，
    最终返回结果硬保证带完成状态与北京时间字符串。
    """

    name = "lark_my_tasks"
    description = (
        "Query Feishu tasks assigned to the current user, with full completion status. "
        "Always prefer this over `lark_command task +get-my-tasks` when the user asks about "
        "task completion / completion time: the raw list endpoint omits status and completed_at, "
        "while this tool merges per-task details and returns is_completed, completed_at, overdue, "
        "and Beijing-time strings. Supports relative date windows via `due` "
        "(today / tomorrow / this_week / overdue / ...) so the LLM never needs to compute timestamps. "
        "RECOMMENDED: call `current_time` BEFORE the first invocation in a conversation so you "
        "share an explicit 'now' anchor with the user when interpreting today/this-week/overdue. "
        "The response includes a `query_time` field showing the Beijing-time anchor used for "
        "window resolution — quote it when explaining results."
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "completed": {
                        "type": "string",
                        "enum": ["all", "done", "todo"],
                        "description": (
                            "Completion filter: all (default), done (only completed), "
                            "todo (only unfinished). When `due=overdue`, this is forced to "
                            "'todo' (completed tasks are never overdue)."
                        ),
                        "default": "all",
                    },
                    "due": {
                        "type": "string",
                        "enum": [
                            "all",
                            "today",
                            "tomorrow",
                            "yesterday",
                            "this_week",
                            "next_week",
                            "last_week",
                            "this_month",
                            "overdue",
                            "upcoming_7d",
                        ],
                        "description": (
                            "Relative due-date window (Beijing time). 'overdue' returns tasks "
                            "past their due date and implicitly forces completed='todo'. "
                            "Use `due_start` / `due_end` for arbitrary ranges. Default 'all' = "
                            "no due filter."
                        ),
                        "default": "all",
                    },
                    "due_start": {
                        "type": "string",
                        "description": (
                            "Lower bound of due date. Overrides `due` when set. Accepts ISO 8601 "
                            "(`2026-05-21` / `2026-05-21T08:00:00+08:00`), relative offsets "
                            "(`+3d`, `-1w`), or millisecond timestamps."
                        ),
                    },
                    "due_end": {
                        "type": "string",
                        "description": (
                            "Upper bound of due date. Same format as `due_start`. Either bound "
                            "may be omitted; pair with `due_start` for ranges."
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional keyword to search by task summary.",
                    },
                    "page_limit": {
                        "type": "integer",
                        "description": "Max items per page (lark-cli default 20, max 40).",
                        "minimum": 1,
                        "maximum": 40,
                    },
                    "include_detail": {
                        "type": "boolean",
                        "description": (
                            "Whether to call `task tasks get` per item to merge status / "
                            "completed_at. Default true (guarantees completion status). "
                            "Set false for faster, status-less listing."
                        ),
                        "default": True,
                    },
                    "account_id": {
                        "type": "integer",
                        "description": "Optional bound Lark account ID. Defaults to user's default account.",
                    },
                },
            },
        )

    async def execute(
        self,
        completed: str = "all",
        due: str = "all",
        due_start: str | None = None,
        due_end: str | None = None,
        query: str | None = None,
        page_limit: int | None = None,
        include_detail: bool = True,
        account_id: int | None = None,
        current_user_id: int | None = None,
    ) -> str:
        try:
            account = await self._get_account(current_user_id, account_id)
            # 个人任务必须以 user 身份调用
            identity = self._resolve_identity("user", "task")

            # 一次性捕获"现在"锚点（北京时区），同时用于：
            #   - resolve_due_window: 计算 today/this_week/overdue 等窗口
            #   - build_tasks_payload: 写入响应的 query_time 字段
            # 这样窗口与响应锚点严格一致，便于审计与解释。
            now = datetime.now(tz=_CN_TZ)

            # 解析相对日期 → 毫秒时间戳窗口（避免依赖 CLI 字符串解析）
            start_ms, end_ms, due_meta = resolve_due_window(due, due_start, due_end, now=now)

            # due=overdue 隐含 completed=todo（已完成的任务谈不上逾期）
            effective_completed = completed
            if (due or "").strip().lower() == "overdue":
                effective_completed = "todo"

            args = ["task", "+get-my-tasks", "--as", identity]
            if effective_completed == "done":
                args.append("--complete")
            elif effective_completed == "todo":
                args.append("--complete=false")
            # all 时不传 --complete，CLI 同时返回两类
            if query:
                args.extend(["--query", query])
            if page_limit:
                args.extend(["--page-limit", str(int(page_limit))])
            if start_ms is not None:
                args.extend(["--due-start", str(start_ms)])
            if end_ms is not None:
                args.extend(["--due-end", str(end_ms)])

            list_result = await run_lark_command(account, args)
            items = extract_task_items(list_result.get("data"))

            merged = await fetch_and_merge_tasks(
                account,
                items,
                identity=identity,
                include_detail=include_detail,
            )
            summaries = [summarize_task(t) for t in merged]
            payload = build_tasks_payload(
                summaries,
                filter_meta={
                    "completed": effective_completed,
                    "completed_input": completed,
                    "due_window": due_meta,
                    "query": query,
                    "include_detail": include_detail,
                },
                query_time=now,
            )
            return json.dumps(payload, ensure_ascii=False, indent=2)
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._raise_external_error(exc)
