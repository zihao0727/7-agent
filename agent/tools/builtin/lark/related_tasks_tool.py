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
    filter_by_due_window,
    resolve_due_window,
    summarize_task,
)

_CN_TZ = timezone(timedelta(hours=8))


class LarkRelatedTasksTool(LarkBaseTool):
    """
    查询与当前用户相关的飞书任务（创建/关注等），同样补齐完成状态。

    与 `lark_my_tasks` 的区别：
      - 子命令为 `+get-related-tasks`
      - 完成状态过滤旗标只有 `--include-complete`（默认 true=全部、false=仅未完成）
        CLI 不支持仅返回已完成，因此 `completed="done"` 通过客户端二次过滤实现
      - 额外支持 `relation`: all / created_by_me / followed_by_me
      - 不支持 `--query`
      - 不支持 `--due-start` / `--due-end`，因此 due 窗口也走客户端过滤
    """

    name = "lark_related_tasks"
    description = (
        "Query Feishu tasks related to the current user (created by me / followed by me / etc), "
        "with full completion status merged in. Same enrichment guarantees as `lark_my_tasks`. "
        "Use this when the user asks about tasks they created, follow, or are otherwise related "
        "(not strictly assigned to them). Supports the same relative date windows via `due` "
        "(today / tomorrow / this_week / overdue / ...) — note that `lark-cli +get-related-tasks` "
        "has no native due filter, so the window is applied client-side after fetching. "
        "RECOMMENDED: call `current_time` BEFORE the first invocation in a conversation so you "
        "share an explicit 'now' anchor with the user. The response includes a `query_time` "
        "field showing the Beijing-time anchor used."
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
                            "Completion filter. 'done' is implemented via client-side filter "
                            "since lark-cli +get-related-tasks only supports --include-complete. "
                            "When `due=overdue` is set, this is forced to 'todo'."
                        ),
                        "default": "all",
                    },
                    "relation": {
                        "type": "string",
                        "enum": ["all", "created_by_me", "followed_by_me"],
                        "description": (
                            "Relation filter: all (default), created_by_me, followed_by_me."
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
                            "Relative due-date window (Beijing time), applied client-side after "
                            "the related-tasks list is fetched. 'overdue' returns tasks past "
                            "their due date and implicitly forces completed='todo'. Use "
                            "`due_start` / `due_end` for arbitrary ranges. Default 'all' = no "
                            "due filter."
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
                            "completed_at. Default true."
                        ),
                        "default": True,
                    },
                    "account_id": {
                        "type": "integer",
                        "description": "Optional bound Lark account ID.",
                    },
                },
            },
        )

    async def execute(
        self,
        completed: str = "all",
        relation: str = "all",
        due: str = "all",
        due_start: str | None = None,
        due_end: str | None = None,
        page_limit: int | None = None,
        include_detail: bool = True,
        account_id: int | None = None,
        current_user_id: int | None = None,
    ) -> str:
        try:
            account = await self._get_account(current_user_id, account_id)
            identity = self._resolve_identity("user", "task")

            # 一次性捕获"现在"锚点（北京时区），同时用于：
            #   - resolve_due_window: 计算 today/this_week/overdue 等窗口
            #   - filter_by_due_window: 客户端过滤
            #   - build_tasks_payload: 写入响应的 query_time 字段
            now = datetime.now(tz=_CN_TZ)

            # 解析相对日期 → 毫秒时间戳窗口（CLI 不支持，所以仅本地用）
            start_ms, end_ms, due_meta = resolve_due_window(due, due_start, due_end, now=now)
            has_due_filter = start_ms is not None or end_ms is not None

            # due=overdue 隐含 completed=todo（已完成的任务谈不上逾期）
            effective_completed = completed
            if (due or "").strip().lower() == "overdue":
                effective_completed = "todo"

            args = ["task", "+get-related-tasks", "--as", identity]
            # CLI 仅支持 "排除已完成"
            if effective_completed == "todo":
                args.append("--include-complete=false")
            if page_limit:
                args.extend(["--page-limit", str(int(page_limit))])
            if relation == "created_by_me":
                args.append("--created-by-me")
            elif relation == "followed_by_me":
                args.append("--followed-by-me")

            list_result = await run_lark_command(account, args)
            items = extract_task_items(list_result.get("data"))

            # 注意：先做 due 客户端过滤，再拉详情。
            # 原因：tasks.get 是逐条 HTTP，过滤越早越省调用。
            # 列表字段已经包含 due_at / due.timestamp（足够过滤），缺的是 status / completed_at。
            if has_due_filter:
                items = filter_by_due_window(
                    items, start_ms=start_ms, end_ms=end_ms, drop_no_due=True
                )

            merged = await fetch_and_merge_tasks(
                account,
                items,
                identity=identity,
                include_detail=include_detail,
            )
            summaries = [summarize_task(t) for t in merged]

            # CLI 不支持"仅已完成"，在客户端剔除未完成
            if effective_completed == "done":
                summaries = [s for s in summaries if s.get("is_completed")]

            payload = build_tasks_payload(
                summaries,
                filter_meta={
                    "completed": effective_completed,
                    "completed_input": completed,
                    "relation": relation,
                    "due_window": due_meta,
                    "include_detail": include_detail,
                },
                query_time=now,
            )
            return json.dumps(payload, ensure_ascii=False, indent=2)
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._raise_external_error(exc)
