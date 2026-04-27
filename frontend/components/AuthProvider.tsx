"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  clearStoredAccessToken,
  setStoredAccessToken,
  type AuthResult,
  type AuthUser,
} from "@/lib/auth";
import {
  fetchCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
  sendRegisterCode,
} from "@/lib/api";

interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  requestRegisterCode: (email: string) => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (payload: {
    email: string;
    password: string;
    code: string;
    display_name?: string;
  }) => Promise<void>;
  signOut: () => Promise<void>;
  refreshCurrentUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function applyAuthResult(result: AuthResult) {
  setStoredAccessToken(result.access_token);
  return result.user;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const clearAuth = useCallback(() => {
    clearStoredAccessToken();
    setAccessToken(null);
    setUser(null);
  }, []);

  const refreshCurrentUser = useCallback(async () => {
    try {
      const response = await fetchCurrentUser();
      setUser(response.user);
    } catch {
      clearAuth();
    }
  }, [clearAuth]);

  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? window.localStorage.getItem("sevn:access-token")
        : null;
    if (!token) {
      setLoading(false);
      return;
    }

    setAccessToken(token);
    void refreshCurrentUser().finally(() => setLoading(false));
  }, [refreshCurrentUser]);

  useEffect(() => {
    const handler = () => {
      clearAuth();
      setLoading(false);
    };
    window.addEventListener("sevn:auth-expired", handler);
    return () => window.removeEventListener("sevn:auth-expired", handler);
  }, [clearAuth]);

  const requestRegisterCode = useCallback(async (email: string) => {
    await sendRegisterCode(email);
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await loginUser({ email, password });
    const nextUser = applyAuthResult(result);
    setAccessToken(result.access_token);
    setUser(nextUser);
  }, []);

  const signUp = useCallback(
    async (payload: {
      email: string;
      password: string;
      code: string;
      display_name?: string;
    }) => {
      const result = await registerUser(payload);
      const nextUser = applyAuthResult(result);
      setAccessToken(result.access_token);
      setUser(nextUser);
    },
    []
  );

  const signOut = useCallback(async () => {
    try {
      await logoutUser();
    } catch {
      // ignore and clear local state anyway
    } finally {
      clearAuth();
    }
  }, [clearAuth]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      accessToken,
      loading,
      isAuthenticated: !!user && !!accessToken,
      requestRegisterCode,
      signIn,
      signUp,
      signOut,
      refreshCurrentUser,
    }),
    [
      user,
      accessToken,
      loading,
      requestRegisterCode,
      signIn,
      signUp,
      signOut,
      refreshCurrentUser,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
