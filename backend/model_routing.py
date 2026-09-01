"""
前端 X-Model 与后端实际 API 模型的路由。

前端可传「展示用」的模型 id（与 .env 中 DEEPSEEK_MODEL / KIMI_MODEL /
SEVNX_MODEL 一致），也可传历史兼容值 kimi-k2.5；此处统一判断实际
使用哪个 OpenAI 兼容客户端。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    api_key: str
    base_url: str
    model: str


def is_kimi_route(model: str | None) -> bool:
    m = (model or "").strip()
    if not m:
        return False
    if m == "kimi-k2.5":
        return True
    from backend.config import get_settings

    configured = (get_settings().kimi_model or "").strip()
    return bool(configured and m == configured)


def is_sevnx_route(model: str | None) -> bool:
    m = (model or "").strip()
    if not m:
        return False
    from backend.config import get_settings

    configured = (get_settings().sevnx_model or "").strip()
    return bool(configured and m == configured)


def get_model_route(model: str | None) -> ModelRoute:
    from backend.config import get_settings

    settings = get_settings()
    if is_kimi_route(model):
        return ModelRoute(
            provider="Kimi",
            api_key=settings.kimi_api_key,
            base_url=settings.kimi_base_url,
            model=settings.kimi_model,
        )
    if is_sevnx_route(model):
        return ModelRoute(
            provider="SevnX",
            api_key=settings.sevnx_api_key,
            base_url=settings.sevnx_base_url,
            model=settings.sevnx_model,
        )
    return ModelRoute(
        provider="DeepSeek",
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
