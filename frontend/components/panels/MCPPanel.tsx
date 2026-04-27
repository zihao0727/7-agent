"use client";

import { useEffect, useState, useCallback } from "react";
import { Server, Plus, Trash2, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { fetchMCPServers, addMCPServer, removeMCPServer } from "@/lib/api";
import type { MCPServerInfo, MCPTransport } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  connected: "bg-green-500",
  error: "bg-red-500",
  loading: "bg-yellow-500",
};

export function MCPPanel() {
  const [servers, setServers] = useState<MCPServerInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  // 表单状态
  const [form, setForm] = useState({
    name: "",
    transport: "stdio" as MCPTransport,
    command: "",
    args: "",
    url: "",
  });
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setServers(await fetchMCPServers());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    if (!form.name.trim()) { setError("请填写名称"); return; }
    if (form.transport === "stdio" && !form.command.trim()) { setError("stdio 模式请填写命令"); return; }
    if (form.transport === "sse" && !form.url.trim()) { setError("sse 模式请填写 URL"); return; }

    setAdding(true);
    setError(null);
    try {
      await addMCPServer({
        name: form.name.trim(),
        transport: form.transport,
        command: form.command.trim(),
        args: form.args.trim() ? form.args.trim().split(/\s+/) : [],
        url: form.url.trim(),
      });
      setForm({ name: "", transport: "stdio", command: "", args: "", url: "" });
      setShowForm(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "添加失败");
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (id: string) => {
    setRemoving(id);
    setError(null);
    try {
      await removeMCPServer(id);
      setServers((prev) => prev.filter((s) => s.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setRemoving(null);
    }
  };

  return (
    <div className="flex flex-col h-full gap-3">
      {/* 标题栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-sm font-medium text-gray-500 uppercase tracking-wide">
          <Server className="h-3.5 w-3.5" />
          MCP 服务器
          <span className="ml-1 rounded-full bg-gray-200/90 dark:bg-gray-700 px-1.5 py-0.5 text-sm">
            {servers.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={load}
            className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600"
            title="刷新"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600"
            title="添加服务器"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* 添加表单 */}
      {showForm && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-200/35 dark:bg-gray-800 p-3 space-y-2">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">添加 MCP 服务器</p>

          <input
            type="text"
            placeholder="名称"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 dark:border-gray-600
              bg-white dark:bg-gray-800 focus:outline-none focus:ring-1 focus:ring-gray-500 dark:focus:ring-gray-400"
          />

          <div className="flex gap-1">
            {(["stdio", "sse"] as MCPTransport[]).map((t) => (
              <button
                key={t}
                onClick={() => setForm((f) => ({ ...f, transport: t }))}
                className={`flex-1 text-sm py-1 rounded border transition-colors
                  ${form.transport === t
                    ? "bg-black dark:bg-white text-white dark:text-black border-black dark:border-white"
                    : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-600"
                  }`}
              >
                {t}
              </button>
            ))}
          </div>

          {form.transport === "stdio" ? (
            <>
              <input
                type="text"
                placeholder="命令（如 python）"
                value={form.command}
                onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 dark:border-gray-600
                  bg-white dark:bg-gray-800 focus:outline-none focus:ring-1 focus:ring-gray-500 dark:focus:ring-gray-400"
              />
              <input
                type="text"
                placeholder="参数（空格分隔，如 server.py --port 8080）"
                value={form.args}
                onChange={(e) => setForm((f) => ({ ...f, args: e.target.value }))}
                className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 dark:border-gray-600
                  bg-white dark:bg-gray-800 focus:outline-none focus:ring-1 focus:ring-gray-500 dark:focus:ring-gray-400"
              />
            </>
          ) : (
            <input
              type="url"
              placeholder="SSE URL（如 http://localhost:8080/sse）"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 dark:border-gray-600
                bg-white dark:bg-gray-800 focus:outline-none focus:ring-1 focus:ring-gray-500 dark:focus:ring-gray-400"
            />
          )}

          {error && <p className="text-sm text-red-500">{error}</p>}

          <div className="flex gap-1.5 pt-0.5">
            <button
              onClick={handleAdd}
              disabled={adding}
              className="flex-1 text-sm py-1.5 rounded bg-black hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-200
                disabled:opacity-50 text-white dark:text-black font-medium"
            >
              {adding ? "连接中..." : "连接"}
            </button>
            <button
              onClick={() => { setShowForm(false); setError(null); }}
              className="flex-1 text-sm py-1.5 rounded border border-gray-200 dark:border-gray-600
                hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {!showForm && error && <p className="text-sm text-red-500 px-1">{error}</p>}

      {/* 服务器列表 */}
      {loading && servers.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <RefreshCw className="h-4 w-4 animate-spin text-gray-400" />
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto space-y-2 pr-0.5">
          {servers.map((srv) => (
            <li
              key={srv.id}
              className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden bg-gray-200/30 dark:bg-gray-800/50"
            >
              <div
                className="flex items-center gap-2 px-2.5 py-2 cursor-pointer
                  hover:bg-gray-200/40 dark:hover:bg-gray-800/80 transition-colors"
                onClick={() => setExpanded((v) => v === srv.id ? null : srv.id)}
              >
                {/* 状态指示器 */}
                <span
                  className={`flex-shrink-0 w-1.5 h-1.5 rounded-full ${STATUS_COLORS[srv.status] ?? "bg-gray-400"}`}
                />
                <span className="flex-1 text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                  {srv.name}
                </span>
                <span className="text-sm text-gray-400 font-mono">{srv.transport}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); handleRemove(srv.id); }}
                  disabled={removing === srv.id}
                  className="p-0.5 rounded hover:bg-red-50 dark:hover:bg-red-900
                    text-gray-300 hover:text-red-500 transition-colors disabled:opacity-50"
                  title="移除"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
                {expanded === srv.id ? (
                  <ChevronUp className="h-3 w-3 text-gray-400" />
                ) : (
                  <ChevronDown className="h-3 w-3 text-gray-400" />
                )}
              </div>

              {expanded === srv.id && (
                <div className="px-3 pb-2.5 pt-1 border-t border-gray-200 dark:border-gray-700 space-y-1.5">
                  <p className="text-sm text-gray-400">
                    状态：
                    <span className={`font-medium ${
                      srv.status === "connected" ? "text-green-600 dark:text-green-400"
                      : srv.status === "error" ? "text-red-500"
                      : "text-yellow-500"
                    }`}>
                      {srv.status === "connected" ? "已连接" : srv.status === "error" ? "连接失败" : "加载中"}
                    </span>
                  </p>
                  {srv.transport === "stdio" && srv.command && (
                    <p className="text-sm text-gray-400 font-mono truncate">
                      {srv.command} {srv.args.join(" ")}
                    </p>
                  )}
                  {srv.transport === "sse" && srv.url && (
                    <p className="text-sm text-gray-400 font-mono truncate">{srv.url}</p>
                  )}
                  {srv.tool_names.length > 0 && (
                    <div>
                      <p className="text-sm text-gray-400 mb-1">工具 ({srv.tool_names.length})</p>
                      <div className="flex flex-wrap gap-1">
                        {srv.tool_names.map((t) => (
                          <span
                            key={t}
                            className="text-sm bg-gray-200/90 dark:bg-gray-700 text-gray-500 dark:text-gray-400
                              px-1.5 py-0.5 rounded font-mono"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </li>
          ))}
          {servers.length === 0 && !loading && (
            <li className="text-sm text-gray-400 text-center py-6">
              暂无 MCP 服务器，点击 + 添加
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
