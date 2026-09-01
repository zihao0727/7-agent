"""
自动技能提取服务 —— Hermes 风格的学习闭环

当 Agent 完成复杂任务（5+ 工具调用）时：
1. 分析对话历史，提取可复用的模式
2. 自动生成技能文档（Markdown 格式）
3. 存储到数据库，等待用户确认后激活
4. 激活后的技能可在下次同类任务中自动调用

这形成了"执行 → 学习 → 改进"的闭环，让 Agent 越用越聪明。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.db import get_db
from backend.model_routing import get_model_route

logger = logging.getLogger(__name__)

# 复杂任务的工具调用阈值（Hermes 用 5）
COMPLEX_TASK_THRESHOLD = 5

# 技能状态
SKILL_STATUS_PENDING = "pending"  # 等待用户确认
SKILL_STATUS_ACTIVE = "active"    # 已激活，可使用
SKILL_STATUS_ARCHIVED = "archived"  # 已归档


def _normalize_text(text: str) -> str:
    """标准化文本"""
    return " ".join((text or "").split()).strip()


def _extract_message_text(message: dict[str, Any]) -> str:
    """从消息中提取纯文本内容"""
    content = message.get("content", "")
    if isinstance(content, str):
        return content

    # 处理结构化内容
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    texts.append(part.get("text", ""))
                elif part.get("type") == "tool_use":
                    texts.append(f"[使用工具: {part.get('name')}]")
                elif part.get("type") == "tool_result":
                    texts.append(f"[工具结果]")
        return " ".join(texts)

    return str(content)


def _serialize_skill(skill: dict[str, Any]) -> dict[str, Any]:
    """序列化技能文档为 API 响应格式"""
    row = dict(skill)
    row["id"] = str(row.get("_id") or row.get("id"))
    row.pop("_id", None)

    for key in ("created_at", "updated_at", "last_used_at"):
        if isinstance(row.get(key), datetime):
            row[key] = row[key].isoformat()

    return row


def analyze_task_complexity(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    分析任务复杂度，判断是否值得生成技能

    返回:
        {
            "is_complex": bool,
            "tool_call_count": int,
            "unique_tools": list[str],
            "reasoning": str
        }
    """
    tool_call_count = 0
    unique_tools = set()

    for msg in messages:
        content = msg.get("content", [])
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    tool_call_count += 1
                    unique_tools.add(part.get("name", "unknown"))

    is_complex = tool_call_count >= COMPLEX_TASK_THRESHOLD

    reasoning = ""
    if is_complex:
        reasoning = f"任务包含 {tool_call_count} 次工具调用，使用了 {len(unique_tools)} 个不同工具：{', '.join(unique_tools)}"
    else:
        reasoning = f"任务较简单（{tool_call_count} 次工具调用），不足以生成技能"

    return {
        "is_complex": is_complex,
        "tool_call_count": tool_call_count,
        "unique_tools": list(unique_tools),
        "reasoning": reasoning
    }


async def extract_skill_from_session(
    *,
    user_id: int,
    session_id: str,
    messages: list[dict[str, Any]],
    model: str = "deepseek-v4-flash",
) -> dict[str, Any] | None:
    """
    从会话历史中自动提取技能文档

    Args:
        user_id: 用户 ID
        session_id: 会话 ID
        messages: 完整对话历史
        model: 使用的 LLM 模型

    Returns:
        生成的技能文档（待确认状态），或 None（如果不值得生成）
    """
    # 1. 分析任务复杂度
    complexity = analyze_task_complexity(messages)

    if not complexity["is_complex"]:
        logger.info(f"Session {session_id} 不够复杂，跳过技能提取: {complexity['reasoning']}")
        return None

    logger.info(f"检测到复杂任务，开始提取技能: {complexity['reasoning']}")

    # 2. 准备 LLM 提示
    route = get_model_route(model)
    if not route.api_key:
        logger.warning("跳过技能提取：未配置 API key")
        return None

    client = AsyncOpenAI(api_key=route.api_key, base_url=route.base_url)

    # 构建对话转录
    transcript_lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        text = _extract_message_text(msg)
        if text:
            transcript_lines.append(f"{role}: {text[:500]}")  # 限制长度

    transcript = "\n".join(transcript_lines[-20:])  # 只取最后 20 条消息

    prompt = f"""分析以下对话，提取可复用的技能模式。

对话历史：
{transcript}

任务统计：
- 工具调用次数: {complexity['tool_call_count']}
- 使用的工具: {', '.join(complexity['unique_tools'])}

请提取一个可复用的技能模板。技能应该：
1. 描述一个通用的任务类型（而非具体实例）
2. 列出完成该任务的关键步骤
3. 说明需要使用哪些工具
4. 给出触发条件（什么时候应该使用这个技能）

返回格式为 JSON：
{{
  "name": "技能名称（英文 snake_case）",
  "title": "技能标题（中文，简短）",
  "description": "技能描述（这个技能解决什么问题）",
  "trigger_patterns": ["触发模式1", "触发模式2"],
  "steps": [
    "步骤1",
    "步骤2"
  ],
  "required_tools": ["工具1", "工具2"],
  "examples": ["示例用户请求1", "示例用户请求2"],
  "confidence": 0.8
}}

只返回 JSON，不要其他内容。"""

    # 3. 调用 LLM 生成技能
    try:
        kwargs: dict[str, Any] = {
            "model": route.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个技能提取专家。分析对话历史，提取可复用的技能模式。只返回 JSON。"
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 1500,
        }

        if route.provider == "SevnX":
            kwargs["extra_body"] = {
                "instructions": "你是一个技能提取专家。只返回 JSON。"
            }

        response = await client.chat.completions.create(**kwargs)
    except Exception as exc:
        logger.error(f"技能提取 LLM 调用失败: {exc}")
        return None

    # 4. 解析响应
    raw_content = response.choices[0].message.content or ""
    parsed = _parse_json_object(raw_content)

    if not parsed:
        logger.warning(f"无法解析技能提取结果: {raw_content[:200]}")
        return None

    # 5. 验证必需字段
    required_fields = ["name", "title", "description", "steps", "required_tools"]
    for field in required_fields:
        if field not in parsed:
            logger.warning(f"技能提取结果缺少字段: {field}")
            return None

    # 6. 生成技能文档（Markdown 格式）
    skill_content = _generate_skill_markdown(parsed)

    # 7. 存储到数据库
    skill_doc = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": parsed["name"],
        "title": parsed["title"],
        "description": parsed.get("description", ""),
        "content": skill_content,
        "trigger_patterns": parsed.get("trigger_patterns", []),
        "required_tools": parsed.get("required_tools", []),
        "examples": parsed.get("examples", []),
        "confidence": float(parsed.get("confidence", 0.7)),
        "source_session_id": session_id,
        "status": SKILL_STATUS_PENDING,  # 需要用户确认
        "usage_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_used_at": None,
    }

    await get_db()["auto_skills"].insert_one(skill_doc)

    logger.info(f"成功生成技能: {parsed['name']} ({parsed['title']})")

    return _serialize_skill(skill_doc)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """从文本中解析 JSON 对象"""
    text = text.strip()
    if not text:
        return None

    # 尝试直接解析
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 对象
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _generate_skill_markdown(skill_data: dict[str, Any]) -> str:
    """根据提取的技能数据生成 Markdown 格式的技能文档"""

    parts = [
        f"# {skill_data['title']}\n",
        f"**名称**: `{skill_data['name']}`\n",
        f"**描述**: {skill_data['description']}\n",
        "---\n",
    ]

    # 触发条件
    if skill_data.get("trigger_patterns"):
        parts.append("## 触发条件\n")
        parts.append("当用户请求符合以下模式时，考虑使用此技能：\n")
        for pattern in skill_data["trigger_patterns"]:
            parts.append(f"- {pattern}\n")
        parts.append("\n")

    # 执行步骤
    if skill_data.get("steps"):
        parts.append("## 执行步骤\n")
        for i, step in enumerate(skill_data["steps"], 1):
            parts.append(f"{i}. {step}\n")
        parts.append("\n")

    # 所需工具
    if skill_data.get("required_tools"):
        parts.append("## 所需工具\n")
        for tool in skill_data["required_tools"]:
            parts.append(f"- `{tool}`\n")
        parts.append("\n")

    # 示例
    if skill_data.get("examples"):
        parts.append("## 示例用户请求\n")
        for example in skill_data["examples"]:
            parts.append(f'- "{example}"\n')
        parts.append("\n")

    parts.append("---\n")
    parts.append("*此技能由 AI 自动提取生成*\n")

    return "".join(parts)


# ── CRUD 操作 ────────────────────────────────────────────────────────────────


async def list_auto_skills(
    user_id: int,
    include_archived: bool = False
) -> list[dict[str, Any]]:
    """列出用户的自动生成技能"""
    query: dict[str, Any] = {"user_id": user_id}

    if not include_archived:
        query["status"] = {"$in": [SKILL_STATUS_PENDING, SKILL_STATUS_ACTIVE]}

    skills = await get_db()["auto_skills"].find(query).sort([("created_at", -1)]).to_list(None)

    return [_serialize_skill(skill) for skill in skills]


async def get_auto_skill(skill_id: str, user_id: int) -> dict[str, Any] | None:
    """获取单个技能详情"""
    skill = await get_db()["auto_skills"].find_one({
        "_id": skill_id,
        "user_id": user_id
    })

    return _serialize_skill(skill) if skill else None


async def confirm_auto_skill(skill_id: str, user_id: int, approved: bool) -> dict[str, Any] | None:
    """确认或拒绝自动生成的技能"""
    from pymongo import ReturnDocument

    new_status = SKILL_STATUS_ACTIVE if approved else SKILL_STATUS_ARCHIVED

    skill = await get_db()["auto_skills"].find_one_and_update(
        {"_id": skill_id, "user_id": user_id},
        {
            "$set": {
                "status": new_status,
                "updated_at": datetime.utcnow()
            }
        },
        return_document=ReturnDocument.AFTER
    )

    if skill:
        logger.info(f"技能 {skill_id} 已{'激活' if approved else '拒绝'}")

    return _serialize_skill(skill) if skill else None


async def update_skill_usage(skill_id: str, user_id: int) -> None:
    """更新技能使用统计"""
    await get_db()["auto_skills"].update_one(
        {"_id": skill_id, "user_id": user_id},
        {
            "$inc": {"usage_count": 1},
            "$set": {"last_used_at": datetime.utcnow()}
        }
    )


async def get_active_skills_for_prompt(user_id: int) -> str:
    """获取激活的技能列表，格式化为 prompt 可用的文本"""
    skills = await get_db()["auto_skills"].find({
        "user_id": user_id,
        "status": SKILL_STATUS_ACTIVE
    }).sort([("usage_count", -1), ("created_at", -1)]).limit(10).to_list(None)

    if not skills:
        return ""

    lines = ["你已学会以下技能（自动从历史任务中提取）：\n"]

    for skill in skills:
        title = skill.get("title", "未命名技能")
        description = skill.get("description", "")
        trigger_patterns = skill.get("trigger_patterns", [])

        lines.append(f"- **{title}**: {description}")
        if trigger_patterns:
            lines.append(f"  触发条件: {', '.join(trigger_patterns[:2])}")

    return "\n".join(lines)
