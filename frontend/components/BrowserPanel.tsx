"use client";

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
import { authorizedFetch } from "@/lib/auth";
import { buildApiUrl } from "@/lib/api";

interface BrowserState {
  url: string;
  title: string;
  screenshot_url: string;
  active: boolean;
}

interface BrowserPanelProps {
  open: boolean;
  onClose: () => void;
  sessionId?: string;
}

export function BrowserPanel({ open, onClose, sessionId }: BrowserPanelProps) {
  const [state, setState] = useState<BrowserState>({
    url: "",
    title: "",
    screenshot_url: "",
    active: false,
  });
  const [refreshing, setRefreshing] = useState(false);
  const [imgLoading, setImgLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [screenshotBlobUrl, setScreenshotBlobUrl] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevScreenshotRef = useRef<string>("");

  const revokeScreenshotUrl = useCallback(() => {
    setScreenshotBlobUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
  }, []);

  const loadScreenshot = useCallback(
    async (relativeUrl: string) => {
      if (!relativeUrl) {
        revokeScreenshotUrl();
        return;
      }

      setImgLoading(true);
      try {
        const response = await authorizedFetch(buildApiUrl(relativeUrl), {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`Screenshot request failed: ${response.status}`);
        }
        const blob = await response.blob();
        const nextUrl = URL.createObjectURL(blob);
        setScreenshotBlobUrl((current) => {
          if (current) URL.revokeObjectURL(current);
          return nextUrl;
        });
      } catch (error) {
        console.error("load browser screenshot failed", error);
        revokeScreenshotUrl();
      } finally {
        setImgLoading(false);
      }
    },
    [revokeScreenshotUrl]
  );

  const fetchState = useCallback(
    async (showSpinner = false) => {
      if (!sessionId) return;
      if (showSpinner) setRefreshing(true);
      try {
        const params = `?session_id=${encodeURIComponent(sessionId)}`;
        const response = await authorizedFetch(
          buildApiUrl(`/api/browser/state${params}`),
          { cache: "no-store" }
        );
        if (!response.ok) return;
        const data: BrowserState = await response.json();
        setState(data);
        if (data.screenshot_url && data.screenshot_url !== prevScreenshotRef.current) {
          prevScreenshotRef.current = data.screenshot_url;
          void loadScreenshot(data.screenshot_url);
        } else if (!data.screenshot_url) {
          prevScreenshotRef.current = "";
          revokeScreenshotUrl();
        }
        if (data.active) setLastUpdated(new Date());
      } catch (error) {
        console.error("fetch browser state failed", error);
      } finally {
        if (showSpinner) setRefreshing(false);
      }
    },
    [loadScreenshot, revokeScreenshotUrl, sessionId]
  );

  useEffect(() => {
    if (!open) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }
    void fetchState();
    intervalRef.current = setInterval(() => void fetchState(), 1500);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [open, fetchState]);

  useEffect(() => {
    return () => revokeScreenshotUrl();
  }, [revokeScreenshotUrl]);

  const openFullScreen = () => {
    if (screenshotBlobUrl) {
      window.open(screenshotBlobUrl, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div
      className={cn(
        "flex h-full flex-shrink-0 flex-col overflow-hidden border-l border-gray-200/80 bg-white transition-all duration-300 ease-in-out dark:border-gray-800 dark:bg-gray-950",
        open
          ? "w-[560px] opacity-100 shadow-[-10px_0_30px_rgba(0,0,0,0.02)]"
          : "w-0 border-l-0 opacity-0"
      )}
    >
      <div className="sticky top-0 z-10 flex h-[56px] flex-shrink-0 items-center gap-3 border-b border-gray-200/80 bg-white/90 px-4 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-950/90">
        <div className="flex flex-shrink-0 items-center gap-1.5">
          <MonitorIcon className="h-4 w-4 text-gray-500 dark:text-gray-400" />
          <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            Browser
          </span>
        </div>

        <div className="flex items-center gap-1.5 px-2">
          <span
            className={cn(
              "h-2 w-2 flex-shrink-0 rounded-full shadow-sm transition-all duration-500",
              state.active
                ? "animate-pulse bg-emerald-400 shadow-emerald-400/50"
                : "bg-gray-300 dark:bg-gray-600"
            )}
          />
        </div>

        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-full border border-gray-200/50 bg-gray-100 px-4 py-1.5 shadow-inner transition-colors focus-within:border-blue-400/50 focus-within:ring-1 focus-within:ring-blue-400/20 dark:border-gray-800/50 dark:bg-gray-900">
          <span className="flex-1 truncate select-all font-mono text-[12px] text-gray-600 dark:text-gray-300">
            {state.url || "about:blank"}
          </span>
          {state.url && (
            <a
              href={state.url}
              target="_blank"
              rel="noopener noreferrer"
              title="在新标签页打开"
              className="flex-shrink-0 text-gray-400 transition-colors hover:text-blue-500"
            >
              <ExternalLinkIcon className="h-3.5 w-3.5" />
            </a>
          )}
        </div>

        <div className="flex flex-shrink-0 items-center gap-1">
          <button
            onClick={() => void fetchState(true)}
            title="刷新状态"
            className="flex h-7 w-7 items-center justify-center rounded-full text-gray-400 transition-all hover:bg-gray-200 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200"
          >
            <RefreshCwIcon className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
          </button>
          <button
            onClick={onClose}
            title="关闭面板"
            className="flex h-7 w-7 items-center justify-center rounded-full text-gray-400 transition-all hover:bg-gray-200 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200"
          >
            <XIcon className="h-4 w-4" />
          </button>
        </div>
      </div>

      {state.title && (
        <div className="flex-shrink-0 border-b border-gray-100/80 bg-gray-50/50 px-5 py-2 dark:border-gray-800/80 dark:bg-gray-900/30">
          <p className="flex items-center gap-2 truncate text-[13px] font-medium text-gray-700 dark:text-gray-300">
            <span className="select-none font-normal text-gray-400 dark:text-gray-500">
              Title
            </span>
            {state.title}
          </p>
        </div>
      )}

      <div className="group relative flex flex-1 flex-col items-center overflow-auto bg-[#f8f9fa] p-6 dark:bg-[#0a0a0a]">
        {screenshotBlobUrl ? (
          <div className="relative mx-auto w-full max-w-[1000px] flex-shrink-0 overflow-hidden rounded-xl border border-gray-200/60 bg-white shadow-[0_12px_40px_-10px_rgba(0,0,0,0.1)] ring-1 ring-black/5 transition-all duration-300 dark:border-gray-800/80 dark:bg-gray-950 dark:shadow-[0_12px_40px_-10px_rgba(0,0,0,0.5)] dark:ring-white/10">
            <div className="flex h-8 flex-shrink-0 items-center gap-1.5 border-b border-gray-200/60 bg-gray-100 px-3 dark:border-gray-800 dark:bg-gray-900">
              <div className="h-2.5 w-2.5 rounded-full bg-red-400 shadow-inner dark:bg-red-500/80" />
              <div className="h-2.5 w-2.5 rounded-full bg-amber-400 shadow-inner dark:bg-amber-500/80" />
              <div className="h-2.5 w-2.5 rounded-full bg-green-400 shadow-inner dark:bg-green-500/80" />
            </div>

            <div className="relative flex min-h-[200px] w-full justify-center bg-white dark:bg-zinc-950">
              {imgLoading && (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/60 backdrop-blur-sm dark:bg-zinc-950/60">
                  <Loader2Icon className="h-8 w-8 animate-spin text-blue-500/80" />
                </div>
              )}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                key={screenshotBlobUrl}
                src={screenshotBlobUrl}
                alt="浏览器截图"
                className="block h-auto w-full object-top"
                onLoad={() => setImgLoading(false)}
                onError={() => setImgLoading(false)}
              />
            </div>

            <button
              onClick={openFullScreen}
              title="全屏查看"
              className="absolute bottom-4 right-4 flex h-10 w-10 items-center justify-center rounded-full bg-gray-900/80 text-white opacity-0 shadow-lg backdrop-blur-md transition-all duration-300 hover:scale-105 group-hover:opacity-100 dark:bg-gray-100/90 dark:text-gray-900"
            >
              <ZoomInIcon className="h-5 w-5" />
            </button>
          </div>
        ) : (
          <div className="mt-20 flex h-full flex-col items-center justify-center gap-5 text-center">
            <div className="flex h-20 w-20 items-center justify-center rounded-3xl border border-gray-200/50 bg-white shadow-sm ring-1 ring-black/5 dark:border-gray-800 dark:bg-gray-900 dark:ring-white/5">
              <MonitorIcon className="h-8 w-8 text-gray-400 dark:text-gray-500" strokeWidth={1.5} />
            </div>
            <div className="max-w-[280px] space-y-2">
              <p className="text-[15px] font-semibold tracking-tight text-gray-700 dark:text-gray-200">
                等待浏览器活动
              </p>
              <p className="text-[13px] leading-relaxed text-gray-500 dark:text-gray-400">
                当对话里调用浏览器相关工具后，这里会实时展示页面快照。
              </p>
            </div>
          </div>
        )}
      </div>

      {lastUpdated && (
        <div className="z-10 flex flex-shrink-0 items-center justify-between border-t border-gray-200/60 bg-white/50 px-5 py-2 backdrop-blur-md dark:border-gray-800 dark:bg-gray-950/50">
          <p className="text-[11px] font-medium text-gray-400 dark:text-gray-500">
            Last Updated
          </p>
          <p className="font-mono text-[11px] text-gray-500 dark:text-gray-400">
            {lastUpdated.toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
}
