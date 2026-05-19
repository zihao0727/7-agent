"""
RunCodeTool —— AI 代码执行工具

AI 调用此工具生成并运行代码，结果自动存储到 session 级别的内存 store。
前端 CodePanel 轮询 GET /api/code/results/{session_id} 实时展示。

支持语言：Python（含 matplotlib 图表）、JavaScript、TypeScript、Bash
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import tempfile
import textwrap
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from backend.workspace import session_subdir, session_workspace_root

from ..base import BaseTool, ToolExecutionError, ToolSchema

# ─────────────────────────────────────────────────────────────────────────────
# 结果存储（内存，按 session_id 隔离，每个 session 最多保留 50 条）
# ─────────────────────────────────────────────────────────────────────────────

_store: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))


def _store_key(session_id: str, user_id: int | None = None) -> str:
    user_part = f"user:{int(user_id)}" if user_id is not None else "user:system"
    return f"{user_part}:session:{session_id}"


def get_code_results(session_id: str, user_id: int | None = None) -> list[dict]:
    """返回指定 session 的执行历史（最新在后）"""
    return list(_store.get(_store_key(session_id, user_id), []))


def clear_code_results(session_id: str, user_id: int | None = None) -> None:
    """清除指定 session 的执行历史"""
    key = _store_key(session_id, user_id)
    if key in _store:
        _store[key].clear()


# ─────────────────────────────────────────────────────────────────────────────
# Python matplotlib 拦截包装
# ─────────────────────────────────────────────────────────────────────────────

_MATPLOTLIB_PREAMBLE = textwrap.dedent("""\
import sys as _sys, io as _io, base64 as _base64, json as _json

try:
    import matplotlib as _mpl
    _mpl.use('Agg')
    import matplotlib.pyplot as _plt
    from matplotlib import font_manager as _font_manager
    import platform as _platform

    # ── 中文显示：择优选用本机已安装的 CJK 无衬线字体，并修复负号乱码 ──
    _cjk_by_os = {
        "Windows": [
            "Microsoft YaHei", "Microsoft YaHei UI", "SimHei", "KaiTi",
            "FangSong", "SimSun",
        ],
        "Darwin": [
            "PingFang SC", "Heiti SC", "Songti SC", "STHeiti", "Arial Unicode MS",
        ],
    }
    _cjk_fallback = [
        "Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Serif CJK SC",
        "WenQuanYi Micro Hei", "WenQuanYi Zen Hei", "Source Han Sans SC",
        "Droid Sans Fallback", "AR PL UMing CN", "SimHei",
    ]
    _installed = {getattr(_f, "name", "") for _f in _font_manager.fontManager.ttflist}
    _prefer = list(_cjk_by_os.get(_platform.system(), [])) + _cjk_fallback
    _first = next((_n for _n in _prefer if _n in _installed), None)
    if _first:
        _plt.rcParams["font.sans-serif"] = [_first] + [x for x in _prefer if x != _first] + ["DejaVu Sans"]
    else:
        # 未命中名称时仍设置候选链，由 matplotlib 在系统中解析
        _plt.rcParams["font.sans-serif"] = _prefer + ["DejaVu Sans", "sans-serif"]
    _plt.rcParams["axes.unicode_minus"] = False

    _captured_images: list[str] = []

    def _capture_show(*a, **kw):
        for _fn in _plt.get_fignums():
            _plt.figure(_fn)
            _buf = _io.BytesIO()
            _plt.savefig(_buf, format='png', dpi=150, bbox_inches='tight')
            _buf.seek(0)
            _captured_images.append(_base64.b64encode(_buf.read()).decode())
            _buf.close()
            _plt.close(_fn)

    _plt.show = _capture_show
    import matplotlib.pyplot as plt   # 供用户代码使用
except ImportError:
    _captured_images = []

""")

_MATPLOTLIB_POSTAMBLE = textwrap.dedent("""\

# 捕获未调用 show() 的图形
try:
    import matplotlib.pyplot as _plt_f
    for _fn in _plt_f.get_fignums():
        _plt_f.figure(_fn)
        _buf = _io.BytesIO()
        _plt_f.savefig(_buf, format='png', dpi=150, bbox_inches='tight')
        _buf.seek(0)
        _captured_images.append(_base64.b64encode(_buf.read()).decode())
        _buf.close()
        _plt_f.close(_fn)
except Exception:
    pass

if _captured_images:
    print("\\n__IMAGES__" + _json.dumps(_captured_images) + "__IMAGES__", flush=True)
""")


# ─────────────────────────────────────────────────────────────────────────────
# 子进程输出解码（Windows 下 Python 默认控制台常为 GBK，需与 UTF-8 兼容）
# ─────────────────────────────────────────────────────────────────────────────

def _decode_subprocess_output(data: bytes) -> str:
    """将子进程原始字节解码为 str；优先 UTF-8，失败或含替换符时回退 GBK/cp936。"""
    if not data:
        return ""
    try:
        text = data.decode("utf-8")
        if "\ufffd" not in text:
            return text
    except UnicodeDecodeError:
        pass
    for enc in ("gbk", "gb18030", "cp936"):
        try:
            t = data.decode(enc)
            if "\ufffd" not in t:
                return t
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _python_utf8_env() -> dict[str, str]:
    """强制子进程 Python 使用 UTF-8 标准流，避免 Windows 下 print 走 ANSI 代码页导致乱码。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


# ─────────────────────────────────────────────────────────────────────────────
# 各语言执行器
# ─────────────────────────────────────────────────────────────────────────────

async def _exec_python(code: str, timeout: int, workspace: str) -> tuple[str, str, int, list[str]]:
    wrapped = _MATPLOTLIB_PREAMBLE + code + _MATPLOTLIB_POSTAMBLE
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8", dir=workspace) as f:
        f.write(wrapped)
        path = f.name
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_python_utf8_env(),
            cwd=workspace,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill(); await proc.communicate()
            return "", f"执行超时（{timeout}s）", -1, []

        stdout = _decode_subprocess_output(out)
        stderr = _decode_subprocess_output(err)
        images: list[str] = []
        if "__IMAGES__" in stdout:
            parts = stdout.split("__IMAGES__")
            stdout = parts[0].rstrip("\n")
            try:
                images = json.loads(parts[1])
            except Exception:
                pass
        return stdout, stderr, proc.returncode or 0, images
    finally:
        try: os.unlink(path)
        except Exception: pass


async def _exec_node(code: str, timeout: int, workspace: str) -> tuple[str, str, int, list[str]]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False, encoding="utf-8", dir=workspace) as f:
        f.write(code); path = f.name
    try:
        proc = await asyncio.create_subprocess_exec(
            "node", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=workspace,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill(); await proc.communicate()
            return "", f"执行超时（{timeout}s）", -1, []
        return _decode_subprocess_output(out), _decode_subprocess_output(err), proc.returncode or 0, []
    finally:
        try: os.unlink(path)
        except Exception: pass


async def _exec_typescript(code: str, timeout: int, workspace: str) -> tuple[str, str, int, list[str]]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False, encoding="utf-8", dir=workspace) as f:
        f.write(code); path = f.name
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    try:
        for runner in [[npx, "tsx", path], [npx, "ts-node", path]]:
            proc = await asyncio.create_subprocess_exec(
                *runner,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill(); await proc.communicate()
                return "", f"执行超时（{timeout}s）", -1, []
            if proc.returncode not in (127, 9009):
                return _decode_subprocess_output(out), _decode_subprocess_output(err), proc.returncode or 0, []
        return "", "未找到 tsx 或 ts-node，请运行: npm install -g tsx", 1, []
    finally:
        try: os.unlink(path)
        except Exception: pass


async def _exec_bash(code: str, timeout: int, workspace: str) -> tuple[str, str, int, list[str]]:
    if sys.platform == "win32":
        bash = next(
            (c for c in [r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe", "bash"]
             if os.path.isfile(c) or c == "bash"),
            "bash",
        )
    else:
        bash = "bash"
    proc = await asyncio.create_subprocess_exec(
        bash, "-c", code,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=workspace,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill(); await proc.communicate()
        return "", f"执行超时（{timeout}s）", -1, []
    return _decode_subprocess_output(out), _decode_subprocess_output(err), proc.returncode or 0, []


# ─────────────────────────────────────────────────────────────────────────────
# AI 工具定义
# ─────────────────────────────────────────────────────────────────────────────

class RunCodeTool(BaseTool):
    """
    在沙箱中执行 AI 生成的代码，结果展示给用户。
    支持 Python / JavaScript / TypeScript / Bash。
    Python 代码中使用 matplotlib 绘图会自动捕获图表。
    """

    name = "run_code"
    description = (
        "执行代码并将结果（输出、图表）实时展示给用户。\n"
        "【必填】每次调用必须同时传入 code（完整代码字符串）和 description（一句话说明目的）；禁止传空参数 {}。\n"
        "【适用场景】数据分析、算法验证、可视化、文件处理、前端动画（可用 javascript 输出 HTML 到 stdout 供用户复制）等。\n"
        "【支持语言】python（matplotlib/numpy/pandas）、javascript、typescript、bash。\n"
        "【绘图】Python 中 matplotlib 的 plt.show() 会自动捕获图表展示给用户。\n"
        "【注意】每次调用独立进程，变量不跨调用共享；返回给模型的是 stdout/stderr 摘要，不要通过反复打印整份文件来读取数据，文件处理请输出结构化摘要并保存结果文件。"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的完整代码",
                    },
                    "language": {
                        "type": "string",
                        "enum": ["python", "javascript", "typescript", "bash"],
                        "description": "代码语言，默认 python",
                        "default": "python",
                    },
                    "description": {
                        "type": "string",
                        "description": "简短描述本次代码的目的（会显示给用户），例如：'绘制销售趋势折线图'",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话 ID（系统自动注入，无需手动填写）",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数（默认 30）",
                        "default": 30,
                    },
                },
                "required": ["code", "description"],
            },
        )

    async def execute(
        self,
        code: str | None = None,
        description: str | None = None,
        language: str = "python",
        session_id: str = "",
        current_user_id: int | None = None,
        timeout: int = 30,
        **_: Any,
    ) -> str:
        # LLM 有时会传 {} 或漏字段；用可选参数避免 TypeError，再显式校验
        code_s = (code or "").strip()
        desc_s = (description or "").strip()
        if not code_s:
            raise ToolExecutionError(
                self.name,
                "调用 run_code 时必须提供非空字符串参数 code（完整可执行代码）。"
                "禁止发送空对象 {}。若需生成前端动画，请把完整 JavaScript/HTML 代码写入 code。",
            )
        if not desc_s:
            raise ToolExecutionError(
                self.name,
                "调用 run_code 时必须提供非空字符串参数 description（简述本次代码目的，将展示给用户）。",
            )

        if current_user_id is None:
            raise ToolExecutionError(self.name, "Missing current_user_id for workspace-isolated code execution.")
        scoped_session_id = session_id or "default"
        session_workspace_root(int(current_user_id), scoped_session_id)
        workspace = str(session_subdir(int(current_user_id), scoped_session_id, "code"))

        start = time.monotonic()

        if language == "python":
            stdout, stderr, exit_code, images = await _exec_python(code_s, timeout, workspace)
        elif language == "javascript":
            stdout, stderr, exit_code, images = await _exec_node(code_s, timeout, workspace)
        elif language == "typescript":
            stdout, stderr, exit_code, images = await _exec_typescript(code_s, timeout, workspace)
        elif language == "bash":
            stdout, stderr, exit_code, images = await _exec_bash(code_s, timeout, workspace)
        else:
            raise ToolExecutionError(self.name, f"不支持的语言: {language}")

        elapsed = time.monotonic() - start

        # 存储到 session 结果库
        record: dict = {
            "id": uuid.uuid4().hex[:12],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "language": language,
            "description": desc_s,
            "code": code_s,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "images": images,
            "execution_time": round(elapsed, 3),
        }
        _store[_store_key(scoped_session_id, current_user_id)].append(record)

        # 返回给 AI 的简洁摘要
        status = "成功" if exit_code == 0 else f"失败(exit={exit_code})"
        parts = [f"[{language}] {desc_s} — 执行{status}，耗时 {elapsed:.2f}s"]
        if stdout:
            limit = 4000
            preview = stdout[:limit]
            if len(stdout) > limit:
                preview += (
                    "\n\n[stdout preview truncated; full stdout is shown in the code panel. "
                    "Do not retry only to print more rows. Save complete data to a file or print a compact summary.]"
                )
            parts.append(f"stdout:\n{preview}")
        if stderr:
            limit = 1200
            preview = stderr[:limit]
            if len(stderr) > limit:
                preview += "\n\n[stderr preview truncated.]"
            parts.append(f"stderr:\n{preview}")
        if images:
            parts.append(f"已生成 {len(images)} 张图表，已展示给用户。")
        return "\n\n".join(parts)
