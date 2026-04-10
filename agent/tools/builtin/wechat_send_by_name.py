"""
WechatSendByNameTool —— 根据接收人姓名通过微信发送消息或链接
"""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from ..base import BaseTool, ToolExecutionError, ToolSchema

WECHAT_SEND_API_URL = "https://zzh.wygzc.cn/app14/v2/api/send_message_by_name"


class WechatSendByNameTool(BaseTool):
    """调用企业/业务网关 API，按姓名查找联系人并发送微信消息（文本或链接）。"""

    name = "wechat_send_by_name"
    description = (
        "根据接收人真实姓名（name）发送微信消息。"
        "message 与 url 至少填一项：可只发文字、只发链接，或同时发送。"
        "成功时返回服务端提示文案及对方微信标识（wcid）。"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "接收人姓名（必填）",
                    },
                    "message": {
                        "type": "string",
                        "description": "消息正文（可选；与 url 至少填一项）",
                    },
                    "url": {
                        "type": "string",
                        "description": "链接地址（可选；与 message 至少填一项）",
                    },
                },
                "required": ["name"],
            },
        )

    async def execute(
        self,
        name: str,
        message: str | None = None,
        url: str | None = None,
    ) -> str:
        if not name or not str(name).strip():
            raise ToolExecutionError(self.name, "接收人姓名（name）不能为空")

        msg = (message or "").strip()
        link = (url or "").strip()
        if not msg and not link:
            raise ToolExecutionError(
                self.name,
                "message 与 url 至少需要填写一项，请提供文字内容或链接",
            )

        payload: dict[str, Any] = {"name": str(name).strip()}
        if msg:
            payload["message"] = msg
        if link:
            payload["url"] = link

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    WECHAT_SEND_API_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    text_body = await resp.text()
                    try:
                        body = json.loads(text_body)
                    except json.JSONDecodeError:
                        body = None

                    if resp.status >= 400:
                        detail: str | None = None
                        if isinstance(body, dict):
                            detail = body.get("detail")
                            if isinstance(detail, list):
                                detail = json.dumps(detail, ensure_ascii=False)
                        if not detail:
                            detail = text_body or f"HTTP {resp.status}"
                        raise ToolExecutionError(self.name, str(detail))

                    if not isinstance(body, dict):
                        raise ToolExecutionError(
                            self.name,
                            f"响应非 JSON：{text_body[:500]}",
                        )

                    if body.get("success") is True:
                        parts = [
                            body.get("message") or "发送成功",
                            f"姓名: {body.get('name', name)}",
                        ]
                        if body.get("wcid"):
                            parts.append(f"wcid: {body['wcid']}")
                        return "\n".join(parts)

                    if body.get("success") is False:
                        detail = body.get("detail") or body.get("message") or json.dumps(
                            body, ensure_ascii=False
                        )
                        raise ToolExecutionError(self.name, str(detail))

                    detail = body.get("detail")
                    if detail:
                        raise ToolExecutionError(self.name, str(detail))
                    raise ToolExecutionError(
                        self.name,
                        f"未识别的响应：{text_body[:500]}",
                    )

        except ToolExecutionError:
            raise
        except aiohttp.ClientError as exc:
            raise ToolExecutionError(self.name, f"网络错误：{exc}") from exc
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc)) from exc
