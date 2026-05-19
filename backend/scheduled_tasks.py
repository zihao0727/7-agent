from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import redis.asyncio as redis

from backend.agent_runner import run_agent_streaming
from backend.config import get_settings
from backend.db import get_db
from backend.memory_service import build_memory_context, extract_memory_from_session
from backend.models import Message, Session
from backend.state import get_app_state

logger = logging.getLogger(__name__)

TASK_PREFIX = "scheduled_tasks:task:"
USER_PREFIX = "scheduled_tasks:user:"
DUE_KEY = "scheduled_tasks:due"
LOCK_PREFIX = "scheduled_tasks:lock:"

ScheduleType = Literal["once", "interval", "daily"]
TaskStatus = Literal["enabled", "paused", "running", "completed", "failed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def task_key(task_id: str) -> str:
    return f"{TASK_PREFIX}{task_id}"


def user_key(user_id: int) -> str:
    return f"{USER_PREFIX}{user_id}"


def serialize_task(task: dict[str, Any]) -> dict[str, str]:
    return {key: json.dumps(value, ensure_ascii=False) for key, value in task.items()}


def deserialize_task(raw: dict[Any, Any]) -> dict[str, Any]:
    task: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        task[str(key)] = json.loads(value)
    return task


def compute_next_run(task: dict[str, Any], *, after: datetime | None = None) -> datetime | None:
    base = after or utc_now()
    schedule_type = task.get("schedule_type")
    if schedule_type == "once":
        return None
    if schedule_type == "interval":
        minutes = int(task.get("interval_minutes") or 0)
        if minutes <= 0:
            return None
        return base + timedelta(minutes=minutes)
    if schedule_type == "daily":
        time_of_day = str(task.get("time_of_day") or "").strip()
        hour_text, minute_text = time_of_day.split(":", 1)
        offset = task.get("timezone_offset_minutes")
        task_timezone = timezone.utc
        if offset is not None:
            task_timezone = timezone(timedelta(minutes=-int(offset)))
        base_local = base.astimezone(task_timezone)
        candidate = base_local.replace(
            hour=int(hour_text),
            minute=int(minute_text),
            second=0,
            microsecond=0,
        )
        if candidate <= base:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)
    return None


class ScheduledTaskService:
    def __init__(self) -> None:
        self.client: redis.Redis | None = None
        self.worker: asyncio.Task[None] | None = None
        self.stop_event = asyncio.Event()

    async def start(self) -> None:
        settings = get_settings()
        client = redis.from_url(settings.redis_url, decode_responses=False)
        await client.ping()
        self.client = client
        self.stop_event.clear()
        self.worker = asyncio.create_task(self._run_loop(), name="scheduled-task-worker")
        logger.info("Scheduled task worker started with Redis: %s", settings.redis_url)

    async def stop(self) -> None:
        self.stop_event.set()
        if self.worker:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
            self.worker = None
        if self.client:
            await self.client.aclose()
            self.client = None
        logger.info("Scheduled task worker stopped")

    def require_client(self) -> redis.Redis:
        if self.client is None:
            raise RuntimeError("Redis scheduler is not initialized")
        return self.client

    async def create_task(
        self,
        *,
        user_id: int,
        title: str,
        prompt: str,
        schedule_type: ScheduleType,
        run_at: datetime | None = None,
        interval_minutes: int | None = None,
        time_of_day: str | None = None,
        timezone_offset_minutes: int | None = None,
        model: str = "deepseek-v4-flash",
        max_retries: int = 2,
    ) -> dict[str, Any]:
        client = self.require_client()
        now = utc_now()
        task_id = str(uuid.uuid4())
        task: dict[str, Any] = {
            "id": task_id,
            "user_id": user_id,
            "title": title.strip(),
            "prompt": prompt.strip(),
            "schedule_type": schedule_type,
            "run_at": iso(run_at),
            "interval_minutes": interval_minutes,
            "time_of_day": time_of_day,
            "timezone_offset_minutes": timezone_offset_minutes,
            "model": model,
            "status": "enabled",
            "workflow_status": "waiting",
            "steps": [
                {"name": "prepare", "status": "pending"},
                {"name": "run_agent", "status": "pending"},
                {"name": "save_result", "status": "pending"},
            ],
            "retry_count": 0,
            "max_retries": max(0, min(5, int(max_retries))),
            "last_run_at": None,
            "next_run_at": None,
            "last_session_id": None,
            "last_error": None,
            "created_at": iso(now),
            "updated_at": iso(now),
        }

        if schedule_type == "once":
            next_run = run_at
        else:
            next_run = compute_next_run(task, after=now - timedelta(seconds=1))
        if next_run is None:
            raise ValueError("Unable to compute next run time")
        task["next_run_at"] = iso(next_run)

        await client.hset(task_key(task_id), mapping=serialize_task(task))
        await client.sadd(user_key(user_id), task_id)
        await client.zadd(DUE_KEY, {task_id: next_run.timestamp()})
        return task

    async def list_tasks(self, user_id: int) -> list[dict[str, Any]]:
        client = self.require_client()
        ids = await client.smembers(user_key(user_id))
        tasks: list[dict[str, Any]] = []
        for raw_id in ids:
            task_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else str(raw_id)
            raw = await client.hgetall(task_key(task_id))
            if raw:
                tasks.append(deserialize_task(raw))
        tasks.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return tasks

    async def delete_task(self, user_id: int, task_id: str) -> bool:
        client = self.require_client()
        raw = await client.hgetall(task_key(task_id))
        if not raw:
            return False
        task = deserialize_task(raw)
        if int(task.get("user_id") or 0) != int(user_id):
            return False
        await client.delete(task_key(task_id), f"{LOCK_PREFIX}{task_id}")
        await client.srem(user_key(user_id), task_id)
        await client.zrem(DUE_KEY, task_id)
        return True

    async def set_enabled(self, user_id: int, task_id: str, enabled: bool) -> dict[str, Any] | None:
        client = self.require_client()
        raw = await client.hgetall(task_key(task_id))
        if not raw:
            return None
        task = deserialize_task(raw)
        if int(task.get("user_id") or 0) != int(user_id):
            return None
        task["status"] = "enabled" if enabled else "paused"
        task["workflow_status"] = "waiting" if enabled else "paused"
        task["updated_at"] = iso(utc_now())
        await client.hset(task_key(task_id), mapping=serialize_task(task))
        if enabled and task.get("next_run_at"):
            await client.zadd(DUE_KEY, {task_id: parse_datetime(task["next_run_at"]).timestamp()})
        else:
            await client.zrem(DUE_KEY, task_id)
        return task

    async def _run_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                await self._process_due_tasks()
            except Exception:
                logger.exception("Scheduled task polling failed")
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    async def _process_due_tasks(self) -> None:
        client = self.require_client()
        now_score = time.time()
        due_ids = await client.zrangebyscore(DUE_KEY, min=0, max=now_score, start=0, num=10)
        for raw_id in due_ids:
            task_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else str(raw_id)
            lock_key = f"{LOCK_PREFIX}{task_id}"
            locked = await client.set(lock_key, "1", nx=True, ex=600)
            if not locked:
                continue
            await client.zrem(DUE_KEY, task_id)
            asyncio.create_task(self._execute_task(task_id), name=f"scheduled-task-{task_id}")

    async def _save_task(self, task: dict[str, Any]) -> None:
        client = self.require_client()
        task["updated_at"] = iso(utc_now())
        await client.hset(task_key(task["id"]), mapping=serialize_task(task))

    async def _execute_task(self, task_id: str) -> None:
        client = self.require_client()
        raw = await client.hgetall(task_key(task_id))
        if not raw:
            return
        task = deserialize_task(raw)
        if task.get("status") != "enabled":
            await client.delete(f"{LOCK_PREFIX}{task_id}")
            return

        task["status"] = "running"
        task["workflow_status"] = "running"
        task["steps"] = [
            {"name": "prepare", "status": "completed"},
            {"name": "run_agent", "status": "running"},
            {"name": "save_result", "status": "pending"},
        ]
        task["last_run_at"] = iso(utc_now())
        task["last_error"] = None
        await self._save_task(task)

        try:
            session_id = await execute_agent_task(task)
            next_run = compute_next_run(task)
            task["last_session_id"] = session_id
            task["next_run_at"] = iso(next_run)
            task["status"] = "enabled" if next_run else "completed"
            task["workflow_status"] = "waiting" if next_run else "completed"
            task["retry_count"] = 0
            task["steps"] = [
                {"name": "prepare", "status": "completed"},
                {"name": "run_agent", "status": "completed"},
                {"name": "save_result", "status": "completed"},
            ]
            await self._save_task(task)
            if next_run:
                await client.zadd(DUE_KEY, {task_id: next_run.timestamp()})
        except Exception as exc:
            logger.exception("Scheduled task failed: %s", task_id)
            task["retry_count"] = int(task.get("retry_count") or 0) + 1
            task["last_error"] = str(exc)
            task["steps"] = [
                {"name": "prepare", "status": "completed"},
                {"name": "run_agent", "status": "failed"},
                {"name": "save_result", "status": "pending"},
            ]
            if task["retry_count"] <= int(task.get("max_retries") or 0):
                retry_at = utc_now() + timedelta(minutes=min(60, 2 ** task["retry_count"]))
                task["status"] = "enabled"
                task["workflow_status"] = "retrying"
                task["next_run_at"] = iso(retry_at)
                await self._save_task(task)
                await client.zadd(DUE_KEY, {task_id: retry_at.timestamp()})
            else:
                task["status"] = "failed"
                task["workflow_status"] = "failed"
                await self._save_task(task)
        finally:
            await client.delete(f"{LOCK_PREFIX}{task_id}")


async def execute_agent_task(task: dict[str, Any]) -> str:
    db = get_db()
    user_id = int(task["user_id"])
    title = str(task["title"] or "Scheduled task")
    prompt = str(task["prompt"] or "")
    model = str(task.get("model") or "deepseek-v4-flash")

    session = Session(title=f"[定时任务] {title}", description="由定时任务自动创建")
    user_message = Message(role="user", content=prompt)
    session_doc = session.model_dump()
    session_doc["_id"] = session_doc.pop("id")
    session_doc["user_id"] = user_id
    session_doc["messages"] = [user_message.model_dump()]
    session_doc["updated_at"] = utc_now().replace(tzinfo=None)
    await db["sessions"].insert_one(session_doc)

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    memory_context = await build_memory_context(user_id, messages)
    final_text = ""
    final_reasoning = ""
    while True:
        step_text = ""
        step_reasoning = ""
        step_calls: list[dict[str, Any]] = []
        step_results: list[dict[str, Any]] = []
        finish_reason = "stop"
        step_error = ""

        async for line in run_agent_streaming(
            messages=messages,
            state=get_app_state(user_id),
            model=model,
            session_id=session.id,
            memory_context=memory_context,
            current_user_id=user_id,
        ):
            prefix, _, payload_text = line.partition(":")
            if not payload_text:
                continue
            payload = json.loads(payload_text)
            if prefix == "0":
                step_text += str(payload)
            elif prefix == "g":
                step_reasoning += str(payload)
            elif prefix == "9":
                step_calls.append(payload)
            elif prefix == "a":
                step_results.append(payload)
            elif prefix == "3":
                step_error = str(payload)
            elif prefix == "d":
                finish_reason = str(payload.get("finishReason") or "stop")

        if finish_reason == "error":
            raise RuntimeError(step_error or "Scheduled task agent execution failed")

        final_text += step_text
        final_reasoning += step_reasoning
        if finish_reason != "tool-calls" or not step_calls:
            break

        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": step_text or None,
            "tool_calls": [
                {
                    "id": call["toolCallId"],
                    "type": "function",
                    "function": {
                        "name": call["toolName"],
                        "arguments": json.dumps(call.get("args") or {}, ensure_ascii=False),
                    },
                }
                for call in step_calls
            ],
        }
        messages.append(assistant_message)
        for result in step_results:
            content = result.get("result")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.get("toolCallId"),
                    "content": content,
                }
            )

    assistant = Message(
        role="assistant",
        content=final_text.strip() or "定时任务已执行，但没有生成文本结果。",
        reasoning_content=final_reasoning or None,
    )
    await db["sessions"].update_one(
        {"_id": session.id, "user_id": user_id},
        {
            "$push": {"messages": assistant.model_dump()},
            "$set": {"updated_at": utc_now().replace(tzinfo=None)},
        },
    )

    saved = await db["sessions"].find_one({"_id": session.id, "user_id": user_id})
    if saved:
        await extract_memory_from_session(
            user_id=user_id,
            session_id=session.id,
            messages=saved.get("messages", []),
        )
    return session.id


scheduled_task_service = ScheduledTaskService()
