"use client";

import { useChat } from "@ai-sdk/react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useVercelUseChatRuntime } from "@assistant-ui/react-ai-sdk";
import { chatAttachmentAdapter } from "@/lib/chat-attachment-adapter";
import { ChevronDownIcon, Loader } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Thread } from "./assistant-ui/thread";
import { ToolDescriptionsProvider } from "@/lib/tool-descriptions-context";
import {
  addMessageToSession,
  createSession,
  getSession,
  summarizeSession,
  notifySessionsListRefresh,
} from "@/lib/api";
import { ThemeToggle } from "./ThemeToggle";
import {
  buildPersistableAttachments,
  buildPersistableContent,
  buildPersistableParts,
  normalizeMessagesFromSessionApi,
} from "@/lib/chat-message-normalize";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:6868";

/** 切换会话时 loading 最短展示时间，避免请求过快结束造成闪烁 */
const MIN_SESSION_LOAD_MS = 880;

interface ChatAreaProps {
  sessionId?: string;
  /** 懒创建会话后回写父级，便于左侧列表选中并后续落库 */
  onSessionIdChange?: (sessionId: string) => void;
}

const MODELS = [
  { id: "deepseek-chat", name: "DeepSeek", label: "DeepSeek Chat" },
  { id: "kimi-k2.5", name: "Kimi K2.5", label: "Kimi K2.5" },
];

export function ChatArea({ sessionId, onSessionIdChange }: ChatAreaProps) {
  const [selectedModel, setSelectedModel] = useState("deepseek-chat");
  const [showModelMenu, setShowModelMenu] = useState(false);
  /** 切换会话拉取历史时的全屏加载，避免空列表闪一下 */
  const [sessionSwitchLoading, setSessionSwitchLoading] = useState(false);
  
  const chat = useChat({
    api: `${API_URL}/api/chat`,
    // 通过 body 透传 sessionId 给后端，后端用它作为浏览器 session_id，
    // 使 BrowserPanel 轮询与 Agent 工具执行的 session_id 保持一致。
    // 注意：不用 useChat 的 id 选项，避免 sessionId 变化时 SDK 重置 store
    // 导致 ThreadPrimitive.MessageByIndex 访问越界崩溃。
    body: { sessionId },
    // 后端每次请求只做一步（单次 LLM 调用），多轮 Agent 循环由 useChat 驱动：
    // 每步以 finishReason="tool-calls" 结束后，SDK 自动发起下一步请求，
    // 实现类 Manus 的分步流式展示（每个工具调用结果立即呈现）。
    maxSteps: 20,
    onError: (err) => console.error("[Chat error]", err),
    headers: {
      "X-Model": selectedModel,
    },
  });

  const runtime = useVercelUseChatRuntime(chat, {
    // 覆盖默认附件适配器：在 accept 中加入 Word，其它行为与官方 vercelAttachmentAdapter 一致
    adapters: { attachments: chatAttachmentAdapter },
  } as any);

  // 已保存的消息 ID 集合，避免重复写入
  const savedMessageIds = useRef(new Set<string>());
  // 上一次渲染时的 sessionId，用于检测会话切换
  const prevSessionIdRef = useRef<string | undefined>(undefined);
  const activeSessionLoadRef = useRef<string | null>(null);
  const lazyCreatingSessionRef = useRef(false);
  /** 避免 useLayoutEffect 依赖 chat.messages，与流式更新冲突（如 React/useChat 内部报错） */
  const messagesLenRef = useRef(0);
  messagesLenRef.current = Array.isArray(chat.messages) ? chat.messages.length : 0;
  /** 主页跳转携带的初始消息，每次挂载只发一次 */
  const initialMsgSentRef = useRef(false);

  // 切换会话 loading：仅随 sessionId 变化触发；是否「含本地消息」读 ref，不订阅 messages
  useLayoutEffect(() => {
    if (!sessionId) {
      setSessionSwitchLoading(false);
      return;
    }
    const prev = prevSessionIdRef.current;
    if (prev === undefined) {
      // 检查是否有待发送的初始消息（从主页跳转），如果有则不显示 loading
      const initialSession = sessionStorage.getItem("sevn:initial-session");
      const hasPendingContent =
        !!sessionStorage.getItem("sevn:initial-message") ||
        !!sessionStorage.getItem("sevn:initial-attachments");
      const hasInitialMessage =
        hasPendingContent &&
        (!initialSession || initialSession === sessionId);
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
        // 主页跳转：会话在服务端仍为空，若此处拉取晚于 append 完成，setMessages([]) 会覆盖用户首条消息
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

    // 流式输出期间不保存（等待完整响应）
    if (!sessionId || chat.messages.length === 0 || chat.isLoading) return;

    // 找出尚未保存的消息
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

    // 顺序保存：确保用户消息先于助手消息入库，避免时间戳相同导致顺序错乱
    void (async () => {
      for (const message of unsaved) {
        const content = buildPersistableContent(message as Parameters<typeof buildPersistableContent>[0]);
        const experimentalAttachments =
          message.role === "user"
            ? buildPersistableAttachments(
                message as Parameters<typeof buildPersistableAttachments>[0]
              )
            : undefined;
        const persistableParts = buildPersistableParts(message as Parameters<typeof buildPersistableParts>[0]);
        try {
          await addMessageToSession(
            capturedSessionId,
            message.role,
            content,
            (message as any).toolInvocations,
            experimentalAttachments,
            persistableParts
          );
        } catch (e) {
          savedMessageIds.current.delete(message.id);
          console.error("保存消息失败:", e);
          throw e;
        }
      }
      const last = messagesSnapshot[messagesSnapshot.length - 1];
      if (last?.role === "assistant") {
        return summarizeSession(capturedSessionId);
      }
    })()
      .then((summarizeResult) => {
        if (summarizeResult) notifySessionsListRefresh();
      })
      .catch((e) => {
        console.error("保存消息或会话标题总结失败:", e);
      });
  }, [sessionId, chat.messages, chat.isLoading]);

  // 未选会话但用户已发消息：自动创建会话并选中，以便写入数据库与列表展示
  useEffect(() => {
    if (sessionId) {
      lazyCreatingSessionRef.current = false;
      return;
    }
    if (!onSessionIdChange) return;
    if (chat.messages.length === 0) return;
    if (!chat.messages.some((m) => m.role === "user")) return;
    if (lazyCreatingSessionRef.current) return;
    lazyCreatingSessionRef.current = true;
    void createSession("新建会话")
      .then((r) => {
        notifySessionsListRefresh();
        onSessionIdChange(r.id);
      })
      .catch((e) => {
        lazyCreatingSessionRef.current = false;
        console.error("创建会话失败:", e);
      });
  }, [sessionId, chat.messages, onSessionIdChange]);

  // 主页输入框跳转后，自动发送存储在 sessionStorage 的初始消息（含附件）
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

    let experimental_attachments: Array<{ name: string; contentType: string; url: string }> | undefined;
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, sessionSwitchLoading]);

  // 加载会话消息
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
    } catch (e) {
      console.error("加载会话消息失败:", e);
    }
  };

  return (
    <ToolDescriptionsProvider>
      <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex h-full flex-col">
        {/* 顶部标题栏 */}
        <header className="flex items-center gap-2.5 px-5 h-[52px] flex-shrink-0 bg-white dark:bg-gray-900">

          {/* 模型选择下拉菜单 */}
          <div className="relative">
            <button
              onClick={() => setShowModelMenu(!showModelMenu)}
              className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <span className="text-[15px] text-gray-900 dark:text-gray-100 leading-none">
                {MODELS.find(m => m.id === selectedModel)?.label ?? selectedModel}
              </span>
              <ChevronDownIcon className="h-4 w-4 text-gray-400" />
            </button>
            
            {/* 下拉菜单 */}
            {showModelMenu && (
              <div className="absolute top-full left-0 mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 min-w-48">
                {MODELS.map(model => (
                  <button
                    key={model.id}
                    onClick={() => {
                      setSelectedModel(model.id);
                      setShowModelMenu(false);
                    }}
                    className={`w-full text-left px-4 py-2 text-sm transition-colors
                      ${selectedModel === model.id
                        ? "bg-blue-50 dark:bg-blue-900/30 text-blue-900 dark:text-blue-100 font-semibold"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                      }
                      ${model !== MODELS[MODELS.length - 1] ? "border-b border-gray-100 dark:border-gray-700" : ""}`}
                  >
                    <div className="font-medium">{model.label}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">{model.id}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
          
          {/* 运行状态指示 */}
          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle />
          </div>
        </header>

        {/* 对话主体 */}
        <div className="flex-1 overflow-hidden relative min-h-0 bg-gray-50 dark:bg-gray-900">
          <div
            className={
              sessionSwitchLoading
                ? "h-full opacity-0 pointer-events-none"
                : "h-full opacity-100"
            }
            aria-hidden={sessionSwitchLoading}
          >
            <Thread />
          </div>
          {sessionSwitchLoading && (
            <div
              className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3
                bg-gray-50 dark:bg-gray-900"
              role="status"
              aria-live="polite"
              aria-busy="true"
            >
              <Loader
                className="h-9 w-9 animate-spin text-gray-400 dark:text-gray-500"
                aria-hidden
              />
              <span className="text-sm text-gray-500 dark:text-gray-400">
                加载会话…
              </span>
            </div>
          )}
        </div>
      </div>
      </AssistantRuntimeProvider>
    </ToolDescriptionsProvider>
  );
}
