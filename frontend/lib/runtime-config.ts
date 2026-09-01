const DEFAULT_API_URL = "http://localhost:6868";

export function getApiBaseUrl(): string {
  const desktopUrl =
    typeof window !== "undefined" ? window.agentDesktop?.config.apiUrl : undefined;
  return (desktopUrl || process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/$/, "");
}
