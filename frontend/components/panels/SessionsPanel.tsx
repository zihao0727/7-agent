"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import {
  Plus,
  Search,
  ChevronDown,
  RefreshCw,
  Loader2,
  Trash2,
  MessageCircle,
} from "lucide-react";
import {
  fetchSessions,
  createSession,
  deleteSession,
  type SessionInfo,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface SessionsPanelProps {
  onSelectSession: (sessionId: string | undefined) => void;
  currentSessionId?: string;
}

function formatSessionTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffM = Math.floor(diffMs / 60000);
  const diffH = Math.floor(diffMs / 3600000);
  const diffD = Math.floor(diffMs / 86400000);

  if (diffM < 1) return "刚刚";
  if (diffM < 60) return `${diffM} 分钟前`;
  if (diffH < 24) return `${diffH} 小时前`;
  if (diffD === 1) return "昨天";
  if (diffD < 7) return `${diffD} 天前`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function SessionsPanel({
  onSelectSession,
  currentSessionId,
}: SessionsPanelProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSessions = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent === true;
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await fetchSessions();
      setSessions(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    const onRefresh = () => {
      void loadSessions({ silent: true });
    };
    window.addEventListener("sevn:sessions-refresh", onRefresh);
    return () => window.removeEventListener("sevn:sessions-refresh", onRefresh);
  }, [loadSessions]);

  const handleCreateSession = async () => {
    try {
      const result = await createSession("新建会话");
      await loadSessions();
      onSelectSession(result.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    }
  };

  const handleDeleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定删除此会话吗？")) return;
    try {
      await deleteSession(id);
      await loadSessions();
      if (id === currentSessionId) {
        onSelectSession(undefined);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const sortedSessions = useMemo(() => {
    return [...sessions].sort(
      (a, b) =>
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
  }, [sessions]);

  return (
    <div className="flex h-full flex-col gap-1">
      {/* 模块标题 */}
      <div className="text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1 px-2">聊天</div>

      {/* 新建聊天 */}
      <button
        type="button"
        onClick={handleCreateSession}
        disabled={loading}
        className={cn(
          "group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-all",
          "text-gray-700 dark:text-gray-300",
          "hover:bg-gray-200/50 dark:hover:bg-white/5",
          "disabled:pointer-events-none disabled:opacity-50"
        )}
      >
        <Plus className="h-4 w-4" />
        <span className="text-[13px] font-medium">新聊天</span>
      </button>

      {/* 搜索聊天 (仅样式占位) */}
      <button
        type="button"
        className={cn(
          "group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-all mb-2",
          "text-gray-700 dark:text-gray-300",
          "hover:bg-gray-200/50 dark:hover:bg-white/5",
        )}
      >
        <Search className="h-4 w-4" />
        <span className="text-[13px] font-medium">搜索聊天</span>
      </button>

      {/* 最近对话区块标题 */}
      <div className="flex items-center justify-between px-2 py-1.5 group cursor-pointer text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors">
        <div className="flex items-center gap-1.5">
          <ChevronDown className="h-3.5 w-3.5" />
          <span className="text-[12px] font-medium">最近</span>
        </div>
        <div className="flex items-center gap-2">
          {loading && <Loader2 className="h-3 w-3 animate-spin" />}
          <span className="text-[10px] font-medium bg-gray-200/50 dark:bg-white/10 px-1.5 py-0.5 rounded text-gray-500 dark:text-gray-400">
            {sessions.length}
          </span>
        </div>
      </div>

      {error && (
        <p className="rounded-lg bg-red-50 px-2.5 py-1.5 text-[11px] text-red-600 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      {loading && sessions.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 py-8">
          <Loader2 className="h-6 w-6 animate-spin text-gray-300 dark:text-gray-600" />
        </div>
      ) : (
        <ul className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto pr-0.5 [-ms-overflow-style:none] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300/80 dark:[&::-webkit-scrollbar-thumb]:bg-gray-600">
          {sortedSessions.map((session) => {
            const active = currentSessionId === session.id;

            return (
              <li key={session.id} className="group/row relative">
                <button
                  type="button"
                  onClick={() => onSelectSession(session.id)}
                  className={cn(
                    "flex w-full items-center rounded-lg px-3 py-2.5 pr-8 text-left transition-all",
                    active
                      ? "bg-gray-200/80 dark:bg-white/10"
                      : "hover:bg-gray-200/50 dark:hover:bg-white/5"
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        "block truncate text-[13px] leading-snug",
                        active
                          ? "font-medium text-gray-900 dark:text-gray-100"
                          : "text-gray-700 dark:text-gray-300"
                      )}
                    >
                      {session.title || "新对话"}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={(e) => handleDeleteSession(session.id, e)}
                  className={cn(
                    "absolute right-2 top-1/2 -translate-y-1/2 rounded p-1",
                    "text-gray-400 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-500",
                    "group-hover/row:opacity-100",
                    "dark:text-gray-500 dark:hover:text-red-400"
                  )}
                  title="删除会话"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
