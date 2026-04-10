"use client";

/**
 * ToolFallback —— 工具调用的通用渲染组件
 * 基于 assistant-ui 官方 tool-fallback 实现，带折叠/展开交互
 * 浏览器工具（browser_*）结果含 screenshot_url 时内联展示截图
 */

import { memo, useMemo, useState } from "react";
import {
  CheckIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  LoaderIcon,
  XCircleIcon,
  AlertCircleIcon,
  ExternalLinkIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useToolPurposeLine } from "@/lib/tool-descriptions-context";
import { PdfDownloadCard, extractPdfFromToolResult } from "./pdf-preview-handler";

const CONVERT_WORD_TO_PDF_TOOL = "convert_word_to_pdf";

/** 浏览器工具名前缀 */
const BROWSER_TOOL_PREFIX = "browser_";
const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:6868")
    : "";

/** 从工具结果中提取浏览器截图数据（含 screenshot_url 字段的 JSON） */
function extractBrowserResult(result: unknown): {
  screenshotUrl: string;
  pageUrl: string;
  title: string;
} | null {
  if (!result) return null;
  let parsed: Record<string, unknown> | null = null;
  if (typeof result === "string") {
    try {
      parsed = JSON.parse(result);
    } catch {
      return null;
    }
  } else if (typeof result === "object") {
    parsed = result as Record<string, unknown>;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const screenshotUrl = typeof parsed.screenshot_url === "string" ? parsed.screenshot_url : "";
  if (!screenshotUrl) return null;
  return {
    screenshotUrl,
    pageUrl: typeof parsed.url === "string" ? parsed.url : "",
    title: typeof parsed.title === "string" ? parsed.title : "",
  };
}

type ToolStatus = { type: "running" | "complete" | "incomplete" | "requires-action"; reason?: string; error?: unknown };

export interface ToolFallbackProps {
  toolName: string;
  argsText?: string;
  args?: unknown;
  result?: unknown;
  status?: ToolStatus;
  addResult?: (result: unknown) => void;
}

function StatusIcon({ status }: { status?: ToolStatus }) {
  const type = status?.type ?? "complete";
  if (type === "running")
    return <LoaderIcon className="h-3.5 w-3.5 animate-spin text-zinc-500 dark:text-zinc-400" />;
  if (type === "complete")
    return <CheckIcon className="h-3.5 w-3.5 text-zinc-400 dark:text-zinc-500" />;
  if (type === "incomplete") {
    if (status?.reason === "cancelled")
      return <XCircleIcon className="h-3.5 w-3.5 text-zinc-400" />;
    return <XCircleIcon className="h-3.5 w-3.5 text-red-400" />;
  }
  return <AlertCircleIcon className="h-3.5 w-3.5 text-amber-400" />;
}

function ToolFallbackImpl({ toolName, argsText, args, result, status }: ToolFallbackProps) {
  const [open, setOpen] = useState(false);
  const staticPurposeLine = useToolPurposeLine(toolName);
  // 优先使用 LLM 生成的 _purpose（结合用户实际问题的上下文），降级到工具静态描述
  const purposeLine = (args as Record<string, unknown> | null | undefined)?._purpose as string | undefined
    || staticPurposeLine;
  const isRunning = status?.type === "running";
  const isCancelled = status?.type === "incomplete" && status.reason === "cancelled";

  // 过滤掉 _purpose，避免在"Input"详情区重复展示
  const filteredArgs = args && typeof args === "object"
    ? Object.fromEntries(Object.entries(args as Record<string, unknown>).filter(([k]) => k !== "_purpose"))
    : args;
  const displayArgs = argsText || (filteredArgs && Object.keys(filteredArgs as object).length > 0
    ? JSON.stringify(filteredArgs, null, 2)
    : undefined);
  const displayResult = result !== undefined ? (typeof result === "string" ? result : JSON.stringify(result, null, 2)) : undefined;
  const displayError = status?.error ? (typeof status.error === "string" ? status.error : JSON.stringify(status.error)) : undefined;
  const hasDetails = !!displayArgs || result !== undefined;

  const pdfFromTool = useMemo(() => {
    if (toolName !== CONVERT_WORD_TO_PDF_TOOL) return null;
    if (status?.type !== "complete") return null;
    return extractPdfFromToolResult(result);
  }, [toolName, status?.type, result]);

  const browserResult = useMemo(() => {
    if (!toolName.startsWith(BROWSER_TOOL_PREFIX)) return null;
    if (status?.type !== "complete") return null;
    return extractBrowserResult(result);
  }, [toolName, status?.type, result]);

  return (
    <div className="my-3 rounded-xl border border-zinc-200/60 dark:border-zinc-700/60 overflow-hidden text-sm bg-white dark:bg-zinc-800/50 shadow-sm transition-all hover:shadow-md">
      {/* 标题行 */}
      <button
        onClick={() => hasDetails && setOpen((v) => !v)}
        className={cn(
          "w-full flex items-center gap-2.5 px-4 py-3 text-left transition-colors",
          hasDetails && "hover:bg-zinc-50 dark:hover:bg-zinc-800 cursor-pointer",
          !hasDetails && "cursor-default",
        )}
      >
        <StatusIcon status={status} />
        <span className="flex-1 font-medium text-zinc-700 dark:text-zinc-300 truncate">
          {isCancelled
            ? "已取消"
            : isRunning
              ? `进行中：${purposeLine}`
              : purposeLine}
        </span>
        {hasDetails && (
          open
            ? <ChevronDownIcon className="h-4 w-4 text-zinc-400 flex-shrink-0" />
            : <ChevronRightIcon className="h-4 w-4 text-zinc-400 flex-shrink-0" />
        )}
      </button>

      {/* Word→PDF：转换完成即展示下载（不依赖助手是否把 JSON 写进正文） */}
      {pdfFromTool && (
        <div className="px-4 pb-3 pt-0 border-t border-zinc-100 dark:border-zinc-800">
          <PdfDownloadCard
            url={pdfFromTool.url}
            title={pdfFromTool.title}
            className="my-0 mt-2"
          />
        </div>
      )}

      {/* 浏览器工具：内联截图预览 */}
      {browserResult && (
        <div className="border-t border-zinc-100 dark:border-zinc-800">
          {/* 页面 URL 小标题行 */}
          {browserResult.pageUrl && (
            <div className="flex items-center gap-2 px-4 py-2 bg-zinc-50/80 dark:bg-zinc-900/60">
              <span className="text-[11px] font-mono text-zinc-400 truncate flex-1">
                {browserResult.pageUrl}
              </span>
              <a
                href={browserResult.pageUrl}
                target="_blank"
                rel="noopener noreferrer"
                title="在浏览器中打开"
                className="flex-shrink-0 text-zinc-300 hover:text-blue-500 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLinkIcon className="h-3 w-3" />
              </a>
            </div>
          )}
          {/* 截图 */}
          <div className="relative group overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${API_URL}${browserResult.screenshotUrl}`}
              alt="浏览器截图"
              className="w-full h-auto block max-h-72 object-cover object-top"
              loading="lazy"
            />
            {/* hover 时展示"查看完整截图"按钮 */}
            <a
              href={`${API_URL}${browserResult.screenshotUrl}`}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                "absolute inset-0 flex items-end justify-center pb-3",
                "opacity-0 group-hover:opacity-100 transition-opacity",
                "bg-gradient-to-t from-black/40 to-transparent",
              )}
              onClick={(e) => e.stopPropagation()}
            >
              <span className="flex items-center gap-1 text-white text-[11px] font-medium
                bg-black/50 rounded-full px-3 py-1 backdrop-blur-sm">
                <ExternalLinkIcon className="h-3 w-3" />
                查看完整截图
              </span>
            </a>
          </div>
        </div>
      )}

      {/* 折叠详情 */}
      {open && hasDetails && (
        <div className="border-t border-zinc-100 dark:border-zinc-800">
          {/* 参数 */}
          {displayArgs && (
            <div className="px-4 py-3 bg-zinc-50/50 dark:bg-zinc-900/50 border-b border-zinc-100 dark:border-zinc-800">
              <p className="text-[11px] uppercase tracking-wider text-zinc-400 mb-2 font-semibold">
                Input
              </p>
              <pre className="text-zinc-700 dark:text-zinc-300 overflow-x-auto text-[13px] leading-relaxed font-mono">
                {displayArgs}
              </pre>
            </div>
          )}

          {/* 结果 */}
          {displayResult !== undefined && (
            <div className="px-4 py-3 bg-zinc-50/50 dark:bg-zinc-900/50">
              <p className="text-[11px] uppercase tracking-wider text-zinc-400 mb-2 font-semibold">
                Result
              </p>
              <pre className="text-zinc-700 dark:text-zinc-300 overflow-x-auto max-h-64 text-[13px] leading-relaxed font-mono whitespace-pre-wrap">
                {displayResult}
              </pre>
            </div>
          )}

          {/* 错误信息 */}
          {status?.type === "incomplete" && displayError && (
            <div className="px-4 py-3 bg-red-50/50 dark:bg-red-950/30 border-t border-red-100 dark:border-red-900/50">
              <p className="text-[11px] uppercase tracking-wider text-red-400 mb-2 font-semibold">
                {isCancelled ? "Cancel Reason" : "Error"}
              </p>
              <pre className="text-red-600 dark:text-red-400 text-[13px] font-mono whitespace-pre-wrap">
                {displayError}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export const ToolFallback = memo(ToolFallbackImpl);
ToolFallback.displayName = "ToolFallback";
