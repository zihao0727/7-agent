"use client";

/**
 * BrowserPanel —— 右侧浏览器实时预览面板
 *
 * 功能：
 *  - 每 1.5 秒轮询 /api/browser/state，展示当前 URL、标题、截图
 *  - 截图点击可在新标签页全屏查看
 *  - 显示浏览器活动状态指示灯
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ExternalLinkIcon,
  Loader2Icon,
  MonitorIcon,
  RefreshCwIcon,
  XIcon,
  ZoomInIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:6868";

interface BrowserState {
  url: string;
  title: string;
  screenshot_url: string;
  active: boolean;
}

interface BrowserPanelProps {
  open: boolean;
  onClose: () => void;
}

export function BrowserPanel({ open, onClose }: BrowserPanelProps) {
  const [state, setState] = useState<BrowserState>({
    url: "",
    title: "",
    screenshot_url: "",
    active: false,
  });
  const [refreshing, setRefreshing] = useState(false);
  const [imgLoading, setImgLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevScreenshotRef = useRef<string>("");

  const fetchState = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    try {
      const res = await fetch(`${API_URL}/api/browser/state`, { cache: "no-store" });
      if (res.ok) {
        const data: BrowserState = await res.json();
        setState(data);
        if (data.screenshot_url && data.screenshot_url !== prevScreenshotRef.current) {
          prevScreenshotRef.current = data.screenshot_url;
          setImgLoading(true);
        }
        if (data.active) setLastUpdated(new Date());
      }
    } catch {
      // 静默失败，服务器未启动时不报错
    } finally {
      if (showSpinner) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }
    fetchState();
    intervalRef.current = setInterval(() => fetchState(), 1500);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [open, fetchState]);

  const screenshotSrc = state.screenshot_url
    ? `${API_URL}${state.screenshot_url}`
    : null;

  const openFullScreen = () => {
    if (screenshotSrc) window.open(screenshotSrc, "_blank");
  };

  return (
    <div
      className={cn(
        "flex flex-col h-full border-l border-gray-200/80 dark:border-gray-800",
        "bg-white dark:bg-gray-950 flex-shrink-0",
        "transition-all duration-300 ease-in-out overflow-hidden",
        open
          ? "w-[560px] opacity-100 shadow-[-10px_0_30px_rgba(0,0,0,0.02)]"
          : "w-0 opacity-0 border-l-0",
      )}
    >
      {/* ── 标题与地址栏合并 (类似现代简约浏览器) ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 h-[56px] border-b border-gray-200/80 dark:border-gray-800 flex-shrink-0 bg-white/90 dark:bg-gray-950/90 backdrop-blur-sm z-10 sticky top-0">
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <MonitorIcon className="h-4 w-4 text-gray-500 dark:text-gray-400" />
          <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            Browser
          </span>
        </div>

        {/* 状态指示 */}
        <div className="flex items-center gap-1.5 px-2">
          <span
            className={cn(
              "h-2 w-2 rounded-full flex-shrink-0 transition-all duration-500 shadow-sm",
              state.active
                ? "bg-emerald-400 shadow-emerald-400/50 animate-pulse"
                : "bg-gray-300 dark:bg-gray-600",
            )}
          />
        </div>

        {/* 简约地址栏 */}
        <div className="flex-1 flex items-center gap-2 min-w-0 rounded-full bg-gray-100 dark:bg-gray-900 border border-gray-200/50 dark:border-gray-800/50 px-4 py-1.5 shadow-inner transition-colors focus-within:border-blue-400/50 focus-within:ring-1 focus-within:ring-blue-400/20">
          <span className="text-[12px] font-mono text-gray-600 dark:text-gray-300 truncate flex-1 select-all">
            {state.url || "about:blank"}
          </span>
          {state.url && (
            <a
              href={state.url}
              target="_blank"
              rel="noopener noreferrer"
              title="在新标签页打开"
              className="flex-shrink-0 text-gray-400 hover:text-blue-500 transition-colors"
            >
              <ExternalLinkIcon className="h-3.5 w-3.5" />
            </a>
          )}
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={() => fetchState(true)}
            title="刷新状态"
            className="flex h-7 w-7 items-center justify-center rounded-full text-gray-400
              hover:bg-gray-200 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-all"
          >
            <RefreshCwIcon className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
          </button>
          <button
            onClick={onClose}
            title="关闭面板"
            className="flex h-7 w-7 items-center justify-center rounded-full text-gray-400
              hover:bg-gray-200 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-all"
          >
            <XIcon className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* ── 页面标题 ──────────────────────────────────────────────────── */}
      {state.title && (
        <div className="px-5 py-2 border-b border-gray-100/80 dark:border-gray-800/80 flex-shrink-0 bg-gray-50/50 dark:bg-gray-900/30">
          <p className="text-[13px] text-gray-700 dark:text-gray-300 truncate font-medium flex items-center gap-2">
            <span className="text-gray-400 dark:text-gray-500 font-normal select-none">Title</span>
            {state.title}
          </p>
        </div>
      )}

      {/* ── 截图主区域 (居中卡片式展示) ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto bg-[#f8f9fa] dark:bg-[#0a0a0a] relative group p-6 flex flex-col items-center custom-scrollbar">
        {screenshotSrc ? (
          <div className="relative w-full max-w-[1000px] flex-shrink-0 mx-auto rounded-xl shadow-[0_12px_40px_-10px_rgba(0,0,0,0.1)] dark:shadow-[0_12px_40px_-10px_rgba(0,0,0,0.5)] border border-gray-200/60 dark:border-gray-800/80 bg-white dark:bg-gray-950 overflow-hidden ring-1 ring-black/5 dark:ring-white/10 transition-all duration-300">
            {/* 顶栏装饰 */}
            <div className="h-8 bg-gray-100 dark:bg-gray-900 border-b border-gray-200/60 dark:border-gray-800 flex items-center px-3 gap-1.5 flex-shrink-0">
              <div className="w-2.5 h-2.5 rounded-full bg-red-400 dark:bg-red-500/80 shadow-inner"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-amber-400 dark:bg-amber-500/80 shadow-inner"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-green-400 dark:bg-green-500/80 shadow-inner"></div>
            </div>

            <div className="relative w-full min-h-[200px] flex justify-center bg-white dark:bg-zinc-950">
              {imgLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/60 dark:bg-zinc-950/60 z-10 backdrop-blur-sm">
                  <Loader2Icon className="h-8 w-8 animate-spin text-blue-500/80" />
                </div>
              )}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                key={screenshotSrc}
                src={screenshotSrc}
                alt="浏览器截图"
                className="w-full h-auto block object-top"
                onLoad={() => setImgLoading(false)}
                onError={() => setImgLoading(false)}
              />
            </div>

            {/* 点击放大按钮（hover 时显示在右下角） */}
            <button
              onClick={openFullScreen}
              title="全屏查看"
              className={cn(
                "absolute bottom-4 right-4 h-10 w-10 flex items-center justify-center",
                "rounded-full bg-gray-900/80 dark:bg-gray-100/90 text-white dark:text-gray-900 backdrop-blur-md shadow-lg",
                "opacity-0 group-hover:opacity-100 transition-all duration-300 hover:scale-105",
              )}
            >
              <ZoomInIcon className="h-5 w-5" />
            </button>
          </div>
        ) : (
          /* 空态提示 */
          <div className="flex flex-col items-center justify-center h-full gap-5 text-center mt-20">
            <div className="h-20 w-20 rounded-3xl bg-white dark:bg-gray-900 shadow-sm border border-gray-200/50 dark:border-gray-800 flex items-center justify-center ring-1 ring-black/5 dark:ring-white/5">
              <MonitorIcon className="h-8 w-8 text-gray-400 dark:text-gray-500" strokeWidth={1.5} />
            </div>
            <div className="space-y-2 max-w-[280px]">
              <p className="text-[15px] font-semibold text-gray-700 dark:text-gray-200 tracking-tight">
                等待浏览器活动
              </p>
              <p className="text-[13px] text-gray-500 dark:text-gray-400 leading-relaxed">
                在对话中让 AI 使用 <code className="font-mono text-[12px] bg-gray-200/50 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-700 dark:text-gray-300">browser_navigate</code> 等工具后，此处将实时展示页面。
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── 底部状态栏 ─────────────────────────────────────────────────── */}
      {lastUpdated && (
        <div className="px-5 py-2 border-t border-gray-200/60 dark:border-gray-800 flex-shrink-0 bg-white/50 dark:bg-gray-950/50 backdrop-blur-md z-10 flex justify-between items-center">
          <p className="text-[11px] text-gray-400 dark:text-gray-500 font-medium">
            Last Updated
          </p>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 font-mono">
            {lastUpdated.toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
}
