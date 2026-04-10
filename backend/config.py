"""
后端配置 —— 从环境变量读取，提供合理默认值
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DeepSeek / OpenAI 兼容接口
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Kimi API (OpenAI 兼容接口)
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "kimi-k2.5"

    # Tavily 搜索 API
    tavily_api_key: str = ""

    # MongoDB 数据库
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db: str = "7_agent"

    # Agent 循环参数
    max_iterations: int = 20
    max_tokens: int = 4096

    # 系统提示（可在运行时覆盖）
    system_prompt: str = (
        "你是一个强大的 AI 助手，可以使用工具完成各种任务。"
        "优先调用工具获取准确信息，而非依靠记忆作答。"
        "每次工具调用后，仔细阅读结果再决定下一步。"
        "若工具调用的是 HTTP/API 类接口且返回了 JSON 等结构化数据，面向用户的回复中不要原样粘贴完整响应体；"
        "用一两句话概括是否成功，必要时简述关键业务含义或错误原因（如状态码、错误信息），避免冗长原始 JSON。"
        "\n\n【重要】每次调用工具时，必须在参数中加入 `_purpose` 字段，"
        "用一句简洁的中文说明你此刻调用该工具的具体目的，要结合用户的实际请求背景，"
        "而非照搬工具的通用描述。"
        "示例：调用 bash 工具时写 `\"_purpose\": \"列出项目根目录的文件，了解代码结构\"`；"
        "调用读文件工具时写 `\"_purpose\": \"读取 config.py 查看数据库连接配置\"`。"
    )

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
