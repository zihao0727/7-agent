from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI
from pymongo import ReturnDocument

from backend.config import get_settings
from backend.db import get_db
from backend.model_routing import is_kimi_route

logger = logging.getLogger(__name__)

MEMORY_KINDS = {"preference", "profile", "project", "instruction", "fact"}
ACTIVE_STATUS = "active"


def _now() -> datetime:
    return datetime.utcnow()


def _normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _message_text(message: dict[str, Any], max_chars: int = 1200) -> str:
    parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        parts.append(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") in {"text", "input_text"}:
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)

    for part in message.get("parts") or []:
        if isinstance(part, dict) and part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)

    return _normalize_text(" ".join(parts))[:max_chars]


def _serialize_memory(memory: dict[str, Any]) -> dict[str, Any]:
    row = dict(memory)
    row["id"] = str(row.get("_id") or row.get("id"))
    row.pop("_id", None)
    for key in ("created_at", "updated_at", "last_used_at"):
        if isinstance(row.get(key), datetime):
            row[key] = row[key].isoformat()
    return row


def _tokenize(text: str) -> set[str]:
    text = text.lower()
    latin = re.findall(r"[a-z0-9_]{2,}", text)
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    cjk_pairs: list[str] = []
    for chunk in cjk:
        cjk_pairs.extend(chunk[i : i + 2] for i in range(max(0, len(chunk) - 1)))
    return set(latin + cjk + cjk_pairs)


def _score_memory(memory: dict[str, Any], query_tokens: set[str]) -> float:
    content = str(memory.get("content") or "")
    memory_tokens = _tokenize(content)
    overlap = len(query_tokens & memory_tokens)
    importance = float(memory.get("importance") or 0.5)
    confidence = float(memory.get("confidence") or 0.7)
    recency = 0.0
    updated_at = memory.get("updated_at")
    if isinstance(updated_at, datetime):
        age_days = max(0, (_now() - updated_at).days)
        recency = max(0.0, 1.0 - min(age_days, 180) / 180)
    return overlap * 3.0 + importance + confidence + recency


async def list_memories(user_id: int, include_archived: bool = False) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"user_id": user_id}
    if not include_archived:
        query["status"] = ACTIVE_STATUS
    rows = (
        await get_db()["memories"]
        .find(query)
        .sort([("updated_at", -1)])
        .to_list(None)
    )
    return [_serialize_memory(row) for row in rows]


async def create_memory(
    user_id: int,
    content: str,
    *,
    kind: str = "fact",
    importance: float = 0.5,
    confidence: float = 0.8,
    source_session_id: str | None = None,
    source_message_ids: list[str] | None = None,
) -> dict[str, Any]:
    content = _normalize_text(content)
    if not content:
        raise ValueError("Memory content is required")
    if kind not in MEMORY_KINDS:
        kind = "fact"

    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "kind": kind,
        "content": content[:1000],
        "source_session_id": source_session_id,
        "source_message_ids": source_message_ids or [],
        "importance": max(0.0, min(1.0, float(importance))),
        "confidence": max(0.0, min(1.0, float(confidence))),
        "status": ACTIVE_STATUS,
        "created_at": _now(),
        "updated_at": _now(),
        "last_used_at": None,
    }
    await get_db()["memories"].insert_one(doc)
    return _serialize_memory(doc)


async def update_memory(
    user_id: int,
    memory_id: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    allowed = {"kind", "content", "importance", "confidence", "status"}
    update = {key: value for key, value in patch.items() if key in allowed}
    if "kind" in update and update["kind"] not in MEMORY_KINDS:
        update["kind"] = "fact"
    if "content" in update:
        update["content"] = _normalize_text(str(update["content"]))[:1000]
    for key in ("importance", "confidence"):
        if key in update:
            update[key] = max(0.0, min(1.0, float(update[key])))
    update["updated_at"] = _now()

    result = await get_db()["memories"].find_one_and_update(
        {"_id": memory_id, "user_id": user_id},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    return _serialize_memory(result) if result else None


async def delete_memory(user_id: int, memory_id: str) -> bool:
    result = await get_db()["memories"].update_one(
        {"_id": memory_id, "user_id": user_id},
        {"$set": {"status": "deleted", "updated_at": _now()}},
    )
    return result.modified_count > 0


async def retrieve_relevant_memories(
    user_id: int,
    query_text: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    query_text = _normalize_text(query_text)
    rows = (
        await get_db()["memories"]
        .find({"user_id": user_id, "status": ACTIVE_STATUS})
        .sort([("importance", -1), ("updated_at", -1)])
        .limit(200)
        .to_list(None)
    )
    if not rows:
        return []

    tokens = _tokenize(query_text)
    if not tokens:
        selected = rows[:limit]
    else:
        selected = sorted(rows, key=lambda row: _score_memory(row, tokens), reverse=True)[:limit]

    ids = [row["_id"] for row in selected]
    if ids:
        await get_db()["memories"].update_many(
            {"_id": {"$in": ids}, "user_id": user_id},
            {"$set": {"last_used_at": _now()}},
        )
    return [_serialize_memory(row) for row in selected]


def format_memories_for_prompt(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = [
        "以下是该账户的长期记忆。只在与当前问题相关时使用，不要主动复述这些记忆，除非用户询问。"
    ]
    for memory in memories:
        kind = memory.get("kind") or "fact"
        content = _normalize_text(str(memory.get("content") or ""))
        if content:
            lines.append(f"- [{kind}] {content}")
    return "\n".join(lines)


async def build_memory_context(user_id: int, messages: list[dict[str, Any]]) -> str:
    query_parts = [_message_text(message) for message in messages[-4:] if message.get("role") == "user"]
    memories = await retrieve_relevant_memories(user_id, "\n".join(query_parts), limit=8)
    return format_memories_for_prompt(memories)


def _make_memory_client(model: str) -> tuple[AsyncOpenAI | None, str]:
    settings = get_settings()
    if is_kimi_route(model):
        if not settings.kimi_api_key:
            return None, ""
        return AsyncOpenAI(api_key=settings.kimi_api_key, base_url=settings.kimi_base_url), settings.kimi_model
    if not settings.deepseek_api_key:
        return None, ""
    return AsyncOpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url), settings.deepseek_model


def _parse_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


async def extract_memory_from_session(
    *,
    user_id: int,
    session_id: str,
    messages: list[dict[str, Any]],
    model: str = "deepseek-v4-flash",
) -> None:
    if not messages:
        return

    recent = messages[-8:]
    if not any(message.get("role") == "user" for message in recent):
        return

    existing = await list_memories(user_id)
    client, model_name = _make_memory_client(model)
    if client is None:
        logger.info("Skipping memory extraction because no API key is configured")
        return

    transcript_lines: list[str] = []
    for message in recent:
        role = message.get("role") or "unknown"
        text = _message_text(message, max_chars=1000)
        if text:
            transcript_lines.append(f"{role}: {text}")

    existing_lines = [
        f"{memory['id']}: [{memory.get('kind', 'fact')}] {memory.get('content', '')}"
        for memory in existing[:30]
    ]

    prompt = {
        "existing_memories": existing_lines,
        "recent_transcript": transcript_lines,
        "rules": [
            "Only save durable user-specific information useful in future conversations.",
            "Save explicit 'remember this' requests, stable preferences, ongoing projects, standing instructions, and durable profile facts.",
            "Do not save sensitive personal data, secrets, passwords, one-off mood/status, or temporary task details unless the user explicitly asks to remember them.",
            "If an existing memory should change, return operation=update with existing_memory_id.",
            "Return exactly one JSON object.",
        ],
        "schema": {
            "operation": "create | update | ignore",
            "existing_memory_id": "string or null",
            "kind": "preference | profile | project | instruction | fact",
            "content": "concise memory in Chinese when possible",
            "importance": "0.0-1.0",
            "confidence": "0.0-1.0",
        },
    }

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a conservative long-term memory extractor. Return only JSON.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.1,
            max_tokens=500,
        )
    except Exception as exc:
        logger.warning("Memory extraction failed: %s", exc)
        return

    parsed = _parse_json_object(response.choices[0].message.content or "")
    if not parsed:
        return

    operation = str(parsed.get("operation") or "ignore").lower()
    content = _normalize_text(str(parsed.get("content") or ""))
    if operation == "ignore" or len(content) < 4:
        return

    kind = str(parsed.get("kind") or "fact")
    importance = float(parsed.get("importance") or 0.5)
    confidence = float(parsed.get("confidence") or 0.75)

    if operation == "update" and parsed.get("existing_memory_id"):
        await update_memory(
            user_id,
            str(parsed["existing_memory_id"]),
            {
                "kind": kind,
                "content": content,
                "importance": importance,
                "confidence": confidence,
                "status": ACTIVE_STATUS,
            },
        )
        return

    if operation == "create":
        await create_memory(
            user_id,
            content,
            kind=kind,
            importance=importance,
            confidence=confidence,
            source_session_id=session_id,
        )
