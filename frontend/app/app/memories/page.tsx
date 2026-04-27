"use client";

import { useEffect, useMemo, useState } from "react";
import { Brain, Loader2, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import {
  createMemory,
  deleteMemory,
  fetchMemories,
  updateMemory,
} from "@/lib/api";
import type { MemoryInfo, MemoryKind } from "@/lib/types";
import { cn } from "@/lib/utils";

const KIND_LABELS: Record<MemoryKind, string> = {
  preference: "偏好",
  profile: "资料",
  project: "项目",
  instruction: "指令",
  fact: "事实",
};

const KIND_OPTIONS = Object.keys(KIND_LABELS) as MemoryKind[];

function formatDate(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`;
}

export default function MemoriesPage() {
  const [memories, setMemories] = useState<MemoryInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState({ content: "", kind: "fact" as MemoryKind });

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setMemories(await fetchMemories());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载记忆失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const grouped = useMemo(() => {
    return KIND_OPTIONS.map((kind) => ({
      kind,
      items: memories.filter((memory) => memory.kind === kind),
    })).filter((group) => group.items.length > 0);
  }, [memories]);

  const handleCreate = async () => {
    const content = draft.content.trim();
    if (!content) return;
    setSavingId("new");
    setError(null);
    try {
      const memory = await createMemory({
        content,
        kind: draft.kind,
        importance: 0.6,
        confidence: 0.95,
      });
      setMemories((prev) => [memory, ...prev]);
      setDraft({ content: "", kind: "fact" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "新增记忆失败");
    } finally {
      setSavingId(null);
    }
  };

  const handleUpdate = async (memory: MemoryInfo, content: string, kind: MemoryKind) => {
    const nextContent = content.trim();
    if (!nextContent) return;
    setSavingId(memory.id);
    setError(null);
    try {
      const updated = await updateMemory(memory.id, {
        content: nextContent,
        kind,
      });
      setMemories((prev) => prev.map((item) => (item.id === memory.id ? updated : item)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存记忆失败");
    } finally {
      setSavingId(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除这条长期记忆吗？")) return;
    setSavingId(id);
    setError(null);
    try {
      await deleteMemory(id);
      setMemories((prev) => prev.filter((memory) => memory.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除记忆失败");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-white dark:bg-[#191919]">
      <header className="flex h-[64px] shrink-0 items-center justify-between border-b border-gray-200 px-6 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gray-100 text-gray-800 dark:bg-white/10 dark:text-gray-100">
            <Brain className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-gray-950 dark:text-gray-50">
              长期记忆
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              每个账户独立保存，聊天时只注入相关内容。
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
        <div className="mx-auto flex max-w-4xl flex-col gap-5">
          <section className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200">
              <Plus className="h-4 w-4" />
              手动添加记忆
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <select
                value={draft.kind}
                onChange={(e) => setDraft((prev) => ({ ...prev, kind: e.target.value as MemoryKind }))}
                className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-800 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111] dark:text-gray-100"
              >
                {KIND_OPTIONS.map((kind) => (
                  <option key={kind} value={kind}>
                    {KIND_LABELS[kind]}
                  </option>
                ))}
              </select>
              <input
                value={draft.content}
                onChange={(e) => setDraft((prev) => ({ ...prev, content: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleCreate();
                }}
                placeholder="例如：我希望技术回答先给结论，再给实现步骤"
                className="h-10 min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#111] dark:text-gray-100"
              />
              <button
                type="button"
                onClick={() => void handleCreate()}
                disabled={!draft.content.trim() || savingId === "new"}
                className="flex h-10 items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 text-sm font-medium text-white transition-colors hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
              >
                {savingId === "new" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                添加
              </button>
            </div>
          </section>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
              {error}
            </div>
          )}

          {loading && memories.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-gray-400">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : grouped.length === 0 ? (
            <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-gray-200 text-sm text-gray-400 dark:border-white/10">
              还没有长期记忆。
            </div>
          ) : (
            grouped.map((group) => (
              <section key={group.kind} className="flex flex-col gap-2">
                <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {KIND_LABELS[group.kind]}
                </h2>
                <div className="flex flex-col gap-2">
                  {group.items.map((memory) => (
                    <MemoryRow
                      key={memory.id}
                      memory={memory}
                      saving={savingId === memory.id}
                      onSave={handleUpdate}
                      onDelete={handleDelete}
                    />
                  ))}
                </div>
              </section>
            ))
          )}
        </div>
      </main>
    </div>
  );
}

function MemoryRow({
  memory,
  saving,
  onSave,
  onDelete,
}: {
  memory: MemoryInfo;
  saving: boolean;
  onSave: (memory: MemoryInfo, content: string, kind: MemoryKind) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [content, setContent] = useState(memory.content);
  const [kind, setKind] = useState<MemoryKind>(memory.kind);
  const dirty = content !== memory.content || kind !== memory.kind;

  useEffect(() => {
    setContent(memory.content);
    setKind(memory.kind);
  }, [memory.content, memory.kind]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm dark:border-white/10 dark:bg-[#111]">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as MemoryKind)}
          className="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm text-gray-800 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#191919] dark:text-gray-100"
        >
          {KIND_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {KIND_LABELS[option]}
            </option>
          ))}
        </select>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={2}
          className="min-h-[72px] min-w-0 flex-1 resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm leading-relaxed text-gray-900 outline-none focus:border-gray-400 dark:border-white/10 dark:bg-[#191919] dark:text-gray-100"
        />
        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            onClick={() => void onSave(memory, content, kind)}
            disabled={!dirty || saving}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-35 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-gray-100"
            title="保存"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          </button>
          <button
            type="button"
            onClick={() => void onDelete(memory.id)}
            disabled={saving}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-35 dark:hover:bg-red-500/10 dark:hover:text-red-300"
            title="删除"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 px-1 text-xs text-gray-400">
        <span>重要度 {Math.round((memory.importance ?? 0) * 100)}%</span>
        <span>置信度 {Math.round((memory.confidence ?? 0) * 100)}%</span>
        <span>更新于 {formatDate(memory.updated_at)}</span>
      </div>
    </div>
  );
}
