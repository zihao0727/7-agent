"""
前端 X-Model 与后端实际 API 模型的路由。

前端可传「展示用」的模型 id（与 .env 中 DEEPSEEK_MODEL / KIMI_MODEL 一致），
也可传历史兼容值 kimi-k2.5；此处统一判断是否走 Kimi 客户端。
"""

from __future__ import annotations


def is_kimi_route(model: str | None) -> bool:
    m = (model or "").strip()
    if not m:
        return False
    if m == "kimi-k2.5":
        return True
    from backend.config import get_settings

    configured = (get_settings().kimi_model or "").strip()
    return bool(configured and m == configured)
