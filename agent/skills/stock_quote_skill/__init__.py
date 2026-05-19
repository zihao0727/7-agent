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


EASTMONEY_FIELDS = (
    "f120,f121,f122,f174,f175,f59,f163,f43,f57,f58,f169,f170,f46,f44,f51,"
    "f168,f47,f164,f116,f60,f45,f52,f50,f48,f167,f117,f71,f161,f49,f530,"
    "f135,f136,f137,f138,f139,f141,f142,f144,f145,f147,f148,f140,f143,f146,"
    "f149,f55,f62,f162,f92,f173,f104,f105,f84,f85,f183,f184,f185,f186,f187,"
    "f188,f189,f190,f191,f192,f107,f111,f86,f177,f78,f110,f262,f263,f264,f267,"
    "f268,f255,f256,f257,f258,f127,f199,f128,f198,f259,f260,f261,f171,f277,f278,"
    "f279,f288,f152,f250,f251,f252,f253,f254,f269,f270,f271,f272,f273,f274,f275,"
    "f276,f265,f266,f289,f290,f286,f285,f292,f293,f294,f295"
)


def _target_prefix(symbol: str) -> str:
    return "sh" if symbol.startswith("6") else "sz"


def _market_code(symbol: str) -> int:
    return 1 if symbol.startswith("6") else 0


def _eastmoney_tick_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "sell_5": data["f31"],
        "sell_5_vol": data["f32"] * 100,
        "sell_4": data["f33"],
        "sell_4_vol": data["f34"] * 100,
        "sell_3": data["f35"],
        "sell_3_vol": data["f36"] * 100,
        "sell_2": data["f37"],
        "sell_2_vol": data["f38"] * 100,
        "sell_1": data["f39"],
        "sell_1_vol": data["f40"] * 100,
        "buy_1": data["f19"],
        "buy_1_vol": data["f20"] * 100,
        "buy_2": data["f17"],
        "buy_2_vol": data["f18"] * 100,
        "buy_3": data["f15"],
        "buy_3_vol": data["f16"] * 100,
        "buy_4": data["f13"],
        "buy_4_vol": data["f14"] * 100,
        "buy_5": data["f11"],
        "buy_5_vol": data["f12"] * 100,
        "最新": data["f43"],
        "均价": data["f71"],
        "涨幅": data["f170"],
        "涨跌": data["f169"],
        "总手": data["f47"],
        "金额": data["f48"],
        "换手": data["f168"],
        "量比": data["f50"],
        "最高": data["f44"],
        "最低": data["f45"],
        "今开": data["f46"],
        "昨收": data["f60"],
        "涨停": data["f51"],
        "跌停": data["f52"],
        "外盘": data["f49"],
        "内盘": data["f161"],
    }


def _fetch_eastmoney_records(symbol: str) -> list[dict[str, Any]]:
    import requests

    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": EASTMONEY_FIELDS,
        "secid": f"{_market_code(symbol)}.{symbol}",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": f"https://quote.eastmoney.com/{_target_prefix(symbol)}{symbol}.html",
    }

    last_error: Exception | None = None
    for trust_env in (True, False):
        session = requests.Session()
        session.trust_env = trust_env
        try:
            response = session.get(url, params=params, headers=headers, timeout=10)
        except requests.RequestException as exc:
            last_error = exc
            continue

        content_type = response.headers.get("content-type", "")
        body_preview = response.text[:160].replace("\n", " ").replace("\r", " ")
        if response.status_code != 200:
            last_error = RuntimeError(
                f"东方财富 HTTP {response.status_code}，content-type={content_type!r}，响应片段={body_preview!r}"
            )
            continue

        try:
            payload = response.json()
        except ValueError:
            last_error = RuntimeError(
                f"东方财富返回了非 JSON 内容，content-type={content_type!r}，响应片段={body_preview!r}"
            )
            continue

        data = payload.get("data")
        if not isinstance(data, dict):
            last_error = RuntimeError(f"东方财富响应缺少 data 字段：{body_preview!r}")
            continue

        tick_dict = _eastmoney_tick_dict(data)
        return [{"item": key, "value": value} for key, value in tick_dict.items()]

    raise RuntimeError(str(last_error) if last_error else "东方财富行情接口请求失败")


def _fetch_sina_records(symbol: str) -> list[dict[str, Any]]:
    import re
    import requests

    market_symbol = f"{_target_prefix(symbol)}{symbol}"
    url = f"https://hq.sinajs.cn/list={market_symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn",
    }

    last_error: Exception | None = None
    for trust_env in (True, False):
        session = requests.Session()
        session.trust_env = trust_env
        try:
            response = session.get(url, headers=headers, timeout=10)
        except requests.RequestException as exc:
            last_error = exc
            continue

        body_preview = response.content[:160]
        if response.status_code != 200:
            last_error = RuntimeError(
                f"Sina HTTP {response.status_code}, response bytes={body_preview!r}"
            )
            continue

        text = response.content.decode("gb18030", errors="replace")
        match = re.search(r'="(.*)"', text)
        if not match:
            last_error = RuntimeError(f"Sina response has no quote payload: {text[:160]!r}")
            continue

        parts = match.group(1).split(",")
        if len(parts) < 32 or not parts[0]:
            last_error = RuntimeError(f"Sina response payload is incomplete: {text[:160]!r}")
            continue

        tick_dict = {
            "name": parts[0],
            "buy_1": parts[6],
            "buy_1_vol": _safe_int(parts[10]),
            "buy_2": parts[13],
            "buy_2_vol": _safe_int(parts[12]),
            "buy_3": parts[15],
            "buy_3_vol": _safe_int(parts[14]),
            "buy_4": parts[17],
            "buy_4_vol": _safe_int(parts[16]),
            "buy_5": parts[19],
            "buy_5_vol": _safe_int(parts[18]),
            "sell_1": parts[7],
            "sell_1_vol": _safe_int(parts[20]),
            "sell_2": parts[23],
            "sell_2_vol": _safe_int(parts[22]),
            "sell_3": parts[25],
            "sell_3_vol": _safe_int(parts[24]),
            "sell_4": parts[27],
            "sell_4_vol": _safe_int(parts[26]),
            "sell_5": parts[29],
            "sell_5_vol": _safe_int(parts[28]),
            "最新": parts[3],
            "均价": None,
            "涨幅": None,
            "涨跌": None,
            "总手": (_safe_float(parts[8]) or 0) / 100,
            "金额": parts[9],
            "换手": None,
            "量比": None,
            "最高": parts[4],
            "最低": parts[5],
            "今开": parts[1],
            "昨收": parts[2],
            "涨停": None,
            "跌停": None,
            "外盘": None,
            "内盘": None,
            "date": parts[30],
            "time": parts[31],
        }
        latest = _safe_float(tick_dict["最新"])
        prev_close = _safe_float(tick_dict["昨收"])
        if latest is not None and prev_close not in (None, 0):
            change = latest - prev_close
            tick_dict["涨跌"] = change
            tick_dict["涨幅"] = change / prev_close * 100
            tick_dict["涨停"] = prev_close * 1.1
            tick_dict["跌停"] = prev_close * 0.9
        return [{"item": key, "value": value} for key, value in tick_dict.items()]

    raise RuntimeError(str(last_error) if last_error else "Sina request failed")


def _fetch_bid_ask_records(symbol: str) -> tuple[list[dict[str, Any]], str, str | None]:
    try:
        return _fetch_eastmoney_records(symbol), "eastmoney.push2.stock.get", None
    except Exception as eastmoney_error:
        try:
            return (
                _fetch_sina_records(symbol),
                "sina.hq.sinajs.cn",
                f"Eastmoney failed, used Sina fallback: {eastmoney_error}",
            )
        except Exception as sina_error:
            raise RuntimeError(
                f"Eastmoney failed: {eastmoney_error}; Sina fallback failed: {sina_error}"
            ) from sina_error


class StockBidAskEmTool(BaseTool):
    name = "stock_bid_ask_em"
    description = (
        "获取东方财富盘口行情报价。输入 symbol 股票代码，例如 000001、600010。"
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
                        "description": '股票代码，例如 "000001" 或 "600010"',
                    }
                },
                "required": ["symbol"],
            },
        )

    async def execute(self, symbol: str) -> str:
        normalized_symbol = (symbol or "").strip().lower()
        if normalized_symbol.startswith(("sh", "sz")):
            normalized_symbol = normalized_symbol[2:]
        if not normalized_symbol:
            raise ToolExecutionError(self.name, "symbol 不能为空")

        target_prefix = _target_prefix(normalized_symbol)
        try:
            records, source, source_warning = await asyncio.to_thread(
                _fetch_bid_ask_records, normalized_symbol
            )
        except Exception as exc:
            raise ToolExecutionError(
                self.name,
                f"获取股票 {normalized_symbol} 行情失败，请检查网络、代理或东方财富接口状态: {exc}",
                cause=exc,
            ) from exc

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
            "distance_to_down_limit_pct": _round_or_none(distance_to_down_limit_pct, 4),
        }

        result = {
            "symbol": normalized_symbol,
            "source": source,
            "source_warning": source_warning,
            "target": f"https://quote.eastmoney.com/{target_prefix}{normalized_symbol}.html",
            "items": items,
            "quote": quote_map,
            "analysis": analysis,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


class StockQuoteSkill(BaseSkill):
    name = "stock_quote"
    description = (
        "股票行情分析：调用东方财富盘口报价接口 stock_bid_ask_em 获取个股买卖盘、"
        "最新价、涨跌幅、量比、换手等数据，并结合盘口结构做简明分析。"
        "适合用户查询 A 股个股实时行情、盘口强弱、价差和短线状态时使用。"
    )
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list[BaseTool]:
        return [StockBidAskEmTool()]
