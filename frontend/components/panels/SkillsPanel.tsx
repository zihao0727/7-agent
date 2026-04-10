"use client";

import { useEffect, useState, useCallback } from "react";
import { Zap, RefreshCw, Upload } from "lucide-react";
import { fetchSkills, activateSkill, deactivateSkill, loadSkillFromMd } from "@/lib/api";
import type { SkillInfo } from "@/lib/types";

export function SkillsPanel() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mdPath, setMdPath] = useState("");
  const [loadingMd, setLoadingMd] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSkills(await fetchSkills());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggle = async (skill: SkillInfo) => {
    setBusy(skill.name);
    setError(null);
    try {
      if (skill.active) {
        await deactivateSkill(skill.name);
      } else {
        await activateSkill(skill.name);
      }
      setSkills((prev) =>
        prev.map((s) => s.name === skill.name ? { ...s, active: !skill.active } : s)
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(null);
    }
  };

  const handleLoadMd = async () => {
    if (!mdPath.trim()) return;
    setLoadingMd(true);
    setError(null);
    try {
      await loadSkillFromMd(mdPath.trim());
      setMdPath("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoadingMd(false);
    }
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-medium text-gray-500 uppercase tracking-wide">
          <Zap className="h-3.5 w-3.5" />
          技能包
          <span className="ml-1 rounded-full bg-gray-200/90 dark:bg-gray-700 px-1.5 py-0.5 text-xs">
            {skills.filter((s) => s.active).length}/{skills.length}
          </span>
        </div>
        <button
          onClick={load}
          className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600"
          title="刷新"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* 从 SKILL.md 加载 */}
      <div className="flex gap-1.5">
        <input
          type="text"
          value={mdPath}
          onChange={(e) => setMdPath(e.target.value)}
          placeholder="SKILL.md 路径"
          className="flex-1 text-xs px-2 py-1.5 rounded border border-gray-200 dark:border-gray-600
            bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100
            placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-gray-500 dark:focus:ring-gray-400"
          onKeyDown={(e) => e.key === "Enter" && handleLoadMd()}
        />
        <button
          onClick={handleLoadMd}
          disabled={loadingMd || !mdPath.trim()}
          className="px-2 py-1.5 rounded bg-black hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-200 disabled:opacity-50
            text-white dark:text-black text-xs flex items-center gap-1 whitespace-nowrap"
        >
          <Upload className="h-3 w-3" />
          加载
        </button>
      </div>

      {error && <p className="text-xs text-red-500 px-1">{error}</p>}

      {loading && skills.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <RefreshCw className="h-4 w-4 animate-spin text-gray-400" />
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto space-y-2 pr-0.5">
          {skills.map((skill) => (
            <li
              key={skill.name}
              className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-200/30 dark:bg-gray-800/50 p-2.5 space-y-1.5"
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`text-xs font-semibold
                  ${skill.active ? "text-gray-900 dark:text-gray-100" : "text-gray-700 dark:text-gray-300"}`}>
                  {skill.name}
                </span>
                <button
                  onClick={() => handleToggle(skill)}
                  disabled={busy === skill.name}
                  className={`flex-shrink-0 w-8 h-4 rounded-full transition-colors relative
                    ${skill.active ? "bg-gray-900 dark:bg-gray-100" : "bg-gray-200 dark:bg-gray-600"}
                    ${busy === skill.name ? "opacity-50 cursor-wait" : "cursor-pointer"}`}
                >
                  <span
                    className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform
                      ${skill.active ? "left-4" : "left-0.5"}`}
                  />
                </button>
              </div>
              {skill.description && (
                <p className="text-xs text-gray-400 leading-relaxed">{skill.description}</p>
              )}
              {skill.tools.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {skill.tools.map((t) => (
                    <span
                      key={t}
                      className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400
                        px-1.5 py-0.5 rounded font-mono"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </li>
          ))}
          {skills.length === 0 && !loading && (
            <li className="text-xs text-gray-400 text-center py-4">
              暂无注册技能包，可加载 SKILL.md 添加
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
