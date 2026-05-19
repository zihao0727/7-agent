from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from redis.exceptions import RedisError

from backend.auth_dependencies import require_current_user
from backend.scheduled_tasks import (
    parse_datetime,
    scheduled_task_service,
)

router = APIRouter(tags=["scheduled-tasks"])


class CreateScheduledTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=8000)
    schedule_type: Literal["once", "interval", "daily"] = "once"
    run_at: str | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=525600)
    time_of_day: str | None = None
    timezone_offset_minutes: int | None = Field(default=None, ge=-840, le=720)
    model: str = Field(default="deepseek-v4-flash", min_length=1, max_length=80)
    max_retries: int = Field(default=2, ge=0, le=5)

    @model_validator(mode="after")
    def validate_schedule(self) -> "CreateScheduledTaskRequest":
        if self.schedule_type == "once":
            if not self.run_at:
                raise ValueError("run_at is required for once tasks")
            parse_datetime(self.run_at)
        elif self.schedule_type == "interval":
            if not self.interval_minutes:
                raise ValueError("interval_minutes is required for interval tasks")
        elif self.schedule_type == "daily":
            if not self.time_of_day or not re.match(r"^\d{2}:\d{2}$", self.time_of_day):
                raise ValueError("time_of_day must use HH:MM format")
            hour, minute = [int(part) for part in self.time_of_day.split(":", 1)]
            if hour > 23 or minute > 59:
                raise ValueError("time_of_day is out of range")
        return self


class UpdateScheduledTaskRequest(BaseModel):
    enabled: bool


def redis_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"Redis scheduler unavailable: {exc}")


@router.get("/scheduled-tasks")
async def list_scheduled_tasks(current_user: dict = Depends(require_current_user)) -> dict:
    try:
        tasks = await scheduled_task_service.list_tasks(int(current_user["id"]))
    except (RuntimeError, RedisError) as exc:
        raise redis_unavailable(exc) from exc
    return {"tasks": tasks}


@router.post("/scheduled-tasks")
async def create_scheduled_task(
    req: CreateScheduledTaskRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    run_at: datetime | None = parse_datetime(req.run_at) if req.run_at else None
    try:
        task = await scheduled_task_service.create_task(
            user_id=int(current_user["id"]),
            title=req.title,
            prompt=req.prompt,
            schedule_type=req.schedule_type,
            run_at=run_at,
            interval_minutes=req.interval_minutes,
            time_of_day=req.time_of_day,
            timezone_offset_minutes=req.timezone_offset_minutes,
            model=req.model,
            max_retries=req.max_retries,
        )
    except (RuntimeError, RedisError) as exc:
        raise redis_unavailable(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"task": task}


@router.patch("/scheduled-tasks/{task_id}")
async def update_scheduled_task(
    task_id: str,
    req: UpdateScheduledTaskRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    try:
        task = await scheduled_task_service.set_enabled(
            int(current_user["id"]),
            task_id,
            req.enabled,
        )
    except (RuntimeError, RedisError) as exc:
        raise redis_unavailable(exc) from exc
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return {"task": task}


@router.delete("/scheduled-tasks/{task_id}")
async def delete_scheduled_task(
    task_id: str,
    current_user: dict = Depends(require_current_user),
) -> dict:
    try:
        deleted = await scheduled_task_service.delete_task(int(current_user["id"]), task_id)
    except (RuntimeError, RedisError) as exc:
        raise redis_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return {"id": task_id}
