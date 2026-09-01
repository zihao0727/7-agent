const WebSocket = require("ws");

function runtimeWebSocketUrl(apiUrl) {
  const url = new URL(apiUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `${url.pathname.replace(/\/$/, "")}/api/client-runtime/ws`;
  url.search = "";
  url.hash = "";
  return url.toString();
}

class RuntimeSocket {
  constructor({ larkCliManager, onStatus = () => {} }) {
    this.larkCliManager = larkCliManager;
    this.onStatus = onStatus;
    this.socket = null;
    this.credentials = null;
    this.reconnectTimer = null;
    this.reconnectAttempt = 0;
    this.closedByUser = false;
  }

  connect({ apiUrl, accessToken, userId }) {
    this.credentials = {
      apiUrl: String(apiUrl || "").replace(/\/$/, ""),
      accessToken: String(accessToken || ""),
      userId: Number(userId),
    };
    if (!this.credentials.apiUrl || !this.credentials.accessToken || !this.credentials.userId) {
      throw new Error("桌面运行时连接参数不完整");
    }
    this.closedByUser = false;
    this._open();
  }

  disconnect() {
    this.closedByUser = true;
    this.credentials = null;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (this.socket) this.socket.close(1000, "Signed out");
    this.socket = null;
    this.onStatus({ connected: false, state: "disconnected" });
  }

  _open() {
    if (!this.credentials || this.closedByUser) return;
    const credentials = { ...this.credentials };
    if (this.socket) {
      this.socket.removeAllListeners();
      this.socket.terminate();
    }
    const socket = new WebSocket(runtimeWebSocketUrl(credentials.apiUrl), {
      headers: { Authorization: `Bearer ${credentials.accessToken}` },
    });
    this.socket = socket;
    this.onStatus({ connected: false, state: "connecting" });

    socket.on("open", () => {
      this.reconnectAttempt = 0;
      this.onStatus({ connected: true, state: "connected" });
    });
    socket.on("message", (raw) => void this._handleMessage(socket, credentials, raw));
    socket.on("close", () => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.onStatus({ connected: false, state: "disconnected" });
      this._scheduleReconnect();
    });
    socket.on("error", () => {
      if (this.socket !== socket) return;
      this.onStatus({ connected: false, state: "error" });
    });
  }

  async _handleMessage(socket, credentials, raw) {
    if (this.socket !== socket) return;
    let message;
    try {
      message = JSON.parse(raw.toString("utf8"));
    } catch {
      return;
    }
    if (message.type !== "request" || !message.request_id) return;

    try {
      if (message.capability !== "lark-cli") throw new Error("不支持的客户端能力");
      const payload = message.payload || {};
      const result = await this.larkCliManager.runForUser({
        userId: credentials.userId,
        account: payload.account,
        args: payload.args,
        stdin: payload.stdin,
        timeoutSeconds: payload.timeout_seconds,
      });
      this._send(socket, {
        type: "response",
        request_id: message.request_id,
        ok: true,
        result,
      });
    } catch (error) {
      this._send(socket, {
        type: "response",
        request_id: message.request_id,
        ok: false,
        error: error instanceof Error ? error.message : "客户端能力执行失败",
      });
    }
  }

  _send(socket, payload) {
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload));
  }

  _scheduleReconnect() {
    if (!this.credentials || this.closedByUser || this.reconnectTimer) return;
    const delay = Math.min(30_000, 1_000 * 2 ** this.reconnectAttempt);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this._open();
    }, delay);
  }
}

module.exports = { RuntimeSocket, runtimeWebSocketUrl };
