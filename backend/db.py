"""
MongoDB 数据库连接和初始化
"""

from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """连接 MongoDB"""
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_url)
    _db = _client[settings.mongodb_db]
    
    # 创建索引
    sessions_coll = _db["sessions"]
    await sessions_coll.create_index("created_at")
    
    messages_coll = _db["messages"]
    await messages_coll.create_index("session_id")
    await messages_coll.create_index([("session_id", 1), ("created_at", 1)])
    
    logger.info(f"MongoDB 已连接: {settings.mongodb_db}")


async def disconnect_db() -> None:
    """断开 MongoDB"""
    global _client, _db
    if _client:
        _client.close()
        _db = None
    logger.info("MongoDB 已断开")


def get_db() -> AsyncIOMotorDatabase:
    """获取数据库实例"""
    if _db is None:
        raise RuntimeError("数据库未初始化，请先调用 connect_db()")
    return _db
