"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bot,
  CheckCircle2,
  Eye,
  EyeOff,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import {
  completeLarkAuth,
  deleteLarkAccount,
  fetchLarkAccounts,
  fetchLarkAuthStatus,
  saveLarkAccount,
  startLarkAuthLogin,
} from "@/lib/api";
import type { LarkAccountInfo } from "@/lib/types";
import { LARK_DOMAINS } from "@/lib/lark-actions";
import { runLarkCommand } from "@/lib/api";

type NoticeTone = "success" | "error" | "muted";

function findUrl(value: unknown): string | null {
  if (typeof value === "string") {
    return value.match(/https?:\/\/[^\s"'<>]+/)?.[0] ?? null;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findUrl(item);
      if (found) return found;
    }
  }
  if (value && typeof value === "object") {
    for (const item of Object.values(value as Record<string, unknown>)) {
      const found = findUrl(item);
      if (found) return found;
    }
  }
  return null;
}

function findStringField(value: unknown, field: string): string | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    if (typeof record[field] === "string") return record[field];
    for (const item of Object.values(record)) {
      const found = findStringField(item, field);
      if (found) return found;
    }
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findStringField(item, field);
      if (found) return found;
    }
  }
  return null;
}

function formatValue(value: string | boolean): string {
  return typeof value === "boolean" ? (value ? "true" : "false") : value;
}

function normalizePayload(result: unknown): string {
  if (typeof result === "string") return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}

function LarkActionCard({
  action,
  accountId,
}: {
  action: (typeof LARK_DOMAINS)[number]["actions"][number];
  accountId: number | null;
}) {
  const [values, setValues] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(
      action.fields.map((field) => [
        field.key,
        field.defaultValue ?? (field.type === "checkbox" ? false : ""),
      ])
    )
  );
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState<string | null>(null);

  useEffect(() => {
    setValues(
      Object.fromEntries(
        action.fields.map((field) => [
          field.key,
          field.defaultValue ?? (field.type === "checkbox" ? false : ""),
        ])
      )
    );
    setError(null);
    setOutput(null);
  }, [action]);

  const commandPreview = useMemo(() => {
    try {
      return action.buildCommand(values).join(" ");
    } catch {
      return "";
    }
  }, [action, values]);

  const handleChange = (key: string, value: string | boolean) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleRun = async () => {
    if (!accountId) {
      setError("请先选择飞书账号");
      return;
    }
    for (const field of action.fields) {
      if (field.required) {
        const current = values[field.key];
        if (
          (typeof current === "string" && !current.trim()) ||
          (typeof current === "boolean" && !current)
        ) {
          setError(`请填写 ${field.label}`);
          return;
        }
      }
    }
    setRunning(true);
    setError(null);
    setOutput(null);
    try {
      const command = action.buildCommand(values);
      const result = await runLarkCommand(accountId, {
        command,
        identity: action.identity,
        add_format: false,
      });
      setOutput(normalizePayload(result));
    } catch (e) {
      setError(e instanceof Error ? e.message : "执行失败");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{action.label}</div>
          <div className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{action.description}</div>
        </div>
        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          {action.identity}
        </span>
      </div>

      <div className="mt-3 grid gap-2">
        {action.fields.map((field) => {
          const value = values[field.key];
          if (field.type === "textarea") {
            return (
              <label key={field.key} className="grid gap-1">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  {field.label}
                </span>
                <textarea
                  value={formatValue(value)}
                  onChange={(event) => handleChange(field.key, event.target.value)}
                  placeholder={field.placeholder}
                  className="min-h-20 rounded-md border border-gray-200 bg-gray-50 px-2 py-2 text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-gray-400 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
                />
              </label>
            );
          }
          if (field.type === "select") {
            return (
              <label key={field.key} className="grid gap-1">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  {field.label}
                </span>
                <select
                  value={formatValue(value)}
                  onChange={(event) => handleChange(field.key, event.target.value)}
                  className="h-9 rounded-md border border-gray-200 bg-gray-50 px-2 text-sm text-gray-900 outline-none focus:border-gray-400 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
                >
                  {field.options?.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            );
          }
          if (field.type === "checkbox") {
            return (
              <label
                key={field.key}
                className="flex items-center justify-between gap-3 rounded-md border border-gray-200 bg-gray-50 px-2 py-2 dark:border-gray-700 dark:bg-gray-950"
              >
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  {field.label}
                </span>
                <input
                  type="checkbox"
                  checked={Boolean(value)}
                  onChange={(event) => handleChange(field.key, event.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-gray-900"
                />
              </label>
            );
          }
          return (
            <label key={field.key} className="grid gap-1">
              <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                {field.label}
              </span>
              <input
                type={field.type === "number" ? "number" : "text"}
                value={formatValue(value)}
                onChange={(event) => handleChange(field.key, event.target.value)}
                placeholder={field.placeholder}
                className="h-9 rounded-md border border-gray-200 bg-gray-50 px-2 text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-gray-400 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
              />
            </label>
          );
        })}
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => void handleRun()}
          disabled={running || !accountId}
          className="inline-flex items-center gap-1.5 rounded-md bg-gray-950 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-gray-200"
        >
          <ShieldCheck className="h-3.5 w-3.5" />
          {running ? "执行中" : "运行"}
        </button>
        {commandPreview && (
          <span className="min-w-0 truncate font-mono text-xs text-gray-400 dark:text-gray-500">
            {commandPreview}
          </span>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      {output && (
        <pre className="mt-2 max-h-48 overflow-auto rounded-md bg-gray-950 p-2 text-xs leading-5 text-gray-100 dark:bg-black">
          {output}
        </pre>
      )}
    </div>
  );
}

function LarkActionBoard({ accounts }: { accounts: LarkAccountInfo[] }) {
  const defaultAccount = useMemo(
    () => accounts.find((item) => item.is_default)?.id ?? accounts[0]?.id ?? null,
    [accounts]
  );
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(defaultAccount);
  const [activeDomainId, setActiveDomainId] = useState(LARK_DOMAINS[0]?.id ?? "docs");

  useEffect(() => {
    setSelectedAccountId((current) =>
      current && accounts.some((item) => item.id === current) ? current : defaultAccount
    );
  }, [accounts, defaultAccount]);

  const activeDomain = useMemo(
    () => LARK_DOMAINS.find((item) => item.id === activeDomainId) ?? LARK_DOMAINS[0],
    [activeDomainId]
  );

  return (
    <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">高频入口</div>
          <div className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            这些入口直接生成 lark-cli 命令，不需要记命令参数。
          </div>
        </div>

        <select
          value={selectedAccountId ?? ""}
          onChange={(event) =>
            setSelectedAccountId(event.target.value ? Number(event.target.value) : null)
          }
          className="h-9 min-w-40 rounded-md border border-gray-200 bg-gray-50 px-2 text-sm text-gray-900 outline-none focus:border-gray-400 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
        >
          <option value="">选择账号</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {LARK_DOMAINS.map((domain) => (
          <button
            key={domain.id}
            type="button"
            onClick={() => setActiveDomainId(domain.id)}
            className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-sm transition-colors ${
              activeDomain?.id === domain.id
                ? "bg-gray-950 text-white dark:bg-white dark:text-black"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
            }`}
          >
            <span className="text-xs uppercase tracking-wide">{domain.label}</span>
          </button>
        ))}
      </div>

      {activeDomain && (
        <div className="grid gap-3">
          {activeDomain.actions.map((action) => (
            <LarkActionCard
              key={action.id}
              action={action}
              accountId={selectedAccountId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function LarkPanel() {
  const [accounts, setAccounts] = useState<LarkAccountInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeTone, setNoticeTone] = useState<NoticeTone>("muted");
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [deviceCode, setDeviceCode] = useState<string | null>(null);
  const [authAccountId, setAuthAccountId] = useState<number | null>(null);
  const [form, setForm] = useState({
    name: "default",
    app_id: "",
    app_secret: "",
  });

  const showNotice = useCallback((text: string, tone: NoticeTone = "muted") => {
    setNotice(text);
    setNoticeTone(tone);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setNotice(null);
    try {
      setAccounts(await fetchLarkAccounts());
    } catch {
      showNotice("暂时无法读取飞书账户。", "error");
    } finally {
      setLoading(false);
    }
  }, [showNotice]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async () => {
    if (!form.app_id.trim() || !form.app_secret.trim()) {
      showNotice("请填写 App ID 和 App Secret。", "error");
      return;
    }

    setSaving(true);
    setAuthUrl(null);
    setDeviceCode(null);
    setAuthAccountId(null);
    showNotice("正在写入飞书配置...");
    try {
      await saveLarkAccount({
        name: form.name.trim() || "default",
        app_id: form.app_id.trim(),
        app_secret: form.app_secret.trim(),
        brand: "feishu",
        make_default: true,
        configure_cli: true,
      });
      setForm((prev) => ({ ...prev, app_secret: "" }));
      await load();
      showNotice("绑定成功，可以继续授权。", "success");
    } catch {
      showNotice("绑定没有完成，请检查 App ID / App Secret 后重试。", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleAuth = async (account: LarkAccountInfo) => {
    setBusyId(account.id);
    setAuthUrl(null);
    setDeviceCode(null);
    setAuthAccountId(account.id);
    showNotice("正在准备飞书授权...");
    try {
      const result = await startLarkAuthLogin(account.id, {
        recommend: true,
        no_wait: true,
      });
      const url = findUrl(result);
      const code = findStringField(result, "device_code");
      setAuthUrl(url);
      setDeviceCode(code);
      showNotice(url ? "授权链接已生成，完成后回到这里确认。" : "授权已发起，请按飞书提示完成。", "success");
    } catch {
      showNotice("授权没有启动，请稍后重试。", "error");
    } finally {
      setBusyId(null);
    }
  };

  const handleCompleteAuth = async () => {
    if (!authAccountId || !deviceCode) {
      showNotice("请先点击授权生成授权链接。", "error");
      return;
    }
    setBusyId(authAccountId);
    showNotice("正在确认授权...");
    try {
      await completeLarkAuth(authAccountId, deviceCode);
      setAuthUrl(null);
      setDeviceCode(null);
      setAuthAccountId(null);
      showNotice("授权完成，飞书连接可用了。", "success");
    } catch {
      showNotice("还没有检测到授权完成，请稍后再试。", "error");
    } finally {
      setBusyId(null);
    }
  };

  const handleStatus = async (account: LarkAccountInfo) => {
    setBusyId(account.id);
    setAuthUrl(null);
    setDeviceCode(null);
    setAuthAccountId(null);
    showNotice("正在检查连接...");
    try {
      const result = await fetchLarkAuthStatus(account.id);
      const connected =
        !!result &&
        typeof result === "object" &&
        "connected" in result &&
        (result as { connected?: unknown }).connected === true;
      showNotice(connected ? "飞书连接可用。" : "飞书尚未完成授权。", connected ? "success" : "error");
    } catch {
      showNotice("飞书尚未完成授权。", "error");
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (account: LarkAccountInfo) => {
    setBusyId(account.id);
    setAuthUrl(null);
    try {
      await deleteLarkAccount(account.id);
      setAccounts((prev) => prev.filter((item) => item.id !== account.id));
      showNotice("已移除飞书账户。", "success");
    } catch {
      showNotice("移除失败，请稍后重试。", "error");
    } finally {
      setBusyId(null);
    }
  };

  const noticeClass =
    noticeTone === "success"
      ? "bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-300"
      : noticeTone === "error"
        ? "bg-red-50 text-red-600 dark:bg-red-950/30 dark:text-red-300"
        : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300";

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-white text-gray-700 shadow-sm ring-1 ring-gray-200 dark:bg-gray-900 dark:text-gray-200 dark:ring-gray-800">
            <Bot className="h-4 w-4" />
          </span>
          飞书
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400">
            {accounts.length}
          </span>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800"
          title="刷新"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
        <div>
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">绑定飞书应用</div>
          <div className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            写入独立 CLI profile，并按用户隔离存储。
          </div>
        </div>

        <input
          type="text"
          value={form.name}
          onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          placeholder="账户名称，例如 default"
          className="w-full rounded-md border border-gray-200 bg-gray-50 px-2.5 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:bg-white focus:outline-none dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
        />
        <input
          type="text"
          value={form.app_id}
          onChange={(event) => setForm((prev) => ({ ...prev, app_id: event.target.value }))}
          placeholder="App ID / cli_xxx"
          className="w-full rounded-md border border-gray-200 bg-gray-50 px-2.5 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:bg-white focus:outline-none dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
        />
        <div className="flex gap-1.5">
          <input
            type={showSecret ? "text" : "password"}
            value={form.app_secret}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, app_secret: event.target.value }))
            }
            placeholder="App Secret"
            className="min-w-0 flex-1 rounded-md border border-gray-200 bg-gray-50 px-2.5 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:bg-white focus:outline-none dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
          />
          <button
            type="button"
            onClick={() => setShowSecret((value) => !value)}
            className="flex h-9 w-9 items-center justify-center rounded-md border border-gray-200 bg-white text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800"
            title={showSecret ? "隐藏密钥" : "显示密钥"}
          >
            {showSecret ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        </div>

        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="flex w-full items-center justify-center gap-1.5 rounded-md bg-gray-950 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-gray-200"
        >
          <ShieldCheck className="h-3.5 w-3.5" />
          {saving ? "绑定中..." : "绑定飞书"}
        </button>
      </div>

      {notice && <p className={`rounded-md px-2.5 py-2 text-sm ${noticeClass}`}>{notice}</p>}

      <div className="min-h-0 flex-1 overflow-y-auto space-y-3 pr-0.5">
        <div className="space-y-2">
          {loading && accounts.length === 0 ? (
            <div className="flex h-20 items-center justify-center">
              <RefreshCw className="h-4 w-4 animate-spin text-gray-400" />
            </div>
          ) : (
            accounts.map((account) => (
              <div
                key={account.id}
                className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900"
              >
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-500" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <p className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                        {account.name}
                      </p>
                      {account.is_default && (
                        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                          默认
                        </span>
                      )}
                    </div>
                    <p className="mt-1 truncate font-mono text-xs text-gray-500">{account.app_id}</p>
                    <p className="mt-0.5 truncate font-mono text-xs text-gray-400">
                      {account.profile_name}
                    </p>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-3 gap-1.5">
                  <button
                    type="button"
                    onClick={() => void handleAuth(account)}
                    disabled={busyId === account.id}
                    className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-sm text-gray-700 hover:bg-white disabled:opacity-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-800"
                  >
                    授权
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleStatus(account)}
                    disabled={busyId === account.id}
                    className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-sm text-gray-700 hover:bg-white disabled:opacity-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-800"
                  >
                    状态
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(account)}
                    disabled={busyId === account.id}
                    className="flex items-center justify-center rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-sm text-red-500 hover:bg-red-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-950 dark:hover:bg-red-950/40"
                    title="删除"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))
          )}

          {accounts.length === 0 && !loading && (
            <p className="py-4 text-center text-sm text-gray-400">暂无飞书账户。</p>
          )}
        </div>

        <LarkActionBoard accounts={accounts} />
      </div>

      {authUrl && (
        <div className="flex flex-shrink-0 gap-2">
          <a
            href={authUrl}
            target="_blank"
            rel="noreferrer"
            className="flex flex-1 items-center justify-center rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
          >
            打开飞书授权
          </a>
          <button
            type="button"
            onClick={() => void handleCompleteAuth()}
            disabled={busyId === authAccountId}
            className="flex flex-1 items-center justify-center rounded-md bg-gray-950 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:opacity-50 dark:bg-white dark:text-black"
          >
            我已完成授权
          </button>
        </div>
      )}
    </div>
  );
}
