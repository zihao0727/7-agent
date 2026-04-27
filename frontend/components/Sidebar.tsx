"use client";

import { useState } from "react";
import { Wrench, Zap, Server, ChevronLeft, Bot } from "lucide-react";
import { ToolsPanel } from "./panels/ToolsPanel";
import { SkillsPanel } from "./panels/SkillsPanel";
import { MCPPanel } from "./panels/MCPPanel";
import { LarkPanel } from "./panels/LarkPanel";

export type ConfigTabId = "tools" | "skills" | "mcp" | "lark";

const TABS: { id: ConfigTabId; label: string; icon: React.ElementType }[] = [
  { id: "tools",  label: "工具",   icon: Wrench },
  { id: "skills", label: "技能",   icon: Zap },
  { id: "mcp",    label: "MCP",    icon: Server },
  { id: "lark",   label: "飞书",    icon: Bot },
];

interface SidebarProps {
  isOpen: boolean;
  onToggle: (open: boolean) => void;
  activeTab?: ConfigTabId;
  onTabChange?: (tab: ConfigTabId) => void;
}

export function Sidebar({ isOpen, onToggle, activeTab = "tools", onTabChange }: SidebarProps) {
  return (
    <aside className={`flex flex-col flex-shrink-0 border-r border-gray-200 dark:border-gray-700
      bg-gray-100 dark:bg-gray-900 overflow-hidden transition-all duration-300
      ${isOpen ? "w-72" : "w-0"}`}>
      {/* 标题 */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex-shrink-0 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">配置面板</h2>
          <p className="text-sm text-gray-400 mt-0.5">管理工具、技能和 MCP 服务器</p>
        </div>
        <button
          onClick={() => onToggle(false)}
          className="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          title="隐藏配置面板"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      {/* Tab 切换栏 */}
      <div className="flex border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onTabChange?.(id)}
            className={`flex-1 flex flex-col items-center gap-0.5 py-2 text-sm transition-colors
              ${activeTab === id
                ? "text-gray-900 dark:text-gray-100 border-b-2 border-gray-900 dark:border-gray-100 -mb-px"
                : "text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-400"
              }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* 面板内容 */}
      <div className="flex-1 overflow-hidden p-3">
        {activeTab === "tools"  && <ToolsPanel />}
        {activeTab === "skills" && <SkillsPanel />}
        {activeTab === "mcp"    && <MCPPanel />}
        {activeTab === "lark"   && <LarkPanel />}
      </div>
    </aside>
  );
}
