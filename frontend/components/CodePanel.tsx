"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircleIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  Code2Icon,
  ImageIcon,
  Loader2Icon,
  TerminalIcon,
  Trash2Icon,
  XIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { authorizedFetch } from "@/lib/auth";
import { buildApiUrl } from "@/lib/api";

const LANG_COLOR: Record<string, string> = {
  python: "#3776ab",
  javascript: "#f0db4f",
  typescript: "#3178c6",
  bash: "#4eaa25",
};

const LANG_LABEL: Record<string, string> = {
  python: "Python",
  javascript: "JS",
  typescript: "TS",
  bash: "Bash",
};

interface CodeResult {
  id: string;
  timestamp: string;
  language: string;
  description: string;
  code: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  images: string[];
  execution_time: number;
}

export interface CodePanelProps {
  open: boolean;
  onClose: () => void;
  sessionId?: string;
}

export function CodePanel({ open, onClose, sessionId }: CodePanelProps) {
  const [results, setResults] = useState<CodeResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedCodes, setExpandedCodes] = useState<Set<string>>(new Set());
  const [expandedImages, setExpandedImages] = useState<Set<string>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchResults = useCallback(
    async (silent = true) => {
      if (!sessionId) return;
      if (!silent) setLoading(true);
      try {
        const response = await authorizedFetch(
          buildApiUrl(`/api/code/results/${encodeURIComponent(sessionId)}`),
          { cache: "no-store" }
        );
        if (!response.ok) return;
        const data = await response.json();
        const newResults: CodeResult[] = data.results ?? [];
        setResults(newResults);
        if (newResults.length > prevCountRef.current) {
          const latest = newResults[newResults.length - 1];
          if (latest?.images?.length) {
            setExpandedImages((value) => new Set([...value, latest.id]));
          }
          setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 80);
        }
        prevCountRef.current = newResults.length;
      } catch (error) {
        console.error("fetch code results failed", error);
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [sessionId]
  );

  useEffect(() => {
    if (!open || !sessionId) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }
    void fetchResults(false);
    intervalRef.current = setInterval(() => void fetchResults(), 2000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [open, sessionId, fetchResults]);

  const clearAll = useCallback(async () => {
    if (!sessionId) return;
    const response = await authorizedFetch(
      buildApiUrl(`/api/code/results/${encodeURIComponent(sessionId)}`),
      { method: "DELETE" }
    );
    if (!response.ok) {
      throw new Error(`clear code results failed: ${response.status}`);
    }
    setResults([]);
    prevCountRef.current = 0;
    setExpandedCodes(new Set());
    setExpandedImages(new Set());
  }, [sessionId]);

  const toggleCode = (id: string) => {
    setExpandedCodes((value) => {
      const next = new Set(value);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleImages = (id: string) => {
    setExpandedImages((value) => {
      const next = new Set(value);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  return (
    <div
      className={cn(
        "flex h-full flex-shrink-0 flex-col overflow-hidden border-l border-gray-200/80 bg-white transition-all duration-300 ease-in-out dark:border-gray-800 dark:bg-[#0d0d12]",
        open ? "w-[600px] opacity-100" : "w-0 border-l-0 opacity-0"
      )}
    >
      <div className="z-10 flex h-[52px] flex-shrink-0 items-center gap-2 border-b border-gray-200/80 bg-white/90 px-4 backdrop-blur-sm dark:border-gray-800 dark:bg-[#0d0d12]/90">
        <Code2Icon className="h-4 w-4 flex-shrink-0 text-blue-500 dark:text-blue-400" />
        <span className="flex-1 text-sm font-semibold text-gray-800 dark:text-gray-100">
          代码执行
        </span>

        {results.length > 0 && (
          <span className="font-mono text-[11px] text-gray-400 dark:text-gray-500">
            {results.length} 条记录
          </span>
        )}

        {results.length > 0 && (
          <button
            onClick={() => void clearAll()}
            title="清空所有记录"
            className="flex h-7 w-7 items-center justify-center rounded-full text-gray-400 transition-all hover:bg-gray-200 hover:text-red-500 dark:hover:bg-white/10"
          >
            <Trash2Icon className="h-3.5 w-3.5" />
          </button>
        )}

        <button
          onClick={onClose}
          title="关闭面板"
          className="flex h-7 w-7 items-center justify-center rounded-full text-gray-400 transition-all hover:bg-gray-200 hover:text-gray-700 dark:hover:bg-white/10 dark:hover:text-gray-200"
        >
          <XIcon className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto bg-[#f8f9fa] [scrollbar-width:thin] dark:bg-[#0a0a0f]">
        {loading && results.length === 0 && (
          <div className="flex h-32 items-center justify-center gap-2 text-gray-400">
            <Loader2Icon className="h-4 w-4 animate-spin" />
            <span className="text-[13px]">加载中...</span>
          </div>
        )}

        {!loading && results.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 px-6 py-16 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-gray-200/60 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
              <Code2Icon className="h-7 w-7 text-gray-300 dark:text-gray-600" strokeWidth={1.5} />
            </div>
            <div className="max-w-[260px] space-y-1.5">
              <p className="text-[14px] font-semibold text-gray-700 dark:text-gray-200">
                等待 AI 执行代码
              </p>
              <p className="text-[12px] leading-relaxed text-gray-400 dark:text-gray-500">
                当对话里调用代码工具后，这里会展示脚本、输出和图表结果。
              </p>
            </div>
          </div>
        )}

        {results.length > 0 && (
          <div className="space-y-3 p-4">
            {results.map((result) => (
              <ResultCard
                key={result.id}
                result={result}
                codeExpanded={expandedCodes.has(result.id)}
                imagesExpanded={expandedImages.has(result.id)}
                onToggleCode={() => toggleCode(result.id)}
                onToggleImages={() => toggleImages(result.id)}
              />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}

interface ResultCardProps {
  result: CodeResult;
  codeExpanded: boolean;
  imagesExpanded: boolean;
  onToggleCode: () => void;
  onToggleImages: () => void;
}

function ResultCard({
  result,
  codeExpanded,
  imagesExpanded,
  onToggleCode,
  onToggleImages,
}: ResultCardProps) {
  const isSuccess = result.exit_code === 0;
  const hasImages = result.images.length > 0;
  const hasOutput = result.stdout || result.stderr;
  const time = new Date(result.timestamp).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200/80 bg-white shadow-sm dark:border-gray-800 dark:bg-[#111118]">
      <div className="flex items-center gap-2.5 border-b border-gray-100 px-4 py-3 dark:border-gray-800/80">
        <span
          className="flex-shrink-0 rounded px-2 py-0.5 text-[11px] font-bold text-white"
          style={{ backgroundColor: LANG_COLOR[result.language] ?? "#666" }}
        >
          {LANG_LABEL[result.language] ?? result.language}
        </span>

        <span className="flex-1 truncate text-[13px] font-medium text-gray-800 dark:text-gray-200">
          {result.description}
        </span>

        <span
          className={cn(
            "flex flex-shrink-0 items-center gap-1 text-[11px] font-medium",
            isSuccess ? "text-emerald-500" : "text-red-400"
          )}
        >
          {isSuccess ? (
            <CheckCircle2Icon className="h-3.5 w-3.5" />
          ) : (
            <AlertCircleIcon className="h-3.5 w-3.5" />
          )}
          {isSuccess ? "成功" : "失败"}
        </span>

        <span className="flex flex-shrink-0 items-center gap-1 font-mono text-[11px] text-gray-400 dark:text-gray-600">
          <ClockIcon className="h-3 w-3" />
          {result.execution_time.toFixed(2)}s
        </span>

        <span className="flex-shrink-0 font-mono text-[11px] text-gray-300 dark:text-gray-700">
          {time}
        </span>
      </div>

      <button
        onClick={onToggleCode}
        className="flex w-full items-center gap-2 border-b border-gray-100 px-4 py-2 text-left transition-colors hover:bg-gray-50 dark:border-gray-800/60 dark:hover:bg-white/4"
      >
        {codeExpanded ? (
          <ChevronDownIcon className="h-3.5 w-3.5 flex-shrink-0 text-gray-400" />
        ) : (
          <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0 text-gray-400" />
        )}
        <span className="font-mono text-[12px] text-gray-500 dark:text-gray-400">
          查看代码 ({result.code.split("\n").length} 行)
        </span>
      </button>

      {codeExpanded && (
        <div className="max-h-[320px] overflow-auto border-b border-gray-800 bg-[#1e1e2e]">
          <pre className="overflow-x-auto whitespace-pre p-4 font-mono text-[12.5px] leading-relaxed text-[#cdd6f4]">
            {result.code}
          </pre>
        </div>
      )}

      {hasOutput && (
        <div className="max-h-[300px] overflow-auto space-y-1 border-b border-gray-800/60 bg-[#1a1b26] px-4 py-3 last:border-b-0">
          <div className="mb-2 flex items-center gap-1.5">
            <TerminalIcon className="h-3 w-3 text-gray-600" />
            <span className="text-[11px] font-medium uppercase tracking-wide text-gray-600">
              输出
            </span>
          </div>
          {result.stdout && (
            <pre className="whitespace-pre-wrap break-all font-mono text-[12.5px] leading-relaxed text-[#a6e3a1]">
              {result.stdout}
            </pre>
          )}
          {result.stderr && (
            <pre className="whitespace-pre-wrap break-all font-mono text-[12.5px] leading-relaxed text-[#f38ba8]">
              {result.stderr}
            </pre>
          )}
        </div>
      )}

      {hasImages && (
        <div className="border-t border-gray-100 dark:border-gray-800/60">
          <button
            onClick={onToggleImages}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-gray-50 dark:hover:bg-white/4"
          >
            <ImageIcon className="h-3.5 w-3.5 flex-shrink-0 text-blue-500" />
            <span className="flex-1 text-[12px] font-medium text-blue-500 dark:text-blue-400">
              {result.images.length} 张图表
            </span>
            {imagesExpanded ? (
              <ChevronDownIcon className="h-3.5 w-3.5 text-gray-400" />
            ) : (
              <ChevronRightIcon className="h-3.5 w-3.5 text-gray-400" />
            )}
          </button>

          {imagesExpanded && (
            <div className="space-y-2.5 bg-[#0a0a0f] px-3 pb-3">
              {result.images.map((img, index) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={index}
                  src={`data:image/png;base64,${img}`}
                  alt={`图表 ${index + 1}`}
                  className="w-full rounded-lg border border-gray-700/50 shadow-md"
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
