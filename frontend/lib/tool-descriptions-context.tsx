"use client";

/**
 * 预取工具 schema 中的 description，供聊天里工具卡片展示「在做什么」而非裸工具名。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { fetchTools } from "@/lib/api";

const FALLBACK_PURPOSE = "执行辅助操作";

function condenseToolDescription(raw: string, maxLen = 120): string {
  const s = raw.trim().replace(/\s+/g, " ");
  if (!s) return "";
  const parts = s.split("。");
  const first = parts[0]?.trim() ?? "";
  let out =
    parts.length > 1 && first.length > 0 ? `${first}。` : s;
  if (out.length > maxLen) out = `${out.slice(0, maxLen - 1)}…`;
  return out;
}

const ToolDescriptionsContext = createContext<Record<string, string>>({});

export function ToolDescriptionsProvider({ children }: { children: ReactNode }) {
  const [byName, setByName] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const tools = await fetchTools();
      setByName(
        Object.fromEntries(
          tools.map((t) => [t.name, t.description?.trim() ?? ""])
        )
      );
    } catch {
      /* 离线或 API 不可用时保留空表，由展示层回退 */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <ToolDescriptionsContext.Provider value={byName}>
      {children}
    </ToolDescriptionsContext.Provider>
  );
}

export function useToolPurposeLine(toolName: string): string {
  const byName = useContext(ToolDescriptionsContext);
  return useMemo(() => {
    const d = byName[toolName]?.trim();
    if (!d) return FALLBACK_PURPOSE;
    const line = condenseToolDescription(d);
    return line || FALLBACK_PURPOSE;
  }, [byName, toolName]);
}
