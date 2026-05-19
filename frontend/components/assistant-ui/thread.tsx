"use client";

/**
 * Thread —— 完整对话界面
 * 基于 @assistant-ui/react v0.10 原语 API，参考官方 thread.json 实现
 * 包含：消息列表、工具调用展示、复制/编辑/重试、分支导航、输入框
 * 使用 react-virtuoso 实现虚拟列表优化
 *
 * AI 头像：浅色用 frontend/logo1.png，深色用 frontend/logo2.png（可替换同路径文件）
 */

import Image from "next/image";
import logoLight from "@/logo1.png";
import logoDark from "@/logo2.png";
import {
  ActionBarPrimitive,
  AttachmentPrimitive,
  BranchPickerPrimitive,
  ComposerPrimitive,
  ContentPartPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useComposer,
  useComposerRuntime,
  useEditComposer,
  useMessage,
  useMessageRuntime,
  useThread,
} from "@assistant-ui/react";
import { Virtuoso } from "react-virtuoso";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  PencilIcon,
  RefreshCwIcon,
  SendHorizonalIcon,
  SquareIcon,
  Loader,
  PaperclipIcon,
  FileText,
  FileImage,
  X,
} from "lucide-react";
import type { FC } from "react";
import { useCallback, useRef, useMemo, useEffect, useState } from "react";
import { ToolFallback } from "./tool-fallback";
import { MarkdownText } from "./markdown-text";
import { ArchiveDownloadHandler } from "./archive-download-handler";
import { PdfPreviewHandler } from "./pdf-preview-handler";
import { cn } from "@/lib/utils";
import { detectUrls, separateUrlAndText, splitTextByUrls } from "@/lib/url-parser";
import { UrlReferenceChip } from "@/components/UrlReferenceChip";

// ── 入口组件 ────────────────────────────────────────────────────────────────

export const Thread: FC = () => {
  const messagesLength = useThread((t) => t.messages.length);
  const isRunning = useThread((t) => t.isRunning);
  const virtuosoRef = useRef<any>(null);
  const prevMessagesLengthRef = useRef(0);

  useEffect(() => {
    if (
      messagesLength > 0 &&
      prevMessagesLengthRef.current === 0 &&
      virtuosoRef.current
    ) {
      setTimeout(() => {
        virtuosoRef.current?.scrollToIndex({
          index: messagesLength - 1,
          behavior: "auto",
          align: "end",
        });
      }, 50);
    }
    prevMessagesLengthRef.current = messagesLength;
  }, [messagesLength]);

  const messageComponents = useMemo(
    () => ({
      UserMessage: UserMessage,
      UserEditComposer: UserEditComposer,
      AssistantMessage: AssistantMessage,
    }),
    []
  );

  const handleScrollToBottom = useCallback(() => {
    if (virtuosoRef.current && messagesLength > 0) {
      virtuosoRef.current.scrollToIndex({
        index: messagesLength - 1,
        behavior: "smooth",
        align: "end",
      });
    }
  }, [messagesLength]);

  const itemContent = useCallback(
    (index: number) => (
      <div className="mx-auto max-w-3xl px-4 py-1">
        <ThreadPrimitive.MessageByIndex
          index={index}
          components={messageComponents}
        />
      </div>
    ),
    [messageComponents]
  );

  return (
    <ThreadPrimitive.Root className="flex flex-col h-full bg-white dark:bg-gray-900 overflow-hidden relative">
      <ThreadPrimitive.Viewport className="flex-1 min-h-0 overflow-hidden relative">
        <ThreadPrimitive.Empty>
          <div className="h-full flex items-center justify-center">
            <ThreadWelcome />
          </div>
        </ThreadPrimitive.Empty>

        <Virtuoso
          ref={virtuosoRef}
          className="h-full"
          totalCount={messagesLength}
          itemContent={itemContent}
          followOutput={isRunning ? true : false}
          increaseViewportBy={{ top: 200, bottom: 200 }}
          overscan={5}
          components={{
            Header: () => <div className="h-8" />,
            Footer: () => <div className="h-40" />,
          }}
        />

        <ScrollToBottom onScrollToBottom={handleScrollToBottom} />
      </ThreadPrimitive.Viewport>

      <Composer />
    </ThreadPrimitive.Root>
  );
};

// ── 欢迎界面 ────────────────────────────────────────────────────────────────

const ThreadWelcome: FC = () => {
  const suggestions = [
    { prompt: "列出当前目录的文件" },
    { prompt: "帮我写一个 Python 快速排序算法" },
    { prompt: "查看系统信息" },
  ];

  return (
    <div className="flex flex-col items-center justify-center py-20 gap-6 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gray-100 dark:bg-gray-800 ring-1 ring-gray-200 dark:ring-gray-700">
        <svg
          className="h-8 w-8 text-gray-700 dark:text-gray-200"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
          />
        </svg>
      </div>
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 tracking-tight">
          你好，有什么可以帮你的？
        </h2>
        <p className="text-[15px] text-gray-500 dark:text-gray-400 max-w-xs mx-auto">
          我是 AI 助手，可以执行命令、读写文件、搜索信息等
        </p>
      </div>
      {/* 快捷建议 */}
      <div className="flex flex-wrap justify-center gap-2 w-full max-w-lg mt-4">
        {suggestions.map(({ prompt }) => (
          <ThreadPrimitive.Suggestion
            key={prompt}
            prompt={prompt}
            method="replace"
            autoSend
            asChild
          >
            <button
              className="rounded-full border border-gray-200/60 dark:border-gray-700/60
                bg-white/50 dark:bg-gray-800/50 backdrop-blur-sm
                px-4 py-2 text-sm text-gray-600 dark:text-gray-300
                hover:bg-gray-50 dark:hover:bg-gray-700/50
                hover:border-gray-300 dark:hover:border-gray-500
                hover:text-gray-900 dark:hover:text-gray-100
                hover:shadow-sm transition-all duration-200"
            >
              {prompt}
            </button>
          </ThreadPrimitive.Suggestion>
        ))}
      </div>
    </div>
  );
};

// ── 滚动到底部按钮 ──────────────────────────────────────────────────────────

const ScrollToBottom: FC<{ onScrollToBottom?: () => void }> = ({
  onScrollToBottom,
}) => {
  const handleClick = useCallback(() => {
    if (onScrollToBottom) {
      onScrollToBottom();
    }
  }, [onScrollToBottom]);

  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <button
        onClick={handleClick}
        className={cn(
          "absolute bottom-4 left-1/2 -translate-x-1/2 z-10",
          "flex items-center gap-1.5 rounded-full border border-gray-200",
          "dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5 text-xs font-medium",
          "text-gray-500 dark:text-gray-400 shadow-md hover:shadow-lg",
          "hover:text-gray-700 dark:hover:text-gray-200 transition-all",
          "opacity-0 pointer-events-none data-[visible]:opacity-100 data-[visible]:pointer-events-auto",
        )}
      >
        <ArrowDownIcon className="h-3 w-3" />
        滚动到底部
      </button>
    </ThreadPrimitive.ScrollToBottom>
  );
};

// ── 用户消息 ────────────────────────────────────────────────────────────────

/** 已发送用户消息里的附件（只读，显示在气泡上方） */
const MessageBubbleFileAttachmentChip: FC = () => (
  <AttachmentPrimitive.Root
    className={cn(
      "flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-600",
      "bg-white dark:bg-gray-800 px-2.5 py-1.5 max-w-[min(100%,280px)] shadow-sm",
    )}
  >
    <FileText className="h-4 w-4 text-gray-500 shrink-0" aria-hidden />
    <span className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate min-w-0">
      <AttachmentPrimitive.Name />
    </span>
  </AttachmentPrimitive.Root>
);

const MessageBubbleImageAttachmentChip: FC = () => (
  <AttachmentPrimitive.Root
    className={cn(
      "flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-600",
      "bg-white dark:bg-gray-800 px-2.5 py-1.5 max-w-[min(100%,280px)] shadow-sm",
    )}
  >
    <FileImage className="h-4 w-4 text-gray-500 shrink-0" aria-hidden />
    <span className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate min-w-0">
      <AttachmentPrimitive.Name />
    </span>
  </AttachmentPrimitive.Root>
);

/** 用户消息：普通文字原样换行展示；仅 http(s)/ftp 链接片段单行省略，避免撑破布局 */
const UserMessageText: FC<any> = ({ text }) => {
  if (text == null || text === "") return null;
  const s = String(text);
  const parts = splitTextByUrls(s);
  return (
    <p
      className={cn(
        "m-0 min-w-0 max-w-full select-text",
        "whitespace-pre-wrap break-words [overflow-wrap:anywhere]",
      )}
    >
      {parts.map((part, i) =>
        part.type === "url" ? (
          <a
            key={i}
            href={part.value}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "inline-block max-w-full min-w-0 align-baseline truncate",
              "text-blue-600 underline decoration-blue-600/40 underline-offset-2",
              "dark:text-blue-400 dark:decoration-blue-400/40",
            )}
          >
            {part.value}
          </a>
        ) : (
          <span key={i}>{part.value}</span>
        ),
      )}
    </p>
  );
};

const UserMessage: FC = () => (
  <MessagePrimitive.Root className="group mb-8 flex justify-end animate-in fade-in slide-in-from-bottom-2 duration-300">
    <div className="flex min-w-0 max-w-[80%] flex-col items-end gap-1.5">
      <MessagePrimitive.If hasAttachments>
        <div className="mb-1 flex w-full flex-wrap justify-end gap-2">
          <MessagePrimitive.Attachments
            components={{
              File: MessageBubbleFileAttachmentChip,
              Image: MessageBubbleImageAttachmentChip,
              Document: MessageBubbleFileAttachmentChip,
              Attachment: MessageBubbleFileAttachmentChip,
            }}
          />
        </div>
      </MessagePrimitive.If>
      {/* 消息气泡（与助手侧一致的浅底 + 边框，避免深色反色块） */}
      <div
        className="w-full min-w-0 max-w-full overflow-hidden rounded-3xl rounded-br-sm border border-gray-200/80 dark:border-gray-700/80
          bg-gray-50 dark:bg-gray-800/80 px-5 py-3 text-[15px]
          text-gray-800 dark:text-gray-200 leading-relaxed shadow-sm"
      >
        <MessagePrimitive.Parts components={{ Text: UserMessageText }} />
      </div>

      {/* 操作栏（hover 显示） */}
      <UserActionBar />
    </div>
  </MessagePrimitive.Root>
);

const UserEditComposer: FC = () => {
  const text = useEditComposer((c) => c.text);
  const isEmpty = useEditComposer((c) => c.isEmpty);
  const runtime = useMessageRuntime().composer;
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.focus();
    const pos = el.value.length;
    el.setSelectionRange(pos, pos);
  }, []);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [text]);

  return (
    <MessagePrimitive.Root className="mb-8 flex justify-end">
      <div className="flex min-w-0 max-w-[80%] flex-col items-end gap-1.5">
        <MessagePrimitive.If hasAttachments>
          <div className="mb-1 flex w-full flex-wrap justify-end gap-2">
            <MessagePrimitive.Attachments
              components={{
                File: MessageBubbleFileAttachmentChip,
                Image: MessageBubbleImageAttachmentChip,
                Document: MessageBubbleFileAttachmentChip,
                Attachment: MessageBubbleFileAttachmentChip,
              }}
            />
          </div>
        </MessagePrimitive.If>

        <div
          className="w-full min-w-0 max-w-full overflow-hidden rounded-3xl rounded-br-sm border border-blue-200/80 dark:border-blue-700/70
            bg-white dark:bg-gray-800 px-4 py-3 text-[15px] shadow-sm"
        >
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => runtime.setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                runtime.cancel();
                return;
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!isEmpty) runtime.send();
              }
            }}
            rows={1}
            className="min-h-[72px] w-full resize-none bg-transparent text-[15px] leading-relaxed
              text-gray-900 dark:text-gray-100 focus:outline-none"
          />
          <div className="mt-3 flex items-center justify-between gap-3 border-t border-gray-200/70 pt-3 dark:border-gray-700/70">
            <span className="text-xs text-gray-400 dark:text-gray-500">
              Enter 发送，Shift+Enter 换行，Esc 取消
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => runtime.cancel()}
                className="rounded-lg px-3 py-1.5 text-sm text-gray-500 transition-colors
                  hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
              >
                取消
              </button>
              <button
                type="button"
                disabled={isEmpty}
                onClick={() => {
                  if (!isEmpty) runtime.send();
                }}
                className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm text-white transition-colors
                  hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40
                  dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
              >
                重新发送
              </button>
            </div>
          </div>
        </div>
      </div>
    </MessagePrimitive.Root>
  );
};

const UserActionBar: FC = () => (
  <ActionBarPrimitive.Root
    hideWhenRunning
    autohide="never"
    autohideFloat="never"
    className={cn(
      "flex h-7 items-center gap-1",
      "opacity-0 translate-y-1 pointer-events-none transition-all duration-200",
      "group-hover:opacity-100 group-hover:translate-y-0 group-hover:pointer-events-auto",
    )}
  >
    <ActionBarPrimitive.Copy
      asChild
    >
      <button
        title="复制"
        className={cn(
          "flex h-6 w-6 items-center justify-center rounded-md text-gray-400",
          "hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300",
          "transition-colors",
        )}
      >
        <CopyIcon className="h-3 w-3" />
      </button>
    </ActionBarPrimitive.Copy>
    <ActionBarPrimitive.Edit asChild>
      <button
        title="编辑"
        className={cn(
          "flex h-6 w-6 items-center justify-center rounded-md text-gray-400",
          "hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300",
          "transition-colors",
        )}
      >
        <PencilIcon className="h-3 w-3" />
      </button>
    </ActionBarPrimitive.Edit>
  </ActionBarPrimitive.Root>
);

// ── 助手消息 ────────────────────────────────────────────────────────────────

const AssistantAvatar: FC = () => {
  const isRunning = useMessage((message) => message.status?.type === "running");

  return (
    <div className="relative mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center">
      {isRunning ? (
        <span
          className="assistant-avatar-breathe absolute inset-[-4px] rounded-full
            bg-[radial-gradient(circle,rgba(59,130,246,0.18)_0%,rgba(59,130,246,0.08)_42%,transparent_72%)]
            dark:bg-[radial-gradient(circle,rgba(96,165,250,0.22)_0%,rgba(96,165,250,0.08)_42%,transparent_72%)]"
          aria-hidden
        />
      ) : null}
      <div
        className="relative flex h-8 w-8 overflow-hidden rounded-full ring-1 ring-gray-200 dark:ring-gray-700
          bg-white dark:bg-gray-900 shadow-sm"
      >
        <Image
          src={logoLight}
          alt=""
          width={32}
          height={32}
          className="h-full w-full object-cover dark:hidden"
        />
        <Image
          src={logoDark}
          alt=""
          width={32}
          height={32}
          className="hidden h-full w-full object-cover dark:block"
        />
      </div>
    </div>
  );
};

function hasRenderableAssistantContent(content: unknown): boolean {
  if (!Array.isArray(content)) return false;

  return content.some((part) => {
    if (!part || typeof part !== "object") return false;
    const x = part as Record<string, unknown>;
    const type = typeof x.type === "string" ? x.type : "";
    if (type === "text") return typeof x.text === "string" && x.text.trim().length > 0;
    if (type === "reasoning") {
      const reasoning =
        typeof x.reasoning === "string"
          ? x.reasoning
          : typeof x.text === "string"
            ? x.text
            : "";
      return reasoning.trim().length > 0;
    }
    return (
      type === "tool-invocation" ||
      type === "source" ||
      type === "image" ||
      type === "file" ||
      type === "audio"
    );
  });
}

const AssistantPendingShell: FC = () => (
  <div
    className={cn(
      "assistant-wait-pill ml-0.5 inline-flex items-center gap-3 overflow-hidden",
      "rounded-full border border-gray-200/80 bg-white/75 px-3.5 py-2",
      "text-[13px] font-medium text-gray-600 shadow-[0_10px_30px_rgba(15,23,42,0.08)] backdrop-blur-xl",
      "dark:border-white/10 dark:bg-gray-900/72 dark:text-gray-300 dark:shadow-[0_14px_36px_rgba(0,0,0,0.35)]",
    )}
    role="status"
    aria-live="polite"
  >
    <span className="assistant-wait-orb" aria-hidden>
      <span className="assistant-wait-core" />
    </span>
    <span className="relative z-10 flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
      <span>{"SevnX \u6b63\u5728\u601d\u8003"}</span>
      <span className="assistant-thinking-dots inline-flex items-end gap-0.5" aria-hidden>
        <span />
        <span />
        <span />
      </span>
    </span>
    <span
      className="assistant-thinking-bar absolute bottom-0 left-7 h-px w-24 rounded-full bg-gradient-to-r from-transparent via-sky-400/70 to-transparent dark:via-sky-300/70"
      aria-hidden
    />
  </div>
);

const AssistantMessage: FC = () => {
  const statusType = useMessage((message) => message.status?.type);
  const isLast = useMessage((message) => message.isLast);
  const content = useMessage((message) => message.content);
  const showPendingShell =
    isLast && statusType === "running" && !hasRenderableAssistantContent(content);

  return (
    <MessagePrimitive.Root className="group mb-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
    <div className="flex gap-4 items-start">
      <AssistantAvatar />

      {/* 内容区 */}
      <div className="flex-1 min-w-0 space-y-2">
        {showPendingShell ? <AssistantPendingShell /> : null}
        {/* 消息内容（去除强背景框，模拟文档流） */}
        <div className="px-1 py-1 text-[15px] text-gray-800 dark:text-gray-200 leading-relaxed">
          <MessagePrimitive.Parts
            components={{
              Text: AssistantText,
              tools: { Fallback: ToolFallback },
            }}
          />
        </div>

        {/* 错误提示 */}
        <MessageError />

        {/* 操作栏 */}
        <AssistantActionBar />

        {/* 分支导航 */}
        <BranchPicker />
      </div>
    </div>
    </MessagePrimitive.Root>
  );
};

// 助手文本内容（含打字光标）—— 支持 markdown
const AssistantText: FC<any> = ({ text }) => {
  // 如果文本为空，显示加载动画
  if (!text) {
    return null;
  }

  return (
    <>
      <PdfPreviewHandler text={text} />
      <ArchiveDownloadHandler text={text} />
      <MarkdownText content={text} />
      <ContentPartPrimitive.InProgress>
        <span className="assistant-inline-cursor ml-1 inline-block h-3 w-3 rounded-full bg-zinc-400 dark:bg-zinc-500 align-middle" />
      </ContentPartPrimitive.InProgress>
    </>
  );
};

// 消息错误提示
const MessageError: FC = () => (
  <MessagePrimitive.Error>
    <div className="flex items-center gap-2 text-xs text-red-500 dark:text-red-400 px-1">
      <span className="h-1.5 w-1.5 rounded-full bg-red-500 flex-shrink-0" />
      生成过程中发生错误
    </div>
  </MessagePrimitive.Error>
);

// 助手操作栏（复制 / 重试）
const AssistantActionBar: FC = () => (
  <ActionBarPrimitive.Root
    hideWhenRunning
    autohide="never"
    autohideFloat="never"
    className={cn(
      "flex h-7 items-center gap-1 ml-1",
      "opacity-0 translate-y-1 pointer-events-none transition-all duration-200",
      "group-hover:opacity-100 group-hover:translate-y-0 group-hover:pointer-events-auto",
    )}
  >
    <ActionBarPrimitive.Copy
      asChild
    >
      <button
        title="复制"
        className={cn(
          "flex h-6 w-6 items-center justify-center rounded-md text-gray-400",
          "hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300",
          "transition-colors",
        )}
      >
        <CopyIcon className="h-3 w-3" />
      </button>
    </ActionBarPrimitive.Copy>
    <ActionBarPrimitive.Reload asChild>
      <button
        title="重新生成"
        className={cn(
          "flex h-6 w-6 items-center justify-center rounded-md text-gray-400",
          "hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300",
          "transition-colors",
        )}
      >
        <RefreshCwIcon className="h-3 w-3" />
      </button>
    </ActionBarPrimitive.Reload>
  </ActionBarPrimitive.Root>
);

// 分支导航（多个答案版本切换）
const BranchPicker: FC<{ className?: string }> = ({ className }) => (
  <BranchPickerPrimitive.Root
    hideWhenSingleBranch
    className={cn(
      "flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500",
      className,
    )}
  >
    <BranchPickerPrimitive.Previous asChild>
      <IconButton title="上一个版本">
        <ChevronLeftIcon className="h-3 w-3" />
      </IconButton>
    </BranchPickerPrimitive.Previous>
    <span className="tabular-nums">
      <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
    </span>
    <BranchPickerPrimitive.Next asChild>
      <IconButton title="下一个版本">
        <ChevronRightIcon className="h-3 w-3" />
      </IconButton>
    </BranchPickerPrimitive.Next>
  </BranchPickerPrimitive.Root>
);

// ── 输入框区域 ──────────────────────────────────────────────────────────────

/** 已选附件预览（须注册 File/Image 等组件，否则 type:file 的附件不会显示） */
const ComposerAttachmentsBar: FC = () => {
  const count = useComposer((c) => c.attachments.length);
  if (count === 0) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-2 px-1">
      <ComposerPrimitive.Attachments
        components={{
          File: ComposerFileAttachmentChip,
          Image: ComposerImageAttachmentChip,
          Document: ComposerFileAttachmentChip,
          Attachment: ComposerFileAttachmentChip,
        }}
      />
    </div>
  );
};

const ComposerFileAttachmentChip: FC = () => (
  <AttachmentPrimitive.Root
    className={cn(
      "flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-600",
      "bg-white dark:bg-gray-800 pl-2.5 pr-1 py-1.5 max-w-[min(100%,280px)] shadow-sm",
    )}
  >
    <FileText className="h-4 w-4 text-gray-500 shrink-0" aria-hidden />
    <span className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate min-w-0">
      <AttachmentPrimitive.Name />
    </span>
    <AttachmentPrimitive.Remove asChild>
      <button
        type="button"
        title="移除"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-gray-400
          hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-200"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </AttachmentPrimitive.Remove>
  </AttachmentPrimitive.Root>
);

const ComposerImageAttachmentChip: FC = () => (
  <AttachmentPrimitive.Root
    className={cn(
      "flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-600",
      "bg-white dark:bg-gray-800 pl-2.5 pr-1 py-1.5 max-w-[min(100%,280px)] shadow-sm",
    )}
  >
    <FileImage className="h-4 w-4 text-gray-500 shrink-0" aria-hidden />
    <span className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate min-w-0">
      <AttachmentPrimitive.Name />
    </span>
    <AttachmentPrimitive.Remove asChild>
      <button
        type="button"
        title="移除"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-gray-400
          hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-200"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </AttachmentPrimitive.Remove>
  </AttachmentPrimitive.Root>
);

const Composer: FC = () => {
  const [pendingUrls, setPendingUrls] = useState<Array<{ url: string; id: string }>>([]);
  const text = useComposer((c) => c.text);
  const isEmpty = useComposer((c) => c.isEmpty);
  const attachmentCount = useComposer((c) => c.attachments.length);
  const runtime = useComposerRuntime();
  const isRunning = useThread((t) => t.isRunning);

  const handleInputChange = useCallback(
    (newValue: string) => {
      // 检测新输入中是否有 URL
      const { urls, remainingText } = separateUrlAndText(newValue);

      if (urls.length > 0) {
        // 有新 URL 被检测到，加入 pending
        const newUrls = urls
          .filter((u) => !pendingUrls.some((pu) => pu.url === u.url))
          .map((u) => ({
            url: u.url,
            id: `url-${Date.now()}-${Math.random()}`,
          }));
        if (newUrls.length > 0) {
          setPendingUrls((prev) => [...prev, ...newUrls]);
        }
        // 更新输入框只显示纯文本部分
        runtime.setText(remainingText);
      } else {
        // 无 URL，直接更新
        runtime.setText(newValue);
      }
    },
    [pendingUrls, runtime]
  );

  const removeUrl = (id: string) => {
    setPendingUrls((prev) => prev.filter((u) => u.id !== id));
  };

  const canSendNow =
    !isEmpty || attachmentCount > 0 || pendingUrls.length > 0;

  const handleSend = useCallback(() => {
    if (pendingUrls.length > 0) {
      const urlsText = pendingUrls.map((u) => u.url).join("\n");
      const finalMessage = [urlsText, text].filter(Boolean).join("\n\n");
      runtime.setText(finalMessage);
      setPendingUrls([]);
      window.setTimeout(() => {
        const s = runtime.getState();
        if (!s.isEmpty || s.attachments.length > 0) runtime.send();
      }, 0);
      return;
    }
    const s = runtime.getState();
    if (!s.isEmpty || s.attachments.length > 0) runtime.send();
  }, [pendingUrls, runtime, text]);

  const ComposerPrimaryAction: FC = () => (
    <div className="ml-auto flex items-center">
      {isRunning ? (
        <ComposerPrimitive.Cancel asChild>
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-xl
              border-2 border-gray-300 dark:border-gray-600 hover:border-red-400
              text-gray-500 hover:text-red-500 transition-colors shadow-sm"
            title="停止生成"
            aria-label="停止生成"
          >
            <SquareIcon className="h-3.5 w-3.5" />
          </button>
        </ComposerPrimitive.Cancel>
      ) : (
        <button
          type="button"
          data-composer-send="true"
          disabled={!canSendNow}
          onClick={handleSend}
          className="flex h-8 w-8 items-center justify-center rounded-xl
            bg-black hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-200 text-white dark:text-black transition-colors
            disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
          title="发送 (Enter)"
          aria-label="发送"
        >
          <ArrowUpIcon className="h-4 w-4" />
        </button>
      )}
    </div>
  );

  return (
    <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white/90 to-transparent dark:from-gray-900 dark:via-gray-900/90 px-4 pb-6 pt-10 pointer-events-none z-10">
      <div className="mx-auto max-w-3xl pointer-events-auto">
        <ComposerAttachmentsBar />

        {/* URL 参考卡片 */}
        {pendingUrls.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1 mb-2">
            {pendingUrls.map((u) => (
              <UrlReferenceChip
                key={u.id}
                url={u.url}
                onRemove={() => removeUrl(u.id)}
              />
            ))}
          </div>
        )}

        <ComposerPrimitive.Root
          className="relative flex flex-col rounded-3xl border border-gray-200/80 dark:border-gray-700/80
            bg-white/80 dark:bg-gray-800/80 backdrop-blur-xl shadow-lg hover:shadow-xl
            focus-within:border-gray-400 dark:focus-within:border-gray-500
            focus-within:shadow-xl transition-all duration-300"
        >
          <input
            type="text"
            value={text}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== "Enter" || e.shiftKey) return;
              e.preventDefault();
              if (isRunning) return;
              if (!canSendNow) return;
              handleSend();
            }}
            placeholder="给 AI 助手发送消息..."
            className="min-h-[56px] max-h-48 resize-none bg-transparent px-5 py-4
              text-[15px] text-gray-900 dark:text-gray-100
              placeholder:text-gray-400 dark:placeholder:text-gray-500
              focus:outline-none leading-relaxed rounded-3xl w-full"
          />
          {/* 回形针在左，右侧单一主按钮：空闲为发送，生成中为停止 */}
          <div className="flex items-center px-3 pb-3 gap-1.5">
            <ComposerPrimitive.AddAttachment asChild>
              <button
                type="button"
                title="上传附件（支持 Word、PDF、图片、TXT 等）"
                className="flex h-8 w-8 items-center justify-center rounded-xl text-gray-500
                  hover:bg-gray-100 dark:hover:bg-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
              >
                <PaperclipIcon className="h-4 w-4" />
              </button>
            </ComposerPrimitive.AddAttachment>
            <ComposerPrimaryAction />
          </div>
        </ComposerPrimitive.Root>
        <p className="mt-2 text-center text-xs text-gray-300 dark:text-gray-600">
          AI 可能会出错，重要信息请自行核实
        </p>
      </div>
    </div>
  );
};

// ── 通用图标按钮 ────────────────────────────────────────────────────────────

const IconButton: FC<{
  title: string;
  children: React.ReactNode;
  className?: string;
}> = ({ title, children, className }) => (
  <button
    title={title}
    className={cn(
      "flex h-6 w-6 items-center justify-center rounded-md text-gray-400",
      "hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300",
      "transition-colors",
      className,
    )}
  >
    {children}
  </button>
);
