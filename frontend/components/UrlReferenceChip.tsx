"use client";

import { LinkIcon, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { generateUrlTitle } from "@/lib/url-parser";

interface UrlReferenceChipProps {
  url: string;
  onRemove?: () => void;
  className?: string;
}

/**
 * URL 引用卡片 —— 显示检测到的 URL 为可视化引用形式
 */
export function UrlReferenceChip({
  url,
  onRemove,
  className,
}: UrlReferenceChipProps) {
  const title = generateUrlTitle(url);

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-gray-600",
        "bg-white dark:bg-gray-800 pl-2.5 pr-1 py-1.5 max-w-[min(100%,280px)] shadow-sm",
        "hover:shadow-md transition-all group",
        className,
      )}
    >
      <LinkIcon className="h-3.5 w-3.5 text-blue-500 dark:text-blue-400 flex-shrink-0" />
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        title={url}
        className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate min-w-0 hover:underline"
      >
        {title}
      </a>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          title="移除"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-gray-400
            hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-200
            opacity-0 group-hover:opacity-100 transition-all"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
