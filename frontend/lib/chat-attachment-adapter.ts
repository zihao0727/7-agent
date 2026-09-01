/**
 * 自定义附件适配器：
 * - 在官方 vercelAttachmentAdapter 基础上扩大 accept
 * - 支持 Word (.doc/.docx)、PDF (.pdf)、图片、TXT 等文件类型
 * - 发送前把文件读成 data URL（experimental_attachments），由后端处理：
 *   Word → 落盘 + 路径注入
 *   PDF  → 文本提取注入（Kimi 用 Files API，DeepSeek 用 pypdf）
 *   TXT  → 文本内容注入
 *   图片 → 保留 data URL 用于 vision
 */

import type { AttachmentAdapter } from "@assistant-ui/react";
import { generateId } from "@ai-sdk/ui-utils";

/** 所有支持的文件类型（MIME + 扩展名后缀） */
export const ACCEPTED_FILE_TYPES =
  // 图片
  "image/jpeg,image/jpg,image/png,image/gif,image/webp,image/bmp," +
  // Word
  "application/msword," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  // Excel
  "application/vnd.ms-excel," +
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet," +
  // PDF
  "application/pdf," +
  // 纯文本
  "text/plain,text/markdown,text/csv,text/xml," +
  // 扩展名（兜底）
  ".doc,.docx,.xls,.xlsx,.pdf,.txt,.md,.csv,.jpg,.jpeg,.png,.gif,.webp,.bmp";

export const chatAttachmentAdapter: AttachmentAdapter = {
  accept: ACCEPTED_FILE_TYPES,

  async add({ file }) {
    return {
      id: generateId(),
      type: "file",
      name: file.name,
      file,
      contentType: file.type,
      content: [],
      status: { type: "requires-action", reason: "composer-send" },
    };
  },

  async send(attachment) {
    return {
      ...attachment,
      status: { type: "complete" },
      content: [],
    };
  },

  async remove() {
    /* noop */
  },
};
