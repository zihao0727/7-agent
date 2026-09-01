export {};

declare global {
  interface DesktopRuntimeStatus {
    connected: boolean;
    state: "connecting" | "connected" | "disconnected" | "error";
  }

  interface DesktopLarkStatus {
    installed: boolean;
    source: "managed" | "bundled";
    version: string | null;
    latestVersion: string | null;
    updateAvailable: boolean;
    warning?: string;
  }

  interface Window {
    agentDesktop?: {
      isDesktop: true;
      config: {
        apiUrl: string;
      };
      runtime: {
        connect(payload: {
          apiUrl: string;
          accessToken: string;
          userId: number;
        }): Promise<{ ok: boolean }>;
        disconnect(): Promise<{ ok: boolean }>;
        onStatus(listener: (status: DesktopRuntimeStatus) => void): () => void;
      };
      lark: {
        status(): Promise<DesktopLarkStatus>;
        ensureLatest(): Promise<DesktopLarkStatus>;
      };
    };
  }
}
