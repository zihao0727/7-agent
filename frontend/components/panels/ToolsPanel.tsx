"use client";

import { useEffect, useState, useCallback } from "react";
import { Wrench, RefreshCw } from "lucide-react";
import { fetchTools, toggleTool } from "@/lib/api";
import type { ToolInfo } from "@/lib/types";

export function ToolsPanel() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTools(await fetchTools());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggle = async (name: string, current: boolean) => {
    setToggling(name);
    try {
      await toggleTool(name, !current);
      setTools((prev) =>
        prev.map((t) => t.name === name ? { ...t, enabled: !current } : t)
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setToggling(null);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5 text-xs font-medium text-gray-500 uppercase tracking-wide">
          <Wrench className="h-3.5 w-3.5" />
          工具
          <span className="ml-1 rounded-full bg-gray-200/90 dark:bg-gray-700 px-1.5 py-0.5 text-xs">
            {tools.filter((t) => t.enabled).length}/{tools.length}
          </span>
        </div>
        <button
          onClick={load}
          className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600"
          title="刷新"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-500 mb-2 px-1">{error}</p>
      )}

      {loading && tools.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <RefreshCw className="h-4 w-4 animate-spin text-gray-400" />
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto space-y-1 pr-0.5">
          {tools.map((tool) => (
            <li
              key={tool.name}
              className="flex items-start gap-2 rounded-lg p-2 hover:bg-gray-200/50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <button
                onClick={() => handleToggle(tool.name, tool.enabled)}
                disabled={toggling === tool.name}
                className={`mt-0.5 flex-shrink-0 w-8 h-4 rounded-full transition-colors relative
                  ${tool.enabled ? "bg-gray-900 dark:bg-gray-100" : "bg-gray-200 dark:bg-gray-600"}
                  ${toggling === tool.name ? "opacity-50 cursor-wait" : "cursor-pointer"}`}
                title={tool.enabled ? "点击禁用" : "点击启用"}
              >
                <span
                  className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform
                    ${tool.enabled ? "left-4" : "left-0.5"}`}
                />
              </button>
              <div className="min-w-0 flex-1">
                <p className={`text-xs font-mono font-medium truncate
                  ${tool.enabled ? "text-gray-900 dark:text-gray-100" : "text-gray-400 dark:text-gray-500"}`}>
                  {tool.name}
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 leading-relaxed line-clamp-2">
                  {tool.description}
                </p>
              </div>
            </li>
          ))}
          {tools.length === 0 && !loading && (
            <li className="text-xs text-gray-400 text-center py-4">暂无工具</li>
          )}
        </ul>
      )}
    </div>
  );
}
