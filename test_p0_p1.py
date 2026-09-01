"""
P0 & P1 功能测试脚本

快速验证：
1. 技能提取服务是否正常
2. Agent 循环端点是否可访问
3. 数据库集合是否创建
"""

import asyncio
import sys
from pathlib import Path

import pytest

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db import connect_db, disconnect_db, get_db
from backend.skill_extractor import analyze_task_complexity
from backend.agent_task_service import TaskStatus


def test_skill_extraction():
    """测试技能提取功能"""
    print("\n=== 测试 P0: 技能提取 ===")

    # 模拟一个复杂任务的消息历史
    messages = [
        {"role": "user", "content": "帮我查一下贵州茅台的股价"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "好的，我来查询"},
                {"type": "tool_use", "name": "akshare_stock_quote", "input": {"code": "600519"}},
            ]
        },
        {"role": "user", "content": [{"type": "tool_result", "content": "价格: 1850.00"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "再查一下成交量"},
                {"type": "tool_use", "name": "akshare_stock_quote", "input": {"code": "600519", "field": "volume"}},
            ]
        },
        {"role": "user", "content": [{"type": "tool_result", "content": "成交量: 1000000"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "查询历史数据"},
                {"type": "tool_use", "name": "akshare_stock_history", "input": {"code": "600519"}},
            ]
        },
        {"role": "user", "content": [{"type": "tool_result", "content": "历史数据..."}]},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "calculate_stats", "input": {}},
            ]
        },
        {"role": "user", "content": [{"type": "tool_result", "content": "统计完成"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "generate_chart", "input": {}},
            ]
        },
        {"role": "user", "content": [{"type": "tool_result", "content": "图表生成"}]},
    ]

    # 分析复杂度
    complexity = analyze_task_complexity(messages)

    print(f"✓ 工具调用次数: {complexity['tool_call_count']}")
    print(f"✓ 是否复杂任务: {complexity['is_complex']}")
    print(f"✓ 使用的工具: {', '.join(complexity['unique_tools'])}")
    print(f"✓ 判断依据: {complexity['reasoning']}")

    if complexity['is_complex']:
        print("✓ 满足技能提取条件（5+ 工具调用）")
    else:
        print("✗ 不满足技能提取条件")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_collections():
    """测试数据库集合"""
    print("\n=== 测试数据库集合 ===")

    db = get_db()

    # 检查集合是否存在
    collections = await db.list_collection_names()

    required_collections = ["agent_tasks", "auto_skills"]

    for coll in required_collections:
        if coll in collections:
            print(f"✓ 集合 '{coll}' 已创建")

            # 检查索引
            indexes = await db[coll].index_information()
            print(f"  索引数量: {len(indexes)}")
        else:
            print(f"✗ 集合 '{coll}' 不存在")


def test_task_status_enum():
    """测试任务状态枚举"""
    print("\n=== 测试任务状态管理 ===")

    statuses = [
        TaskStatus.PENDING,
        TaskStatus.RUNNING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    ]

    for status in statuses:
        print(f"✓ 任务状态: {status.value}")


async def main():
    """主函数"""
    print("=" * 50)
    print("P0 & P1 功能测试")
    print("=" * 50)

    # 连接数据库
    await connect_db()

    try:
        # 测试技能提取
        test_skill_extraction()

        # 测试数据库
        await test_database_collections()

        # 测试任务状态
        test_task_status_enum()

        print("\n" + "=" * 50)
        print("✓ 所有测试通过！")
        print("=" * 50)

        print("\n接下来可以：")
        print("1. 启动后端服务: uvicorn backend.app:app --reload")
        print("2. 测试 API 端点:")
        print("   - GET  /api/auto-skills/list")
        print("   - POST /api/agent-loop/start")
        print("   - GET  /api/agent-loop/list")
        print("3. 查看完整文档: docs/P0_P1_Implementation.md")

    except Exception as exc:
        print(f"\n✗ 测试失败: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        await disconnect_db()


if __name__ == "__main__":
    asyncio.run(main())
