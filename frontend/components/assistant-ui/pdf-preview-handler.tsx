"use client";

/**
 * PdfPreviewHandler —— 从助手文本或工具返回中解析 Word→PDF 的 presigned_url，提供新窗口打开与下载
 */

import { FC, useEffect, useState } from "react";
import { Download, ExternalLink, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

function isPdfUrl(url: string): boolean {
  try {
    const p = new URL(url).pathname.toLowerCase();
    return p.endsWith(".pdf");
  } catch {
    return false;
  }
}

/** 从已解析的 JSON（工具或回复中的对象）提取 PDF 下载信息 */
export function extractPdfFromParsedJson(
  j: Record<string, unknown>,
): { url: string; title: string } | null {
  const url = j.presigned_url;
  if (!url || typeof url !== "string") return null;

  const cosKeyRaw = j.cos_key != null ? String(j.cos_key) : "";
  const cosEndsPdf = cosKeyRaw.toLowerCase().endsWith(".pdf");
  const urlLooksPdf = isPdfUrl(url);
  const success = j.success === true;
  if (!urlLooksPdf && !cosEndsPdf && !success) return null;

  const fromKey = cosKeyRaw ? cosKeyRaw.split("/").pop() : null;
  let title = fromKey || "document.pdf";
  try {
    const seg = new URL(url).pathname.split("/").pop();
    if (seg) title = decodeURIComponent(seg);
  } catch {
    /* keep title */
  }
  return { url, title };
}

export function extractPdfFromAssistantText(
  text: string,
): { url: string; title: string } | null {
  const idx = text.indexOf('"presigned_url"');
  if (idx === -1) return null;

  let start = text.lastIndexOf("{", idx);
  if (start === -1) return null;

  let depth = 0;
  let end = -1;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === -1) return null;

  try {
    const j = JSON.parse(text.slice(start, end + 1)) as Record<string, unknown>;
    const parsed = extractPdfFromParsedJson(j);
    if (parsed) return parsed;
  } catch {
    /* fall through */
  }

  const kv = text.match(/presigned_url\s*[:=]\s*(https?:\/\/\S+)/i);
  if (kv) {
    const url = kv[1].trim().replace(/\)+$/, "").replace(/[,;]+$/, "");
    if (isPdfUrl(url))
      return {
        url,
        title:
          (() => {
            try {
              return decodeURIComponent(
                new URL(url).pathname.split("/").pop() || "document.pdf",
              );
            } catch {
              return "document.pdf";
            }
          })(),
      };
  }

  return null;
}

/** 从工具 result（字符串 JSON 或对象）提取 PDF 信息，供 ToolFallback 使用 */
export function extractPdfFromToolResult(
  result: unknown,
): { url: string; title: string } | null {
  if (result == null) return null;
  if (typeof result === "string") {
    const fromText = extractPdfFromAssistantText(result);
    if (fromText) return fromText;
    try {
      const j = JSON.parse(result) as Record<string, unknown>;
      return extractPdfFromParsedJson(j);
    } catch {
      return null;
    }
  }
  if (typeof result === "object" && !Array.isArray(result)) {
    return extractPdfFromParsedJson(result as Record<string, unknown>);
  }
  return null;
}

function triggerDownload(filename: string, url: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.target = "_blank";
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => document.body.removeChild(a), 100);
}

/** 纯展示：保证转换完成后始终有可点的「下载 PDF」与「新窗口打开」 */
export const PdfDownloadCard: FC<{
  url: string;
  title: string;
  className?: string;
}> = ({ url, title, className }) => (
  <div
    className={cn(
      "my-3 overflow-hidden rounded-xl border border-stone-200/90 bg-white shadow-sm shadow-stone-950/5",
      "dark:border-zinc-700/80 dark:bg-zinc-950/40 dark:shadow-black/20",
      className,
    )}
  >
    <div
      className="flex flex-wrap items-center gap-3 px-4 py-3 bg-gradient-to-b from-stone-50/90 to-stone-50/40
        dark:from-zinc-900/50 dark:to-zinc-900/20"
    >
      <FileText
        className="h-4 w-4 flex-shrink-0 text-stone-400 dark:text-zinc-500"
        strokeWidth={1.75}
      />
      <span className="min-w-0 flex-1 truncate text-sm font-medium tracking-tight text-stone-800 dark:text-zinc-100">
        {title}
      </span>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white/80 px-3 py-1.5 text-xs
            font-medium text-stone-600 antialiased transition-colors
            hover:border-stone-300 hover:bg-white hover:text-stone-900
            dark:border-zinc-600 dark:bg-zinc-900/60 dark:text-zinc-300 dark:hover:border-zinc-500 dark:hover:bg-zinc-800/80 dark:hover:text-zinc-100"
        >
          <ExternalLink className="h-3.5 w-3.5 opacity-70" strokeWidth={1.75} />
          新窗口打开
        </a>
        <button
          type="button"
          onClick={() => triggerDownload(title, url)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-3 py-1.5 text-xs font-semibold
            tracking-wide text-white antialiased shadow-sm transition-colors
            hover:bg-stone-800 active:bg-stone-950
            dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white dark:active:bg-zinc-200"
        >
          <Download className="h-3.5 w-3.5" strokeWidth={1.75} />
          下载 PDF
        </button>
      </div>
    </div>
  </div>
);

export const PdfPreviewHandler: FC<{ text: string }> = ({ text }) => {
  const [info, setInfo] = useState<{ url: string; title: string } | null>(
    null,
  );

  useEffect(() => {
    setInfo(extractPdfFromAssistantText(text));
  }, [text]);

  if (!info) return null;

  return <PdfDownloadCard url={info.url} title={info.title} />;
};
