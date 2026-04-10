"use client";

import { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, RefreshCw, Loader } from "lucide-react";
import {
  fetchSessions,
  createSession,
  deleteSession,
  type SessionInfo,
} from "@/lib/api";

interface SessionsPanelProps {
  onSelectSession: (sessionId: string | undefined) => void;
  currentSessionId?: string;
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
      // 列表已展示时后台刷新，避免整页闪烁
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
      // 如果删除的是当前激活会话，则清空选中状态
      if (id === currentSessionId) {
        onSelectSession(undefined);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div className="flex flex-col h-full gap-2">
      {/* 标题和操作按钮 */}
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          会话列表
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => void loadSessions()}
            disabled={loading}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 disabled:opacity-50"
            title="刷新"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={handleCreateSession}
            disabled={loading}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 disabled:opacity-50"
            title="新建会话"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* 错误信息 */}
      {error && (
        <p className="text-xs text-red-500 mb-2 px-1">{error}</p>
      )}

      {/* 会话列表 */}
      {loading && sessions.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <RefreshCw className="h-4 w-4 animate-spin text-gray-400" />
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto space-y-1.5 pr-0.5">
          {sessions.map((session) => (
            <li
              key={session.id}
              onClick={() => onSelectSession(session.id)}
              className={`flex items-start justify-between gap-2 rounded-lg px-3 py-2.5 cursor-pointer transition-colors
                ${
                  currentSessionId === session.id
                    ? "bg-white dark:bg-gray-800 border-l-2 border-gray-900 dark:border-gray-100 shadow-sm"
                    : "hover:bg-gray-200/60 dark:hover:bg-gray-800/50"
                }`}
            >
              <div className="min-w-0 flex-1 flex items-center">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                  {session.title}
                </p>
              </div>
              <button
                onClick={(e) => handleDeleteSession(session.id, e)}
                className="flex-shrink-0 p-1 rounded hover:bg-red-50 dark:hover:bg-red-900
                  text-gray-300 hover:text-red-500 transition-colors"
                title="删除"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
          {sessions.length === 0 && !loading && (
            <li className="text-xs text-gray-400 text-center py-4">
              暂无会话，点击 + 创建
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
