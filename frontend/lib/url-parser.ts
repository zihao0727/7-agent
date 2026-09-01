/**
 * URL 检测和解析工具
 * 从输入文本中提取和识别 URL，支持转换为引用形式的数据结构
 */

/**
 * 简单的 URL 正则表达式，匹配 http/https/ftp URL
 * 支持：
 *  - http://example.com
 *  - https://example.com:8080/path?query=value#hash
 *  - ftp://files.example.com
 */
const URL_REGEX =
  /\b(https?:\/\/|ftp:\/\/)[-A-Z0-9+&@#/%?=~_|!:,.;()]*[-A-Z0-9+&@#/%=~_|]/gi;

export interface DetectedUrl {
  url: string;
  title?: string;
  description?: string;
}

/**
 * 将文本按 URL 切分为交替片段，便于对链接单独做省略样式、其余原文正常展示
 */
export function splitTextByUrls(
  text: string
): Array<{ type: "text" | "url"; value: string }> {
  if (!text) return [];
  const re = new RegExp(URL_REGEX.source, "gi");
  const out: Array<{ type: "text" | "url"; value: string }> = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    const idx = m.index ?? 0;
    if (idx > last) {
      out.push({ type: "text", value: text.slice(last, idx) });
    }
    out.push({ type: "url", value: m[0] });
    last = idx + m[0].length;
  }
  if (last < text.length) {
    out.push({ type: "text", value: text.slice(last) });
  }
  return out;
}

/**
 * 从文本中检测所有 URL
 */
export function detectUrls(text: string): DetectedUrl[] {
  if (!text) return [];
  const matches = text.match(URL_REGEX);
  if (!matches) return [];
  // 去重
  return Array.from(new Set(matches)).map((url) => ({
    url,
  }));
}

/**
 * 检查文本是否以 URL 开头（用于快速判断输入意图）
 */
export function startsWithUrl(text: string): boolean {
  const trimmed = text.trim();
  return /^(https?:\/\/|ftp:\/\/)/.test(trimmed);
}

/**
 * 提取纯 URL（去掉可能附带的输入文本）
 * 例如：
 *  "https://example.com" → "https://example.com"
 *  "https://example.com 帮我分析这个页面" → "https://example.com"
 */
export function extractPrimaryUrl(text: string): string | null {
  const urls = detectUrls(text);
  return urls.length > 0 ? urls[0].url : null;
}

/**
 * 从输入中分离 URL 和其他文本内容
 */
export function separateUrlAndText(
  text: string
): { urls: DetectedUrl[]; remainingText: string } {
  const urls = detectUrls(text);
  let remainingText = text;
  for (const urlObj of urls) {
    remainingText = remainingText.replace(urlObj.url, "").trim();
  }
  return { urls, remainingText };
}

/**
 * 从 URL 提取域名/主机名（用于显示）
 */
export function extractDomain(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname || url;
  } catch {
    return url;
  }
}

/**
 * 生成 URL 引用卡片显示用的标题
 */
export function generateUrlTitle(url: string): string {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    return `${parsed.hostname}${path}`.slice(0, 50);
  } catch {
    return url.slice(0, 50);
  }
}
