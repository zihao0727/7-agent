"use client";

import Image from "next/image";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  BadgeCheck,
  DatabaseZap,
  Fingerprint,
  KeyRound,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";
import brandLogo from "@/logo.png";
import { useAuth } from "@/components/AuthProvider";
import { cn } from "@/lib/utils";

type Mode = "login" | "register";

const INITIAL_COOLDOWN = 60;

function LoginPageContent() {
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
  const gridFrameRef = useRef<number | null>(null);

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

  const handleHeroPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const section = event.currentTarget;
    const rect = section.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;

    if (gridFrameRef.current !== null) {
      window.cancelAnimationFrame(gridFrameRef.current);
    }

    gridFrameRef.current = window.requestAnimationFrame(() => {
      section.style.setProperty("--grid-x", `${x * 100}%`);
      section.style.setProperty("--grid-y", `${y * 100}%`);
      section.style.setProperty("--grid-pan-x", `${(x - 0.5) * 34}px`);
      section.style.setProperty("--grid-pan-y", `${(y - 0.5) * 24}px`);
      section.style.setProperty("--grid-scale", "1.018");
    });
  };

  const handleHeroPointerLeave = (event: React.PointerEvent<HTMLElement>) => {
    const section = event.currentTarget;
    if (gridFrameRef.current !== null) {
      window.cancelAnimationFrame(gridFrameRef.current);
      gridFrameRef.current = null;
    }
    section.style.setProperty("--grid-pan-x", "0px");
    section.style.setProperty("--grid-pan-y", "0px");
    section.style.setProperty("--grid-scale", "1");
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
      <div className="flex h-screen items-center justify-center bg-[#f7f7f5] text-neutral-500">
        <div className="flex items-center gap-3 text-sm">
          <Loader2 className="h-5 w-5 animate-spin" />
          正在准备登录环境
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-[#f7f7f5] text-neutral-950">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[1fr_minmax(420px,520px)]">
        <section
          className="relative flex min-h-[52vh] flex-col justify-between overflow-hidden border-b border-black/[0.08] bg-[#f8f8f6] px-6 py-7 sm:px-10 lg:min-h-screen lg:border-b-0 lg:border-r lg:px-14 lg:py-10"
          onPointerMove={handleHeroPointerMove}
          onPointerLeave={handleHeroPointerLeave}
        >
          <div className="login-grid-wave pointer-events-none absolute inset-0" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_26%,rgba(255,255,255,0.95)_0,rgba(255,255,255,0.55)_24%,transparent_48%),radial-gradient(circle_at_76%_72%,rgba(12,12,12,0.08)_0,transparent_34%)]" />
          <div className="pointer-events-none absolute right-[-4rem] top-[8%] hidden select-none text-[22rem] font-semibold leading-none tracking-[-0.08em] text-black/[0.025] lg:block">
            X
          </div>

          <div className="relative flex items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-[14px] border border-black/10 bg-white/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_18px_42px_rgba(15,23,42,0.06)] backdrop-blur">
                <Image src={brandLogo} alt="SevnX" width={26} height={26} className="h-6 w-6 object-contain" />
              </div>
              <div>
                <div className="text-xl font-semibold tracking-tight">SevnX</div>
                <div className="text-xs font-medium text-neutral-500">Personal AI Operating Layer</div>
              </div>
            </div>
            <div className="hidden items-center gap-2 rounded-full border border-black/10 bg-white/60 px-3 py-1.5 text-xs font-medium text-neutral-600 shadow-[0_12px_34px_rgba(15,23,42,0.05)] backdrop-blur sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.8)]" />
              Core online
            </div>
          </div>

          <div className="relative max-w-3xl py-12 lg:py-0">
            <p className="mb-5 text-xs font-semibold uppercase tracking-[0.34em] text-neutral-400">
              Intelligence, composed
            </p>
            <h1 className="max-w-2xl font-display text-[3.35rem] font-semibold leading-[0.98] tracking-tight text-neutral-950 sm:text-6xl lg:text-[5.45rem]">
              为你而生的超级智能助手
            </h1>
            <p className="mt-7 max-w-xl text-base leading-8 text-neutral-500 sm:text-lg">
              把想法、任务和工具交给 SevnX，让复杂工作自然向前。
            </p>

            <div className="mt-11 grid max-w-2xl gap-3 sm:grid-cols-3">
              <SignalCard icon={Fingerprint} title="Private Space" text="账号独立" />
              <SignalCard icon={DatabaseZap} title="Long Memory" text="持续协作" />
              <SignalCard icon={KeyRound} title="Tool Ready" text="即刻执行" />
            </div>

            <div className="mt-8 max-w-2xl border-y border-black/[0.08] py-5">
              <div className="flex flex-col gap-4 text-sm text-neutral-500 sm:flex-row sm:items-center sm:justify-between">
                <span className="font-semibold text-neutral-950">SevnX Assistant Core</span>
                <span className="font-medium">Chat / Browser / Code / Skills</span>
              </div>
            </div>
          </div>

          <div className="relative hidden items-center justify-between text-sm text-neutral-400 lg:flex">
            <span>SevnX / 2026</span>
            <span>Encrypted workspace</span>
          </div>
        </section>

        <section className="relative flex items-center justify-center bg-white px-6 py-12 sm:px-10">
          <div className="pointer-events-none absolute inset-y-10 left-0 hidden w-px bg-gradient-to-b from-transparent via-black/10 to-transparent lg:block" />
          <div className="w-full max-w-[360px]">
            <div className="mb-9">
              <div className="inline-flex rounded-full border border-black/10 bg-[#f7f7f5] p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
                <ModeButton
                  active={mode === "login"}
                  onClick={() => {
                    setMode("login");
                    resetNotice();
                  }}
                >
                  登录
                </ModeButton>
                <ModeButton
                  active={mode === "register"}
                  onClick={() => {
                    setMode("register");
                    resetNotice();
                  }}
                >
                  注册
                </ModeButton>
              </div>
              <div className="mt-8 flex items-start gap-3">
                <div className="mt-1 flex h-8 w-8 items-center justify-center rounded-full bg-neutral-950 text-white shadow-[0_14px_30px_rgba(0,0,0,0.16)]">
                  {mode === "login" ? <Sparkles className="h-4 w-4" /> : <BadgeCheck className="h-4 w-4" />}
                </div>
                <div>
                  <h2 className="text-3xl font-semibold tracking-tight">
                    {mode === "login" ? "欢迎回来" : "创建助手空间"}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-neutral-500">
                    {mode === "login" ? "继续你的智能工作流。" : "建立属于你的私人智能工作层。"}
                  </p>
                </div>
              </div>
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
                  <label className="text-xs font-semibold uppercase tracking-[0.16em] text-neutral-500">验证码</label>
                  <div className="flex gap-2">
                    <div className="flex min-w-0 flex-1 items-center gap-3 rounded-[14px] border border-black/10 bg-white px-4 py-3.5 shadow-[0_10px_28px_rgba(15,23,42,0.035)] transition-all focus-within:border-neutral-950 focus-within:shadow-[0_18px_38px_rgba(15,23,42,0.08)]">
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
                      className="min-w-[96px] rounded-[14px] border border-black/10 bg-[#f7f7f5] px-3 text-sm font-semibold transition-all hover:border-neutral-950 hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {sendingCode ? "发送中" : cooldown > 0 ? `${cooldown}s` : "发送"}
                    </button>
                  </div>
                </div>
              )}

              {error && (
                <div className="rounded-[14px] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              {success && (
                <div className="rounded-[14px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  {success}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="group mt-2 flex w-full items-center justify-center gap-2 rounded-[14px] bg-neutral-950 px-4 py-3.5 text-sm font-semibold text-white shadow-[0_18px_38px_rgba(0,0,0,0.16)] transition-all hover:-translate-y-0.5 hover:bg-black hover:shadow-[0_24px_46px_rgba(0,0,0,0.22)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    处理中
                  </>
                ) : (
                  <>
                    {submitLabel}
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                  </>
                )}
              </button>
            </form>

            <div className="mt-7 flex flex-wrap gap-2">
              <TrustPill>Encrypted workspace</TrustPill>
              <TrustPill>Private memory</TrustPill>
              <TrustPill>Tool execution</TrustPill>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#f7f7f5]" />}>
      <LoginPageContent />
    </Suspense>
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
    <div className="group rounded-[14px] border border-black/[0.08] bg-white/68 p-4 shadow-[0_18px_60px_rgba(15,23,42,0.07)] backdrop-blur transition-all hover:-translate-y-0.5 hover:bg-white/85 hover:shadow-[0_24px_70px_rgba(15,23,42,0.1)]">
      <div className="mb-5 flex h-9 w-9 items-center justify-center rounded-[13px] bg-neutral-950 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.24),0_12px_26px_rgba(0,0,0,0.18)]">
        <Icon className="h-4 w-4" />
      </div>
      <div className="text-sm font-semibold text-neutral-950">{title}</div>
      <div className="mt-1 text-xs font-medium text-neutral-500">{text}</div>
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
        "rounded-full px-5 py-2 text-sm font-semibold transition-all",
        active
          ? "bg-neutral-950 text-white shadow-[0_10px_22px_rgba(0,0,0,0.16)]"
          : "text-neutral-500 hover:text-neutral-950"
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
      <label className="text-xs font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</label>
      <div className="flex items-center gap-3 rounded-[14px] border border-black/10 bg-white px-4 py-3.5 shadow-[0_10px_28px_rgba(15,23,42,0.035)] transition-all focus-within:border-neutral-950 focus-within:shadow-[0_18px_38px_rgba(15,23,42,0.08)]">
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

function TrustPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-black/[0.08] bg-[#f7f7f5] px-3 py-1.5 text-xs font-medium text-neutral-500">
      {children}
    </span>
  );
}
