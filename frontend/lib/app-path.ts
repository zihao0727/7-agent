/** 从 `/app` 或 `/app/会话id` 解析当前会话 id（供 App Shell 同步高亮与列表） */
export function sessionIdFromAppPath(pathname: string): string | undefined {
  const path =
    (pathname.split("?")[0] ?? "/").replace(/\/+$/, "") || "/";
  if (path === "/app") return undefined;
  const prefix = "/app/";
  if (!path.startsWith(prefix)) return undefined;
  const rest = path.slice(prefix.length);
  if (!rest || rest.includes("/")) return undefined;
  try {
    return decodeURIComponent(rest);
  } catch {
    return undefined;
  }
}
