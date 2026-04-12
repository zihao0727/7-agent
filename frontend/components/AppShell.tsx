"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { sessionIdFromAppPath } from "@/lib/app-path";
import { Sidebar } from "./Sidebar";
import { SessionsPanel } from "./panels/SessionsPanel";
import { BrowserPanel } from "./BrowserPanel";
import { useTheme } from "next-themes";
import {
  MonitorIcon,
  ChevronLeft,
  Clock,
  Zap,
  Wrench,
  Server,
  Sun,
  Moon,
} from "lucide-react";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const currentSessionId = sessionIdFromAppPath(pathname);
  const { theme, setTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeConfigTab, setActiveConfigTab] = useState<"tools" | "skills" | "mcp">("tools");

  const openConfig = (tab: "tools" | "skills" | "mcp") => {
    setActiveConfigTab(tab);
    setSidebarOpen(true);
  };

  /**
   * 为每个会话单独记录浏览器面板状态。
   * Map<sessionId, isOpen>
   */
  const [sessionBrowserStates, setSessionBrowserStates] = useState<
    Map<string, boolean>
  >(new Map());

  const prevSessionIdRef = useRef<string | undefined>(undefined);

  const handleSelectSession = (id: string | undefined) => {
    if (id) router.push(`/app/${id}`);
    else router.push("/app");
  };

  // 获取当前会话的浏览器面板状态
  const currentBrowserPanelOpen =
    currentSessionId && sessionBrowserStates.has(currentSessionId)
      ? sessionBrowserStates.get(currentSessionId)!
      : false;

  // 切换当前会话的浏览器面板状态
  const toggleBrowserPanel = () => {
    if (!currentSessionId) return;
    setSessionBrowserStates((prev) => {
      const newMap = new Map(prev);
      const current = newMap.get(currentSessionId) ?? false;
      newMap.set(currentSessionId, !current);
      return newMap;
    });
  };

  // 监听路由变化：进入会话 → 加载该会话的状态；离开到主页 → 清空状态
  useEffect(() => {
    if (!currentSessionId) {
      // 回到主页，不做任何改动（之后切换出去时会保留各自的状态）
      prevSessionIdRef.current = undefined;
      return;
    }
    // 切换到新会话（或第一次进入会话）时，使用该会话保存的状态
    prevSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  // 面板只在会话页渲染，主页完全不挂载
  const showBrowserPanel = !!currentSessionId;

  return (
    <div className="flex h-screen w-full overflow-hidden bg-white dark:bg-[#0f0f0f]">
      {/* 弹出的配置抽屉 (原 Sidebar) */}
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={setSidebarOpen}
        activeTab={activeConfigTab}
        onTabChange={setActiveConfigTab as any}
      />

      {/* 统一的左侧导航与会话面板 */}
      <div
        className="w-[260px] flex-shrink-0 border-r border-gray-200 dark:border-[#222222]
        bg-[#f9f9f9] dark:bg-[#111111] flex flex-col overflow-hidden transition-colors duration-200"
      >
        {/* 顶部 Logo 区 */}
        <div className="px-5 py-3 h-[52px] flex items-center justify-between flex-shrink-0">
          <Link
            href="/app"
            className="flex items-center gap-2 min-w-0 hover:opacity-75 transition-opacity"
          >
            <h3 className="font-inter text-[15px] font-extrabold tracking-tight text-gray-900 dark:text-gray-100 min-w-0 whitespace-nowrap">
              Sevan
            </h3>
          </Link>

          <div className="flex items-center gap-2">
            {/* 浏览器面板切换按钮：仅会话页显示 */}
            {showBrowserPanel && (
              <button
                onClick={toggleBrowserPanel}
                title={currentBrowserPanelOpen ? "收起浏览器面板" : "展开浏览器面板"}
                className={`relative flex h-6 w-6 items-center justify-center rounded-md transition-colors ${
                  currentBrowserPanelOpen
                    ? "bg-gray-300 dark:bg-white/20 text-gray-700 dark:text-gray-200"
                    : "text-gray-400 hover:bg-gray-200 dark:hover:bg-white/10 hover:text-gray-600 dark:hover:text-gray-300"
                }`}
              >
                <MonitorIcon className="h-3.5 w-3.5" />
              </button>
            )}
            <button className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors">
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* 滚动区域：包含会话、控制台、代理、设置 */}
        <div className="flex-1 overflow-y-auto flex flex-col px-3 py-2 gap-6 [-ms-overflow-style:none] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300/80 dark:[&::-webkit-scrollbar-thumb]:bg-gray-600">
          
          {/* 聊天模块 */}
          <div className="flex-shrink-0">
            <SessionsPanel
              onSelectSession={handleSelectSession}
              currentSessionId={currentSessionId}
            />
          </div>

          {/* 控制台模块 */}
          <div className="flex flex-col gap-0.5">
            <div className="text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1 px-2">控制台</div>
            <button className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-all text-gray-700 dark:text-gray-300 hover:bg-gray-200/50 dark:hover:bg-white/5">
              <Clock className="h-4 w-4" />
              <span className="text-[13px] font-medium">定时任务</span>
            </button>
          </div>

          {/* 代理模块 */}
          <div className="flex flex-col gap-0.5">
            <div className="text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1 px-2">代理</div>
            <button onClick={() => openConfig("skills")} className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-all text-gray-700 dark:text-gray-300 hover:bg-gray-200/50 dark:hover:bg-white/5">
              <Zap className="h-4 w-4" />
              <span className="text-[13px] font-medium">技能</span>
            </button>
            <button onClick={() => openConfig("tools")} className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-all text-gray-700 dark:text-gray-300 hover:bg-gray-200/50 dark:hover:bg-white/5">
              <Wrench className="h-4 w-4" />
              <span className="text-[13px] font-medium">工具</span>
            </button>
            <button onClick={() => openConfig("mcp")} className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-all text-gray-700 dark:text-gray-300 hover:bg-gray-200/50 dark:hover:bg-white/5">
              <Server className="h-4 w-4" />
              <span className="text-[13px] font-medium">MCP</span>
            </button>
          </div>

          {/* 设置模块 */}
          <div className="flex flex-col gap-0.5 pb-4">
            <div className="text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1 px-2">设置</div>
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-all text-gray-700 dark:text-gray-300 hover:bg-gray-200/50 dark:hover:bg-white/5"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              <span className="text-[13px] font-medium">
                {theme === "dark" ? "切换亮色" : "切换暗色"}
              </span>
            </button>
          </div>
        </div>
      </div>

      <main className="flex flex-1 flex-col min-w-0 overflow-hidden bg-white dark:bg-[#191919] transition-colors">
        {children}
      </main>

      {/* 右侧浏览器面板：只在会话页挂载 */}
      {showBrowserPanel && (
        <BrowserPanel
          open={currentBrowserPanelOpen}
          onClose={() => toggleBrowserPanel()}
          sessionId={currentSessionId}
        />
      )}
    </div>
  );
}
