"use client";

/**
 * ToolFallback —— 工具调用的通用渲染组件
 * 基于 assistant-ui 官方 tool-fallback 实现，带折叠/展开交互
 * 浏览器工具（browser_*）结果含 screenshot_url 时内联展示截图
 */

import { memo, useEffect, useMemo, useState } from "react";
import {
  CheckIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  LoaderIcon,
  XCircleIcon,
  AlertCircleIcon,
  ExternalLinkIcon,
  Code2Icon,
  ShieldAlertIcon,
  Trash2Icon,
  FileTextIcon,
  PencilLineIcon,
  WrenchIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { authorizedFetch } from "@/lib/auth";
import { buildApiUrl, resolvePermissionRequest } from "@/lib/api";
import { useToolPurposeLine } from "@/lib/tool-descriptions-context";
import { PdfDownloadCard, extractPdfFromToolResult } from "./pdf-preview-handler";

const CONVERT_WORD_TO_PDF_TOOL = "convert_word_to_pdf";
const TRANSLATE_PDF_PRESERVE_LAYOUT_TOOL = "translate_pdf_preserve_layout";

/** 代码执行工具（Code Runner Skill） */
const RUN_CODE_TOOL = "run_code";
const TEXT_TO_IMAGE_TOOL = "text_to_image";

/** 浏览器工具名前缀 */
const BROWSER_TOOL_PREFIX = "browser_";
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

function resolveScreenshotRequestUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  return buildApiUrl(url);
}

function BrowserScreenshotPreview({
  screenshotUrl,
}: {
  screenshotUrl: string;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    setBlobUrl(null);
    setFailed(false);

    const load = async () => {
      try {
        const response = await authorizedFetch(resolveScreenshotRequestUrl(screenshotUrl), {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`Screenshot request failed: ${response.status}`);
        }
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) {
          setBlobUrl(objectUrl);
        }
      } catch (error) {
        console.error("load browser screenshot failed", error);
        if (!cancelled) {
          setFailed(true);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [screenshotUrl]);

  if (failed) {
    return (
      <div className="flex min-h-32 items-center justify-center bg-zinc-50 px-4 py-8 text-xs text-zinc-500 dark:bg-zinc-900/50 dark:text-zinc-400">
        截图加载失败
      </div>
    );
  }

  if (!blobUrl) {
    return (
      <div className="flex min-h-32 items-center justify-center bg-zinc-50 px-4 py-8 text-xs text-zinc-500 dark:bg-zinc-900/50 dark:text-zinc-400">
        加载截图中...
      </div>
    );
  }

  return (
    <div className="relative group overflow-hidden">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={blobUrl}
        alt="浏览器截图"
        className="w-full h-auto block max-h-72 object-cover object-top"
        loading="lazy"
      />
      <a
        href={blobUrl}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          "absolute inset-0 flex items-end justify-center pb-3",
          "opacity-0 group-hover:opacity-100 transition-opacity",
          "bg-gradient-to-t from-black/40 to-transparent",
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <span className="flex items-center gap-1 text-white text-[11px] font-medium bg-black/50 rounded-full px-3 py-1 backdrop-blur-sm">
          <ExternalLinkIcon className="h-3 w-3" />
          查看完整截图
        </span>
      </a>
    </div>
  );
}

type PermissionRequest = {
  type: "permission_required";
  id: string;
  tool_name?: string;
  action?: string;
  summary?: string;
  target?: string;
  status?: string;
};

function extractPermissionRequest(result: unknown): PermissionRequest | null {
  if (!result) return null;

  let parsed: unknown = result;
  if (typeof result === "string") {
    try {
      parsed = JSON.parse(result);
    } catch {
      return null;
    }
  }

  if (!parsed || typeof parsed !== "object") return null;
  const obj = parsed as Record<string, unknown>;
  if (obj.type !== "permission_required" || typeof obj.id !== "string") return null;

  return {
    type: "permission_required",
    id: obj.id,
    tool_name: typeof obj.tool_name === "string" ? obj.tool_name : undefined,
    action: typeof obj.action === "string" ? obj.action : undefined,
    summary: typeof obj.summary === "string" ? obj.summary : undefined,
    target: typeof obj.target === "string" ? obj.target : undefined,
    status: typeof obj.status === "string" ? obj.status : undefined,
  };
}

function getPreferredLanguage(): "zh" | "en" {
  if (typeof navigator === "undefined") return "zh";
  return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

function getLocalizedPurposeLine(toolName: string, fallback: string): string {
  const lang = getPreferredLanguage();
  const zh: Record<string, string> = {
    bash: "执行系统命令",
    read_file: "读取文件内容",
    write_file: "写入文件内容",
    edit_file: "编辑文件内容",
    str_replace: "替换文件内容",
    list_dir: "列出目录内容",
    glob_search: "搜索文件路径",
    run_code: "执行代码并展示结果",
    translate_pdf_preserve_layout: "翻译 PDF 并保留版式",
  };
  const en: Record<string, string> = {
    bash: "Run a system command",
    read_file: "Read file contents",
    write_file: "Write file contents",
    edit_file: "Edit file contents",
    str_replace: "Replace file contents",
    list_dir: "List directory contents",
    glob_search: "Search file paths",
    run_code: "Run code and show results",
    translate_pdf_preserve_layout: "Translate PDF and preserve layout",
  };
  return (lang === "zh" ? zh[toolName] : en[toolName]) || fallback;
}

type PermissionActionMeta = {
  badge: string;
  approveLabel: string;
  approvingLabel: string;
  defaultSummary: string;
  deniedText: string;
  executedText: string;
  accentClassName: string;
  icon: "delete" | "read" | "write" | "tool";
};

const permissionActionMeta: Record<string, PermissionActionMeta> = {
  delete_files: {
    badge: "删除操作",
    approveLabel: "允许删除",
    approvingLabel: "删除中...",
    defaultSummary: "该命令会删除文件或目录，请确认后再执行。",
    deniedText: "已拒绝删除。",
    executedText: "删除操作已执行。",
    accentClassName: "border-red-200 bg-red-50 text-red-600 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-300",
    icon: "delete",
  },
  read_external_file: {
    badge: "读取文件",
    approveLabel: "允许读取",
    approvingLabel: "读取中...",
    defaultSummary: "该操作需要读取工作区外的受限目录文件，请确认后再继续。",
    deniedText: "已拒绝读取。",
    executedText: "文件读取已执行。",
    accentClassName: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/40 dark:text-sky-300",
    icon: "read",
  },
  external_shell_write: {
    badge: "写入操作",
    approveLabel: "允许写入",
    approvingLabel: "写入中...",
    defaultSummary: "该命令会写入工作区外的受限目录，请确认后再执行。",
    deniedText: "已拒绝写入。",
    executedText: "写入操作已执行。",
    accentClassName: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-300",
    icon: "write",
  },
  tool_call: {
    badge: "工具调用",
    approveLabel: "允许执行",
    approvingLabel: "执行中...",
    defaultSummary: "该工具调用需要授权，请确认后再执行。",
    deniedText: "已拒绝执行。",
    executedText: "操作已执行。",
    accentClassName: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-300",
    icon: "tool",
  },
};

function getPermissionActionMeta(action?: string): PermissionActionMeta {
  return permissionActionMeta[action || ""] || permissionActionMeta.tool_call;
}

function PermissionActionIcon({ icon }: { icon: PermissionActionMeta["icon"] }) {
  if (icon === "delete") return <Trash2Icon className="h-3.5 w-3.5" />;
  if (icon === "read") return <FileTextIcon className="h-3.5 w-3.5" />;
  if (icon === "write") return <PencilLineIcon className="h-3.5 w-3.5" />;
  return <WrenchIcon className="h-3.5 w-3.5" />;
}

function formatPermissionResult(result: unknown, meta: PermissionActionMeta): string {
  if (!result || typeof result !== "object") return "";
  const obj = result as Record<string, unknown>;
  if (typeof obj.error === "string") return obj.error;
  if (typeof obj.result === "string") {
    const text = obj.result.trim();
    if (!text) return "";
    if (text.includes("<exit_code>0</exit_code>")) return meta.executedText;
    return text;
  }
  if (obj.status === "denied") return meta.deniedText;
  if (obj.status === "executed") return meta.executedText;
  return "";
}

/** 从 text_to_image 工具结果中提取图片 URL（支持纯文本与 JSON） */
function extractTextToImageUrls(result: unknown): string[] {
  if (!result) return [];

  const urls: string[] = [];
  const pushUrl = (v: unknown) => {
    if (typeof v !== "string") return;
    const s = v.trim();
    if (/^https?:\/\//i.test(s)) urls.push(s);
  };

  if (typeof result === "object") {
    const parsed = result as Record<string, unknown>;
    const arr = parsed.results;
    if (Array.isArray(arr)) {
      for (const item of arr) {
        if (!item || typeof item !== "object") continue;
        pushUrl((item as Record<string, unknown>).url);
      }
    }
    return Array.from(new Set(urls));
  }

  if (typeof result !== "string") return [];

  // 纯文本场景：逐行提取 "1. https://..." 或直接 https://...
  const lines = result.split(/\r?\n/);
  for (const line of lines) {
    const matched = line.match(/https?:\/\/\S+/gi);
    if (!matched) continue;
    for (const u of matched) pushUrl(u);
  }
  return Array.from(new Set(urls));
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

function ToolFallbackImpl({ toolName, argsText, args, result, status, addResult }: ToolFallbackProps) {
  const [open, setOpen] = useState(false);
  const [permissionBusy, setPermissionBusy] = useState<"approve" | "deny" | null>(null);
  const [permissionResult, setPermissionResult] = useState<unknown>(null);
  const [permissionError, setPermissionError] = useState("");
  const staticPurposeLine = useToolPurposeLine(toolName);
  const permissionRequest = useMemo(() => extractPermissionRequest(result), [result]);
  const permissionMeta = useMemo(
    () => getPermissionActionMeta(permissionRequest?.action),
    [permissionRequest?.action],
  );
  // 优先使用 LLM 生成的 _purpose（结合用户实际问题的上下文），降级到工具静态描述
  const purposeLine = permissionRequest?.summary
    || ((args as Record<string, unknown> | null | undefined)?._purpose as string | undefined)
    || getLocalizedPurposeLine(toolName, staticPurposeLine);
  const isRunning = status?.type === "running";
  const isCancelled = status?.type === "incomplete" && status.reason === "cancelled";
  const canRenderPdfCard =
    status?.type === "complete" &&
    (toolName === CONVERT_WORD_TO_PDF_TOOL || toolName === TRANSLATE_PDF_PRESERVE_LAYOUT_TOOL);
  const pdfFromTool = useMemo(() => {
    if (!canRenderPdfCard) return null;
    return extractPdfFromToolResult(result);
  }, [canRenderPdfCard, result]);

  // 过滤掉 _purpose，避免在"Input"详情区重复展示
  const filteredArgs = args && typeof args === "object"
    ? Object.fromEntries(Object.entries(args as Record<string, unknown>).filter(([k]) => k !== "_purpose"))
    : args;
  const displayArgs = argsText || (filteredArgs && Object.keys(filteredArgs as object).length > 0
    ? JSON.stringify(filteredArgs, null, 2)
    : undefined);
  const displayResult = !permissionRequest && !pdfFromTool && result !== undefined ? (typeof result === "string" ? result : JSON.stringify(result, null, 2)) : undefined;
  const displayError = status?.error ? (typeof status.error === "string" ? status.error : JSON.stringify(status.error)) : undefined;
  const hasDetails = !permissionRequest && !pdfFromTool && (!!displayArgs || result !== undefined);

  const resolvedPermissionText = formatPermissionResult(permissionResult, permissionMeta) || formatPermissionResult(result, permissionMeta);
  const canResolvePermission = !permissionResult && permissionRequest?.status === "pending";

  const handlePermissionResolve = async (approved: boolean) => {
    if (!permissionRequest || permissionBusy) return;
    const nextState = approved ? "approve" : "deny";
    setPermissionBusy(nextState);
    setPermissionError("");
    try {
      const response = await resolvePermissionRequest(permissionRequest.id, approved);
      setPermissionResult(response);
      addResult?.(response);
    } catch (error) {
      setPermissionError(error instanceof Error ? error.message : String(error));
    } finally {
      setPermissionBusy(null);
    }
  };

  const browserResult = useMemo(() => {
    if (!toolName.startsWith(BROWSER_TOOL_PREFIX)) return null;
    if (status?.type !== "complete") return null;
    return extractBrowserResult(result);
  }, [toolName, status?.type, result]);

  const runCodeComplete = toolName === RUN_CODE_TOOL && status?.type === "complete";
  const textToImageUrls = useMemo(() => {
    if (toolName !== TEXT_TO_IMAGE_TOOL) return [];
    if (status?.type !== "complete") return [];
    return extractTextToImageUrls(result);
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

      {permissionRequest && (
        <div className="border-t border-zinc-200/70 dark:border-zinc-700/70 bg-zinc-50/80 dark:bg-zinc-900/40 px-4 py-3">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-red-200/80 bg-white text-red-500 shadow-sm dark:border-red-900/60 dark:bg-zinc-950/50 dark:text-red-300">
              <ShieldAlertIcon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  需要授权
                </p>
                <span className={cn(
                  "rounded-full border px-2 py-0.5 text-[11px] font-medium",
                  permissionMeta.accentClassName,
                )}>
                  {permissionMeta.badge}
                </span>
              </div>
              <p className="mt-1 text-[13px] leading-relaxed text-zinc-600 dark:text-zinc-300">
                {permissionRequest.summary || permissionMeta.defaultSummary}
              </p>
              {permissionRequest.target && (
                <div className="mt-2 rounded-md border border-zinc-200 bg-white px-2.5 py-2 font-mono text-[12px] text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950/60 dark:text-zinc-300">
                  <span className="mr-2 text-zinc-400">target</span>
                  <span className="break-all">{permissionRequest.target}</span>
                </div>
              )}

              {canResolvePermission && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handlePermissionResolve(false)}
                    disabled={permissionBusy !== null}
                    className="inline-flex h-8 items-center justify-center rounded-md border border-zinc-200 bg-white px-3 text-xs font-medium text-zinc-700 shadow-sm transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
                  >
                    {permissionBusy === "deny" ? "处理中..." : "拒绝"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handlePermissionResolve(true)}
                    disabled={permissionBusy !== null}
                    className={cn(
                      "inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-3 text-xs font-semibold text-white shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60",
                      permissionMeta.icon === "delete"
                        ? "bg-red-600 hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-400"
                        : "bg-zinc-900 hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white",
                    )}
                  >
                    <PermissionActionIcon icon={permissionMeta.icon} />
                    {permissionBusy === "approve" ? permissionMeta.approvingLabel : permissionMeta.approveLabel}
                  </button>
                </div>
              )}

              {permissionError && (
                <p className="mt-2 text-[12px] text-red-600 dark:text-red-300">
                  {permissionError}
                </p>
              )}

              {resolvedPermissionText && (
                <pre className="mt-3 max-h-48 overflow-auto rounded-md border border-zinc-200 bg-white px-3 py-2 text-[12px] leading-relaxed text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950/60 dark:text-zinc-300 whitespace-pre-wrap">
                  {resolvedPermissionText}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}

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

      {/* run_code：提示右侧面板展示完整记录与图表 */}
      {runCodeComplete && (
        <div className="border-t border-emerald-200/70 dark:border-emerald-900/50 bg-emerald-50/90 dark:bg-emerald-950/35 px-4 py-2.5">
          <p className="text-[12px] text-emerald-900 dark:text-emerald-200/95 leading-snug flex items-start gap-2">
            <Code2Icon className="h-4 w-4 shrink-0 mt-0.5 opacity-90" />
            <span>
              代码、终端输出与 matplotlib 图表已同步到右侧「<strong className="font-semibold">代码执行</strong>」面板（按当前会话隔离）。
            </span>
          </p>
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
          {/* 截图（通过 authorizedFetch 带鉴权加载） */}
          <BrowserScreenshotPreview screenshotUrl={browserResult.screenshotUrl} />
        </div>
      )}

      {/* 文生图工具：内联图片预览 */}
      {textToImageUrls.length > 0 && (
        <div className="border-t border-zinc-100 dark:border-zinc-800 px-4 py-3 space-y-3">
          {textToImageUrls.map((url, idx) => (
            <a
              key={`${url}-${idx}`}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="block group"
              onClick={(e) => e.stopPropagation()}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={url}
                alt={`文生图结果 ${idx + 1}`}
                className="w-full h-auto rounded-lg border border-zinc-200 dark:border-zinc-700 shadow-sm group-hover:shadow-md transition-shadow"
                loading="lazy"
                referrerPolicy="no-referrer"
              />
            </a>
          ))}
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
