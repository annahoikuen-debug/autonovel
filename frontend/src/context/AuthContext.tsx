import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { AUTH_TOKEN_STORAGE_KEY, readAuthToken, clearAuthToken } from '../api/client';

interface User {
  id: number;
  email: string;
  display_name: string;
  role: string;
  credits: number;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  register: (email: string, password: string, display_name: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({} as AuthContextType);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // トークンは api/client.ts と **同じキー** に置く。以前はここが `token` に
  // 書いていたため apiFetch が読めず、ログインしても全リクエストが 401 になっていた。
  // トークンが無い状態（未ログイン）もそのまま描画する（クラッシュさせない）。
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(() => readAuthToken());

  const logout = useCallback(() => {
    // サーバ側でこのトークンを失効 (denylist) させてからローカルを消す。
    // これを省くと JWT は `exp` まで有効なまま残り、ログアウトが形骸化する。
    // トークンが既に無効・期限切れでもログアウト体験は成立させるため、
    // 失敗は握りつぶしてローカルの消去は必ず実行する (fire-and-forget)。
    const accessToken = readAuthToken();
    if (accessToken) {
      void fetch('/api/auth/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      }).catch(() => undefined);
    }
    setToken(null);
    setUser(null);
    clearAuthToken();
  }, []);

  useEffect(() => {
    if (token) {
      void fetchProfile();
    }
  }, [token]);

  const fetchProfile = async () => {
    try {
      const response = await fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) {
        throw new Error('Failed to fetch profile');
      }
      const data = await response.json();
      setUser(data);
    } catch {
      logout();
    }
  };

  const login = async (email: string, password: string) => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) {
      throw new Error('Login failed');
    }
    const data = await response.json();
    const { access_token } = data;
    setToken(access_token);
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, access_token);
  };

  const register = async (email: string, password: string, display_name: string) => {
    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ email, password, display_name })
    });
    if (!response.ok) {
      throw new Error('Registration failed');
    }
    const data = await response.json();
    // 登録直後のユーザー情報をコンテキストに反映する。
    // バックエンドの register エンドポイントは UserProfileResponse を返すため、
    // id / email / display_name / role / credits を含む。
    if (data && typeof data === "object") {
      setUser({
        id: data.id ?? 0,
        email: data.email ?? email,
        display_name: data.display_name ?? display_name,
        role: data.role ?? "user",
        credits: data.credits ?? 0,
      });
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, register }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
