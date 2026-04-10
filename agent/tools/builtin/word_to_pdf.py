"""
ConvertWordToPdfTool —— 将本地 Word（.doc/.docx）转为 PDF（调用远程转换接口）
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import aiohttp

from ..base import BaseTool, ToolExecutionError, ToolSchema

WORD_TO_PDF_API_URL = os.environ.get(
    "WORD_TO_PDF_API_URL",
    "https://zzh.wygzc.cn/app6/convert-word-to-pdf",
)

_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIME_DOC = "application/msword"


class ConvertWordToPdfTool(BaseTool):
    """上传本地 Word 文件到转换服务，返回预签名 PDF 链接等信息。"""

    name = "convert_word_to_pdf"
    description = (
        "将本地 .doc 或 .docx 文件转换为 PDF。"
        "上传文件到转换服务后返回 presigned_url（可直接预览/下载 PDF）、cos_key、file_size。"
        "请在回复中完整附带工具返回的 JSON，以便前端展示 PDF。"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "本地 Word 文件绝对路径或相对路径（.doc 或 .docx）",
                    },
                },
                "required": ["file_path"],
            },
        )

    async def execute(self, file_path: str) -> str:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise ToolExecutionError(self.name, f"文件不存在或不是文件: {file_path}")

        suffix = path.suffix.lower()
        if suffix not in (".doc", ".docx"):
            raise ToolExecutionError(
                self.name,
                "只支持 .doc 和 .docx 格式的 Word 文件",
            )

        content_type = _MIME_DOCX if suffix == ".docx" else _MIME_DOC
        filename = path.name

        try:
            async with aiohttp.ClientSession() as session:
                with open(path, "rb") as fp:
                    data = aiohttp.FormData()
                    data.add_field(
                        "file",
                        fp,
                        filename=filename,
                        content_type=content_type,
                    )
                    async with session.post(
                        WORD_TO_PDF_API_URL,
                        data=data,
                        timeout=aiohttp.ClientTimeout(total=300),
                    ) as resp:
                        text_body = await resp.text()
                        if resp.status >= 400:
                            detail = text_body
                            try:
                                err_json = json.loads(text_body)
                                detail = err_json.get("detail") or detail
                            except Exception:
                                pass
                            raise ToolExecutionError(
                                self.name,
                                f"HTTP {resp.status}: {detail}",
                            )

                        try:
                            body = json.loads(text_body)
                        except json.JSONDecodeError as exc:
                            raise ToolExecutionError(
                                self.name,
                                f"响应不是有效 JSON: {text_body[:500]}",
                            ) from exc

                        if not body.get("success"):
                            raise ToolExecutionError(
                                self.name,
                                body.get("message") or body.get("detail") or str(body),
                            )

                        url = body.get("presigned_url")
                        if not url:
                            raise ToolExecutionError(
                                self.name,
                                "响应中未包含 presigned_url",
                            )

                        out = {
                            "success": True,
                            "message": body.get("message", "转换并上传成功"),
                            "cos_key": body.get("cos_key", ""),
                            "presigned_url": url,
                            "file_size": body.get("file_size"),
                        }
                        return (
                            "Word 已转换为 PDF，以下为结构化结果（请原样包含在回复中以便前端展示）：\n"
                            + json.dumps(out, ensure_ascii=False)
                        )

        except ToolExecutionError:
            raise
        except aiohttp.ClientError as exc:
            raise ToolExecutionError(self.name, f"网络错误：{exc}") from exc
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc)) from exc
