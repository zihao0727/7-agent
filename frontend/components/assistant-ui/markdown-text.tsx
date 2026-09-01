"use client";

/**
 * MarkdownText —— 使用 react-markdown 渲染 markdown 内容
 * 使用 Shiki 进行代码高亮，背景色与对话框一致
 * 根据明暗模式自动切换高亮主题
 */

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Components } from "react-markdown";
import { codeToHtml } from "shiki";
import { useState, useEffect, memo, useMemo } from "react";
import { Check, Copy } from "lucide-react";
import { authorizedFetch } from "@/lib/auth";
import { buildApiUrl } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/runtime-config";

function resolveImageSrc(src?: string): string | undefined {
  if (!src) return src;
  if (/^https?:\/\//i.test(src) || src.startsWith("data:")) return src;
  if (src.startsWith("/api/")) return `${getApiBaseUrl()}${src}`;
  return src;
}

function isInternalApiImage(src?: string): boolean {
  if (!src) return false;
  return src.startsWith("/api/");
}

function resolveAuthImageUrl(src?: string): string {
  if (!src) return "";
  if (/^https?:\/\//i.test(src)) return src;
  return buildApiUrl(src);
}

function AuthImage({ src, alt, className, loading }: { src?: string; alt?: string; className?: string; loading?: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    setBlobUrl(null);
    setFailed(false);

    const load = async () => {
      try {
        const response = await authorizedFetch(resolveAuthImageUrl(src), {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`Image request failed: ${response.status}`);
        }
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) {
          setBlobUrl(objectUrl);
        }
      } catch (error) {
        console.error("load auth image failed", error);
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
  }, [src]);

  if (failed) {
    return (
      <div className={`flex items-center justify-center bg-zinc-50 px-4 py-8 text-xs text-zinc-500 dark:bg-zinc-900/50 dark:text-zinc-400 ${className || ""}`}>
        图片加载失败
      </div>
    );
  }

  if (!blobUrl) {
    return (
      <div className={`flex items-center justify-center bg-zinc-50 px-4 py-8 text-xs text-zinc-500 dark:bg-zinc-900/50 dark:text-zinc-400 ${className || ""}`}>
        加载图片中...
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={blobUrl}
      alt={alt || "image"}
      className={className}
      loading={loading as "lazy" | "eager" | undefined}
    />
  );
}

function getTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "dark";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

const CodeBlock = memo(function CodeBlock({ language, value }: { language: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const [html, setHtml] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const highlightCode = async () => {
      try {
        const theme = getTheme();
        const highlighted = await codeToHtml(value, {
          lang: language || "text",
          theme: theme === "dark" ? "github-dark" : "github-light",
          transformers: [
            {
              pre(node) {
                node.properties.style = "background: transparent !important; padding: 1rem; margin: 0; border-radius: 0; font-size: 13px; line-height: 1.5;";
                node.properties.className = ["shiki-code"];
              },
              code(node) {
                node.properties.style = "font-family: var(--font-mono), ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;";
              },
            },
          ],
        });
        if (isMounted) {
          setHtml(highlighted);
          setIsLoading(false);
        }
      } catch {
        if (isMounted) {
          setHtml(`<pre style="background: transparent; padding: 1rem; margin: 0; font-size: 13px; line-height: 1.5; color: inherit;"><code>${escapeHtml(value)}</code></pre>`);
          setIsLoading(false);
        }
      }
    };

    highlightCode();

    return () => {
      isMounted = false;
    };
  }, [language, value]);

  const onCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="group relative my-4 rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 shadow-sm bg-gray-100 dark:bg-gray-800">
      <div className="flex items-center justify-between px-4 py-1.5 bg-gray-200/50 dark:bg-gray-700/50 border-b border-gray-200 dark:border-gray-700">
        <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 font-mono">
          {language || "text"}
        </span>
        <button
          onClick={onCopy}
          className="flex items-center gap-1.5 text-[10px] font-medium text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 transition-colors"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3" />
              <span>已复制</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>复制</span>
            </>
          )}
        </button>
      </div>

      <div className="overflow-x-auto text-gray-900 dark:text-gray-100">
        {isLoading ? (
          <pre className="p-4 text-sm font-mono whitespace-pre-wrap">
            {value}
          </pre>
        ) : (
          <div dangerouslySetInnerHTML={{ __html: html }} />
        )}
      </div>
    </div>
  );
});

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

const markdownComponents: Components = {
  // pre 只在块级代码（三反引号）时出现，在此拦截并渲染 CodeBlock，
  // 避免 CodeBlock(div) 被嵌入 <p> 导致 hydration 错误。
  pre({ children }: any) {
    const child = React.Children.toArray(children).find(
      (c) => React.isValidElement(c)
    ) as React.ReactElement | undefined;

    if (child) {
      const className = (child.props as any)?.className || "";
      const match = /language-(\w+)/.exec(className);
      const language = match ? match[1] : "";
      const value = String((child.props as any)?.children ?? "").replace(/\n$/, "");
      return <CodeBlock language={language} value={value} />;
    }
    return <pre>{children}</pre>;
  },

  // code 只处理行内代码（块级代码由上方 pre 组件接管）
  code({ className, children, ...props }: any) {
    return (
      <code
        className="rounded bg-gray-200 dark:bg-gray-700 px-1.5 py-0.5 font-mono text-sm font-medium text-gray-900 dark:text-gray-100"
        {...props}
      >
        {children}
      </code>
    );
  },

  a({ ...props }) {
    return (
      <a
        {...props}
        className="text-gray-700 dark:text-gray-300 underline hover:text-gray-900 dark:hover:text-gray-100"
        target="_blank"
        rel="noopener noreferrer"
      />
    );
  },

  img({ src, alt, ...props }) {
    const rawSrc = typeof src === "string" ? src : undefined;
    if (isInternalApiImage(rawSrc)) {
      return (
        <AuthImage
          src={rawSrc}
          alt={typeof alt === "string" ? alt : "image"}
          className="my-3 max-w-full h-auto rounded border border-gray-200 dark:border-gray-700"
          loading="lazy"
        />
      );
    }
    const resolved = resolveImageSrc(rawSrc);
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        {...props}
        src={resolved}
        alt={typeof alt === "string" ? alt : "image"}
        className="my-3 max-w-full h-auto rounded border border-gray-200 dark:border-gray-700"
        loading="lazy"
      />
    );
  },

  h1({ ...props }) {
    return <h1 className="mt-4 mb-2 text-2xl font-bold" {...props} />;
  },
  h2({ ...props }) {
    return <h2 className="mt-3 mb-2 text-xl font-bold" {...props} />;
  },
  h3({ ...props }) {
    return <h3 className="mt-2 mb-1 text-lg font-semibold" {...props} />;
  },

  ul({ ...props }) {
    return <ul className="my-2 ml-4 list-disc space-y-1" {...props} />;
  },
  ol({ ...props }) {
    return <ol className="my-2 ml-4 list-decimal space-y-1" {...props} />;
  },

  table({ ...props }) {
    return (
      <div className="my-2 overflow-x-auto rounded border border-gray-300 dark:border-gray-700">
        <table className="w-full border-collapse text-sm" {...props} />
      </div>
    );
  },
  th({ ...props }) {
    return (
      <th
        className="border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-2 font-semibold text-left"
        {...props}
      />
    );
  },
  td({ ...props }) {
    return (
      <td
        className="border border-gray-300 dark:border-gray-700 px-3 py-2"
        {...props}
      />
    );
  },

  blockquote({ ...props }) {
    return (
      <blockquote
        className="my-2 border-l-4 border-gray-400 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 pl-4 py-2 italic text-gray-600 dark:text-gray-400"
        {...props}
      />
    );
  },

  p({ children, ...props }: any) {
    // 如果子节点包含块级自定义组件（如 CodeBlock），改用 div 避免 <p><div> 非法嵌套
    const hasBlockChild = React.Children.toArray(children).some(
      (child) => React.isValidElement(child) && typeof child.type !== "string"
    );
    return hasBlockChild ? (
      <div className="my-3 pt-0.5 leading-7" {...props}>{children}</div>
    ) : (
      <p className="my-3 pt-0.5 leading-7" {...props}>{children}</p>
    );
  },

  hr({ ...props }) {
    return <hr className="my-3 border-gray-300 dark:border-gray-700" {...props} />;
  },
};

interface MarkdownTextProps {
  content: string;
  className?: string;
}

export const MarkdownText = memo(function MarkdownText({ content, className = "" }: MarkdownTextProps) {
  const components = useMemo(() => markdownComponents, []);

  return (
    <div className={`w-full break-words overflow-visible mt-1 ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
