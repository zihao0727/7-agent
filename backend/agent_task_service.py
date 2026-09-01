"""
Agent 任务状态管理服务 —— 支持长时间运行的后台任务

功能：
1. 任务创建和状态跟踪
2. 支持任务取消
3. 任务历史查询
4. 任务恢复（断线重连）
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from backend.db import get_db

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"      # 等待开始
    RUNNING = "running"      # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消


class AgentTask:
    """Agent 任务状态"""

    def __init__(
        self,
        task_id: str,
        user_id: int,
        session_id: str,
        input_text: str,
        status: TaskStatus = TaskStatus.PENDING,
        result: Optional[str] = None,
        error: Optional[str] = None,
        progress: float = 0.0,
        tool_calls_count: int = 0,
        iterations: int = 0,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ):
        self.task_id = task_id
        self.user_id = user_id
        self.session_id = session_id
        self.input_text = input_text
        self.status = status
        self.result = result
        self.error = error
        self.progress = progress
        self.tool_calls_count = tool_calls_count
        self.iterations = iterations
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.completed_at = completed_at

        # 运行时状态（不存储到数据库）
        self._cancel_event: Optional[asyncio.Event] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "input_text": self.input_text,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "progress": self.progress,
            "tool_calls_count": self.tool_calls_count,
            "iterations": self.iterations,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentTask":
        """从字典创建"""
        return cls(
            task_id=data["task_id"],
            user_id=data["user_id"],
            session_id=data["session_id"],
            input_text=data["input_text"],
            status=TaskStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            progress=data.get("progress", 0.0),
            tool_calls_count=data.get("tool_calls_count", 0),
            iterations=data.get("iterations", 0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            completed_at=data.get("completed_at"),
        )

    def is_terminal(self) -> bool:
        """是否已结束（完成/失败/取消）"""
        return self.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}

    def request_cancel(self) -> None:
        """请求取消任务"""
        if self._cancel_event:
            self._cancel_event.set()

    def is_cancelled(self) -> bool:
        """检查是否已被取消"""
        return self._cancel_event is not None and self._cancel_event.is_set()

    def set_cancel_event(self, event: asyncio.Event) -> None:
        """设置取消事件"""
        self._cancel_event = event


# 全局任务注册表（内存中，用于取消运行中的任务）
_running_tasks: dict[str, AgentTask] = {}


async def create_task(
    user_id: int,
    session_id: str,
    input_text: str,
) -> AgentTask:
    """创建新任务"""
    task_id = str(uuid.uuid4())

    task = AgentTask(
        task_id=task_id,
        user_id=user_id,
        session_id=session_id,
        input_text=input_text,
        status=TaskStatus.PENDING,
    )

    # 存储到数据库
    await get_db()["agent_tasks"].insert_one({
        "_id": task_id,
        **task.to_dict(),
    })

    logger.info(f"创建 Agent 任务: {task_id}")
    return task


async def get_task(task_id: str, user_id: int) -> AgentTask | None:
    """获取任务详情"""
    doc = await get_db()["agent_tasks"].find_one({
        "_id": task_id,
        "user_id": user_id,
    })

    if not doc:
        return None

    doc["task_id"] = doc.pop("_id")
    task = AgentTask.from_dict(doc)

    # 如果任务在运行中，关联内存中的取消事件
    if task_id in _running_tasks:
        task._cancel_event = _running_tasks[task_id]._cancel_event

    return task


async def list_tasks(
    user_id: int,
    session_id: Optional[str] = None,
    limit: int = 50,
) -> list[AgentTask]:
    """列出用户的任务"""
    query: dict[str, Any] = {"user_id": user_id}
    if session_id:
        query["session_id"] = session_id

    docs = await get_db()["agent_tasks"].find(query).sort([("created_at", -1)]).limit(limit).to_list(None)

    tasks = []
    for doc in docs:
        doc["task_id"] = doc.pop("_id")
        task = AgentTask.from_dict(doc)
        tasks.append(task)

    return tasks


async def update_task_status(
    task_id: str,
    status: TaskStatus,
    result: Optional[str] = None,
    error: Optional[str] = None,
    progress: Optional[float] = None,
    tool_calls_count: Optional[int] = None,
    iterations: Optional[int] = None,
) -> None:
    """更新任务状态"""
    update_data: dict[str, Any] = {
        "status": status.value,
        "updated_at": datetime.utcnow(),
    }

    if result is not None:
        update_data["result"] = result
    if error is not None:
        update_data["error"] = error
    if progress is not None:
        update_data["progress"] = progress
    if tool_calls_count is not None:
        update_data["tool_calls_count"] = tool_calls_count
    if iterations is not None:
        update_data["iterations"] = iterations

    if status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
        update_data["completed_at"] = datetime.utcnow()

    await get_db()["agent_tasks"].update_one(
        {"_id": task_id},
        {"$set": update_data}
    )

    # 如果任务结束，从内存注册表中移除
    if status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
        _running_tasks.pop(task_id, None)


async def register_running_task(task: AgentTask) -> None:
    """将任务注册到运行时注册表（用于取消）"""
    _running_tasks[task.task_id] = task
    await update_task_status(task.task_id, TaskStatus.RUNNING)


async def cancel_task(task_id: str, user_id: int) -> bool:
    """取消运行中的任务"""
    # 检查任务是否存在且属于该用户
    task = await get_task(task_id, user_id)
    if not task:
        logger.warning(f"任务不存在: {task_id}")
        return False

    # 如果任务已结束，无需取消
    if task.is_terminal():
        logger.info(f"任务已结束，无需取消: {task_id}")
        return True

    # 如果任务在运行中，设置取消标志
    if task_id in _running_tasks:
        _running_tasks[task_id].request_cancel()
        logger.info(f"已请求取消任务: {task_id}")

    # 更新数据库状态
    await update_task_status(task_id, TaskStatus.CANCELLED)

    return True


async def cleanup_old_tasks(days: int = 30) -> int:
    """清理旧任务（超过指定天数的已完成任务）"""
    from datetime import timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    result = await get_db()["agent_tasks"].delete_many({
        "status": {"$in": [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]},
        "completed_at": {"$lt": cutoff_date}
    })

    deleted_count = result.deleted_count
    if deleted_count > 0:
        logger.info(f"清理了 {deleted_count} 个旧任务")

    return deleted_count
