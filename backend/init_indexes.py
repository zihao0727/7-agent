"""
数据库索引初始化脚本

为新增的集合创建必要的索引：
- agent_tasks: 任务状态管理
- auto_skills: 自动生成的技能
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db import connect_db, disconnect_db, get_db

logger = logging.getLogger(__name__)


async def create_indexes():
    """创建数据库索引"""
    db = get_db()

    # 1. agent_tasks 索引
    logger.info("创建 agent_tasks 索引...")
    await db["agent_tasks"].create_index([("user_id", 1), ("created_at", -1)])
    await db["agent_tasks"].create_index([("user_id", 1), ("session_id", 1)])
    await db["agent_tasks"].create_index([("status", 1), ("created_at", -1)])

    # 2. auto_skills 索引
    logger.info("创建 auto_skills 索引...")
    await db["auto_skills"].create_index([("user_id", 1), ("status", 1), ("created_at", -1)])
    await db["auto_skills"].create_index([("user_id", 1), ("name", 1)])
    await db["auto_skills"].create_index([("user_id", 1), ("usage_count", -1)])

    logger.info("索引创建完成！")


async def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("连接数据库...")
    await connect_db()

    try:
        await create_indexes()
        logger.info("✓ 数据库索引初始化成功")
    except Exception as exc:
        logger.error(f"✗ 数据库索引初始化失败: {exc}")
        raise
    finally:
        await disconnect_db()


if __name__ == "__main__":
    asyncio.run(main())
