const fs = require("node:fs");
const path = require("node:path");
const { app, BrowserWindow, ipcMain, shell } = require("electron");
const { LarkCliManager } = require("./lark-cli-manager.cjs");
const { RuntimeSocket } = require("./runtime-socket.cjs");

let mainWindow = null;
let larkCliManager = null;
let runtimeSocket = null;
let desktopConfig = null;

function readJson(pathname) {
  try {
    return JSON.parse(fs.readFileSync(pathname, "utf8"));
  } catch {
    return {};
  }
}

function loadConfig() {
  const resourceConfig = readJson(path.join(process.resourcesPath, "config.json"));
  const userConfig = readJson(path.join(app.getPath("userData"), "config.json"));
  const development = !app.isPackaged;
  return {
    appUrl:
      process.env.AGENT7_APP_URL ||
      userConfig.appUrl ||
      resourceConfig.appUrl ||
      (development ? "http://localhost:7878" : ""),
    apiUrl:
      process.env.AGENT7_API_URL ||
      userConfig.apiUrl ||
      resourceConfig.apiUrl ||
      (development ? "http://localhost:6868" : ""),
    autoUpdateLarkCli:
      userConfig.autoUpdateLarkCli ?? resourceConfig.autoUpdateLarkCli ?? true,
  };
}

function trustedOrigin(url) {
  try {
    return new URL(url).origin === new URL(desktopConfig.appUrl).origin;
  } catch {
    return false;
  }
}

function assertTrustedSender(event) {
  if (!trustedOrigin(event.senderFrame.url)) throw new Error("Untrusted renderer origin");
}

function registerIpc() {
  ipcMain.handle("runtime:connect", async (event, payload) => {
    assertTrustedSender(event);
    if (String(payload?.apiUrl || "").replace(/\/$/, "") !== desktopConfig.apiUrl.replace(/\/$/, "")) {
      throw new Error("API 地址与桌面配置不一致");
    }
    runtimeSocket.connect(payload);
    return { ok: true };
  });
  ipcMain.handle("runtime:disconnect", async (event) => {
    assertTrustedSender(event);
    runtimeSocket.disconnect();
    return { ok: true };
  });
  ipcMain.handle("lark:status", async (event) => {
    assertTrustedSender(event);
    return larkCliManager.status();
  });
  ipcMain.handle("lark:ensure-latest", async (event) => {
    assertTrustedSender(event);
    return larkCliManager.ensureLatest({ force: true });
  });
}

function configurationErrorPage() {
  const html = `<!doctype html><meta charset="utf-8"><title>Agent7 配置</title>
  <style>body{font-family:system-ui;margin:0;background:#f7f7f5;color:#171717;display:grid;place-items:center;height:100vh}.box{max-width:620px;padding:32px}code{background:#eee;padding:2px 6px;border-radius:4px}</style>
  <div class="box"><h1>缺少客户端服务器配置</h1><p>请在应用数据目录创建 <code>config.json</code>，配置 HTTPS 的 <code>appUrl</code> 与 <code>apiUrl</code> 后重新启动。</p></div>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1040,
    minHeight: 700,
    show: false,
    backgroundColor: "#f7f7f5",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [
        `--agent7-api-url=${encodeURIComponent(desktopConfig.apiUrl)}`,
      ],
    },
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) void shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!trustedOrigin(url)) event.preventDefault();
  });
  await mainWindow.loadURL(
    desktopConfig.appUrl && desktopConfig.apiUrl ? desktopConfig.appUrl : configurationErrorPage()
  );
}

app.whenReady().then(async () => {
  desktopConfig = loadConfig();
  larkCliManager = new LarkCliManager({
    userDataDir: app.getPath("userData"),
    autoUpdate: desktopConfig.autoUpdateLarkCli,
  });
  runtimeSocket = new RuntimeSocket({
    larkCliManager,
    onStatus: (status) => mainWindow?.webContents.send("runtime:status", status),
  });
  registerIpc();
  await createWindow();
  void larkCliManager.ensureLatest();
});

app.on("window-all-closed", () => {
  runtimeSocket?.disconnect();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) void createWindow();
});
