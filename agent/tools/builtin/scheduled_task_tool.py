from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal

from ..base import BaseTool, ToolExecutionError, ToolSchema


class CreateScheduledTaskTool(BaseTool):
    name = "create_scheduled_task"
    description = (
        "创建一个由 7_Agent 后端调度执行的定时任务。适合用户要求稍后、某个时间、"
        "每天或按固定间隔自动让 Agent 执行一段任务时使用。若用户使用“明天”、"
        "“半小时后”等相对时间，先调用 current_time 获取当前时间再换算为绝对时间。"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "任务标题，简短概括用户想定时执行的事情。",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "到点后交给 Agent 执行的完整任务内容。",
                    },
                    "schedule_type": {
                        "type": "string",
                        "enum": ["once", "interval", "daily"],
                        "description": "once=执行一次；interval=固定间隔重复；daily=每天固定时间重复。",
                    },
                    "run_at": {
                        "type": "string",
                        "description": "once 任务必填。ISO 8601 时间，如 2026-04-29T09:00:00+08:00。",
                    },
                    "interval_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 525600,
                        "description": "interval 任务必填。重复间隔分钟数。",
                    },
                    "time_of_day": {
                        "type": "string",
                        "description": "daily 任务必填。每天执行时间，格式 HH:MM，如 09:00。",
                    },
                    "timezone_offset_minutes": {
                        "type": "integer",
                        "minimum": -840,
                        "maximum": 720,
                        "description": (
                            "daily 任务可填。与 JavaScript Date.getTimezoneOffset() 一致，"
                            "中国时间为 -480；未提供时按 UTC 计算。"
                        ),
                    },
                    "model": {
                        "type": "string",
                        "description": "执行任务时使用的模型，不确定时留空。",
                    },
                },
                "required": ["title", "prompt", "schedule_type"],
            },
        )

    async def execute(
        self,
        title: str,
        prompt: str,
        schedule_type: Literal["once", "interval", "daily"],
        run_at: str | None = None,
        interval_minutes: int | None = None,
        time_of_day: str | None = None,
        timezone_offset_minutes: int | None = None,
        model: str = "deepseek-v4-flash",
        current_user_id: int | None = None,
        **_: Any,
    ) -> str:
        if current_user_id is None:
            raise ToolExecutionError(self.name, "缺少当前用户 ID，无法创建个人定时任务")

        title = (title or "").strip()
        prompt = (prompt or "").strip()
        if not title:
            raise ToolExecutionError(self.name, "title 不能为空")
        if not prompt:
            raise ToolExecutionError(self.name, "prompt 不能为空")

        try:
            from backend.scheduled_tasks import parse_datetime, scheduled_task_service

            parsed_run_at: datetime | None = None
            if schedule_type == "once":
                if not run_at:
                    raise ToolExecutionError(self.name, "once 任务必须提供 run_at")
                parsed_run_at = parse_datetime(run_at)
                if parsed_run_at is None:
                    raise ToolExecutionError(self.name, "run_at 解析失败")
            elif schedule_type == "interval":
                if not interval_minutes:
                    raise ToolExecutionError(self.name, "interval 任务必须提供 interval_minutes")
            elif schedule_type == "daily":
                if not time_of_day or not re.match(r"^\d{2}:\d{2}$", time_of_day):
                    raise ToolExecutionError(self.name, "daily 任务必须提供 HH:MM 格式的 time_of_day")
            else:
                raise ToolExecutionError(self.name, f"不支持的 schedule_type: {schedule_type}")

            task = await scheduled_task_service.create_task(
                user_id=int(current_user_id),
                title=title,
                prompt=prompt,
                schedule_type=schedule_type,
                run_at=parsed_run_at,
                interval_minutes=interval_minutes,
                time_of_day=time_of_day,
                timezone_offset_minutes=timezone_offset_minutes,
                model=(model or "deepseek-v4-flash").strip(),
            )
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc), cause=exc) from exc

        return json.dumps(
            {
                "id": task["id"],
                "title": task["title"],
                "schedule_type": task["schedule_type"],
                "next_run_at": task["next_run_at"],
                "status": task["status"],
            },
            ensure_ascii=False,
        )
