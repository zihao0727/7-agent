"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { sessionIdFromAppPath } from "@/lib/app-path";
import { Sidebar } from "./Sidebar";
import { SessionsPanel } from "./panels/SessionsPanel";
import { BrowserPanel } from "./BrowserPanel";
import { ChevronRight, MonitorIcon } from "lucide-react";
import logoPng from "@/logo.png";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const currentSessionId = sessionIdFromAppPath(pathname);
  const [sidebarOpen, setSidebarOpen] = useState(false);

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
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar isOpen={sidebarOpen} onToggle={setSidebarOpen} />

      {!sidebarOpen && (
        <button
          onClick={() => setSidebarOpen(true)}
          className="flex-shrink-0 w-8 flex items-center justify-center border-r border-gray-200 dark:border-gray-700
            bg-gray-100 dark:bg-gray-900 hover:bg-gray-200 dark:hover:bg-gray-800 transition-colors"
          title="显示配置面板"
        >
          <ChevronRight className="h-4 w-4 text-gray-400" />
        </button>
      )}

      {/* 会话列表面板 */}
      <div className="w-56 flex-shrink-0 border-r border-gray-200 dark:border-gray-700
        bg-gray-100 dark:bg-gray-900 flex flex-col overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-200 dark:border-gray-700 h-[52px] flex items-center gap-2">
          <Link
            href="/app"
            className="flex items-center gap-2 min-w-0 hover:opacity-75 transition-opacity flex-1"
          >
            <Image
              src={logoPng}
              alt=""
              width={40}
              height={40}
              className="h-10 w-10 shrink-0 object-contain"
              priority
            />
            <h3 className="font-inter text-base font-extrabold tracking-tight text-gray-900 dark:text-gray-50 min-w-0 whitespace-nowrap">
              Sevn Agent
            </h3>
          </Link>

          {/* 浏览器面板切换按钮：仅会话页显示 */}
          {showBrowserPanel && (
            <button
              onClick={toggleBrowserPanel}
              title={
                currentBrowserPanelOpen ? "收起浏览器面板" : "展开浏览器面板"
              }
              className={`relative flex-shrink-0 flex h-7 w-7 items-center justify-center rounded-md
                transition-colors
                ${
                  currentBrowserPanelOpen
                    ? "bg-gray-300 dark:bg-gray-700 text-gray-700 dark:text-gray-200"
                    : "text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300"
                }`}
            >
              <MonitorIcon className="h-4 w-4" />
            </button>
          )}
        </div>
        <div className="flex-1 overflow-hidden p-3">
          <SessionsPanel
            onSelectSession={handleSelectSession}
            currentSessionId={currentSessionId}
          />
        </div>
      </div>

      <main className="flex flex-1 flex-col min-w-0 overflow-hidden">
        {children}
      </main>

      {/* 右侧浏览器面板：只在会话页挂载 */}
      {showBrowserPanel && (
        <BrowserPanel
          open={currentBrowserPanelOpen}
          onClose={() => toggleBrowserPanel()}
        />
      )}
    </div>
  );
}
