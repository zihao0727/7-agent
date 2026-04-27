"""
TextToImageTool —— 调用网关文生图接口：创建任务并轮询至完成
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from ..base import BaseTool, ToolExecutionError, ToolSchema

TEXT_TO_IMAGE_URL = "https://zzh.wygzc.cn/app10/api/text-to-image"
TEXT_TO_IMAGE_QUERY_URL = "https://zzh.wygzc.cn/app10/api/v2/query"

class TextToImageTool(BaseTool):
    """文生图：提交提示词后由工具内部轮询任务状态，成功时返回图片 URL。"""

    name = "text_to_image"
    description = (
        "根据自然语言提示词生成图片（文生图）。"
        "会调用服务端接口创建异步任务并自动轮询，直到成功、失败或超时。"
        "成功时返回可访问的图片链接；无需在请求中携带 API Key。"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "文生图提示词（必填，不能为空串）",
                    },
                    "width": {
                        "type": "integer",
                        "description": "输出宽度像素，默认 1024",
                    },
                    "height": {
                        "type": "integer",
                        "description": "输出高度像素，默认 1024",
                    },
                    "instance_type": {
                        "type": "string",
                        "description": '实例类型，默认 "default"',
                    },
                    "use_personal_queue": {
                        "type": "boolean",
                        "description": "是否使用个人队列，默认 false",
                    },
                    "max_wait_seconds": {
                        "type": "integer",
                        "description": "最长等待秒数（轮询上限），默认 600",
                    },
                    "poll_interval_seconds": {
                        "type": "number",
                        "description": "轮询间隔秒数，默认 2",
                    },
                },
                "required": ["prompt"],
            },
        )

    async def _request_json(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        json_body: dict[str, Any],
    ) -> tuple[int, Any]:
        async with session.request(
            method,
            url,
            json=json_body,
            headers={"Content-Type": "application/json"},
        ) as resp:
            text_body = await resp.text()
            try:
                body = json.loads(text_body)
            except json.JSONDecodeError:
                body = None
            return resp.status, body

    def _http_error(self, status: int, body: Any, raw: str) -> str:
        if isinstance(body, dict):
            detail = body.get("detail")
            if detail is not None:
                if isinstance(detail, list):
                    return json.dumps(detail, ensure_ascii=False)
                return str(detail)
        return raw[:800] if raw else f"HTTP {status}"

    async def execute(
        self,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        instance_type: str | None = None,
        use_personal_queue: bool = False,
        max_wait_seconds: int = 600,
        poll_interval_seconds: float = 2.0,
    ) -> str:
        p = (prompt or "").strip()
        if not p:
            raise ToolExecutionError(self.name, "提示词 prompt 不能为空")

        w = 1024 if width is None else int(width)
        h = 1024 if height is None else int(height)
        inst = (instance_type or "default").strip() or "default"
        use_q = "true" if use_personal_queue else "false"

        create_payload: dict[str, Any] = {
            "prompt": p,
            "width": w,
            "height": h,
            "instanceType": inst,
            "usePersonalQueue": use_q,
        }

        interval = max(0.5, float(poll_interval_seconds))
        deadline = max(5.0, float(max_wait_seconds))

        timeout = aiohttp.ClientTimeout(total=max(120.0, deadline + 30))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                status, body = await self._request_json(
                    session, "POST", TEXT_TO_IMAGE_URL, create_payload
                )
                if status >= 400:
                    raw = "" if body is None else json.dumps(body, ensure_ascii=False)
                    raise ToolExecutionError(
                        self.name,
                        self._http_error(status, body, raw),
                    )
                if not isinstance(body, dict):
                    raise ToolExecutionError(self.name, "创建任务响应非 JSON 对象")

                task_id = body.get("taskId")
                if not task_id:
                    raise ToolExecutionError(
                        self.name,
                        f"创建任务未返回 taskId：{json.dumps(body, ensure_ascii=False)[:500]}",
                    )

                st0 = (body.get("status") or "").upper()
                err0 = (body.get("errorMessage") or "").strip()
                code0 = (body.get("errorCode") or "").strip()
                if st0 == "FAILED" or (code0 and code0 not in ("", "0")):
                    raise ToolExecutionError(
                        self.name,
                        err0 or code0 or "文生图任务创建失败",
                    )

                # 若创建响应已带结果（少见），直接处理
                if st0 == "SUCCESS":
                    urls = self._extract_image_urls(body)
                    if urls:
                        return self._format_success(str(task_id), urls, body)
                    # 否则继续查询一次
                elapsed = 0.0
                last_status = st0 or "UNKNOWN"
                last_body: dict[str, Any] = dict(body)

                while elapsed < deadline:
                    await asyncio.sleep(interval)
                    elapsed += interval

                    q_status, q_body = await self._request_json(
                        session,
                        "POST",
                        TEXT_TO_IMAGE_QUERY_URL,
                        {"taskId": str(task_id)},
                    )
                    if q_status >= 400:
                        raw = "" if q_body is None else json.dumps(q_body, ensure_ascii=False)
                        raise ToolExecutionError(
                            self.name,
                            f"查询任务失败：{self._http_error(q_status, q_body, raw)}",
                        )
                    if not isinstance(q_body, dict):
                        raise ToolExecutionError(self.name, "查询任务响应非 JSON 对象")

                    last_body = q_body
                    last_status = (q_body.get("status") or "").upper() or last_status

                    if last_status == "SUCCESS":
                        urls = self._extract_image_urls(q_body)
                        if urls:
                            return self._format_success(str(task_id), urls, q_body)
                        # SUCCESS 但尚无 url，继续等
                        continue

                    if last_status == "FAILED":
                        msg = (q_body.get("errorMessage") or "").strip() or "任务失败"
                        fr = q_body.get("failedReason")
                        if isinstance(fr, dict) and fr:
                            msg = f"{msg}；详情：{json.dumps(fr, ensure_ascii=False)[:400]}"
                        raise ToolExecutionError(self.name, msg)

                raise ToolExecutionError(
                    self.name,
                    f"等待超时（{int(deadline)}s），最后状态：{last_status}。"
                    f" 最近响应摘要：{json.dumps(last_body, ensure_ascii=False)[:400]}",
                )

        except ToolExecutionError:
            raise
        except aiohttp.ClientError as exc:
            raise ToolExecutionError(self.name, f"网络错误：{exc}") from exc
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc)) from exc

    def _extract_image_urls(self, body: dict[str, Any]) -> list[str]:
        results = body.get("results")
        if not isinstance(results, list):
            return []
        urls: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            u = item.get("url")
            if isinstance(u, str) and u.strip().startswith("http"):
                urls.append(u.strip())
        return urls

    def _format_success(self, task_id: str, urls: list[str], body: dict[str, Any]) -> str:
        lines = [
            "文生图已完成。",
            f"任务 ID：{task_id}",
            "图片链接：",
        ]
        for i, u in enumerate(urls, 1):
            lines.append(f"{i}. {u}")
        usage = body.get("usage")
        if isinstance(usage, dict) and usage.get("taskCostTime") is not None:
            lines.append(f"耗时（上游字段 taskCostTime）：{usage.get('taskCostTime')}")
        return "\n".join(lines)
