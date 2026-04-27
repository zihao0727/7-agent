from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from agent.skills.base import BaseSkill
from agent.tools.base import BaseTool, ToolExecutionError, ToolSchema


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    number = _safe_float(value)
    if number is None:
        return None
    return int(number)


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


class StockBidAskEmTool(BaseTool):
    name = "stock_bid_ask_em"
    description = (
        "获取东方财富盘口行情报价。输入 symbol 股票代码，例如 000001。"
        "返回 item/value 原始数据，以及买一卖一价差、盘口强弱、振幅、距离涨跌停等分析指标。"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": '股票代码，例如 "000001"',
                    }
                },
                "required": ["symbol"],
            },
        )

    async def execute(self, symbol: str) -> str:
        normalized_symbol = (symbol or "").strip()
        if not normalized_symbol:
            raise ToolExecutionError(self.name, "symbol 不能为空")
        target_prefix = "sh" if normalized_symbol.startswith("6") else "sz"

        try:
            import akshare as ak
        except ImportError as exc:
            raise ToolExecutionError(
                self.name, "未安装 akshare，无法获取东方财富行情数据", cause=exc
            ) from exc

        try:
            quote_df = await asyncio.to_thread(
                ak.stock_bid_ask_em, symbol=normalized_symbol
            )
        except Exception as exc:
            raise ToolExecutionError(
                self.name,
                f"获取股票 {normalized_symbol} 行情失败，请检查网络或代理配置: {exc}",
                cause=exc,
            ) from exc

        records = quote_df.to_dict(orient="records")
        items = [
            {"item": str(row.get("item", "")), "value": _safe_float(row.get("value"))}
            for row in records
        ]
        quote_map = {row["item"]: row["value"] for row in items}

        buy_1 = _safe_float(quote_map.get("buy_1"))
        sell_1 = _safe_float(quote_map.get("sell_1"))
        buy_1_vol = _safe_int(quote_map.get("buy_1_vol"))
        sell_1_vol = _safe_int(quote_map.get("sell_1_vol"))
        latest = _safe_float(quote_map.get("最新"))
        avg_price = _safe_float(quote_map.get("均价"))
        high = _safe_float(quote_map.get("最高"))
        low = _safe_float(quote_map.get("最低"))
        up_limit = _safe_float(quote_map.get("涨停"))
        down_limit = _safe_float(quote_map.get("跌停"))

        spread = None
        spread_pct = None
        if sell_1 is not None and buy_1 is not None:
            spread = sell_1 - buy_1
            if latest not in (None, 0):
                spread_pct = spread / latest * 100

        order_book_imbalance = None
        if buy_1_vol is not None and sell_1_vol is not None:
            total_top = buy_1_vol + sell_1_vol
            if total_top > 0:
                order_book_imbalance = (buy_1_vol - sell_1_vol) / total_top

        intraday_range = None
        intraday_range_pct = None
        price_position_in_range = None
        if high is not None and low is not None:
            intraday_range = high - low
            if latest not in (None, 0):
                intraday_range_pct = intraday_range / latest * 100
            if intraday_range > 0 and latest is not None:
                price_position_in_range = (latest - low) / intraday_range

        latest_vs_avg_pct = None
        if latest not in (None, 0) and avg_price is not None:
            latest_vs_avg_pct = (latest - avg_price) / avg_price * 100

        distance_to_up_limit_pct = None
        if latest not in (None, 0) and up_limit is not None:
            distance_to_up_limit_pct = (up_limit - latest) / latest * 100

        distance_to_down_limit_pct = None
        if latest not in (None, 0) and down_limit is not None:
            distance_to_down_limit_pct = (latest - down_limit) / latest * 100

        analysis = {
            "best_bid": buy_1,
            "best_ask": sell_1,
            "best_bid_volume": buy_1_vol,
            "best_ask_volume": sell_1_vol,
            "bid_ask_spread": _round_or_none(spread, 4),
            "bid_ask_spread_pct": _round_or_none(spread_pct, 4),
            "order_book_imbalance": _round_or_none(order_book_imbalance, 4),
            "intraday_range": _round_or_none(intraday_range, 4),
            "intraday_range_pct": _round_or_none(intraday_range_pct, 4),
            "price_position_in_range": _round_or_none(price_position_in_range, 4),
            "latest_vs_avg_pct": _round_or_none(latest_vs_avg_pct, 4),
            "distance_to_up_limit_pct": _round_or_none(distance_to_up_limit_pct, 4),
            "distance_to_down_limit_pct": _round_or_none(
                distance_to_down_limit_pct, 4
            ),
        }

        result = {
            "symbol": normalized_symbol,
            "source": "akshare.stock_bid_ask_em",
            "target": f"https://quote.eastmoney.com/{target_prefix}{normalized_symbol}.html",
            "items": items,
            "quote": quote_map,
            "analysis": analysis,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


class StockQuoteSkill(BaseSkill):
    name = "stock_quote"
    description = (
        "股票行情分析：调用东方财富盘口报价接口 stock_bid_ask_em 获取个股买卖盘、最新价、涨跌幅、量比、换手等数据，"
        "并结合盘口结构做简明分析。适合用户查询 A 股个股实时行情、盘口强弱、价差和短线状态时使用。"
    )
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list[BaseTool]:
        return [StockBidAskEmTool()]
