"use client";

import {
  clearStoredAccessToken,
  getStoredAccessToken,
  type AuthResult,
  type AuthUser,
} from "./auth";
import type {
  MCPAddPayload,
  MCPServerInfo,
  LarkAccountInfo,
  KnowledgeDocumentInfo,
  KnowledgeSearchResult,
  MemoryInfo,
  MemoryKind,
  ScheduledTaskInfo,
  ScheduledTaskType,
  SkillInfo,
  ToolInfo,
} from "./types";
import { getApiBaseUrl } from "./runtime-config";

function notifyAuthExpired(): void {
  clearStoredAccessToken();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("sevn:auth-expired"));
  }
}

function normalizeApiError(path: string, status: number, body: string): never {
  let detail = body.trim();
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      detail = parsed.detail;
    }
  } catch {
    // Keep the raw body for non-JSON error responses.
  }

  if (
    detail ===
    "Register code email delivery failed. Please check SMTP settings or try again later."
  ) {
    detail = "验证码邮件发送失败，请检查 SMTP 配置或稍后再试";
  }

  throw new Error(detail || `API ${path} failed (${status})`);
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  options?: { auth?: boolean }
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (options?.auth !== false) {
    const token = getStoredAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
  });

  if (res.status === 401 && options?.auth !== false) {
    notifyAuthExpired();
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    normalizeApiError(path, res.status, text);
  }

  return res.json() as Promise<T>;
}

export function buildApiUrl(path: string): string {
  return `${getApiBaseUrl()}${path}`;
}

export interface SessionInfo {
  id: string;
  title: string;
  description?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface SessionDetail {
  id: string;
  title: string;
  description?: string;
  messages: any[];
  created_at: string;
  updated_at: string;
}

export async function sendRegisterCode(email: string): Promise<{ ok: boolean }> {
  return apiFetch(
    "/api/auth/send-register-code",
    {
      method: "POST",
      body: JSON.stringify({ email }),
    },
    { auth: false }
  );
}

export async function registerUser(payload: {
  email: string;
  password: string;
  code: string;
  display_name?: string;
}): Promise<AuthResult> {
  return apiFetch(
    "/api/auth/register",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    { auth: false }
  );
}

export async function loginUser(payload: {
  email: string;
  password: string;
}): Promise<AuthResult> {
  return apiFetch(
    "/api/auth/login",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    { auth: false }
  );
}

export async function fetchCurrentUser(): Promise<{ user: AuthUser }> {
  return apiFetch("/api/auth/me");
}

export async function updateCurrentUserAvatar(
  avatarUrl: string | null
): Promise<{ user: AuthUser }> {
  return apiFetch("/api/auth/me/avatar", {
    method: "PATCH",
    body: JSON.stringify({ avatar_url: avatarUrl }),
  });
}

export async function logoutUser(): Promise<{ ok: boolean }> {
  return apiFetch("/api/auth/logout", { method: "POST" });
}

export async function fetchTools(): Promise<ToolInfo[]> {
  const data = await apiFetch<{ tools: ToolInfo[] }>("/api/tools");
  return data.tools;
}

export async function toggleTool(name: string, enabled: boolean): Promise<void> {
  await apiFetch(`/api/tools/${encodeURIComponent(name)}/toggle`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}

export async function fetchSkills(): Promise<SkillInfo[]> {
  const data = await apiFetch<{ skills: SkillInfo[] }>("/api/skills");
  return data.skills;
}

export async function activateSkill(name: string): Promise<void> {
  await apiFetch(`/api/skills/${encodeURIComponent(name)}/activate`, {
    method: "POST",
  });
}

export async function deactivateSkill(name: string): Promise<void> {
  await apiFetch(`/api/skills/${encodeURIComponent(name)}/deactivate`, {
    method: "POST",
  });
}

export async function updateSkillPermissions(
  name: string,
  payload: {
    risk_level?: "low" | "medium" | "high" | "unknown";
    requires_confirmation?: boolean;
  }
): Promise<SkillInfo["permissions"]> {
  const data = await apiFetch<{ permissions: SkillInfo["permissions"] }>(
    `/api/skills/${encodeURIComponent(name)}/permissions`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    }
  );
  return data.permissions;
}

export async function loadSkillFromMd(
  skillMdPath: string,
  name?: string
): Promise<{ name: string; description: string; active: boolean }> {
  return apiFetch("/api/skills/load", {
    method: "POST",
    body: JSON.stringify({ skill_md_path: skillMdPath, name }),
  });
}

export async function fetchMCPServers(): Promise<MCPServerInfo[]> {
  const data = await apiFetch<{ servers: MCPServerInfo[] }>("/api/mcp");
  return data.servers;
}

export async function addMCPServer(payload: MCPAddPayload): Promise<MCPServerInfo> {
  return apiFetch("/api/mcp", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function removeMCPServer(id: string): Promise<void> {
  await apiFetch(`/api/mcp/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function fetchLarkAccounts(): Promise<LarkAccountInfo[]> {
  const data = await apiFetch<{ accounts: LarkAccountInfo[] }>("/api/lark/accounts");
  return data.accounts;
}

export async function saveLarkAccount(payload: {
  name?: string;
  app_id: string;
  app_secret: string;
  brand?: "feishu" | "lark";
  make_default?: boolean;
  configure_cli?: boolean;
}): Promise<{ account: LarkAccountInfo; configure?: unknown }> {
  return apiFetch("/api/lark/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteLarkAccount(id: number): Promise<void> {
  await apiFetch(`/api/lark/accounts/${encodeURIComponent(String(id))}`, {
    method: "DELETE",
  });
}

export async function startLarkAuthLogin(
  id: number,
  payload: {
    recommend?: boolean;
    domains?: string[];
    scopes?: string[];
    no_wait?: boolean;
  } = {}
): Promise<unknown> {
  return apiFetch(`/api/lark/accounts/${encodeURIComponent(String(id))}/auth-login`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function completeLarkAuth(
  id: number,
  deviceCode: string
): Promise<unknown> {
  return apiFetch(`/api/lark/accounts/${encodeURIComponent(String(id))}/auth-complete`, {
    method: "POST",
    body: JSON.stringify({ device_code: deviceCode }),
  });
}

export async function fetchLarkAuthStatus(id: number): Promise<unknown> {
  return apiFetch(`/api/lark/accounts/${encodeURIComponent(String(id))}/status`);
}

export async function runLarkCommand(
  id: number,
  payload: {
    command: string[];
    identity?: "bot" | "user" | "auto";
    add_format?: boolean;
  }
): Promise<unknown> {
  return apiFetch(`/api/lark/accounts/${encodeURIComponent(String(id))}/command`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchSessions(): Promise<SessionInfo[]> {
  return apiFetch("/api/sessions");
}

export async function createSession(
  title: string,
  description?: string
): Promise<{ id: string; title: string }> {
  return apiFetch("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title, description }),
  });
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  return apiFetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export async function addMessageToSession(
  sessionId: string,
  role: string,
  content: string,
  tool_invocations?: any[],
  experimental_attachments?: Array<{ name: string; contentType?: string }>,
  parts?: any[],
  reasoning_content?: string
): Promise<{ id: string; created_at: string }> {
  return apiFetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    body: JSON.stringify({
      role,
      content,
      tool_invocations,
      ...(reasoning_content ? { reasoning_content } : {}),
      ...(parts?.length ? { parts } : {}),
      ...(experimental_attachments?.length ? { experimental_attachments } : {}),
    }),
  });
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export async function summarizeSession(sessionId: string): Promise<{ title: string }> {
  return apiFetch(`/api/sessions/${encodeURIComponent(sessionId)}/summarize`, {
    method: "POST",
  });
}

export function notifySessionsListRefresh(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("sevn:sessions-refresh"));
}

// ---- Chat busy state (防止回复中切换会话) ----
let _chatBusy = false;

export function setChatBusy(busy: boolean): void {
  if (_chatBusy === busy) return;
  _chatBusy = busy;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("sevn:chat-busy", { detail: busy }));
  }
}

export function isChatBusy(): boolean {
  return _chatBusy;
}

export async function deleteMessagesAfter(
  sessionId: string,
  messageIndex: number
): Promise<{ deleted_count: number }> {
  return apiFetch(
    `/api/sessions/${encodeURIComponent(sessionId)}/messages/${messageIndex}`,
    { method: "DELETE" }
  );
}

export async function fetchMemories(): Promise<MemoryInfo[]> {
  const data = await apiFetch<{ memories: MemoryInfo[] }>("/api/memories");
  return data.memories;
}

export async function fetchKnowledgeDocuments(): Promise<KnowledgeDocumentInfo[]> {
  const data = await apiFetch<{ documents: KnowledgeDocumentInfo[] }>("/api/knowledge/documents");
  return data.documents;
}

export async function uploadKnowledgeFiles(files: File[]): Promise<KnowledgeDocumentInfo[]> {
  const body = new FormData();
  for (const file of files) {
    const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
    body.append("files", file, relativePath || file.name);
  }
  const data = await apiFetch<{ documents: KnowledgeDocumentInfo[] }>(
    "/api/knowledge/upload",
    { method: "POST", body }
  );
  return data.documents;
}

export async function ingestKnowledgeUrl(url: string): Promise<KnowledgeDocumentInfo> {
  const data = await apiFetch<{ document: KnowledgeDocumentInfo }>("/api/knowledge/url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
  return data.document;
}

export async function ingestKnowledgeSession(sessionId: string): Promise<KnowledgeDocumentInfo> {
  const data = await apiFetch<{ document: KnowledgeDocumentInfo }>("/api/knowledge/session", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  return data.document;
}

export async function searchKnowledge(
  query: string,
  limit = 6
): Promise<KnowledgeSearchResult[]> {
  const data = await apiFetch<{ results: KnowledgeSearchResult[] }>("/api/knowledge/search", {
    method: "POST",
    body: JSON.stringify({ query, limit }),
  });
  return data.results;
}

export async function deleteKnowledgeDocument(id: string): Promise<void> {
  await apiFetch(`/api/knowledge/documents/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function createMemory(payload: {
  content: string;
  kind: MemoryKind;
  importance?: number;
  confidence?: number;
  needs_confirmation?: boolean;
}): Promise<MemoryInfo> {
  const data = await apiFetch<{ memory: MemoryInfo }>("/api/memories", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data.memory;
}

export async function updateMemory(
  id: string,
  payload: Partial<Pick<MemoryInfo, "content" | "kind" | "importance" | "confidence" | "status">>
): Promise<MemoryInfo> {
  const data = await apiFetch<{ memory: MemoryInfo }>(
    `/api/memories/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    }
  );
  return data.memory;
}

export async function deleteMemory(id: string): Promise<void> {
  await apiFetch(`/api/memories/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function confirmMemory(id: string, approved: boolean): Promise<MemoryInfo> {
  const data = await apiFetch<{ memory: MemoryInfo }>(
    `/api/memories/${encodeURIComponent(id)}/confirm`,
    {
      method: "POST",
      body: JSON.stringify({ approved }),
    }
  );
  return data.memory;
}

export async function fetchScheduledTasks(): Promise<ScheduledTaskInfo[]> {
  const data = await apiFetch<{ tasks: ScheduledTaskInfo[] }>("/api/scheduled-tasks");
  return data.tasks;
}

export async function createScheduledTask(payload: {
  title: string;
  prompt: string;
  schedule_type: ScheduledTaskType;
  run_at?: string | null;
  interval_minutes?: number | null;
  time_of_day?: string | null;
  timezone_offset_minutes?: number | null;
  model?: string;
  max_retries?: number;
}): Promise<ScheduledTaskInfo> {
  const data = await apiFetch<{ task: ScheduledTaskInfo }>("/api/scheduled-tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data.task;
}

export async function updateScheduledTask(
  id: string,
  enabled: boolean
): Promise<ScheduledTaskInfo> {
  const data = await apiFetch<{ task: ScheduledTaskInfo }>(
    `/api/scheduled-tasks/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }
  );
  return data.task;
}

export async function deleteScheduledTask(id: string): Promise<void> {
  await apiFetch(`/api/scheduled-tasks/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function resolvePermissionRequest(
  id: string,
  approved: boolean
): Promise<unknown> {
  return apiFetch(`/api/permissions/${encodeURIComponent(id)}/resolve`, {
    method: "POST",
    body: JSON.stringify({ approved }),
  });
}

export async function fetchHealth(): Promise<{
  status: string;
  tools: number;
  skills: number;
  mcp_servers: number;
}> {
  return apiFetch("/api/health", undefined, { auth: false });
}
