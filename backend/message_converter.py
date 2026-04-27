"""
消息格式互转 ——
Vercel AI SDK 格式（前端 useChat 发来）↔ OpenAI / DeepSeek / Kimi 格式

Vercel AI SDK 消息结构（useChat 发来的 messages 数组）：
  [
    {
      "id": "1", "role": "user", "content": "Hello",
      "experimental_attachments": [
        { "name": "photo.jpg", "contentType": "image/jpeg", "url": "data:image/jpeg;base64,..." }
      ]
    },
    {
      "id": "2", "role": "assistant", "content": "text",
      "toolInvocations": [
        { "state": "result", "toolCallId": "id",
          "toolName": "bash", "args": {...}, "result": "..." }
      ]
    }
  ]

OpenAI 格式（发给 DeepSeek / Kimi）：
  [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Hello"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}  ← 仅视觉模型
      ]
    },
    { "role": "assistant", "content": "text",
      "tool_calls": [{ "id":"id", "type":"function",
                       "function":{"name":"bash","arguments":"..."} }] },
    { "role": "tool", "tool_call_id": "id", "content": "..." }
  ]

图片处理策略：
  - Kimi：将 image/* 附件转为 image_url content blocks（vision）
  - DeepSeek（含 deepseek-v4-flash 等）：多模态时同样转为 image_url blocks
  - 若某模型不支持 vision，API 会返回错误，前端可提示用户
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _supports_vision() -> bool:
    """本应用仅接 Kimi / DeepSeek；二者当前均支持 image_url 多模态。"""
    return True


def ai_sdk_to_openai(
    messages: list[dict[str, Any]],
    model: str = "deepseek-v4-flash",
) -> list[dict[str, Any]]:
    """
    将 Vercel AI SDK 格式的 messages 列表转为 OpenAI / DeepSeek / Kimi 格式。
    处理：
      - content 为字符串或内容块数组
      - experimental_attachments 中的图片 → image_url content blocks（vision）
      - toolInvocations（含 state: "result"）→ tool_calls + tool messages
      - role: "data" 等无关消息跳过
    """
    result: list[dict[str, Any]] = []
    supports_vision = _supports_vision()

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        text_content = _extract_text(content)

        if role == "user":
            attachments = msg.get("experimental_attachments") or []
            image_blocks = _extract_image_blocks(attachments) if supports_vision else []

            if image_blocks:
                # 多模态内容：文字 + 图片
                content_blocks: list[dict[str, Any]] = []
                if text_content:
                    content_blocks.append({"type": "text", "text": text_content})
                content_blocks.extend(image_blocks)
                result.append({"role": "user", "content": content_blocks})
            else:
                result.append({"role": "user", "content": text_content or ""})

        elif role == "assistant":
            invocations = msg.get("toolInvocations", [])
            parts = msg.get("parts", [])
            msg_reasoning = _extract_reasoning_content(msg)

            if not invocations and parts:
                invocations = [
                    p for p in parts
                    if p.get("type") == "tool-invocation"
                ]

            if invocations:
                tool_calls = []
                tool_results = []
                reasoning_from_invocations = ""
                for inv in invocations:
                    tc_id = inv.get("toolCallId") or inv.get("toolInvocationId", "")
                    tc_name = inv.get("toolName", "")
                    tc_args = inv.get("args", {})
                    tc_result = inv.get("result", "")
                    state = inv.get("state", "result")
                    if not reasoning_from_invocations:
                        reasoning_from_invocations = _extract_reasoning_content(inv)

                    tool_calls.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": tc_name,
                            "arguments": json.dumps(tc_args, ensure_ascii=False),
                        },
                    })
                    if state == "result":
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": _result_to_str(tc_result),
                        })

                assistant_row: dict[str, Any] = {
                    "role": "assistant",
                    "content": text_content or None,
                    "tool_calls": tool_calls,
                }
                reasoning = msg_reasoning or reasoning_from_invocations
                if reasoning:
                    assistant_row["reasoning_content"] = reasoning
                result.append(assistant_row)
                result.extend(tool_results)
            else:
                assistant_row: dict[str, Any] = {
                    "role": "assistant",
                    "content": text_content or "",
                }
                if msg_reasoning:
                    assistant_row["reasoning_content"] = msg_reasoning
                result.append(assistant_row)

        elif role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id", ""),
                "content": text_content or "",
            })

        # 忽略 system、data 等其它 role

    return result


def _extract_image_blocks(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 experimental_attachments 中提取图片，转为 image_url content blocks。"""
    blocks: list[dict[str, Any]] = []
    for att in attachments:
        url = att.get("url") or ""
        content_type = (att.get("contentType") or att.get("content_type") or "").lower()
        name = att.get("name") or ""

        is_image = content_type.startswith("image/") or (
            not content_type and url.startswith("data:image/")
        )
        if not is_image and name:
            from pathlib import Path
            suf = Path(name).suffix.lower()
            is_image = suf in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

        if is_image and url:
            blocks.append({
                "type": "image_url",
                "image_url": {"url": url},
            })
            logger.debug("图片附件转为 image_url block: %s", name or url[:40])

    return blocks


def _extract_text(content: Any) -> str:
    """从字符串或内容块数组中提取纯文本"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content) if content else ""


def _result_to_str(result: Any) -> str:
    """将工具执行结果转为字符串"""
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False)
    return str(result) if result is not None else ""


def _extract_reasoning_content(obj: Any) -> str:
    """兼容 top-level 字段和 parts 中的 reasoning 内容。"""
    if not isinstance(obj, dict):
        return ""
    v = obj.get("reasoning_content")
    if isinstance(v, str) and v.strip():
        return v
    v = obj.get("reasoningContent")
    if isinstance(v, str) and v.strip():
        return v
    for part in obj.get("parts") or []:
        if not isinstance(part, dict) or part.get("type") != "reasoning":
            continue
        v = part.get("text")
        if isinstance(v, str) and v.strip():
            return v
        v = part.get("reasoning")
        if isinstance(v, str) and v.strip():
            return v
    return ""
