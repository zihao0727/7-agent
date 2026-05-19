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
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from ..base import BaseTool, ToolExecutionError, ToolSchema

logger = logging.getLogger(__name__)

# ── 更接近真实 Chrome 的默认指纹（可被环境变量覆盖）────────────────────────────
# BROWSER_CHANNEL：留空则用 Playwright 自带 Chromium；可设为 chrome / msedge / chromium
#   使用本机已安装的浏览器常能显著降低被招标/政务站拦截的概率。
# BROWSER_USER_AGENT：完整 UA 覆盖（须与下方 CHROME_MAJOR 一致时效果最好）
# BROWSER_LOCALE / BROWSER_TIMEZONE：语言与时区
# BROWSER_STEALTH：设为 0/false/no 可关闭反自动化脚本注入（调试用）

_CHROME_MAJOR = "131"
_DEFAULT_UA = (
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/{_CHROME_MAJOR}.0.0.0 Safari/537.36"
)

_STEALTH_INIT_SCRIPT = """
(() => {
  const patch = () => {
    try {
      if (navigator.webdriver !== undefined) {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
      }
    } catch (e) {}
    try {
      if (!window.chrome) {
        window.chrome = { runtime: {} };
      }
    } catch (e) {}
  };
  patch();
  document.addEventListener('DOMContentLoaded', patch);
})();
"""


def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")


def _browser_user_agent() -> str:
    return (os.getenv("BROWSER_USER_AGENT") or _DEFAULT_UA).strip()


def _sec_ch_ua_for_major(ua: str) -> str:
    # 从 UA 中取 Chrome/x.y.z 主版本，失败则用默认主版本
    m = re.search(r"Chrome/(\d+)", ua)
    major = m.group(1) if m else _CHROME_MAJOR
    return (
        f'"Google Chrome";v="{major}", "Chromium";v="{major}", "Not_A Brand";v="24"'
    )


def _new_context_kwargs() -> dict[str, Any]:
    ua = _browser_user_agent()
    return {
        "viewport": {"width": 1920, "height": 1080},
        "screen": {"width": 1920, "height": 1080},
        "ignore_https_errors": _env_bool("BROWSER_IGNORE_HTTPS_ERRORS", True),
        "user_agent": ua,
        "locale": os.getenv("BROWSER_LOCALE", "zh-CN"),
        "timezone_id": os.getenv("BROWSER_TIMEZONE", "Asia/Shanghai"),
        "color_scheme": "light",
        "device_scale_factor": 1,
        "has_touch": False,
        "is_mobile": False,
        "extra_http_headers": {
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-CH-UA": _sec_ch_ua_for_major(ua),
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
    }


def _sync_navigate_and_screenshot(
    session_id: str,
    user_id: int | None,
    url: str,
    wait_for: str,
    timeout: int,
) -> dict[str, str]:
    """同步 Playwright 兜底：用于 Windows 某些事件循环不支持 async 子进程场景。"""
    from playwright.sync_api import sync_playwright

    channel = (os.getenv("BROWSER_CHANNEL") or "").strip() or None
    headed = _env_bool("BROWSER_HEADED", False)
    launch_opts: dict[str, Any] = {
        "headless": not headed,
        "args": [
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--lang=zh-CN",
            "--window-size=1920,1080",
            "--disable-infobars",
        ],
    }
    if channel:
        launch_opts["channel"] = channel

    fname = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
    dest = _screenshots_dir(user_id, session_id) / fname

    with sync_playwright() as pw:
        browser = None
        try:
            try:
                browser = pw.chromium.launch(**launch_opts)
            except Exception:
                if channel:
                    launch_opts.pop("channel", None)
                    browser = pw.chromium.launch(**launch_opts)
                else:
                    raise

            context = browser.new_context(**_new_context_kwargs())
            if _env_bool("BROWSER_STEALTH", True):
                context.add_init_script(_STEALTH_INIT_SCRIPT)
            page = context.new_page()

            try:
                page.goto(url, wait_until=wait_for, timeout=timeout)
                wait_used = wait_for
            except Exception:
                if wait_for != "load":
                    raise
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                wait_used = "domcontentloaded"

            title = page.title()
            actual_url = page.url
            page.screenshot(path=str(dest))
            context.close()
            return {
                "url": actual_url,
                "title": title,
                "screenshot_url": f"/api/browser/screenshot/{session_id}/{fname}",
                "wait_for_used": wait_used,
            }
        finally:
            if browser is not None:
                browser.close()


def _sync_screenshot_from_url(
    session_id: str,
    user_id: int | None,
    url: str,
    full_page: bool = False,
    selector: str | None = None,
) -> str:
    """同步 Playwright 截图兜底：基于 URL 重新打开页面并截图。"""
    from playwright.sync_api import sync_playwright

    channel = (os.getenv("BROWSER_CHANNEL") or "").strip() or None
    headed = _env_bool("BROWSER_HEADED", False)
    launch_opts: dict[str, Any] = {
        "headless": not headed,
        "args": [
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--lang=zh-CN",
            "--window-size=1920,1080",
            "--disable-infobars",
        ],
    }
    if channel:
        launch_opts["channel"] = channel

    fname = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
    dest = _screenshots_dir(user_id, session_id) / fname

    with sync_playwright() as pw:
        browser = None
        try:
            try:
                browser = pw.chromium.launch(**launch_opts)
            except Exception:
                if channel:
                    launch_opts.pop("channel", None)
                    browser = pw.chromium.launch(**launch_opts)
                else:
                    raise

            context = browser.new_context(**_new_context_kwargs())
            if _env_bool("BROWSER_STEALTH", True):
                context.add_init_script(_STEALTH_INIT_SCRIPT)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            if selector:
                el = page.query_selector(selector)
                if el:
                    el.screenshot(path=str(dest))
                else:
                    page.screenshot(path=str(dest), full_page=full_page)
            else:
                page.screenshot(path=str(dest), full_page=full_page)

            context.close()
            return f"/api/browser/screenshot/{session_id}/{fname}"
        finally:
            if browser is not None:
                browser.close()


def _supports_async_playwright_subprocess() -> bool:
    """判断当前事件循环是否支持 Playwright async 所需的子进程能力。"""
    if sys.platform != "win32":
        return True
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    # Windows 下只有 Proactor 事件循环支持 asyncio 子进程。
    return "proactor" in loop.__class__.__name__.lower()


def _new_screenshot_target(session_id: str, user_id: int | None = None) -> tuple[Path, str]:
    fname = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
    dest = _screenshots_dir(user_id, session_id) / fname
    return dest, f"/api/browser/screenshot/{session_id}/{fname}"


def _sync_run_on_page(
    url: str,
    worker: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    """同步 Playwright 通用执行器：打开页面后执行 worker。"""
    from playwright.sync_api import sync_playwright

    channel = (os.getenv("BROWSER_CHANNEL") or "").strip() or None
    headed = _env_bool("BROWSER_HEADED", False)
    launch_opts: dict[str, Any] = {
        "headless": not headed,
        "args": [
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--lang=zh-CN",
            "--window-size=1920,1080",
            "--disable-infobars",
        ],
    }
    if channel:
        launch_opts["channel"] = channel

    with sync_playwright() as pw:
        browser = None
        try:
            try:
                browser = pw.chromium.launch(**launch_opts)
            except Exception:
                if channel:
                    launch_opts.pop("channel", None)
                    browser = pw.chromium.launch(**launch_opts)
                else:
                    raise

            context = browser.new_context(**_new_context_kwargs())
            if _env_bool("BROWSER_STEALTH", True):
                context.add_init_script(_STEALTH_INIT_SCRIPT)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            result = worker(page)
            context.close()
            return result
        finally:
            if browser is not None:
                browser.close()


def _sync_extract_text(
    session_id: str,
    user_id: int | None,
    url: str,
    selector: str | None,
    include_title: bool,
    max_length: int,
) -> dict[str, Any]:
    def worker(page: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"url": page.url}
        if include_title:
            out["title"] = page.title()
        if selector:
            elements = page.query_selector_all(selector)
            texts = []
            for el in elements[:100]:
                t = el.inner_text()
                if t.strip():
                    texts.append(t.strip())
            out["selector"] = selector
            out["element_count"] = len(elements)
            out["text"] = "\n---\n".join(texts)
        else:
            body = page.query_selector("body")
            full_text = body.inner_text() if body else ""
            out["text"] = full_text[:max_length]
            out["truncated"] = len(full_text) > max_length

        dest, shot_url = _new_screenshot_target(session_id, user_id=user_id)
        page.screenshot(path=str(dest))
        out["screenshot_url"] = shot_url
        return out

    return _sync_run_on_page(url, worker)


def _sync_extract_attrs(
    session_id: str,
    user_id: int | None,
    url: str,
    selector: str,
    attrs: list[str],
    max_items: int,
) -> dict[str, Any]:
    def worker(page: Any) -> dict[str, Any]:
        elements = page.query_selector_all(selector)
        items: list[dict[str, str]] = []
        for el in elements[:max_items]:
            item: dict[str, str] = {}
            try:
                text = el.inner_text()
                if text.strip():
                    item["text"] = text.strip()[:300]
            except Exception:
                pass
            for attr in attrs:
                try:
                    val = el.get_attribute(attr)
                    if val is not None:
                        item[attr] = val
                except Exception:
                    pass
            if item:
                items.append(item)
        return {
            "success": True,
            "url": page.url,
            "selector": selector,
            "attrs": attrs,
            "total_elements": len(elements),
            "items": items,
        }

    return _sync_run_on_page(url, worker)


def _sync_extract_table(
    session_id: str,
    user_id: int | None,
    url: str,
    selector: str,
    table_index: int,
    output_format: str,
) -> dict[str, Any]:
    def worker(page: Any) -> dict[str, Any]:
        tables = page.query_selector_all(selector)
        if not tables:
            return {"success": False, "error": "页面上未找到表格", "url": page.url}
        idx = min(table_index, len(tables) - 1)
        table = tables[idx]
        headers = [(th.inner_text()).strip() for th in table.query_selector_all("th")]
        rows_data: list[list[str]] = []
        for tr in table.query_selector_all("tr"):
            cells = tr.query_selector_all("td")
            if cells:
                rows_data.append([(td.inner_text()).strip() for td in cells])
        col_names = headers if headers else [f"col_{i}" for i in range(len(rows_data[0]) if rows_data else 0)]
        structured = [
            {(col_names[i] if i < len(col_names) else f"col_{i}"): cell for i, cell in enumerate(row)}
            for row in rows_data
        ]
        if output_format == "csv":
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=col_names or [f"col_{i}" for i in range(len(rows_data[0]) if rows_data else 0)])
            writer.writeheader()
            writer.writerows(structured)
            return {
                "success": True,
                "url": page.url,
                "table_index": idx,
                "total_tables": len(tables),
                "row_count": len(rows_data),
                "csv": buf.getvalue(),
            }
        return {
            "success": True,
            "url": page.url,
            "table_index": idx,
            "total_tables": len(tables),
            "headers": headers,
            "row_count": len(rows_data),
            "data": structured,
        }

    return _sync_run_on_page(url, worker)


def _sync_scroll(
    session_id: str,
    user_id: int | None,
    url: str,
    direction: str,
    amount: int,
    wait_ms: int,
) -> dict[str, Any]:
    def worker(page: Any) -> dict[str, Any]:
        if direction == "bottom":
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif direction == "top":
            page.evaluate("window.scrollTo(0, 0)")
        elif direction == "down":
            page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            page.evaluate(f"window.scrollBy(0, -{amount})")
        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)
        dest, shot_url = _new_screenshot_target(session_id, user_id=user_id)
        page.screenshot(path=str(dest))
        return {
            "success": True,
            "direction": direction,
            "scroll_y": page.evaluate("window.scrollY"),
            "page_height": page.evaluate("document.body.scrollHeight"),
            "screenshot_url": shot_url,
            "url": page.url,
            "title": page.title(),
        }

    return _sync_run_on_page(url, worker)


def _sync_click(
    session_id: str,
    user_id: int | None,
    url: str,
    selector: str | None,
    text: str | None,
    wait_for_navigation: bool,
) -> dict[str, Any]:
    def worker(page: Any) -> dict[str, Any]:
        prev_url = page.url
        if selector:
            if wait_for_navigation:
                try:
                    with page.expect_navigation(wait_until="load", timeout=15000):
                        page.click(selector, timeout=10000)
                except Exception:
                    pass
            else:
                page.click(selector, timeout=10000)
                page.wait_for_timeout(500)
        else:
            if wait_for_navigation:
                try:
                    with page.expect_navigation(wait_until="load", timeout=15000):
                        page.get_by_text(text, exact=False).first.click()
                except Exception:
                    pass
            else:
                page.get_by_text(text, exact=False).first.click()
                page.wait_for_timeout(500)
        dest, shot_url = _new_screenshot_target(session_id, user_id=user_id)
        page.screenshot(path=str(dest))
        return {
            "success": True,
            "prev_url": prev_url,
            "url": page.url,
            "title": page.title(),
            "navigated": page.url != prev_url,
            "screenshot_url": shot_url,
        }

    return _sync_run_on_page(url, worker)


def _sync_extract_list(
    session_id: str,
    user_id: int | None,
    url: str,
    item_selector: str,
    fields: dict | None,
    max_pages: int,
    next_button_selector: str | None,
    infinite_scroll: bool,
    scroll_rounds: int,
) -> dict[str, Any]:
    def worker(page: Any) -> dict[str, Any]:
        all_items: list[dict] = []
        pages_scraped = 0

        def extract_current_page() -> list[dict]:
            elements = page.query_selector_all(item_selector)
            page_items: list[dict] = []
            for el in elements:
                item: dict[str, str] = {}
                if fields:
                    for fname, fsel in fields.items():
                        try:
                            child = el.query_selector(fsel)
                            if child:
                                item[fname] = (child.inner_text()).strip()
                        except Exception:
                            pass
                else:
                    item["text"] = (el.inner_text()).strip()[:500]
                if item:
                    page_items.append(item)
            return page_items

        if infinite_scroll:
            seen = 0
            for rnd in range(scroll_rounds):
                items = extract_current_page()
                all_items.extend(items[seen:])
                seen = len(items)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                new_count = len(page.query_selector_all(item_selector))
                if new_count <= seen:
                    break
                pages_scraped = rnd + 1
        else:
            for page_num in range(max_pages):
                all_items.extend(extract_current_page())
                pages_scraped = page_num + 1
                if not next_button_selector:
                    break
                btn = page.query_selector(next_button_selector)
                if not btn:
                    break
                if btn.get_attribute("disabled"):
                    break
                try:
                    with page.expect_navigation(timeout=15000):
                        btn.click()
                    page.wait_for_timeout(1000)
                except Exception:
                    break

        dest, shot_url = _new_screenshot_target(session_id, user_id=user_id)
        page.screenshot(path=str(dest))
        return {
            "success": True,
            "url": page.url,
            "pages_scraped": pages_scraped,
            "total_items": len(all_items),
            "items": all_items,
            "screenshot_url": shot_url,
            "title": page.title(),
        }

    return _sync_run_on_page(url, worker)


# ── 截图存储目录 ──────────────────────────────────────────────────────────────

def _browser_namespace(user_id: int | None, session_id: str) -> str:
    user_part = f"user_{int(user_id)}" if user_id is not None else "user_system"
    safe_session = re.sub(r"[^a-zA-Z0-9_.-]+", "_", session_id).strip("_") or "default"
    return f"{user_part}/{safe_session}"


def _screenshots_dir(user_id: int | None = None, session_id: str = "default") -> Path:
    root = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "data"
        / "screenshots"
        / (f"user_{int(user_id)}" if user_id is not None else "user_system")
        / (re.sub(r"[^a-zA-Z0-9_.-]+", "_", session_id).strip("_") or "default")
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_screenshots_dir(user_id: int | None = None, session_id: str = "default") -> None:
    root = _screenshots_dir(user_id, session_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def _cleanup_screenshots_namespace(namespace: str) -> None:
    root = Path(__file__).resolve().parent.parent.parent.parent / "data" / "screenshots" / namespace
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


# ── 浏览器状态单例 ────────────────────────────────────────────────────────────

class _BrowserSession:
    """单个会话的浏览器状态（一个 BrowserContext + 一个 Page）"""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._context: Any = None
        self._page: Any = None
        self.current_url: str = ""
        self.page_title: str = ""
        self.last_screenshot_url: str = ""
        self._last_active: float = time.monotonic()

    @property
    def last_active(self) -> float:
        return self._last_active

    def touch(self) -> None:
        self._last_active = time.monotonic()


class BrowserSessionManager:
    """按 session_id 隔离的浏览器会话管理器

    架构：
      1 个 Browser 进程（共享）
        ├── BrowserContext (session_abc) → Page
        ├── BrowserContext (session_def) → Page
        └── BrowserContext (session_xyz) → Page

    每个会话拥有独立的 BrowserContext（Cookie、存储、缓存完全隔离），
    互不干扰，且会话结束后可单独释放资源。
    """

    SESSION_IDLE_TIMEOUT = 1800  # 30 分钟无操作自动清理

    def __init__(self) -> None:
        self._pw: Any = None
        self._browser: Any = None
        self._sessions: dict[str, _BrowserSession] = {}
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Any:
        """确保 Browser 进程已启动"""
        if self._pw is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()

        if self._browser is None or not self._browser.is_connected():
            channel = (os.getenv("BROWSER_CHANNEL") or "").strip() or None
            headed = _env_bool("BROWSER_HEADED", False)
            launch_opts: dict[str, Any] = {
                "headless": not headed,
                "args": [
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--lang=zh-CN",
                    "--window-size=1920,1080",
                    "--disable-infobars",
                ],
            }
            if channel:
                launch_opts["channel"] = channel
            try:
                self._browser = await self._pw.chromium.launch(**launch_opts)
            except Exception as exc:
                if channel:
                    logger.warning(
                        "使用 BROWSER_CHANNEL=%s 启动失败，回退内置 Chromium: %s",
                        channel,
                        exc,
                    )
                    launch_opts.pop("channel", None)
                    self._browser = await self._pw.chromium.launch(**launch_opts)
                else:
                    raise
        return self._browser

    async def get_page(self, session_id: str, user_id: int | None = None) -> Any:
        """获取指定会话的 Page，必要时惰性创建 BrowserContext。"""
        async with self._lock:
            key = _browser_namespace(user_id, session_id)
            if key not in self._sessions:
                self._sessions[key] = _BrowserSession(key)

            session = self._sessions[key]
            session.touch()

            browser = await self._ensure_browser()

            if session._context is None:
                session._context = await browser.new_context(**_new_context_kwargs())
                if _env_bool("BROWSER_STEALTH", True):
                    await session._context.add_init_script(_STEALTH_INIT_SCRIPT)
                session._page = None

            if session._page is None or session._page.is_closed():
                session._page = await session._context.new_page()

            return session._page

    def get_session(self, session_id: str, user_id: int | None = None) -> _BrowserSession | None:
        return self._sessions.get(_browser_namespace(user_id, session_id))

    def get_or_create_session(self, session_id: str, user_id: int | None = None) -> _BrowserSession:
        key = _browser_namespace(user_id, session_id)
        if key not in self._sessions:
            self._sessions[key] = _BrowserSession(key)
        return self._sessions[key]

    async def take_screenshot(
        self,
        session_id: str,
        user_id: int | None = None,
        selector: str | None = None,
        full_page: bool = False,
    ) -> str:
        """截图后保存到磁盘，返回 URL 路径。"""
        page = await self.get_page(session_id, user_id=user_id)
        session = self._sessions[_browser_namespace(user_id, session_id)]
        session.touch()

        fname = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        dest = _screenshots_dir(user_id, session_id) / fname

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

        url = f"/api/browser/screenshot/{session_id}/{fname}"
        session.last_screenshot_url = url
        return url

    async def close_session(self, session_id: str, user_id: int | None = None) -> None:
        """关闭指定会话的 BrowserContext，释放资源。"""
        await self._close_session_by_key(_browser_namespace(user_id, session_id))

    async def _close_session_by_key(self, key: str) -> None:
        session = self._sessions.pop(key, None)
        if session is None:
            _cleanup_screenshots_namespace(key)
            return
        try:
            if session._context:
                await session._context.close()
        except Exception:
            pass
        _cleanup_screenshots_namespace(key)
        logger.info("会话 %s 的浏览器已关闭", key)

    async def reset_session(self, session_id: str, user_id: int | None = None) -> None:
        """重置会话：关闭并清理后等待下一次惰性重建。"""
        await self.close_session(session_id, user_id=user_id)

    async def cleanup_idle_sessions(self) -> int:
        """清理超时未活跃的会话，返回清理数量。"""
        now = time.monotonic()
        expired = [
            sid
            for sid, s in self._sessions.items()
            if now - s.last_active > self.SESSION_IDLE_TIMEOUT
        ]
        for sid in expired:
            await self._close_session_by_key(sid)
        if expired:
            logger.info("清理了 %d 个空闲浏览器会话", len(expired))
        return len(expired)

    async def cleanup(self) -> None:
        """关闭所有会话并释放 Browser 进程（服务器关闭时调用）。"""
        for sid in list(self._sessions.keys()):
            await self._close_session_by_key(sid)
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
        self._pw = None


_manager: BrowserSessionManager | None = None


def get_browser_manager() -> BrowserSessionManager:
    if _manager is None:
        raise RuntimeError("BrowserSessionManager 未初始化，请先调用 init_browser_manager()")
    return _manager


def init_browser_manager() -> BrowserSessionManager:
    global _manager
    if _manager is None:
        _manager = BrowserSessionManager()
    return _manager


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
                    "retry_count": {
                        "type": "integer",
                        "description": "失败重试次数（不含首次），默认 2",
                    },
                    "retry_delay_ms": {
                        "type": "integer",
                        "description": "重试间隔毫秒，默认 1200",
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
        retry_count: int = 2,
        retry_delay_ms: int = 1200,
        session_id: str = "default",
        **_: Any,
    ) -> str:
        mgr = get_browser_manager()
        user_id = _.get("current_user_id") if isinstance(_, dict) else None
        attempts = max(1, retry_count + 1)
        delay_ms = max(0, retry_delay_ms)
        last_exc: Exception | None = None
        async_playwright_ok = _supports_async_playwright_subprocess()

        for attempt in range(1, attempts + 1):
            try:
                if not async_playwright_ok:
                    fallback = await asyncio.to_thread(
                        _sync_navigate_and_screenshot,
                        session_id,
                        user_id,
                        url,
                        wait_for,
                        timeout,
                    )
                    session = mgr.get_or_create_session(session_id, user_id=user_id)
                    session.current_url = fallback["url"]
                    session.page_title = fallback["title"]
                    session.last_screenshot_url = fallback["screenshot_url"]
                    return json.dumps(
                        {
                            "success": True,
                            "url": fallback["url"],
                            "title": fallback["title"],
                            "screenshot_url": fallback["screenshot_url"],
                            "attempt": attempt,
                            "attempts": attempts,
                            "wait_for_used": fallback["wait_for_used"],
                            "fallback": "sync_playwright_precheck",
                        },
                        ensure_ascii=False,
                    )

                page = await mgr.get_page(session_id, user_id=user_id)
                current_wait_for = wait_for
                try:
                    await page.goto(url, wait_until=current_wait_for, timeout=timeout)
                except Exception:
                    # 某些站点会因长尾资源/反爬导致 load 超时；回退到 DOM 就绪提高成功率。
                    if current_wait_for != "load":
                        raise
                    current_wait_for = "domcontentloaded"
                    await page.goto(url, wait_until=current_wait_for, timeout=timeout)

                title = await page.title()
                actual_url = page.url
                session = mgr.get_or_create_session(session_id, user_id=user_id)
                session.current_url = actual_url
                session.page_title = title
                screenshot_url = await mgr.take_screenshot(session_id, user_id=user_id)
                return json.dumps(
                    {
                        "success": True,
                        "url": actual_url,
                        "title": title,
                        "screenshot_url": screenshot_url,
                        "attempt": attempt,
                        "attempts": attempts,
                        "wait_for_used": current_wait_for,
                    },
                    ensure_ascii=False,
                )
            except Exception as exc:
                # Windows 某些运行模式下当前事件循环不支持 asyncio 子进程。
                # Playwright async 驱动会抛 NotImplementedError；改走 sync 兜底。
                if isinstance(exc, NotImplementedError):
                    fallback = await asyncio.to_thread(
                        _sync_navigate_and_screenshot,
                        session_id,
                        user_id,
                        url,
                        wait_for,
                        timeout,
                    )
                    session = mgr.get_or_create_session(session_id, user_id=user_id)
                    session.current_url = fallback["url"]
                    session.page_title = fallback["title"]
                    session.last_screenshot_url = fallback["screenshot_url"]
                    return json.dumps(
                        {
                            "success": True,
                            "url": fallback["url"],
                            "title": fallback["title"],
                            "screenshot_url": fallback["screenshot_url"],
                            "attempt": attempt,
                            "attempts": attempts,
                            "wait_for_used": fallback["wait_for_used"],
                            "fallback": "sync_playwright",
                        },
                        ensure_ascii=False,
                    )
                last_exc = exc
                # 导航失败后重置会话，避免坏掉的 Page/Context 污染后续重试。
                try:
                    await mgr.reset_session(session_id, user_id=user_id)
                except Exception:
                    pass
                if attempt < attempts and delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

        exc = last_exc or RuntimeError("未知导航错误")
        err_name = type(exc).__name__
        err_text = str(exc) or repr(exc)
        hint = ""
        lower = err_text.lower()
        if "cert" in lower or "ssl" in lower or "https" in lower:
            hint = "；建议检查证书，或保持 BROWSER_IGNORE_HTTPS_ERRORS=true"
        elif "timeout" in lower:
            hint = "；建议提高 timeout，或使用 wait_for=domcontentloaded"
        raise ToolExecutionError(
            self.name,
            f"导航失败({err_name})，已重试 {attempts} 次: {err_text}{hint}",
        ) from exc


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
        session_id: str = "default",
        **_: Any,
    ) -> str:
        mgr = get_browser_manager()
        user_id = _.get("current_user_id") if isinstance(_, dict) else None
        session = mgr.get_session(session_id, user_id=user_id)
        if not session or not session.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面，请先使用 browser_navigate")
        if not _supports_async_playwright_subprocess():
            screenshot_url = await asyncio.to_thread(
                _sync_screenshot_from_url,
                session_id,
                user_id,
                session.current_url,
                full_page,
                selector,
            )
            session.last_screenshot_url = screenshot_url
        else:
            screenshot_url = await mgr.take_screenshot(session_id, user_id=user_id, selector=selector, full_page=full_page)
        if not screenshot_url:
            raise ToolExecutionError(self.name, "截图失败")
        return json.dumps(
            {
                "success": True,
                "url": session.current_url,
                "title": session.page_title,
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
        session_id: str = "default",
        **_: Any,
    ) -> str:
        mgr = get_browser_manager()
        user_id = _.get("current_user_id") if isinstance(_, dict) else None
        session = mgr.get_session(session_id, user_id=user_id)
        if not session or not session.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        try:
            if not _supports_async_playwright_subprocess():
                out = await asyncio.to_thread(
                    _sync_extract_text,
                    session_id,
                    user_id,
                    session.current_url,
                    selector,
                    include_title,
                    max_length,
                )
                session.current_url = out.get("url", session.current_url)
                if include_title and isinstance(out.get("title"), str):
                    session.page_title = out["title"]
                if isinstance(out.get("screenshot_url"), str):
                    session.last_screenshot_url = out["screenshot_url"]
                return json.dumps(out, ensure_ascii=False)

            page = await mgr.get_page(session_id, user_id=user_id)
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

            out["screenshot_url"] = await mgr.take_screenshot(session_id, user_id=user_id)
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
        session_id: str = "default",
        **_: Any,
    ) -> str:
        mgr = get_browser_manager()
        user_id = _.get("current_user_id") if isinstance(_, dict) else None
        session = mgr.get_session(session_id, user_id=user_id)
        if not session or not session.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        target_attrs = attrs or ["href", "src"]
        try:
            if not _supports_async_playwright_subprocess():
                out = await asyncio.to_thread(
                    _sync_extract_attrs,
                    session_id,
                    user_id,
                    session.current_url,
                    selector,
                    target_attrs,
                    max_items,
                )
                return json.dumps(out, ensure_ascii=False)

            page = await mgr.get_page(session_id, user_id=user_id)
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
        session_id: str = "default",
        **_: Any,
    ) -> str:
        mgr = get_browser_manager()
        user_id = _.get("current_user_id") if isinstance(_, dict) else None
        session = mgr.get_session(session_id, user_id=user_id)
        if not session or not session.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        try:
            if not _supports_async_playwright_subprocess():
                out = await asyncio.to_thread(
                    _sync_extract_table,
                    session_id,
                    user_id,
                    session.current_url,
                    selector,
                    table_index,
                    output_format,
                )
                return json.dumps(out, ensure_ascii=False)

            page = await mgr.get_page(session_id, user_id=user_id)
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
        session_id: str = "default",
        **_: Any,
    ) -> str:
        mgr = get_browser_manager()
        user_id = _.get("current_user_id") if isinstance(_, dict) else None
        session = mgr.get_session(session_id, user_id=user_id)
        if not session or not session.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        try:
            if not _supports_async_playwright_subprocess():
                out = await asyncio.to_thread(
                    _sync_scroll,
                    session_id,
                    user_id,
                    session.current_url,
                    direction,
                    amount,
                    wait_ms,
                )
                session.current_url = out.get("url", session.current_url)
                if isinstance(out.get("title"), str):
                    session.page_title = out["title"]
                if isinstance(out.get("screenshot_url"), str):
                    session.last_screenshot_url = out["screenshot_url"]
                return json.dumps({k: v for k, v in out.items() if k != "title"}, ensure_ascii=False)

            page = await mgr.get_page(session_id, user_id=user_id)
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
            screenshot_url = await mgr.take_screenshot(session_id, user_id=user_id)

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
        session_id: str = "default",
        **_: Any,
    ) -> str:
        mgr = get_browser_manager()
        user_id = _.get("current_user_id") if isinstance(_, dict) else None
        session = mgr.get_session(session_id, user_id=user_id)
        if not session or not session.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        if not selector and not text:
            raise ToolExecutionError(self.name, "selector 和 text 至少需提供一个")
        try:
            if not _supports_async_playwright_subprocess():
                out = await asyncio.to_thread(
                    _sync_click,
                    session_id,
                    user_id,
                    session.current_url,
                    selector,
                    text,
                    wait_for_navigation,
                )
                session.current_url = out.get("url", session.current_url)
                if isinstance(out.get("title"), str):
                    session.page_title = out["title"]
                if isinstance(out.get("screenshot_url"), str):
                    session.last_screenshot_url = out["screenshot_url"]
                return json.dumps(out, ensure_ascii=False)

            page = await mgr.get_page(session_id, user_id=user_id)
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
            session.current_url = new_url
            session.page_title = title
            screenshot_url = await mgr.take_screenshot(session_id, user_id=user_id)

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
        session_id: str = "default",
        **_: Any,
    ) -> str:
        mgr = get_browser_manager()
        user_id = _.get("current_user_id") if isinstance(_, dict) else None
        session = mgr.get_session(session_id, user_id=user_id)
        if not session or not session.current_url:
            raise ToolExecutionError(self.name, "尚未导航到任何页面")
        try:
            if not _supports_async_playwright_subprocess():
                out = await asyncio.to_thread(
                    _sync_extract_list,
                    session_id,
                    user_id,
                    session.current_url,
                    item_selector,
                    fields,
                    max_pages,
                    next_button_selector,
                    infinite_scroll,
                    scroll_rounds,
                )
                session.current_url = out.get("url", session.current_url)
                if isinstance(out.get("title"), str):
                    session.page_title = out["title"]
                if isinstance(out.get("screenshot_url"), str):
                    session.last_screenshot_url = out["screenshot_url"]
                return json.dumps({k: v for k, v in out.items() if k != "title"}, ensure_ascii=False)

            page = await mgr.get_page(session_id, user_id=user_id)
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

            screenshot_url = await mgr.take_screenshot(session_id, user_id=user_id)
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
