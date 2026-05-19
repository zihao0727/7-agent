"use client";

import { useChat } from "@ai-sdk/react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useVercelUseChatRuntime } from "@assistant-ui/react-ai-sdk";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ChevronDownIcon, Loader } from "lucide-react";
import { chatAttachmentAdapter } from "@/lib/chat-attachment-adapter";
import { ToolDescriptionsProvider } from "@/lib/tool-descriptions-context";
import { ThemeToggle } from "./ThemeToggle";
import { Thread } from "./assistant-ui/thread";
import { useAuth } from "./AuthProvider";
import {
  addMessageToSession,
  createSession,
  deleteMessagesAfter,
  getSession,
  summarizeSession,
  notifySessionsListRefresh,
  setChatBusy,
} from "@/lib/api";
import {
  buildPersistableAttachments,
  buildPersistableContent,
  buildPersistableParts,
  normalizeMessagesFromSessionApi,
} from "@/lib/chat-message-normalize";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:6868";
const MIN_SESSION_LOAD_MS = 880;
const TITLE_SUMMARY_DEBOUNCE_MS = 1500;
const DEEPSEEK_MODEL_ID =
  process.env.NEXT_PUBLIC_DEEPSEEK_MODEL ?? "deepseek-v4-flash";
const KIMI_MODEL_ID = process.env.NEXT_PUBLIC_KIMI_MODEL ?? "kimi-k2.6";

const MODELS = [
  {
    id: DEEPSEEK_MODEL_ID,
    name: "DeepSeek",
    label: `DeepSeek (${DEEPSEEK_MODEL_ID})`,
  },
  {
    id: KIMI_MODEL_ID,
    name: "Kimi",
    label: `Kimi (${KIMI_MODEL_ID})`,
  },
];

interface ChatAreaProps {
  sessionId?: string;
  onSessionIdChange?: (sessionId: string) => void;
}

export function ChatArea({ sessionId, onSessionIdChange }: ChatAreaProps) {
  const { accessToken } = useAuth();
  const [selectedModel, setSelectedModel] = useState(DEEPSEEK_MODEL_ID);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [sessionSwitchLoading, setSessionSwitchLoading] = useState(false);

  const chat = useChat({
    api: `${API_URL}/api/chat`,
    body: { sessionId },
    maxSteps: 20,
    onError: (err) => console.error("[chat]", err),
    headers: {
      "X-Model": selectedModel,
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  });

  const runtime = useVercelUseChatRuntime(chat, {
    adapters: { attachments: chatAttachmentAdapter },
  } as any);

  const savedMessageIds = useRef(new Set<string>());
  const prevSessionIdRef = useRef<string | undefined>(undefined);
  const activeSessionLoadRef = useRef<string | null>(null);
  const lazyCreatingSessionRef = useRef(false);
  const summarizeTimerRef = useRef<number | null>(null);
  const summarizeTokenRef = useRef(0);
  const prevTrimSessionIdRef = useRef<string | undefined>(undefined);
  const prevTrimMessagesLengthRef = useRef(0);
  const messagesLenRef = useRef(0);
  const initialMsgSentRef = useRef(false);
  messagesLenRef.current = Array.isArray(chat.messages) ? chat.messages.length : 0;

  const clearPendingSummary = useCallback(() => {
    if (summarizeTimerRef.current !== null) {
      window.clearTimeout(summarizeTimerRef.current);
      summarizeTimerRef.current = null;
    }
  }, []);

  // 广播忙碌状态：AI 正在回复 或 标题正在生成中
  useEffect(() => {
    setChatBusy(chat.isLoading || summarizeTimerRef.current !== null);
  }, [chat.isLoading]);

  // 组件卸载时清除忙碌状态
  useEffect(() => {
    return () => setChatBusy(false);
  }, []);

  const scheduleSessionSummary = useCallback(
    (targetSessionId: string) => {
      clearPendingSummary();
      const token = ++summarizeTokenRef.current;
      setChatBusy(true);
      summarizeTimerRef.current = window.setTimeout(() => {
        summarizeTimerRef.current = null;
        void summarizeSession(targetSessionId)
          .then(() => {
            if (summarizeTokenRef.current !== token) return;
            notifySessionsListRefresh();
          })
          .catch((error) => {
            if (summarizeTokenRef.current !== token) return;
            console.error("session summary failed", error);
          })
          .finally(() => {
            if (summarizeTokenRef.current !== token) return;
            setChatBusy(false);
          });
      }, TITLE_SUMMARY_DEBOUNCE_MS);
    },
    [clearPendingSummary]
  );

  useEffect(() => {
    return () => clearPendingSummary();
  }, [clearPendingSummary]);

  useEffect(() => {
    const currentLength = chat.messages.length;

    if (prevTrimSessionIdRef.current !== sessionId) {
      prevTrimSessionIdRef.current = sessionId;
      prevTrimMessagesLengthRef.current = currentLength;
      return;
    }

    const previousLength = prevTrimMessagesLengthRef.current;
    prevTrimMessagesLengthRef.current = currentLength;

    if (!sessionId || currentLength >= previousLength) return;

    savedMessageIds.current = new Set(
      chat.messages.map((message) => message.id).filter(Boolean)
    );

    void deleteMessagesAfter(sessionId, currentLength).catch((error) => {
      console.error("trim messages failed", error);
    });
  }, [sessionId, chat.messages]);

  useLayoutEffect(() => {
    if (!sessionId) {
      setSessionSwitchLoading(false);
      return;
    }
    const prev = prevSessionIdRef.current;
    if (prev === undefined) {
      const initialSession = sessionStorage.getItem("sevn:initial-session");
      const hasPendingContent =
        !!sessionStorage.getItem("sevn:initial-message") ||
        !!sessionStorage.getItem("sevn:initial-attachments");
      const hasInitialMessage =
        hasPendingContent && (!initialSession || initialSession === sessionId);
      setSessionSwitchLoading(messagesLenRef.current === 0 && !hasInitialMessage);
      return;
    }
    if (prev !== sessionId) {
      setSessionSwitchLoading(true);
    }
  }, [sessionId]);

  useEffect(() => {
    const sessionChanged = prevSessionIdRef.current !== sessionId;

    if (sessionChanged) {
      clearPendingSummary();
      const prev = prevSessionIdRef.current;
      prevSessionIdRef.current = sessionId;

      const isLazyAttach =
        prev === undefined && !!sessionId && chat.messages.length > 0;

      if (isLazyAttach) {
        activeSessionLoadRef.current = null;
        setSessionSwitchLoading(false);
        return;
      }

      savedMessageIds.current.clear();
      chat.setMessages([]);

      if (sessionId) {
        const pendingForSession =
          typeof window !== "undefined"
            ? sessionStorage.getItem("sevn:initial-session")
            : null;
        const hasInitialPending =
          typeof window !== "undefined" &&
          (!!sessionStorage.getItem("sevn:initial-message") ||
            !!sessionStorage.getItem("sevn:initial-attachments")) &&
          pendingForSession === sessionId;

        if (hasInitialPending) {
          activeSessionLoadRef.current = null;
          setSessionSwitchLoading(false);
          return;
        }

        const loadId = sessionId;
        const startedAt = performance.now();
        activeSessionLoadRef.current = loadId;
        void loadSessionMessages(sessionId).finally(() => {
          const elapsed = performance.now() - startedAt;
          const remain = Math.max(0, MIN_SESSION_LOAD_MS - elapsed);
          const endLoading = () => {
            if (activeSessionLoadRef.current === loadId) {
              activeSessionLoadRef.current = null;
              setSessionSwitchLoading(false);
            }
          };
          if (remain > 0) {
            window.setTimeout(endLoading, remain);
          } else {
            endLoading();
          }
        });
      } else {
        activeSessionLoadRef.current = null;
      }
      return;
    }

    if (!sessionId || chat.messages.length === 0 || chat.isLoading) return;

    const unsaved = chat.messages.filter(
      (msg) =>
        (msg.role === "user" || msg.role === "assistant") &&
        !savedMessageIds.current.has(msg.id)
    );
    if (unsaved.length === 0) return;

    const capturedSessionId = sessionId;
    const messagesSnapshot = chat.messages;

    for (const message of unsaved) {
      savedMessageIds.current.add(message.id);
    }

    void (async () => {
      for (const message of unsaved) {
        const content = buildPersistableContent(
          message as Parameters<typeof buildPersistableContent>[0]
        );
        const experimentalAttachments =
          message.role === "user"
            ? buildPersistableAttachments(
                message as Parameters<typeof buildPersistableAttachments>[0]
              )
            : undefined;
        const persistableParts = buildPersistableParts(
          message as Parameters<typeof buildPersistableParts>[0]
        );
        const reasoningContent =
          message.role === "assistant"
            ? persistableParts
                ?.find(
                  (part) =>
                    part &&
                    typeof part === "object" &&
                    (part as Record<string, unknown>).type === "reasoning"
                )
                ?.text
            : undefined;
        try {
          await addMessageToSession(
            capturedSessionId,
            message.role,
            content,
            (message as any).toolInvocations,
            experimentalAttachments,
            persistableParts,
            typeof reasoningContent === "string" ? reasoningContent : undefined
          );
        } catch (error) {
          savedMessageIds.current.delete(message.id);
          console.error("save message failed", error);
          throw error;
        }
      }
      const last = messagesSnapshot[messagesSnapshot.length - 1];
      const shouldSummarize =
        unsaved.some((message) => message.role === "user") ||
        last?.role === "assistant";
      if (shouldSummarize) {
        scheduleSessionSummary(capturedSessionId);
      }
    })().catch((error) => {
      console.error("persist conversation failed", error);
    });
  }, [sessionId, chat.messages, chat.isLoading, clearPendingSummary, scheduleSessionSummary]);

  useEffect(() => {
    if (sessionId) {
      lazyCreatingSessionRef.current = false;
      return;
    }
    if (!onSessionIdChange) return;
    if (chat.messages.length === 0) return;
    if (!chat.messages.some((message) => message.role === "user")) return;
    if (lazyCreatingSessionRef.current) return;
    lazyCreatingSessionRef.current = true;
    void createSession("新建会话")
      .then((result) => {
        notifySessionsListRefresh();
        onSessionIdChange(result.id);
      })
      .catch((error) => {
        lazyCreatingSessionRef.current = false;
        console.error("create session failed", error);
      });
  }, [sessionId, chat.messages, onSessionIdChange]);

  useEffect(() => {
    if (sessionSwitchLoading) return;
    if (!sessionId) return;
    if (initialMsgSentRef.current) return;
    const pending = sessionStorage.getItem("sevn:initial-message");
    const pendingAttachmentsRaw = sessionStorage.getItem("sevn:initial-attachments");
    if (!pending && !pendingAttachmentsRaw) return;
    initialMsgSentRef.current = true;
    sessionStorage.removeItem("sevn:initial-message");
    sessionStorage.removeItem("sevn:initial-attachments");
    sessionStorage.removeItem("sevn:initial-session");

    let experimental_attachments:
      | Array<{ name: string; contentType: string; url: string }>
      | undefined;
    if (pendingAttachmentsRaw) {
      try {
        experimental_attachments = JSON.parse(pendingAttachmentsRaw);
      } catch {
        experimental_attachments = undefined;
      }
    }

    void chat.append(
      {
        role: "user",
        content: pending || "",
        ...(experimental_attachments && experimental_attachments.length > 0
          ? { experimental_attachments }
          : {}),
      } as Parameters<typeof chat.append>[0]
    );
  }, [chat, sessionId, sessionSwitchLoading]);

  const loadSessionMessages = async (id: string) => {
    try {
      const session = await getSession(id);
      const messages = normalizeMessagesFromSessionApi(
        session.messages
      ) as Parameters<typeof chat.setMessages>[0] & unknown[];
      chat.setMessages(messages);
      (messages as Array<{ id?: string }>).forEach((msg) => {
        if (msg.id) savedMessageIds.current.add(msg.id);
      });
    } catch (error) {
      console.error("load session failed", error);
    }
  };

  return (
    <ToolDescriptionsProvider>
      <AssistantRuntimeProvider runtime={runtime}>
        <div className="flex h-full flex-col">
          <header className="flex h-[52px] flex-shrink-0 items-center gap-2.5 bg-white px-5 dark:bg-gray-900">
            <div className="relative">
              <button
                onClick={() => setShowModelMenu((value) => !value)}
                className="flex items-center gap-1.5 rounded px-2 py-1 transition-colors hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <span className="text-[15px] leading-none text-gray-900 dark:text-gray-100">
                  {MODELS.find((model) => model.id === selectedModel)?.label ?? selectedModel}
                </span>
                <ChevronDownIcon className="h-4 w-4 text-gray-400" />
              </button>

              {showModelMenu && (
                <div className="absolute left-0 top-full z-50 mt-1 min-w-48 rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
                  {MODELS.map((model, index) => (
                    <button
                      key={model.id}
                      onClick={() => {
                        setSelectedModel(model.id);
                        setShowModelMenu(false);
                      }}
                      className={`w-full px-4 py-2 text-left text-sm transition-colors ${
                        selectedModel === model.id
                          ? "bg-blue-50 font-semibold text-blue-900 dark:bg-blue-900/30 dark:text-blue-100"
                          : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
                      } ${index < MODELS.length - 1 ? "border-b border-gray-100 dark:border-gray-700" : ""}`}
                    >
                      <div className="font-medium">{model.label}</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {model.id}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="ml-auto flex items-center gap-3">
              <ThemeToggle />
            </div>
          </header>

          <div className="relative min-h-0 flex-1 overflow-hidden bg-gray-50 dark:bg-gray-900">
            <div
              className={
                sessionSwitchLoading
                  ? "pointer-events-none h-full opacity-0"
                  : "h-full opacity-100"
              }
              aria-hidden={sessionSwitchLoading}
            >
              <Thread />
            </div>
            {sessionSwitchLoading && (
              <div
                className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-gray-50 dark:bg-gray-900"
                role="status"
                aria-live="polite"
                aria-busy="true"
              >
                <Loader className="h-9 w-9 animate-spin text-gray-400 dark:text-gray-500" />
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  正在加载会话...
                </span>
              </div>
            )}
          </div>
        </div>
      </AssistantRuntimeProvider>
    </ToolDescriptionsProvider>
  );
}
