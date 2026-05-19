"""
飞书任务工具共享逻辑。

被 LarkMyTasksTool / LarkRelatedTasksTool 复用：
  - 时间戳格式化（毫秒 / ISO → 北京时间字符串）
  - 相对日期 → 毫秒时间戳窗口（today / tomorrow / this_week / overdue / ...）
  - lark-cli 列表返回结构兼容抽取
  - 单条任务详情合并
  - 并发拉取 tasks.get 补齐 status / completed_at
  - 统一摘要 + 排序 + 打包

设计原则：
  +get-my-tasks / +get-related-tasks 的列表接口只投影 created_at/due_at/guid/summary/url，
  缺失 status 与 completed_at，导致 LLM 误判"任务没有完成时间"。
  这里强制对每条任务再调 `task tasks get` 拉详情拼回，保证返回结果一定带完成状态。

  另外为了让 LLM 无需自己算时间戳，提供 `today/tomorrow/this_week/...` 等相对日期窗口
  解析，本地按北京时区计算后下发毫秒时间戳给 CLI，避免依赖 lark-cli 的字符串解析行为。
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any

from backend.lark_service import run_lark_command

# 飞书任务时间戳为毫秒级 Unix 时间，统一以北京时间呈现
_CN_TZ = timezone(timedelta(hours=8))

# 并发详情拉取上限，避免对 lark-cli / 飞书侧造成压力
_DETAIL_CONCURRENCY = 5


def to_beijing_str(value: Any) -> str | None:
    """
    将任意时间字段规范化为 'YYYY-MM-DD HH:MM:SS' (+08:00)。
    兼容：毫秒 Unix 时间戳（int / 数字字符串）、ISO 8601、None/''/'0'。
    """
    if value is None or value == "" or value == "0":
        return None

    ts_int: int | None = None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        ts_int = int(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.lstrip("-").isdigit():
            ts_int = int(s)
        else:
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_CN_TZ)
                else:
                    dt = dt.astimezone(_CN_TZ)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                return s  # 无法解析就原样返回，避免丢信息

    if ts_int is None or ts_int <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts_int / 1000, tz=_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return None


def _now_ms() -> int:
    return int(datetime.now(tz=_CN_TZ).timestamp() * 1000)


# 相对日期 / 偏移正则（如 +3d / -1w / 0m）。
_OFFSET_RE = re.compile(r"^([+-]?\d+)([dwm])$")


def _dt_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _parse_relative_or_absolute(value: str, *, now: datetime) -> int | None:
    """
    将字符串解析为毫秒时间戳。支持：
      - 纯毫秒数字（'1777334400000'）
      - ISO 8601（'2026-05-21T08:00:00+08:00' / '2026-05-21'）
      - 简单偏移：'+3d' / '-1w' / '0m'（按北京时区从 now 出发的"天/周/月"）
    解析失败返回 None。
    """
    s = (value or "").strip()
    if not s:
        return None

    # 数字字符串视作毫秒时间戳
    if s.lstrip("-").isdigit():
        try:
            ms = int(s)
            return ms if ms > 0 else None
        except ValueError:
            return None

    # 偏移
    m = _OFFSET_RE.match(s)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit == "d":
            target = now + timedelta(days=amount)
        elif unit == "w":
            target = now + timedelta(weeks=amount)
        else:  # 'm' → 当月相邻（按 30 天估算，避免月末歧义；够 LLM 用）
            target = now + timedelta(days=30 * amount)
        return _dt_to_ms(target)

    # ISO 8601
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_CN_TZ)
        return _dt_to_ms(dt)
    except (ValueError, TypeError):
        return None


def resolve_due_window(
    due: str | None,
    due_start: str | None,
    due_end: str | None,
    *,
    now: datetime | None = None,
) -> tuple[int | None, int | None, dict[str, Any]]:
    """
    把 due 关键字 + due_start/due_end 解析成 (start_ms, end_ms, meta)。

    支持的 `due` 关键字（按北京时区，含上下闭半开区间 [start, end)）：
      - today          : 今日 00:00 → 明日 00:00
      - tomorrow       : 明日 00:00 → 后天 00:00
      - yesterday      : 昨日 00:00 → 今日 00:00
      - this_week      : 本周一 00:00 → 下周一 00:00（按 ISO 周）
      - next_week      : 下周一 00:00 → 下下周一 00:00
      - last_week      : 上周一 00:00 → 本周一 00:00
      - this_month     : 本月 1 日 00:00 → 下月 1 日 00:00
      - overdue        : 截至此刻（end=now，start=None）—— 调用方应额外加 completed=todo
      - upcoming_7d    : 此刻 → +7d
      - all / None     : 不限制

    `due_start` / `due_end` 是更细的覆盖：可填 'today' / 'tomorrow' /
    ISO 日期 / 偏移（如 '+3d' / '-1w'） / 毫秒时间戳。两者都不传时，
    用 `due` 计算；如果都传了，以 due_start / due_end 为准。
    单独传其中一个时，另一个保持 None（不加约束）。

    返回 (start_ms, end_ms, meta)：
      meta 用于回显给前端 / 写入 filter 字段，便于审计。
    """
    now = now or datetime.now(tz=_CN_TZ)
    meta: dict[str, Any] = {}

    # 1) 优先以显式 due_start / due_end 覆盖
    if due_start or due_end:
        s_ms = _parse_relative_or_absolute(due_start, now=now) if due_start else None
        e_ms = _parse_relative_or_absolute(due_end, now=now) if due_end else None
        meta = {"due": due, "due_start": due_start, "due_end": due_end}
        return s_ms, e_ms, meta

    # 2) 关键字模式
    key = (due or "").strip().lower()
    if not key or key == "all":
        meta = {"due": key or None}
        return None, None, meta

    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _week_monday(d: datetime) -> datetime:
        return d - timedelta(days=d.weekday())

    if key == "today":
        s, e = today0, today0 + timedelta(days=1)
    elif key == "tomorrow":
        s, e = today0 + timedelta(days=1), today0 + timedelta(days=2)
    elif key == "yesterday":
        s, e = today0 - timedelta(days=1), today0
    elif key == "this_week":
        mon = _week_monday(today0)
        s, e = mon, mon + timedelta(days=7)
    elif key == "next_week":
        mon = _week_monday(today0) + timedelta(days=7)
        s, e = mon, mon + timedelta(days=7)
    elif key == "last_week":
        mon = _week_monday(today0) - timedelta(days=7)
        s, e = mon, mon + timedelta(days=7)
    elif key == "this_month":
        s = today0.replace(day=1)
        # 跳到下月 1 号
        if s.month == 12:
            e = s.replace(year=s.year + 1, month=1)
        else:
            e = s.replace(month=s.month + 1)
    elif key == "overdue":
        # 已到期：截至此刻；调用方一般还要附加 completed=todo
        s, e = None, now
        meta = {"due": "overdue"}
        return None, _dt_to_ms(e), meta
    elif key == "upcoming_7d":
        s, e = now, now + timedelta(days=7)
    else:
        # 未知关键字：原样下发给 CLI，由 CLI 自行解析（最后兜底）
        meta = {"due": key, "_note": "unknown keyword, passed to CLI as-is"}
        # 这里返回 None，让外层把原字符串透传
        return None, None, meta

    meta = {
        "due": key,
        "due_start": to_beijing_str(_dt_to_ms(s)) if s else None,
        "due_end": to_beijing_str(_dt_to_ms(e)) if e else None,
    }
    return (_dt_to_ms(s) if s else None), (_dt_to_ms(e) if e else None), meta


def extract_task_items(raw: Any) -> list[dict[str, Any]]:
    """
    从 lark-cli 返回结构中提取任务列表，兼容多种 schema：
      - {"code":0,"data":{"items":[...]}}
      - {"data":{"tasks":[...]}}
      - {"items":[...]}
      - 直接是 list
      - 单对象（含 guid）
    """
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if not isinstance(raw, dict):
        return []
    candidate = raw.get("data", raw)
    if isinstance(candidate, list):
        return [x for x in candidate if isinstance(x, dict)]
    if isinstance(candidate, dict):
        for key in ("items", "tasks"):
            items = candidate.get(key)
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
        if "guid" in candidate:
            return [candidate]
    return []


def extract_task_detail(raw: Any) -> dict[str, Any] | None:
    """从 `task tasks get` 返回中提取 task 对象。"""
    if not isinstance(raw, dict):
        return None
    inner = raw.get("data", raw)
    if isinstance(inner, dict):
        task = inner.get("task")
        if isinstance(task, dict):
            return task
        if "guid" in inner:
            return inner
    return None


def summarize_task(merged: dict[str, Any]) -> dict[str, Any]:
    """
    将合并后的任务（列表字段 + tasks.get 详情）压成面向 LLM/用户的精简摘要。
    硬性保证：每条结果都带 `status` / `is_completed` / `completed_at`。
    """
    status = str(merged.get("status") or "").strip().lower() or "todo"
    completed_str = to_beijing_str(merged.get("completed_at"))
    is_completed = status == "done" or bool(completed_str)

    due_ms = extract_due_ms(merged)
    due_str = to_beijing_str(due_ms)

    # 逾期判定：未完成且 due 已过
    overdue = bool(not is_completed and due_ms and due_ms > 0 and due_ms < _now_ms())

    guid = merged.get("guid")
    url = merged.get("url") or (
        f"https://applink.feishu.cn/client/todo/detail?guid={guid}" if guid else None
    )

    summary: dict[str, Any] = {
        "guid": guid,
        "summary": merged.get("summary"),
        "status": status,
        "is_completed": is_completed,
        "completed_at": completed_str,
        "created_at": to_beijing_str(merged.get("created_at")),
        "due_at": due_str,
        "overdue": overdue,
        "url": url,
    }
    if "_error" in merged:
        summary["_error"] = merged["_error"]
    return summary


def extract_due_ms(task: dict[str, Any]) -> int | None:
    """
    从任务字典里抽出 due 毫秒时间戳（单源真相，被 summarize_task / filter_by_due_window 共用）。
    兼容多种 schema：
      - {"due_at": <ms int / 数字字符串 / ISO 字符串>}
      - {"due": {"timestamp": <ms>}}
    无 due 或解析失败返回 None。
    """
    raw: Any = task.get("due_at")
    if raw in (None, "", "0"):
        due_obj = task.get("due")
        if isinstance(due_obj, dict):
            raw = due_obj.get("timestamp")

    if raw in (None, "", "0"):
        return None

    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        ms = int(raw)
        return ms if ms > 0 else None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        if s.lstrip("-").isdigit():
            try:
                ms = int(s)
                return ms if ms > 0 else None
            except ValueError:
                return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_CN_TZ)
            return _dt_to_ms(dt)
        except (ValueError, TypeError):
            return None
    return None


def filter_by_due_window(
    items: list[dict[str, Any]],
    *,
    start_ms: int | None,
    end_ms: int | None,
    drop_no_due: bool = True,
) -> list[dict[str, Any]]:
    """
    客户端二次过滤：保留 due 落在 [start_ms, end_ms) 内的任务。
    - 任一边界为 None 表示该方向不限制
    - 都为 None 时直接返回原列表
    - drop_no_due=True 时，无 due 字段的任务会被剔除（默认）；
      drop_no_due=False 时保留（用于"all"等不带窗口的场景）
    """
    if start_ms is None and end_ms is None:
        return list(items)

    out: list[dict[str, Any]] = []
    for item in items:
        ms = extract_due_ms(item)
        if ms is None:
            if not drop_no_due:
                out.append(item)
            continue
        if start_ms is not None and ms < start_ms:
            continue
        if end_ms is not None and ms >= end_ms:
            continue
        out.append(item)
    return out


async def fetch_and_merge_tasks(
    account: Any,
    items: list[dict[str, Any]],
    *,
    identity: str,
    include_detail: bool,
) -> list[dict[str, Any]]:
    """
    对列表里每条任务并发调 `task tasks get` 拉详情，并把详情字段合并回原 item。
    include_detail=False 时直接返回列表字段（不补齐 status / completed_at）。
    单条详情失败不会拖死整体；失败条带 `_error` 继续返回。
    """
    if not include_detail or not items:
        return list(items)

    sem = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def fetch_detail(item: dict[str, Any]) -> dict[str, Any]:
        guid = item.get("guid")
        if not guid:
            return item
        async with sem:
            try:
                detail_res = await run_lark_command(
                    account,
                    [
                        "task",
                        "tasks",
                        "get",
                        "--as",
                        identity,
                        "--params",
                        json.dumps({"task_guid": guid}, ensure_ascii=False),
                    ],
                )
                detail = extract_task_detail(detail_res.get("data"))
                if detail:
                    return {**item, **detail}
                return item
            except Exception as exc:  # 单条失败不中断整体
                detail_err = getattr(exc, "detail", None)
                err_msg = (
                    json.dumps(detail_err, ensure_ascii=False)
                    if detail_err is not None
                    else str(exc)
                )
                return {**item, "_error": f"detail_fetch_failed: {err_msg}"}

    return list(await asyncio.gather(*(fetch_detail(it) for it in items)))


def build_tasks_payload(
    summaries: list[dict[str, Any]],
    *,
    filter_meta: dict[str, Any],
    query_time: datetime | None = None,
) -> dict[str, Any]:
    """
    把摘要列表打包成统一结构（query_time / filter / stats / tasks），
    并按"未完成在前 → due 升序 → created 降序"排序。

    `query_time` 是本次查询使用的"现在"锚点（北京时区）。即使 LLM 没有先调
    `current_time`，响应里仍然会带这个字段，避免"今天 / 已逾期"的解读漂移。
    """
    summaries.sort(
        key=lambda s: (
            s.get("is_completed") is True,
            s.get("due_at") or "9999-12-31 00:00:00",
            s.get("created_at") or "",
        )
    )
    done_count = sum(1 for s in summaries if s.get("is_completed"))
    qt = query_time or datetime.now(tz=_CN_TZ)
    return {
        "query_time": qt.astimezone(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "query_time_weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][qt.weekday()],
        "filter": filter_meta,
        "stats": {
            "total": len(summaries),
            "done": done_count,
            "todo": len(summaries) - done_count,
            "overdue": sum(1 for s in summaries if s.get("overdue")),
        },
        "tasks": summaries,
    }
