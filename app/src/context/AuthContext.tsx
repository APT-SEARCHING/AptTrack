import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import api, { UserProfile } from '../services/api';

interface AuthState {
  token: string | null;
  user: UserProfile | null;
  loading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = 'apttrack_token';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AuthState>({ token: null, user: null, loading: true });

  // On mount: restore token from localStorage and fetch profile
  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_KEY);
    if (!saved) { setState(s => ({ ...s, loading: false })); return; }
    api.getMe(saved)
      .then(user => setState({ token: saved, user, loading: false }))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setState({ token: null, user: null, loading: false });
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.login(email, password);
    const user = await api.getMe(access_token);
    localStorage.setItem(TOKEN_KEY, access_token);
    setState({ token: access_token, user, loading: false });
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.register(email, password);
    const user = await api.getMe(access_token);
    localStorage.setItem(TOKEN_KEY, access_token);
    setState({ token: access_token, user, loading: false });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setState({ token: null, user: null, loading: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
