"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  Clock,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import {
  createScheduledTask,
  deleteScheduledTask,
  fetchScheduledTasks,
  updateScheduledTask,
} from "@/lib/api";
import type { ScheduledTaskInfo, ScheduledTaskType } from "@/lib/types";
import { cn } from "@/lib/utils";

const TYPE_LABELS: Record<ScheduledTaskType, string> = {
  once: "执行一次",
  interval: "固定间隔",
  daily: "每天",
};

const STATUS_LABELS: Record<string, string> = {
  enabled: "等待中",
  paused: "已暂停",
  disabled: "已暂停",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
};

function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}

function toLocalInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

function defaultRunAt(): string {
  const date = new Date(Date.now() + 10 * 60 * 1000);
  return toLocalInputValue(date);
}

export default function ScheduledTasksPage() {
  const [tasks, setTasks] = useState<ScheduledTaskInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState({
    title: "",
    prompt: "",
    schedule_type: "once" as ScheduledTaskType,
    run_at: defaultRunAt(),
    interval_minutes: 60,
    time_of_day: "09:00",
    model: process.env.NEXT_PUBLIC_DEEPSEEK_MODEL || "deepseek-v4-flash",
  });

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setTasks(await fetchScheduledTasks());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载定时任务失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const sortedTasks = useMemo(
    () =>
      [...tasks].sort((a, b) => {
        const left = a.next_run_at ? new Date(a.next_run_at).getTime() : 0;
        const right = b.next_run_at ? new Date(b.next_run_at).getTime() : 0;
        return right - left;
      }),
    [tasks]
  );

  const createDisabled =
    !draft.title.trim() ||
    !draft.prompt.trim() ||
    (draft.schedule_type === "once" && !draft.run_at) ||
    (draft.schedule_type === "interval" && draft.interval_minutes < 1) ||
    (draft.schedule_type === "daily" && !draft.time_of_day) ||
    savingId === "new";

  const handleCreate = async () => {
    if (createDisabled) return;
    setSavingId("new");
    setError(null);
    try {
      const task = await createScheduledTask({
        title: draft.title.trim(),
        prompt: draft.prompt.trim(),
        schedule_type: draft.schedule_type,
        run_at: draft.schedule_type === "once" ? new Date(draft.run_at).toISOString() : null,
        interval_minutes:
          draft.schedule_type === "interval" ? Number(draft.interval_minutes) : null,
        time_of_day: draft.schedule_type === "daily" ? draft.time_of_day : null,
        timezone_offset_minutes:
          draft.schedule_type === "daily" ? new Date().getTimezoneOffset() : null,
        model: draft.model,
      });
      setTasks((prev) => [task, ...prev]);
      setDraft((prev) => ({
        ...prev,
        title: "",
        prompt: "",
        run_at: defaultRunAt(),
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建定时任务失败");
    } finally {
      setSavingId(null);
    }
  };

  const toggleTask = async (task: ScheduledTaskInfo) => {
    setSavingId(task.id);
    setError(null);
    try {
      const next = await updateScheduledTask(task.id, task.status !== "enabled");
      setTasks((prev) => prev.map((item) => (item.id === task.id ? next : item)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "更新定时任务失败");
    } finally {
      setSavingId(null);
    }
  };

  const removeTask = async (task: ScheduledTaskInfo) => {
    if (!confirm(`确定删除定时任务「${task.title}」吗？`)) return;
    setSavingId(task.id);
    setError(null);
    try {
      await deleteScheduledTask(task.id);
      setTasks((prev) => prev.filter((item) => item.id !== task.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除定时任务失败");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-white dark:bg-[#191919]">
      <header className="flex h-[64px] shrink-0 items-center justify-between border-b border-gray-200 px-6 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gray-100 text-gray-800 dark:bg-white/10 dark:text-gray-100">
            <CalendarClock className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-gray-950 dark:text-gray-50">定时任务</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              到点后自动创建会话并执行 Agent 任务，任务调度由 Redis 驱动。
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-gray-100"
          title="刷新"
        >
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
        </button>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto flex max-w-5xl flex-col gap-5">
          <section className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200">
              <Plus className="h-4 w-4" />
              创建任务
            </div>
            <div className="grid gap-3 md:grid-cols-[1fr_180px]">
              <input
                value={draft.title}
                onChange={(e) => setDraft((prev) => ({ ...prev, title: e.target.value }))}
                placeholder="任务名称"
                className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111] dark:text-gray-100"
              />
              <select
                value={draft.schedule_type}
                onChange={(e) =>
                  setDraft((prev) => ({
                    ...prev,
                    schedule_type: e.target.value as ScheduledTaskType,
                  }))
                }
                className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-800 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111] dark:text-gray-100"
              >
                {Object.entries(TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-[1fr_180px_120px]">
              {draft.schedule_type === "once" && (
                <input
                  type="datetime-local"
                  value={draft.run_at}
                  onChange={(e) => setDraft((prev) => ({ ...prev, run_at: e.target.value }))}
                  className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111] dark:text-gray-100"
                />
              )}
              {draft.schedule_type === "interval" && (
                <input
                  type="number"
                  min={1}
                  value={draft.interval_minutes}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      interval_minutes: Number(e.target.value),
                    }))
                  }
                  className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111] dark:text-gray-100"
                  placeholder="间隔分钟"
                />
              )}
              {draft.schedule_type === "daily" && (
                <input
                  type="time"
                  value={draft.time_of_day}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, time_of_day: e.target.value }))
                  }
                  className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111] dark:text-gray-100"
                />
              )}
              <input
                value={draft.model}
                onChange={(e) => setDraft((prev) => ({ ...prev, model: e.target.value }))}
                className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111] dark:text-gray-100"
                placeholder="模型"
              />
              <button
                type="button"
                onClick={() => void handleCreate()}
                disabled={createDisabled}
                className="flex h-10 items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 text-sm font-medium text-white transition-colors hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
              >
                {savingId === "new" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                创建
              </button>
            </div>

            <textarea
              value={draft.prompt}
              onChange={(e) => setDraft((prev) => ({ ...prev, prompt: e.target.value }))}
              rows={4}
              placeholder="到点后要交给 Agent 执行的任务内容"
              className="mt-3 min-h-[112px] w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm leading-relaxed text-gray-900 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111] dark:text-gray-100"
            />
          </section>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
              {error}
            </div>
          )}

          {loading && tasks.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-gray-400">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : sortedTasks.length === 0 ? (
            <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-gray-200 text-sm text-gray-400 dark:border-white/10">
              还没有定时任务。
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {sortedTasks.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  saving={savingId === task.id}
                  onToggle={toggleTask}
                  onDelete={removeTask}
                />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function TaskRow({
  task,
  saving,
  onToggle,
  onDelete,
}: {
  task: ScheduledTaskInfo;
  saving: boolean;
  onToggle: (task: ScheduledTaskInfo) => Promise<void>;
  onDelete: (task: ScheduledTaskInfo) => Promise<void>;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-[#111]">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-sm font-semibold text-gray-950 dark:text-gray-50">
              {task.title}
            </h2>
            <span className="rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-white/10 dark:text-gray-300">
              {TYPE_LABELS[task.schedule_type]}
            </span>
            <span
              className={cn(
                "rounded-md px-2 py-0.5 text-xs",
                task.status === "failed"
                  ? "bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-300"
                  : task.status === "running"
                    ? "bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-300"
                    : "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300"
              )}
            >
              {STATUS_LABELS[task.status] ?? task.status}
            </span>
          </div>
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-gray-600 dark:text-gray-300">
            {task.prompt}
          </p>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              下次：{formatDateTime(task.next_run_at)}
            </span>
            <span>上次：{formatDateTime(task.last_run_at)}</span>
            {task.schedule_type === "interval" && <span>间隔：{task.interval_minutes} 分钟</span>}
            {task.schedule_type === "daily" && <span>每天：{task.time_of_day}</span>}
            {task.last_session_id && (
              <Link
                href={`/app/${task.last_session_id}`}
                className="text-blue-500 hover:text-blue-600 dark:text-blue-300"
              >
                查看最近会话
              </Link>
            )}
          </div>
          {task.last_error && (
            <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 dark:bg-red-500/10 dark:text-red-300">
              {task.last_error}
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            onClick={() => void onToggle(task)}
            disabled={saving || task.status === "completed" || task.status === "running"}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-35 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-gray-100"
            title={task.status === "enabled" ? "暂停" : "启用"}
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : task.status === "enabled" ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </button>
          <button
            type="button"
            onClick={() => void onDelete(task)}
            disabled={saving || task.status === "running"}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-35 dark:hover:bg-red-500/10 dark:hover:text-red-300"
            title="删除"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
