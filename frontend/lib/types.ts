// ── 工具 ─────────────────────────────────────────────────────────────────────

export interface ToolInfo {
  name: string;
  description: string;
  enabled: boolean;
  input_schema: Record<string, unknown>;
}

// ── Skill ─────────────────────────────────────────────────────────────────────

export interface SkillInfo {
  name: string;
  description: string;
  active: boolean;
  tools: string[];
  permissions?: {
    capabilities: string[];
    access: string[];
    risk_level: "low" | "medium" | "high" | "unknown";
    requires_confirmation: boolean;
    requires_confirmation_for: string[];
  };
}

// ── MCP 服务器 ────────────────────────────────────────────────────────────────

export type MCPTransport = "stdio" | "sse";

export interface MCPServerInfo {
  id: string;
  name: string;
  transport: MCPTransport;
  command: string;
  args: string[];
  url: string;
  tool_names: string[];
  status: "connected" | "error" | "loading";
}

export interface MCPAddPayload {
  name: string;
  transport: MCPTransport;
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
}

export interface LarkAccountInfo {
  id: number;
  name: string;
  app_id: string;
  brand: "feishu" | "lark";
  profile_name: string;
  is_default: boolean;
}

export type MemoryKind =
  | "preference"
  | "profile"
  | "project"
  | "contact"
  | "format"
  | "taboo"
  | "instruction"
  | "fact";

export interface MemoryInfo {
  id: string;
  kind: MemoryKind;
  content: string;
  importance: number;
  confidence: number;
  status: "active" | "pending" | "archived" | "deleted";
  needs_confirmation?: boolean;
  source_session_id?: string | null;
  source_message_ids?: string[];
  created_at: string;
  updated_at: string;
  last_used_at?: string | null;
}

export interface KnowledgeDocumentInfo {
  id: string;
  title: string;
  source_type: "file" | "url" | "chat" | string;
  filename?: string | null;
  content_type?: string | null;
  url?: string | null;
  session_id?: string | null;
  status: string;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeSearchResult {
  document_id: string;
  document_title: string;
  source_type: string;
  url?: string | null;
  chunk_index: number;
  source_label: string;
  score: number;
  text: string;
}

export type ScheduledTaskType = "once" | "interval" | "daily";
export type ScheduledTaskStatus = "enabled" | "paused" | "disabled" | "running" | "completed" | "failed";

export interface ScheduledTaskInfo {
  id: string;
  user_id: number;
  title: string;
  prompt: string;
  schedule_type: ScheduledTaskType;
  run_at?: string | null;
  interval_minutes?: number | null;
  time_of_day?: string | null;
  timezone_offset_minutes?: number | null;
  model: string;
  status: ScheduledTaskStatus;
  workflow_status?: "waiting" | "paused" | "running" | "retrying" | "completed" | "failed";
  steps?: Array<{ name: string; status: string }>;
  retry_count?: number;
  max_retries?: number;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_session_id?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
}
