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
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, register }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
