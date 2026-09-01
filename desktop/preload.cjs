const { contextBridge, ipcRenderer } = require("electron");

function argumentValue(name) {
  const prefix = `--${name}=`;
  const value = process.argv.find((item) => item.startsWith(prefix));
  return value ? decodeURIComponent(value.slice(prefix.length)) : "";
}

const runtimeListeners = new Set();
ipcRenderer.on("runtime:status", (_event, status) => {
  for (const listener of runtimeListeners) listener(status);
});

contextBridge.exposeInMainWorld("agentDesktop", {
  isDesktop: true,
  config: {
    apiUrl: argumentValue("agent7-api-url"),
  },
  runtime: {
    connect: (payload) => ipcRenderer.invoke("runtime:connect", payload),
    disconnect: () => ipcRenderer.invoke("runtime:disconnect"),
    onStatus: (listener) => {
      runtimeListeners.add(listener);
      return () => runtimeListeners.delete(listener);
    },
  },
  lark: {
    status: () => ipcRenderer.invoke("lark:status"),
    ensureLatest: () => ipcRenderer.invoke("lark:ensure-latest"),
  },
});
