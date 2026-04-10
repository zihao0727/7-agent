"use client";

/**
 * ArchiveDownloadHandler —— 检测并处理档案下载
 * 当 AI 返回下载 URL 时，自动检测并提供下载按钮
 */

import { FC, useEffect, useState } from "react";
import { Download } from "lucide-react";

interface ArchiveDownloadInfo {
  filename: string;
  content: string; // URL
}

function extractArchiveDownloadInfo(text: string): ArchiveDownloadInfo | null {
  try {
    // 如果返回的是 JSON 字符串，尝试解析 presigned_url
    const jsonUrlMatch = text.match(/\{[\s\S]*?"presigned_url"\s*:\s*"(https?:\/\/[^"\\s]+)"[\s\S]*?\}/i);
    if (jsonUrlMatch) {
      const url = jsonUrlMatch[1].trim();
      let filename = "download.zip";
      try { filename = decodeURIComponent(new URL(url).pathname.split('/').pop() || filename); } catch (e) {}
      console.log("[ArchiveDownloadHandler] 检测到 presigned_url (JSON):", url);
      return { filename, content: url };
    }

    // key:value 样式的 presigned_url: https://...
    const kvUrlMatch = text.match(/presigned_url\s*[:=]\s*(https?:\/\/\S+)/i) || text.match(/presigned-url\s*[:=]\s*(https?:\/\/\S+)/i);
    if (kvUrlMatch) {
      const url = kvUrlMatch[1].trim().replace(/\)$/, '');
      let filename = "download.zip";
      try { filename = decodeURIComponent(new URL(url).pathname.split('/').pop() || filename); } catch (e) {}
      console.log("[ArchiveDownloadHandler] 检测到 presigned_url (kv):", url);
      return { filename, content: url };
    }

    // 如果文本中存在可点击的 http(s) 链接，优先使用第一个链接
    const urlOnlyMatch = text.match(/(https?:\/\/[^\s\n]+)/i);
    if (urlOnlyMatch) {
      const url = urlOnlyMatch[1].trim();
      // 但如果链接看起来像不是下载链接（如指向帮助页面），仍然回退到原先逻辑
      if (/\.(zip|gz|tgz|tar|7z)(\?|$)/i.test(url) || /download/i.test(url)) {
        let filename = "download.zip";
        try { filename = decodeURIComponent(new URL(url).pathname.split('/').pop() || filename); } catch (e) {}
        console.log("[ArchiveDownloadHandler] 检测到直接 URL 链接:", url);
        return { filename, content: url };
      }
    }
  } catch (err) {
    console.warn("[ArchiveDownloadHandler] presigned_url 解析异常:", err);
  }

  console.log("[ArchiveDownloadHandler] 未检测到下载 URL");
  return null;
}

function downloadFile(
  filename: string,
  base64OrUrl: string
): void {
  try {
    // 如果是 URL，直接打开或触发下载
    if (/^https?:\/\//i.test(base64OrUrl)) {
      console.log("[ArchiveDownloadHandler] 触发 URL 下载:", base64OrUrl);
      // 创建链接并触发
      const a = document.createElement('a');
      a.href = base64OrUrl;
      a.target = '_blank';
      // 尝试设置 download 属性以便直接保存文件（部分跨域链接可能被忽略）
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        console.log('[ArchiveDownloadHandler] 下载触发完成');
      }, 100);
      return;
    }

    console.error("[ArchiveDownloadHandler] 无效的下载内容（既不是 URL）");
    alert("无效的下载内容");
  } catch (error) {
    console.error("[ArchiveDownloadHandler] 下载失败:", error);
    alert(`下载失败: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export const ArchiveDownloadHandler: FC<{ text: string }> = ({ text }) => {
  const [archiveInfo, setArchiveInfo] = useState<ArchiveDownloadInfo | null>(
    null
  );

  useEffect(() => {
    console.log("[ArchiveDownloadHandler] 接收到新文本，长度:", text.length);
    const info = extractArchiveDownloadInfo(text);
    setArchiveInfo(info);
  }, [text]);

  if (!archiveInfo) {
    return null;
  }

  return (
    <div className="my-3 flex items-center gap-3 rounded-lg border border-green-300 bg-green-50 dark:border-green-800 dark:bg-green-950 p-3">
      <Download className="h-5 w-5 text-green-600 dark:text-green-400 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-green-900 dark:text-green-100">
          {archiveInfo.filename}
        </p>
      </div>
      <button
        onClick={() => {
          console.log("[ArchiveDownloadHandler] 用户点击下载按钮");
          downloadFile(archiveInfo.filename, archiveInfo.content);
        }}
        className="flex-shrink-0 px-3 py-1.5 rounded bg-green-600 hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600
          text-white text-xs font-medium transition-colors"
      >
        下载
      </button>
    </div>
  );
};
