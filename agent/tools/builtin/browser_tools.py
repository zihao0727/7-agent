"""
浏览器自动化工具集 —— 基于 Playwright 实现类 Manus 的网页抓取与交互能力

支持功能：
  - browser_navigate       导航到 URL，返回标题 + 截图
  - browser_screenshot     截图（全页 / 元素 / 视口）
  - browser_extract_text   提取文本（标题、正文、自定义选择器）
  - browser_extract_attrs  提取 HTML 属性（href、src、data-* 等）
  - browser_extract_table  解析 <table> → JSON / CSV
  - browser_scroll         滚动页面（无限滚动场景）
  - browser_click          点击元素（触发交互、翻页等）
  - browser_extract_list   分页 / 无限滚动列表批量抓取
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolExecutionError, ToolSchema

logger = logging.getLogger(__name__)


# ── 截图存储目录 ──────────────────────────────────────────────────────────────

def _screenshots_dir() -> Path:
    root = Path(__file__).resolve().parent.parent.parent.parent / "data" / "screenshots"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ── 浏览器状态单例 ────────────────────────────────────────────────────────────

class _BrowserState:
    """跨工具调用共享的 Playwright 浏览器实例管理器"""

    def __init__(self) -> None:
        self._pw = None          # Playwright 根对象
        self._browser = None     # Browser 实例
        self._context = None     # BrowserContext
        self._page = None        # Page（当前活跃页面）
        self._lock = asyncio.Lock()

        # 对外暴露给 /api/browser/state 接口
        self.current_url: str = ""
        self.page_title: str = ""
        self.last_screenshot_url: str = ""

    async def get_page(self):
        """返回当前 Page，必要时惰性初始化 Playwright / Browser / Context。"""
        async with self._lock:
            if self._pw is None:
                from playwright.async_api import async_playwright
                self._pw = await async_playwright().start()

            if self._browser is None or not self._browser.is_connected():
                self._browser = await self._pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                self._context = None
                self._page = None

            if self._context is None:
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                self._page = None

            if self._page is None or self._page.is_closed():
                self._page = await self._context.new_page()

            return self._page

    async def take_screenshot(
        self,
        selector: str | None = None,
        full_page: bool = False,
    ) -> str:
        """截图后保存到磁盘，返回 `/api/browser/screenshot/<filename>` 路径。"""
        page = await self.get_page()
        fname = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        dest = _screenshots_dir() / fname

        try:
            if selector:
                el = await page.query_selector(selector)
                if el:
                    await el.screenshot(path=str(dest))
                else:
                    await page.screenshot(path=str(dest), full_page=full_page)
            else:
                await page.screenshot(path=str(dest), full_page=full_page)
        except Exception as exc:
            logger.warning("截图失败: %s", exc)
            return ""

        url = f"/api/browser/screenshot/{fname}"
        self.last_screenshot_url = url
        return url

    async def cleanup(self) -> None:
        """关闭浏览器并释放资源（服务器关闭时调用）。"""
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._page = None
        self._pw = None


# 全局单例
_browser_state = _BrowserState()


def get_browser_state() -> _BrowserState:
    return _browser_state


# ── 工具 1：browser_navigate ──────────────────────────────────────────────────

class BrowserNavigateTool(BaseTool):
    name = "browser_navigate"
    description = "打开浏览器并导航到指定 URL，返回页面标题和截图预览"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要访问的网址（需含 http:// 或 https://）",
                    },
                    "wait_for": {
                        "type": "string",
                        "description": "等待条件：load（默认）| domcontentloaded | networkidle",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时毫秒数，默认 30000",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(
        self,
        url: str,
        wait_for: str = "load",
        timeout: int = 30000,
        **_: Any,
    ) -> str:
        bs = get_browser_state()
        try:
            page = await bs.get_page()
            await page.goto(url, wait_until=wait_for, timeout=timeout)
            title = await page.title()
            actual_url = page.url
            bs.current_url = actual_url
            bs.page_title = title
            screenshot_url = await bs.take_screenshot()
            return json.dumps(
                {
                    "success": True,
                    "url": actual_url,
                    "title": title,
                    "screenshot_url": screenshot_url,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            raise ToolExecutionError(self.name, f"导航失败: {exc}") from exc


# ── 工具 2：browser_screenshot ────────────────────────────────────────────────

class BrowserScreenshotTool(BaseTool):
    name = "browser_screenshot"
    description = "对当前页面截图（全页 / 可见视口 / 指定元素），返回截图 URL"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "full_page": {
                        "type": "boolean",
                        "description": "是否截取整页（含滚动区域），默认 false",
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS 选择器，截取特定元素（不填则截可见视口）",
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self,
        full_page: bool = False,
        selector: str | None = None,
        **_: Any,
    ) -> str:
        bs = get_browser_state()
        if not bs.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面，请先使用 browser_navigate")
        screenshot_url = await bs.take_screenshot(selector=selector, full_page=full_page)
        if not screenshot_url:
            raise ToolExecutionError(self.name, "截图失败")
        return json.dumps(
            {
                "success": True,
                "url": bs.current_url,
                "title": bs.page_title,
                "screenshot_url": screenshot_url,
            },
            ensure_ascii=False,
        )


# ── 工具 3：browser_extract_text ──────────────────────────────────────────────

class BrowserExtractTextTool(BaseTool):
    name = "browser_extract_text"
    description = "提取页面文本内容：标题、正文、价格、评论等，支持 CSS 选择器精准定位"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS 选择器（不填则提取整个 body 文本）",
                    },
                    "include_title": {
                        "type": "boolean",
                        "description": "是否包含页面标题，默认 true",
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "最大返回字符数，默认 5000",
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self,
        selector: str | None = None,
        include_title: bool = True,
        max_length: int = 5000,
        **_: Any,
    ) -> str:
        bs = get_browser_state()
        if not bs.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        try:
            page = await bs.get_page()
            out: dict[str, Any] = {"url": page.url}
            if include_title:
                out["title"] = await page.title()

            if selector:
                elements = await page.query_selector_all(selector)
                texts = []
                for el in elements[:100]:
                    t = await el.inner_text()
                    if t.strip():
                        texts.append(t.strip())
                out["selector"] = selector
                out["element_count"] = len(elements)
                out["text"] = "\n---\n".join(texts)
            else:
                body = await page.query_selector("body")
                if body:
                    full_text = await body.inner_text()
                    out["text"] = full_text[:max_length]
                    out["truncated"] = len(full_text) > max_length
                else:
                    out["text"] = ""

            out["screenshot_url"] = await bs.take_screenshot()
            return json.dumps(out, ensure_ascii=False)
        except Exception as exc:
            raise ToolExecutionError(self.name, f"提取文本失败: {exc}") from exc


# ── 工具 4：browser_extract_attrs ────────────────────────────────────────────

class BrowserExtractAttrsTool(BaseTool):
    name = "browser_extract_attrs"
    description = "提取页面元素的 HTML 属性，如 href、src、data-* 等，适合抓链接、图片 URL、结构化标注"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS 选择器（如 a、img.thumb、[data-price]）",
                    },
                    "attrs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": '要提取的属性名（如 ["href","src","alt"]），默认 ["href","src"]',
                    },
                    "max_items": {
                        "type": "integer",
                        "description": "最多返回元素数，默认 100",
                    },
                },
                "required": ["selector"],
            },
        )

    async def execute(
        self,
        selector: str,
        attrs: list[str] | None = None,
        max_items: int = 100,
        **_: Any,
    ) -> str:
        bs = get_browser_state()
        if not bs.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        target_attrs = attrs or ["href", "src"]
        try:
            page = await bs.get_page()
            elements = await page.query_selector_all(selector)
            items: list[dict[str, str]] = []
            for el in elements[:max_items]:
                item: dict[str, str] = {}
                try:
                    text = await el.inner_text()
                    if text.strip():
                        item["text"] = text.strip()[:300]
                except Exception:
                    pass
                for attr in target_attrs:
                    try:
                        val = await el.get_attribute(attr)
                        if val is not None:
                            item[attr] = val
                    except Exception:
                        pass
                if item:
                    items.append(item)
            return json.dumps(
                {
                    "success": True,
                    "url": page.url,
                    "selector": selector,
                    "attrs": target_attrs,
                    "total_elements": len(elements),
                    "items": items,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            raise ToolExecutionError(self.name, f"提取属性失败: {exc}") from exc


# ── 工具 5：browser_extract_table ────────────────────────────────────────────

class BrowserExtractTableTool(BaseTool):
    name = "browser_extract_table"
    description = "自动识别页面 <table> 结构，转为 JSON 记录列表或 CSV 字符串"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "定位表格的 CSS 选择器，默认 table",
                    },
                    "table_index": {
                        "type": "integer",
                        "description": "页面上第几个匹配表格（0-based），默认 0",
                    },
                    "output_format": {
                        "type": "string",
                        "description": "输出格式：json（默认）或 csv",
                        "enum": ["json", "csv"],
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self,
        selector: str = "table",
        table_index: int = 0,
        output_format: str = "json",
        **_: Any,
    ) -> str:
        bs = get_browser_state()
        if not bs.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        try:
            page = await bs.get_page()
            tables = await page.query_selector_all(selector)
            if not tables:
                return json.dumps(
                    {"success": False, "error": "页面上未找到表格", "url": page.url},
                    ensure_ascii=False,
                )
            idx = min(table_index, len(tables) - 1)
            table = tables[idx]

            # 提取表头
            headers: list[str] = []
            for th in await table.query_selector_all("th"):
                headers.append((await th.inner_text()).strip())

            # 提取数据行
            rows_data: list[list[str]] = []
            for tr in await table.query_selector_all("tr"):
                cells = await tr.query_selector_all("td")
                if cells:
                    row = [(await td.inner_text()).strip() for td in cells]
                    rows_data.append(row)

            # 构建字典列表
            col_names = headers if headers else [f"col_{i}" for i in range(len(rows_data[0]) if rows_data else 0)]
            structured = [
                {(col_names[i] if i < len(col_names) else f"col_{i}"): cell
                 for i, cell in enumerate(row)}
                for row in rows_data
            ]

            if output_format == "csv":
                buf = io.StringIO()
                writer = csv.DictWriter(buf, fieldnames=col_names or [f"col_{i}" for i in range(len(rows_data[0]) if rows_data else 0)])
                writer.writeheader()
                writer.writerows(structured)
                result: dict[str, Any] = {
                    "success": True,
                    "url": page.url,
                    "table_index": idx,
                    "total_tables": len(tables),
                    "row_count": len(rows_data),
                    "csv": buf.getvalue(),
                }
            else:
                result = {
                    "success": True,
                    "url": page.url,
                    "table_index": idx,
                    "total_tables": len(tables),
                    "headers": headers,
                    "row_count": len(rows_data),
                    "data": structured,
                }
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            raise ToolExecutionError(self.name, f"提取表格失败: {exc}") from exc


# ── 工具 6：browser_scroll ────────────────────────────────────────────────────

class BrowserScrollTool(BaseTool):
    name = "browser_scroll"
    description = "滚动浏览器页面，支持向下/向上/到顶部/到底部，用于触发无限滚动加载更多内容"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "description": "滚动方向：down | up | bottom（到底部）| top（到顶部）",
                        "enum": ["down", "up", "bottom", "top"],
                    },
                    "amount": {
                        "type": "integer",
                        "description": "滚动像素数（仅 down/up 有效），默认 800",
                    },
                    "wait_ms": {
                        "type": "integer",
                        "description": "滚动后等待毫秒（等待内容加载），默认 1500",
                    },
                },
                "required": ["direction"],
            },
        )

    async def execute(
        self,
        direction: str = "down",
        amount: int = 800,
        wait_ms: int = 1500,
        **_: Any,
    ) -> str:
        bs = get_browser_state()
        if not bs.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        try:
            page = await bs.get_page()
            if direction == "bottom":
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "top":
                await page.evaluate("window.scrollTo(0, 0)")
            elif direction == "down":
                await page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await page.evaluate(f"window.scrollBy(0, -{amount})")

            if wait_ms > 0:
                await page.wait_for_timeout(wait_ms)

            scroll_y = await page.evaluate("window.scrollY")
            page_height = await page.evaluate("document.body.scrollHeight")
            screenshot_url = await bs.take_screenshot()

            return json.dumps(
                {
                    "success": True,
                    "direction": direction,
                    "scroll_y": scroll_y,
                    "page_height": page_height,
                    "screenshot_url": screenshot_url,
                    "url": page.url,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            raise ToolExecutionError(self.name, f"滚动失败: {exc}") from exc


# ── 工具 7：browser_click ─────────────────────────────────────────────────────

class BrowserClickTool(BaseTool):
    name = "browser_click"
    description = "点击页面元素，支持 CSS 选择器或文字内容匹配，可用于翻页、展开、触发交互"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS 选择器（如 button.submit、a.next-page）",
                    },
                    "text": {
                        "type": "string",
                        "description": "按文字内容点击（与 selector 二选一）",
                    },
                    "wait_for_navigation": {
                        "type": "boolean",
                        "description": "点击后是否等待页面跳转，默认 true",
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self,
        selector: str | None = None,
        text: str | None = None,
        wait_for_navigation: bool = True,
        **_: Any,
    ) -> str:
        bs = get_browser_state()
        if not bs.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        if not selector and not text:
            raise ToolExecutionError(self.name, "selector 和 text 至少需提供一个")
        try:
            page = await bs.get_page()
            prev_url = page.url

            async def do_click():
                if selector:
                    await page.click(selector, timeout=10000)
                else:
                    await page.get_by_text(text, exact=False).first.click()  # type: ignore[arg-type]

            if wait_for_navigation:
                try:
                    async with page.expect_navigation(wait_until="load", timeout=15000):
                        await do_click()
                except Exception:
                    pass  # 可能无跳转（下拉菜单、展开等）
            else:
                await do_click()
                await page.wait_for_timeout(500)

            new_url = page.url
            title = await page.title()
            bs.current_url = new_url
            bs.page_title = title
            screenshot_url = await bs.take_screenshot()

            return json.dumps(
                {
                    "success": True,
                    "prev_url": prev_url,
                    "url": new_url,
                    "title": title,
                    "navigated": new_url != prev_url,
                    "screenshot_url": screenshot_url,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            raise ToolExecutionError(self.name, f"点击失败: {exc}") from exc


# ── 工具 8：browser_extract_list ─────────────────────────────────────────────

class BrowserExtractListTool(BaseTool):
    name = "browser_extract_list"
    description = (
        "批量抓取列表项，支持「下一页」按钮翻页和无限滚动两种模式，"
        "可自定义字段提取规则（字段名 → CSS 选择器）"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "item_selector": {
                        "type": "string",
                        "description": "每个列表项的 CSS 选择器（如 .product-card、li.result）",
                    },
                    "fields": {
                        "type": "object",
                        "description": '字段提取映射 {字段名: 子元素CSS选择器}，如 {"name":".title","price":".price"}',
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "分页模式下最多翻页数，默认 3",
                    },
                    "next_button_selector": {
                        "type": "string",
                        "description": "「下一页」按钮 CSS 选择器（分页模式）",
                    },
                    "infinite_scroll": {
                        "type": "boolean",
                        "description": "是否启用无限滚动模式（滚底触发加载），默认 false",
                    },
                    "scroll_rounds": {
                        "type": "integer",
                        "description": "无限滚动模式下最多滚动轮次，默认 5",
                    },
                },
                "required": ["item_selector"],
            },
        )

    async def execute(
        self,
        item_selector: str,
        fields: dict | None = None,
        max_pages: int = 3,
        next_button_selector: str | None = None,
        infinite_scroll: bool = False,
        scroll_rounds: int = 5,
        **_: Any,
    ) -> str:
        bs = get_browser_state()
        if not bs.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        try:
            page = await bs.get_page()
            all_items: list[dict] = []
            pages_scraped = 0

            async def extract_current_page() -> list[dict]:
                elements = await page.query_selector_all(item_selector)
                page_items: list[dict] = []
                for el in elements:
                    item: dict[str, str] = {}
                    if fields:
                        for fname, fsel in fields.items():
                            try:
                                child = await el.query_selector(fsel)
                                if child:
                                    item[fname] = (await child.inner_text()).strip()
                            except Exception:
                                pass
                    else:
                        item["text"] = (await el.inner_text()).strip()[:500]
                    if item:
                        page_items.append(item)
                return page_items

            if infinite_scroll:
                seen = 0
                for rnd in range(scroll_rounds):
                    items = await extract_current_page()
                    all_items.extend(items[seen:])
                    seen = len(items)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)
                    new_count = len(await page.query_selector_all(item_selector))
                    if new_count <= seen:
                        break
                    pages_scraped = rnd + 1
            else:
                for page_num in range(max_pages):
                    items = await extract_current_page()
                    all_items.extend(items)
                    pages_scraped = page_num + 1
                    if not next_button_selector:
                        break
                    btn = await page.query_selector(next_button_selector)
                    if not btn:
                        break
                    if await btn.get_attribute("disabled"):
                        break
                    try:
                        async with page.expect_navigation(timeout=15000):
                            await btn.click()
                        await page.wait_for_timeout(1000)
                    except Exception:
                        break

            screenshot_url = await bs.take_screenshot()
            return json.dumps(
                {
                    "success": True,
                    "url": page.url,
                    "pages_scraped": pages_scraped,
                    "total_items": len(all_items),
                    "items": all_items,
                    "screenshot_url": screenshot_url,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            raise ToolExecutionError(self.name, f"列表抓取失败: {exc}") from exc
