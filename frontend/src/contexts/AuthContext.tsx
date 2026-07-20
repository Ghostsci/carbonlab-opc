import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";

interface User {
  id: string;
  email: string;
  role: string;
  tenant_id: string | null;
  enterprise_id: string | null;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  getHeaders: () => Record<string, string>;
}

const AuthContext = createContext<AuthState | null>(null);

const API_BASE = "/api";
const CSRF_COOKIE_NAME = "csrf_token";

function getCookie(name: string): string | null {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) ?? null;
}

function getCsrfHeaders(): Record<string, string> {
  const csrfToken = getCookie(CSRF_COOKIE_NAME);
  return csrfToken ? { "X-CSRF-Token": csrfToken } : {};
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const restoreSession = async () => {
      try {
        const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: getCsrfHeaders(),
          credentials: "include",
        });
        if (!refreshRes.ok) {
          return;
        }
        const refreshData = await refreshRes.json();
        const token = refreshData.access_token as string;
        const meRes = await fetch(`${API_BASE}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
          credentials: "include",
        });
        if (!meRes.ok) {
          return;
        }
        setAccessToken(token);
        setUser(await meRes.json());
      } finally {
        setIsLoading(false);
      }
    };

    restoreSession();
  }, []);

  const persist = useCallback((at: string, u: User) => {
    setAccessToken(at);
    setUser(u);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "登录失败");
    }
    const data = await res.json();
    persist(data.access_token, data.user);
  }, [persist]);

  const register = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "注册失败");
    }
    const data = await res.json();
    persist(data.access_token, data.user);
  }, [persist]);

  const logout = useCallback(() => {
    void fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: getCsrfHeaders(),
      credentials: "include",
    });
    setAccessToken(null);
    setUser(null);
  }, []);

  const getHeaders = useCallback((): Record<string, string> => {
    return accessToken
      ? { Authorization: `Bearer ${accessToken}` }
      : {};
  }, [accessToken]);

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        isAuthenticated: !!user && !!accessToken,
        isLoading,
        login,
        register,
        logout,
        getHeaders,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
