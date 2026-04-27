"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  Brain,
  Bot,
  ChevronRight,
  ChevronsLeft,
  Clock,
  Code2Icon,
  LogOut,
  MonitorIcon,
  Moon,
  Server,
  Sun,
  UserCircle2,
  Wrench,
  Zap,
} from "lucide-react";
import brandLogo from "@/logo.png";
import { sessionIdFromAppPath } from "@/lib/app-path";
import { Sidebar, type ConfigTabId } from "./Sidebar";
import { SessionsPanel } from "./panels/SessionsPanel";
import { BrowserPanel } from "./BrowserPanel";
import { CodePanel } from "./CodePanel";
import { useAuth } from "./AuthProvider";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const currentSessionId = sessionIdFromAppPath(pathname);
  const { theme, setTheme } = useTheme();
  const { user, signOut } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeConfigTab, setActiveConfigTab] = useState<ConfigTabId>("tools");
  const [leftNavCollapsed, setLeftNavCollapsed] = useState(false);
  const [sessionBrowserStates, setSessionBrowserStates] = useState<Map<string, boolean>>(
    new Map()
  );
  const [sessionCodeStates, setSessionCodeStates] = useState<Map<string, boolean>>(
    new Map()
  );
  const prevSessionIdRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    try {
      if (localStorage.getItem("sevn:left-nav-collapsed") === "1") {
        setLeftNavCollapsed(true);
      }
    } catch {
      // ignore
    }
  }, []);

  const setLeftNavCollapsedPersist = (value: boolean) => {
    setLeftNavCollapsed(value);
    try {
      localStorage.setItem("sevn:left-nav-collapsed", value ? "1" : "0");
    } catch {
      // ignore
    }
  };

  const openConfig = (tab: ConfigTabId) => {
    setActiveConfigTab(tab);
    setSidebarOpen(true);
  };

  const handleSelectSession = (id: string | undefined) => {
    if (id) router.push(`/app/${id}`);
    else router.push("/app");
  };

  const currentBrowserPanelOpen =
    currentSessionId && sessionBrowserStates.has(currentSessionId)
      ? sessionBrowserStates.get(currentSessionId) ?? false
      : false;

  const toggleBrowserPanel = () => {
    if (!currentSessionId) return;
    setSessionBrowserStates((prev) => {
      const next = new Map(prev);
      const current = next.get(currentSessionId) ?? false;
      next.set(currentSessionId, !current);
      return next;
    });
  };

  const currentCodePanelOpen =
    currentSessionId && sessionCodeStates.has(currentSessionId)
      ? sessionCodeStates.get(currentSessionId) ?? false
      : false;

  const toggleCodePanel = () => {
    if (!currentSessionId) return;
    setSessionCodeStates((prev) => {
      const next = new Map(prev);
      const current = next.get(currentSessionId) ?? false;
      next.set(currentSessionId, !current);
      return next;
    });
  };

  useEffect(() => {
    if (!currentSessionId) {
      prevSessionIdRef.current = undefined;
      return;
    }
    prevSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  const showBrowserPanel = !!currentSessionId;
  const showCodePanel = !!currentSessionId;

  const displayName = user?.display_name?.trim() || user?.email || "账户";

  const handleLogout = async () => {
    await signOut();
    router.replace("/login");
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-white dark:bg-[#0f0f0f]">
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={setSidebarOpen}
        activeTab={activeConfigTab}
        onTabChange={setActiveConfigTab as any}
      />

      {leftNavCollapsed ? (
        <aside
          className="flex h-full w-[52px] flex-shrink-0 flex-col items-center gap-2 border-r border-gray-200 bg-[#f9f9f9] py-2 transition-[width] duration-200 dark:border-[#222222] dark:bg-[#111111]"
          aria-label="已收起的侧边栏"
        >
          <button
            type="button"
            onClick={() => setLeftNavCollapsedPersist(false)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-200 dark:text-gray-400 dark:hover:bg-white/10"
            title="展开侧边栏"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <Link
            href="/app"
            className="flex h-9 w-9 items-center justify-center rounded-lg hover:bg-gray-200 dark:hover:bg-white/10"
            title="首页"
            aria-label="首页"
          >
            <Image
              src={brandLogo}
              alt=""
              width={28}
              height={28}
              className="h-7 w-7 object-contain"
              priority
            />
          </Link>
          <Link
            href="/app/memories"
            className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
              pathname === "/app/memories"
                ? "bg-gray-300 text-gray-800 dark:bg-white/20 dark:text-gray-200"
                : "text-gray-400 hover:bg-gray-200 dark:hover:bg-white/10"
            }`}
            title="长期记忆"
            aria-label="长期记忆"
          >
            <Brain className="h-4 w-4" />
          </Link>
          {showCodePanel && (
            <button
              type="button"
              onClick={toggleCodePanel}
              title={currentCodePanelOpen ? "收起代码运行器" : "展开代码运行器"}
              className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
                currentCodePanelOpen
                  ? "bg-blue-100 text-blue-600 dark:bg-blue-500/25 dark:text-blue-300"
                  : "text-gray-400 hover:bg-gray-200 dark:hover:bg-white/10"
              }`}
            >
              <Code2Icon className="h-4 w-4" />
            </button>
          )}
          {showBrowserPanel && (
            <button
              type="button"
              onClick={toggleBrowserPanel}
              title={currentBrowserPanelOpen ? "收起浏览器面板" : "展开浏览器面板"}
              className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
                currentBrowserPanelOpen
                  ? "bg-gray-300 text-gray-800 dark:bg-white/20 dark:text-gray-200"
                  : "text-gray-400 hover:bg-gray-200 dark:hover:bg-white/10"
              }`}
            >
              <MonitorIcon className="h-4 w-4" />
            </button>
          )}
        </aside>
      ) : (
        <div className="flex w-[280px] flex-shrink-0 flex-col overflow-hidden border-r border-gray-200 bg-[#f9f9f9] transition-[width] duration-200 dark:border-[#222222] dark:bg-[#111111]">
          <div className="flex h-[52px] flex-shrink-0 items-center justify-between gap-2 px-5 py-3">
            <Link
              href="/app"
              className="flex min-w-0 items-center gap-2.5 transition-opacity hover:opacity-80"
              aria-label="首页"
            >
              <Image
                src={brandLogo}
                alt=""
                width={32}
                height={32}
                className="h-8 w-8 shrink-0 object-contain"
                priority
              />
              <h3 className="font-display truncate text-2xl font-extrabold tracking-tight text-gray-900 dark:text-gray-100">
                SevnX
              </h3>
            </Link>

            <div className="flex shrink-0 items-center gap-1.5">
              {showCodePanel && (
                <button
                  type="button"
                  onClick={toggleCodePanel}
                  title={currentCodePanelOpen ? "收起代码运行器" : "展开代码运行器"}
                  className={`relative flex h-6 w-6 items-center justify-center rounded-md transition-colors ${
                    currentCodePanelOpen
                      ? "bg-blue-100 text-blue-600 dark:bg-blue-500/25 dark:text-blue-300"
                      : "text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-white/10 dark:hover:text-gray-300"
                  }`}
                >
                  <Code2Icon className="h-3.5 w-3.5" />
                </button>
              )}
              {showBrowserPanel && (
                <button
                  type="button"
                  onClick={toggleBrowserPanel}
                  title={currentBrowserPanelOpen ? "收起浏览器面板" : "展开浏览器面板"}
                  className={`relative flex h-6 w-6 items-center justify-center rounded-md transition-colors ${
                    currentBrowserPanelOpen
                      ? "bg-gray-300 text-gray-700 dark:bg-white/20 dark:text-gray-200"
                      : "text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-white/10 dark:hover:text-gray-300"
                  }`}
                >
                  <MonitorIcon className="h-3.5 w-3.5" />
                </button>
              )}
              <button
                type="button"
                onClick={() => setLeftNavCollapsedPersist(true)}
                className="text-gray-400 transition-colors hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
                title="收起侧边栏"
                aria-label="收起侧边栏"
              >
                <ChevronsLeft className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-3 py-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <div className="flex-shrink-0">
              <SessionsPanel
                onSelectSession={handleSelectSession}
                currentSessionId={currentSessionId}
              />
            </div>

            <div className="flex flex-col gap-0.5">
              <div className="mb-1 px-2 text-xs font-medium text-gray-500 dark:text-gray-400">
                控制台
              </div>
              <button
                type="button"
                onClick={showCodePanel ? toggleCodePanel : undefined}
                className={`group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-all hover:bg-gray-200/50 dark:hover:bg-white/5 ${
                  currentCodePanelOpen
                    ? "bg-blue-50/50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400"
                    : "text-gray-700 dark:text-gray-300"
                }`}
              >
                <Code2Icon className="h-4 w-4" />
                <span className="text-sm font-medium">代码运行器</span>
                {currentCodePanelOpen && (
                  <span className="ml-auto h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
                )}
              </button>
              <button
                type="button"
                className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-gray-700 transition-all hover:bg-gray-200/50 dark:text-gray-300 dark:hover:bg-white/5"
              >
                <Clock className="h-4 w-4" />
                <span className="text-sm font-medium">定时任务</span>
              </button>
            </div>

            <div className="flex flex-col gap-0.5">
              <div className="mb-1 px-2 text-xs font-medium text-gray-500 dark:text-gray-400">
                代理
              </div>
              <button
                type="button"
                onClick={() => openConfig("skills")}
                className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-gray-700 transition-all hover:bg-gray-200/50 dark:text-gray-300 dark:hover:bg-white/5"
              >
                <Zap className="h-4 w-4" />
                <span className="text-sm font-medium">技能</span>
              </button>
              <button
                type="button"
                onClick={() => openConfig("tools")}
                className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-gray-700 transition-all hover:bg-gray-200/50 dark:text-gray-300 dark:hover:bg-white/5"
              >
                <Wrench className="h-4 w-4" />
                <span className="text-sm font-medium">工具</span>
              </button>
              <button
                type="button"
                onClick={() => openConfig("mcp")}
                className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-gray-700 transition-all hover:bg-gray-200/50 dark:text-gray-300 dark:hover:bg-white/5"
              >
                <Server className="h-4 w-4" />
                <span className="text-sm font-medium">MCP</span>
              </button>
              <button
                type="button"
                onClick={() => openConfig("lark")}
                className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-gray-700 transition-all hover:bg-gray-200/50 dark:text-gray-300 dark:hover:bg-white/5"
              >
                <Bot className="h-4 w-4" />
                <span className="text-sm font-medium">飞书</span>
              </button>
            </div>

            <div className="flex flex-col gap-0.5">
              <div className="mb-1 px-2 text-xs font-medium text-gray-500 dark:text-gray-400">
                设置
              </div>
              <Link
                href="/app/memories"
                className={`group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-all hover:bg-gray-200/50 dark:hover:bg-white/5 ${
                  pathname === "/app/memories"
                    ? "bg-gray-200/80 text-gray-900 dark:bg-white/10 dark:text-gray-100"
                    : "text-gray-700 dark:text-gray-300"
                }`}
              >
                <Brain className="h-4 w-4" />
                <span className="text-sm font-medium">长期记忆</span>
              </Link>
              <button
                type="button"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-gray-700 transition-all hover:bg-gray-200/50 dark:text-gray-300 dark:hover:bg-white/5"
              >
                {theme === "dark" ? (
                  <Sun className="h-4 w-4" />
                ) : (
                  <Moon className="h-4 w-4" />
                )}
                <span className="text-sm font-medium">
                  {theme === "dark" ? "切换亮色" : "切换暗色"}
                </span>
              </button>
            </div>

            <div className="mt-auto border-t border-gray-200/70 px-2 pt-4 dark:border-white/10">
              <div className="rounded-2xl border border-gray-200/80 bg-white/80 p-3 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/5">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gray-100 text-gray-700 dark:bg-white/10 dark:text-gray-200">
                    <UserCircle2 className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {displayName}
                    </div>
                    <div className="truncate text-xs text-gray-500 dark:text-gray-400">
                      {user?.email}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => void handleLogout()}
                  className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-white/10 dark:bg-white/5 dark:text-gray-200 dark:hover:bg-white/10"
                >
                  <LogOut className="h-4 w-4" />
                  退出登录
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-white transition-colors dark:bg-[#191919]">
        {children}
      </main>

      {showCodePanel && (
        <CodePanel
          open={currentCodePanelOpen}
          onClose={toggleCodePanel}
          sessionId={currentSessionId}
        />
      )}

      {showBrowserPanel && (
        <BrowserPanel
          open={currentBrowserPanelOpen}
          onClose={toggleBrowserPanel}
          sessionId={currentSessionId}
        />
      )}
    </div>
  );
}
