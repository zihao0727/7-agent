"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import brandLogo from "@/logo.png";
import { useAuth } from "@/components/AuthProvider";
import { cn } from "@/lib/utils";

type Mode = "login" | "register";

const INITIAL_COOLDOWN = 60;

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = useMemo(() => searchParams.get("next") || "/app", [searchParams]);
  const { isAuthenticated, loading, requestRegisterCode, signIn, signUp } = useAuth();

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && isAuthenticated) {
      router.replace(next);
    }
  }, [isAuthenticated, loading, next, router]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  const submitLabel = mode === "login" ? "登录" : "注册并进入";

  const resetNotice = () => {
    setError(null);
    setSuccess(null);
  };

  const handleSendCode = async () => {
    if (!email.trim() || sendingCode || cooldown > 0) return;
    setSendingCode(true);
    resetNotice();
    try {
      await requestRegisterCode(email.trim());
      setCooldown(INITIAL_COOLDOWN);
      setSuccess("验证码已发送");
    } catch (err) {
      setError(err instanceof Error ? err.message : "验证码发送失败");
    } finally {
      setSendingCode(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    resetNotice();
    try {
      if (mode === "login") {
        await signIn(email.trim(), password);
      } else {
        await signUp({
          email: email.trim(),
          password,
          code: code.trim(),
          display_name: displayName.trim() || undefined,
        });
      }
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-white text-neutral-500">
        <div className="flex items-center gap-3 text-sm">
          <Loader2 className="h-5 w-5 animate-spin" />
          正在准备登录环境
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-white text-neutral-950">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[1fr_520px]">
        <section className="relative flex min-h-[46vh] flex-col justify-between overflow-hidden border-b border-neutral-200 bg-[linear-gradient(135deg,#ffffff_0%,#fafafa_50%,#f3f4f6_100%)] px-6 py-7 sm:px-10 lg:min-h-screen lg:border-b-0 lg:border-r lg:px-14 lg:py-10">
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(15,23,42,0.045)_1px,transparent_1px),linear-gradient(to_bottom,rgba(15,23,42,0.035)_1px,transparent_1px)] bg-[size:72px_72px]" />
          <div className="pointer-events-none absolute bottom-0 right-0 h-72 w-72 rounded-full border border-neutral-200/80 bg-white/50 blur-3xl" />

          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-neutral-200 bg-neutral-50">
              <Image src={brandLogo} alt="SevnX" width={26} height={26} className="h-6 w-6 object-contain" />
            </div>
            <div>
              <div className="text-xl font-semibold tracking-tight">SevnX</div>
              <div className="text-xs text-neutral-500">为你而生的超级智能助手</div>
            </div>
          </div>

          <div className="relative max-w-3xl py-12 lg:py-0">
            <p className="mb-5 text-sm font-medium uppercase tracking-[0.24em] text-neutral-400">
              Super Assistant
            </p>
            <h1 className="max-w-2xl font-display text-5xl font-semibold leading-[1.05] tracking-tight text-neutral-950 sm:text-6xl lg:text-7xl">
              为你而生的超级智能助手
            </h1>
            <p className="mt-6 max-w-lg text-base leading-8 text-neutral-500">
              把想法、任务和工具交给 SevnX，让复杂工作自然向前。
            </p>

            <div className="mt-10 grid max-w-2xl gap-3 sm:grid-cols-3">
              <SignalCard icon={ShieldCheck} title="安全空间" text="账号独立" />
              <SignalCard icon={UserRound} title="长期记忆" text="持续协作" />
              <SignalCard icon={LockKeyhole} title="工具就绪" text="即刻执行" />
            </div>

            <div className="mt-8 max-w-2xl border-y border-neutral-200/80 py-5">
              <div className="flex flex-col gap-4 text-sm text-neutral-500 sm:flex-row sm:items-center sm:justify-between">
                <span className="font-medium text-neutral-950">SevnX Assistant Core</span>
                <span>Chat / Browser / Code / Skills</span>
              </div>
            </div>
          </div>

          <div className="relative hidden text-sm text-neutral-400 lg:block">SevnX / 2026</div>
        </section>

        <section className="flex items-center justify-center px-6 py-12 sm:px-10">
          <div className="w-full max-w-[360px]">
            <div className="mb-8">
              <div className="inline-flex rounded-full border border-neutral-200 bg-neutral-50 p-1">
                <ModeButton active={mode === "login"} onClick={() => {
                  setMode("login");
                  resetNotice();
                }}>
                  登录
                </ModeButton>
                <ModeButton active={mode === "register"} onClick={() => {
                  setMode("register");
                  resetNotice();
                }}>
                  注册
                </ModeButton>
              </div>
              <h2 className="mt-8 text-3xl font-semibold tracking-tight">
                {mode === "login" ? "开始对话" : "创建你的助手空间"}
              </h2>
            </div>

            <form className="space-y-4" onSubmit={handleSubmit}>
              {mode === "register" && (
                <Field
                  label="昵称"
                  icon={UserRound}
                  value={displayName}
                  onChange={setDisplayName}
                  placeholder="你的名字"
                />
              )}

              <Field
                label="邮箱"
                icon={Mail}
                value={email}
                onChange={setEmail}
                placeholder="name@example.com"
                type="email"
              />

              <Field
                label="密码"
                icon={LockKeyhole}
                value={password}
                onChange={setPassword}
                placeholder="至少 8 位"
                type="password"
              />

              {mode === "register" && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-neutral-700">验证码</label>
                  <div className="flex gap-2">
                    <div className="flex min-w-0 flex-1 items-center gap-3 rounded-xl border border-neutral-200 bg-white px-4 py-3 transition-colors focus-within:border-neutral-950">
                      <ShieldCheck className="h-4 w-4 text-neutral-400" />
                      <input
                        value={code}
                        onChange={(event) => setCode(event.target.value)}
                        placeholder="输入验证码"
                        className="w-full bg-transparent text-sm outline-none placeholder:text-neutral-400"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleSendCode()}
                      disabled={sendingCode || cooldown > 0 || !email.trim()}
                      className="min-w-[96px] rounded-xl border border-neutral-200 px-3 text-sm font-medium transition-colors hover:border-neutral-950 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {sendingCode ? "发送中" : cooldown > 0 ? `${cooldown}s` : "发送"}
                    </button>
                  </div>
                </div>
              )}

              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              {success && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  {success}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-neutral-950 px-4 py-3.5 text-sm font-semibold text-white transition-colors hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    处理中
                  </>
                ) : (
                  <>
                    {submitLabel}
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>
          </div>
        </section>
      </div>
    </main>
  );
}

function SignalCard({
  icon: Icon,
  title,
  text,
}: {
  icon: typeof ShieldCheck;
  title: string;
  text: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white/70 p-4 shadow-[0_18px_60px_rgba(15,23,42,0.06)] backdrop-blur">
      <div className="mb-5 flex h-9 w-9 items-center justify-center rounded-xl bg-neutral-950 text-white">
        <Icon className="h-4 w-4" />
      </div>
      <div className="text-sm font-semibold text-neutral-950">{title}</div>
      <div className="mt-1 text-xs text-neutral-500">{text}</div>
    </div>
  );
}

function ModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-5 py-2 text-sm font-medium transition-colors",
        active ? "bg-neutral-950 text-white" : "text-neutral-500 hover:text-neutral-950"
      )}
    >
      {children}
    </button>
  );
}

function Field({
  label,
  icon: Icon,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  icon: typeof Mail;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: string;
}) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-neutral-700">{label}</label>
      <div className="flex items-center gap-3 rounded-xl border border-neutral-200 bg-white px-4 py-3 transition-colors focus-within:border-neutral-950">
        <Icon className="h-4 w-4 text-neutral-400" />
        <input
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="w-full bg-transparent text-sm outline-none placeholder:text-neutral-400"
        />
      </div>
    </div>
  );
}
