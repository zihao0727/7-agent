"""
MongoDB database connection and indexes.
"""

from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """Connect to MongoDB and create application indexes."""
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_url)
    _db = _client[settings.mongodb_db]

    sessions_coll = _db["sessions"]
    await sessions_coll.create_index("created_at")
    await sessions_coll.create_index("user_id")

    messages_coll = _db["messages"]
    await messages_coll.create_index("session_id")
    await messages_coll.create_index([("session_id", 1), ("created_at", 1)])

    memories_coll = _db["memories"]
    await memories_coll.create_index([("user_id", 1), ("status", 1)])
    await memories_coll.create_index([("user_id", 1), ("kind", 1), ("status", 1)])
    await memories_coll.create_index([("user_id", 1), ("updated_at", -1)])

    logger.info("MongoDB connected: %s", settings.mongodb_db)


async def disconnect_db() -> None:
    """Disconnect from MongoDB."""
    global _client, _db
    if _client:
        _client.close()
        _db = None
    logger.info("MongoDB disconnected")


def get_db() -> AsyncIOMotorDatabase:
    """Return the initialized MongoDB database instance."""
    if _db is None:
        raise RuntimeError("Database is not initialized; call connect_db() first")
    return _db
