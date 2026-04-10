"""
ArchiveDownloadTool —— 根据卷号下载档案压缩包
"""

from __future__ import annotations

import aiohttp
import json
from typing import Any

from ..base import BaseTool, ToolExecutionError, ToolSchema

ARCHIVE_API_URL = "https://zzh.wygzc.cn/v3/api/app20/archive-message/download"


class ArchiveDownloadTool(BaseTool):
    """根据卷号（jh）下载档案压缩包。
    
    该工具调用外部 API 并返回预签名下载链接（presigned_url），前端直接使用该链接下载文件。
    """

    name = "archive_download"
    description = (
        "根据卷号（jh，例如 WYGZC2025Z183）下载对应的档案压缩包。"
        "返回预签名下载链接（presigned_url），前端可直接使用该链接下载 ZIP 文件。"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "jh": {
                        "type": "string",
                        "description": "卷号，例如 WYGZC2025Z183",
                    }
                },
                "required": ["jh"],
            },
        )

    async def execute(self, jh: str) -> str:
        """根据卷号请求后端生成的预签名下载链接（presigned_url），并返回给前端"""
        if not jh or not jh.strip():
            raise ToolExecutionError(self.name, "卷号（jh）不能为空")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    ARCHIVE_API_URL,
                    params={"jh": jh},
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status >= 400:
                        # 优先解析 JSON 错误体中的 detail 字段
                        detail: str | None = None
                        try:
                            err_json = await resp.json(content_type=None)
                            detail = err_json.get("detail") or json.dumps(err_json, ensure_ascii=False)
                        except Exception:
                            pass
                        if not detail:
                            detail = await resp.text()
                        raise ToolExecutionError(self.name, f"HTTP {resp.status}: {detail}")

                    # 尝试以 JSON 解析响应，期望返回 {"presigned_url": "https://..."}
                    try:
                        body = await resp.json(content_type=None)
                    except Exception:
                        # 如果不是 JSON，则尝试从文本中抽取 presigned_url
                        text = await resp.text()
                        import re

                        m = re.search(r'"presigned_url"\s*:\s*"(https?://[^"\s]+)"', text)
                        if m:
                            url = m.group(1)
                        else:
                            # 没有 JSON 且无法解析 presigned_url，提示对端需返回 presigned_url
                            raise ToolExecutionError(
                                self.name,
                                "未从响应中解析到 presigned_url，请确认后端接口已改为返回 presigned_url JSON",
                            )
                    else:
                        url = body.get("presigned_url") or body.get("url")
                        if not url:
                            # 如果 JSON 但没有 presigned_url，尝试从任意字符串字段中找 URL
                            import re

                            text = json.dumps(body, ensure_ascii=False)
                            m = re.search(r'"(https?://[^"]+)"', text)
                            url = m.group(1) if m else None

                    if not url:
                        raise ToolExecutionError(
                            self.name, "响应中未包含 presigned_url，无法提供下载链接"
                        )

                    return f"presigned_url: {url}"

        except ToolExecutionError:
            raise
        except aiohttp.ClientError as exc:
            raise ToolExecutionError(self.name, f"网络错误：{exc}") from exc
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc)) from exc
