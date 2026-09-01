"use client";

const TOKEN_KEY = "sevn:access-token";

export interface AuthUser {
  id: number;
  email: string;
  display_name?: string | null;
  avatar_url?: string | null;
}

export interface AuthResult {
  access_token: string;
  token_type: "bearer";
  user: AuthUser;
}

export function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setStoredAccessToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredAccessToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export function buildAuthHeaders(headers?: HeadersInit): Headers {
  const merged = new Headers(headers);
  const token = getStoredAccessToken();
  if (token) {
    merged.set("Authorization", `Bearer ${token}`);
  }
  return merged;
}

export async function authorizedFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const headers = buildAuthHeaders(init?.headers);
  const response = await fetch(input, {
    ...init,
    headers,
  });

  if (response.status === 401) {
    clearStoredAccessToken();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("sevn:auth-expired"));
    }
  }

  return response;
}
