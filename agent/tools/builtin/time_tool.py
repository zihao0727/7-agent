"""
CurrentTimeTool —— 返回当前具体时间（可选时区）
"""

from __future__ import annotations

import datetime
from typing import Any

from ..base import BaseTool, ToolExecutionError, ToolSchema


class CurrentTimeTool(BaseTool):
    """返回当前时间，支持可选时区参数（例如 'UTC' 或 'Asia/Shanghai'）。

    用法示例:
        execute(timezone="Asia/Shanghai")
    """

    name = "current_time"
    description = "返回当前具体时间，支持可选时区参数（例如 'UTC' 或 'Asia/Shanghai'）。"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "可选时区，例如 'UTC' 或 'Asia/Shanghai'（留空表示本地时间）",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, timezone: str = "") -> str:
        try:
            if timezone:
                try:
                    from zoneinfo import ZoneInfo  # Python 3.9+
                except Exception:
                    raise ToolExecutionError(self.name, "当前 Python 环境不支持 zoneinfo 时区库")

                try:
                    tz = ZoneInfo(timezone)
                except Exception as exc:
                    raise ToolExecutionError(self.name, f"无法识别时区 {timezone!r}: {exc}") from exc

                now = datetime.datetime.now(tz)
            else:
                now = datetime.datetime.now()

            weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            weekday = weekday_names[now.weekday()]

            # 返回 ISO 格式并包含友好时区信息（若有）
            tzname = now.tzname() if now.tzinfo is not None else "local"
            return now.isoformat() + f" ({tzname}, weekday={weekday})"

        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc)) from exc
