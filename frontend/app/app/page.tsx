"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createSession, notifySessionsListRefresh } from "@/lib/api";
import { ArrowUp, Paperclip, Sparkles, X, FileText, FileImage, File } from "lucide-react";
import { ACCEPTED_FILE_TYPES } from "@/lib/chat-attachment-adapter";

const SUGGESTIONS = [
  "列出当前目录的文件",
  "帮我写一个 Python 快速排序",
  "查看系统信息",
  "分析这段代码的性能",
];

interface PendingFile {
  name: string;
  contentType: string;
  dataUrl: string;
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function FileChip({
  file,
  onRemove,
}: {
  file: PendingFile;
  onRemove: () => void;
}) {
  const isImage = file.contentType.startsWith("image/");
  const isPdf = file.contentType === "application/pdf";
  const Icon = isImage ? FileImage : isPdf ? File : FileText;

  return (
    <div className="flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-gray-600
      bg-white dark:bg-gray-800 pl-2.5 pr-1 py-1.5 max-w-[200px] shadow-sm">
      <Icon className="h-3.5 w-3.5 text-gray-500 shrink-0" />
      <span className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate min-w-0">
        {file.name}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-gray-400
          hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-200"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = useCallback(async () => {
    const message = input.trim();
    if ((!message && pendingFiles.length === 0) || submitting) return;
    setSubmitting(true);
    try {
      const session = await createSession("新建会话");
      notifySessionsListRefresh();
      sessionStorage.setItem("sevn:initial-message", message);
      if (pendingFiles.length > 0) {
        sessionStorage.setItem(
          "sevn:initial-attachments",
          JSON.stringify(
            pendingFiles.map((f) => ({
              name: f.name,
              contentType: f.contentType,
              url: f.dataUrl,
            }))
          )
        );
      } else {
        sessionStorage.removeItem("sevn:initial-attachments");
      }
      router.push(`/app/${session.id}`);
    } catch (e) {
      console.error("创建会话失败:", e);
      setSubmitting(false);
    }
  }, [input, pendingFiles, submitting, router]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  const handleSuggestion = (text: string) => {
    setInput(text);
    textareaRef.current?.focus();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    const newPending: PendingFile[] = [];
    for (const file of files) {
      try {
        const dataUrl = await fileToDataUrl(file);
        newPending.push({
          name: file.name,
          contentType: file.type || "application/octet-stream",
          dataUrl,
        });
      } catch (err) {
        console.error("读取文件失败:", file.name, err);
      }
    }

    setPendingFiles((prev) => [...prev, ...newPending]);
    e.target.value = "";
  };

  const removeFile = (idx: number) => {
    setPendingFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const canSubmit = (input.trim().length > 0 || pendingFiles.length > 0) && !submitting;

  return (
    <div className="flex h-full flex-col items-center justify-center bg-white dark:bg-gray-900 px-6 pb-20">
      {/* 图标 */}
      <div className="mb-7 flex h-[60px] w-[60px] items-center justify-center rounded-2xl
        bg-gray-50 dark:bg-gray-800 ring-1 ring-gray-200/80 dark:ring-gray-700/80 shadow-sm">
        <Sparkles className="h-7 w-7 text-gray-700 dark:text-gray-200" strokeWidth={1.5} />
      </div>

      {/* 标题 */}
      <h1 className="mb-8 text-[30px] font-semibold tracking-tight text-gray-900 dark:text-gray-50 leading-snug">
        我能为你做什么？
      </h1>

      {/* 输入框区域 */}
      <div className="w-full max-w-[680px]">
        <div
          className="relative rounded-3xl border border-gray-200 dark:border-gray-700
            bg-white dark:bg-gray-800
            shadow-[0_4px_24px_rgba(0,0,0,0.06)] dark:shadow-[0_4px_24px_rgba(0,0,0,0.3)]
            hover:shadow-[0_6px_32px_rgba(0,0,0,0.09)] dark:hover:shadow-[0_6px_32px_rgba(0,0,0,0.4)]
            focus-within:border-gray-400/80 dark:focus-within:border-gray-500/80
            focus-within:shadow-[0_6px_32px_rgba(0,0,0,0.09)] dark:focus-within:shadow-[0_6px_32px_rgba(0,0,0,0.4)]
            transition-all duration-300"
        >
          {/* 已选文件预览 */}
          {pendingFiles.length > 0 && (
            <div className="flex flex-wrap gap-2 px-4 pt-3 pb-1">
              {pendingFiles.map((f, idx) => (
                <FileChip
                  key={`${f.name}-${idx}`}
                  file={f}
                  onRemove={() => removeFile(idx)}
                />
              ))}
            </div>
          )}

          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="给 Sevn Agent 发送消息..."
            rows={1}
            autoFocus
            disabled={submitting}
            className="w-full min-h-[60px] max-h-[200px] resize-none bg-transparent
              px-5 pt-[18px] pb-3
              text-[15px] text-gray-900 dark:text-gray-100
              placeholder:text-gray-400 dark:placeholder:text-gray-500
              focus:outline-none leading-relaxed rounded-3xl"
          />

          <div className="flex items-center px-3 pb-3 gap-1.5">
            {/* 回形针按钮 */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={submitting}
              title="上传文件（支持 Word、PDF、图片、TXT 等）"
              className="flex h-8 w-8 items-center justify-center rounded-xl text-gray-500
                hover:bg-gray-100 dark:hover:bg-gray-700 dark:text-gray-400 dark:hover:text-gray-200
                disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Paperclip className="h-4 w-4" />
            </button>

            {/* 隐藏文件输入 */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPTED_FILE_TYPES}
              className="hidden"
              onChange={handleFileChange}
            />

            {/* 发送按钮 */}
            <button
              onClick={() => void handleSubmit()}
              disabled={!canSubmit}
              className="ml-auto flex h-8 w-8 items-center justify-center rounded-xl
                bg-gray-900 hover:bg-gray-700 dark:bg-white dark:hover:bg-gray-100
                text-white dark:text-gray-900
                disabled:opacity-35 disabled:cursor-not-allowed
                shadow-sm transition-all duration-200"
              title="发送 (Enter)"
            >
              <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
            </button>
          </div>
        </div>

        {/* 文件类型提示 */}
        <p className="mt-2 text-center text-xs text-gray-400 dark:text-gray-600">
          支持上传 Word / PDF / 图片 / TXT 文件
        </p>

        {/* 快捷建议 */}
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => handleSuggestion(s)}
              disabled={submitting}
              className="rounded-full border border-gray-200/70 dark:border-gray-700/70
                bg-gray-50/80 dark:bg-gray-800/80
                px-4 py-1.5 text-[13px] text-gray-600 dark:text-gray-400
                hover:bg-white dark:hover:bg-gray-700/60
                hover:border-gray-300 dark:hover:border-gray-500
                hover:text-gray-900 dark:hover:text-gray-100
                hover:shadow-sm
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-all duration-200"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
