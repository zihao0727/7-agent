/**
 * 会话消息与 AI SDK useChat / fillMessageParts 的兼容层。
 *
 * fillMessageParts → getMessageParts：若 message.parts 为「空数组」，仍会沿用该数组，
 * 导致忽略 message.content，历史消息在界面上变空。加载时必须不传 parts 或传入非空 parts。
 * 保存时：助手正文可能只在 parts[].text 中，需一并写入数据库 content。
 */

type PartsLike = { type?: string; text?: string }[] | undefined;

export function buildPersistableContent(message: {
  content?: unknown;
  parts?: PartsLike;
}): string {
  if (typeof message.content === "string" && message.content.length > 0) {
    return message.content;
  }
  const parts = message.parts;
  if (Array.isArray(parts)) {
    const texts = parts
      .filter(
        (p) =>
          p &&
          p.type === "text" &&
          typeof p.text === "string" &&
          p.text.length > 0,
      )
      .map((p) => p.text);
    const joined = texts.join("\n\n").trim();
    if (joined.length > 0) return joined;
  }
  if (message.content != null && typeof message.content !== "string") {
    try {
      return JSON.stringify(message.content);
    } catch {
      return String(message.content);
    }
  }
  return typeof message.content === "string" ? message.content : "";
}

/** 入库用：只保留文件名与类型，去掉 data URL，避免 Mongo 存巨型字符串。 */
export function buildPersistableAttachments(message: {
  experimental_attachments?: unknown;
}): Array<{ name: string; contentType?: string }> | undefined {
  const raw = message.experimental_attachments;
  if (!Array.isArray(raw) || raw.length === 0) return undefined;

  const out: Array<{ name: string; contentType?: string }> = [];

  for (const item of raw) {
    if (item == null || typeof item !== "object") continue;
    const a = item as Record<string, unknown>;
    let name =
      typeof a.name === "string" && a.name.length > 0 ? a.name : "";
    let contentType: string | undefined =
      typeof a.contentType === "string"
        ? a.contentType
        : typeof a.content_type === "string"
          ? (a.content_type as string)
          : undefined;
    const url = typeof a.url === "string" ? a.url : "";

    if (!name && url.startsWith("data:")) {
      const semi = url.indexOf(";");
      const mime =
        semi > 5 ? url.slice(5, semi).trim().toLowerCase() : "";
      if (mime.startsWith("image/")) {
        const sub = mime.slice("image/".length) || "png";
        name = `image.${sub.split("+")[0]}`;
      } else {
        name = "attachment";
      }
      if (!contentType && mime) contentType = mime;
    }

    if (!name && url && !url.startsWith("data:")) {
      try {
        const last = new URL(url).pathname.split("/").pop();
        if (last) name = decodeURIComponent(last);
      } catch {
        name = "attachment";
      }
    }

    if (!name) name = "attachment";
    const row: { name: string; contentType?: string } = { name };
    if (contentType) row.contentType = contentType;
    out.push(row);
  }

  return out.length > 0 ? out : undefined;
}

/**
 * 将消息的 parts 序列化为可持久化的格式（过滤掉运行时状态，保留顺序信息）。
 * 只保留 text / reasoning / tool-invocation 类型，去掉 step-start 等仅流式需要的 part。
 */
export function buildPersistableParts(message: {
  parts?: unknown;
}): Record<string, unknown>[] | undefined {
  const parts = message.parts;
  if (!Array.isArray(parts) || parts.length === 0) return undefined;

  const out: Record<string, unknown>[] = [];
  for (const p of parts) {
    if (!p || typeof p !== "object") continue;
    const part = p as Record<string, unknown>;
    const type = part.type as string | undefined;
    if (!type) continue;
    // 保留 text / reasoning / tool-invocation；跳过 step-start 等流式内部 part
    if (type === "text") {
      if (typeof part.text === "string" && part.text.length > 0) {
        out.push({ type: "text", text: part.text });
      }
    } else if (type === "reasoning") {
      const text =
        typeof part.text === "string"
          ? part.text
          : typeof part.reasoning === "string"
            ? (part.reasoning as string)
            : "";
      if (text.length > 0) {
        out.push({ type: "reasoning", text });
      }
    } else if (type === "tool-invocation") {
      // toolInvocation 子对象包含 toolCallId / toolName / args / state / result
      out.push({ ...part });
    }
  }
  return out.length > 0 ? out : undefined;
}

export function normalizeMessagesFromSessionApi(raw: unknown): unknown[] {
  if (!Array.isArray(raw)) return [];

  return raw
    .map((entry: unknown) => {
      const msg = entry as Record<string, unknown>;
      const role = msg.role as string | undefined;
      if (role !== "user" && role !== "assistant") return null;

      const id =
        msg.id != null
          ? String(msg.id)
          : `msg-${Math.random().toString(36).slice(2, 11)}`;

      let content: string;
      const c = msg.content;
      if (c == null) content = "";
      else if (typeof c === "string") content = c;
      else {
        try {
          content = JSON.stringify(c);
        } catch {
          content = String(c);
        }
      }

      const out: Record<string, unknown> = { id, role, content };

      // 保留后端时间戳，供 AI SDK 和展示层使用，确保加载历史时顺序正确
      if (msg.created_at) {
        out.createdAt = new Date(msg.created_at as string);
      }

      const ti = (msg.tool_invocations ?? msg.toolInvocations) as
        | unknown[]
        | undefined;
      if (Array.isArray(ti) && ti.length > 0) {
        out.toolInvocations = ti.map((t) => normalizeToolInvocation(t));
      }

      const ea = msg.experimental_attachments as unknown[] | undefined;
      if (Array.isArray(ea) && ea.length > 0) {
        out.experimental_attachments = ea;
      }

      const rawParts = msg.parts as unknown[] | undefined;
      if (Array.isArray(rawParts) && rawParts.length > 0) {
        out.parts = rawParts.map((p) => {
          if (!p || typeof p !== "object") return p;
          const part = p as Record<string, unknown>;
          if (part.type === "tool-invocation" && part.toolInvocation && typeof part.toolInvocation === "object") {
            return {
              ...part,
              toolInvocation: normalizeToolInvocation(part.toolInvocation),
            };
          }
          // assistant-ui / react-ai-sdk 的 convertMessage 对 reasoning 只读 part.reasoning；
          // 入库侧 buildPersistableParts 存的是 { type: "reasoning", text }，不补全会在
          // ThreadMessageLike 里对 undefined 调用 .trim 崩溃。
          if (part.type === "reasoning") {
            const reasoningStr =
              typeof part.reasoning === "string"
                ? part.reasoning
                : typeof part.text === "string"
                  ? part.text
                  : "";
            return { ...part, reasoning: reasoningStr };
          }
          if (part.type === "text") {
            const textStr = typeof part.text === "string" ? part.text : "";
            return { ...part, text: textStr };
          }
          return part;
        });
      }

      const reasoningContent = msg.reasoning_content ?? msg.reasoningContent;
      if (
        (!Array.isArray(rawParts) || rawParts.length === 0) &&
        typeof reasoningContent === "string" &&
        reasoningContent.length > 0
      ) {
        // 与上面对 reasoning part 的说明一致：convertMessage 读 part.reasoning
        out.parts = [{ type: "reasoning", text: reasoningContent, reasoning: reasoningContent }];
      }

      return out;
    })
    .filter(Boolean);
}

function normalizeToolInvocation(t: unknown): unknown {
  if (t == null || typeof t !== "object") return t;
  const x = t as Record<string, unknown>;
  const state =
    x.state ?? (x.result !== undefined ? "result" : undefined);
  return state !== undefined ? { ...x, state } : t;
}
