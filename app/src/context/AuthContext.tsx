import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import api, { UserProfile } from '../services/api';

interface AuthState {
  token: string | null;
  user: UserProfile | null;
  loading: boolean;
  favoriteIds: Set<number>;
  activeAlertsCount: number;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  toggleFavorite: (apartmentId: number) => Promise<void>;
  isFavorite: (apartmentId: number) => boolean;
  updateAlertCount: (n: number) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = 'apttrack_token';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AuthState>({
    token: null, user: null, loading: true, favoriteIds: new Set(), activeAlertsCount: 0,
  });

  // On mount: restore token, fetch profile + favorites + alert count in parallel
  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_KEY);
    if (!saved) { setState(s => ({ ...s, loading: false })); return; }
    Promise.all([api.getMe(saved), api.getFavorites(saved), api.getSubscriptions(saved)])
      .then(([user, ids, subs]) =>
        setState({
          token: saved, user, loading: false,
          favoriteIds: new Set(ids),
          activeAlertsCount: subs.filter(s => s.is_active).length,
        })
      )
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setState({ token: null, user: null, loading: false, favoriteIds: new Set(), activeAlertsCount: 0 });
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.login(email, password);
    const [user, ids, subs] = await Promise.all([
      api.getMe(access_token),
      api.getFavorites(access_token),
      api.getSubscriptions(access_token),
    ]);
    localStorage.setItem(TOKEN_KEY, access_token);
    setState({
      token: access_token, user, loading: false,
      favoriteIds: new Set(ids),
      activeAlertsCount: subs.filter(s => s.is_active).length,
    });
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.register(email, password);
    const user = await api.getMe(access_token);
    localStorage.setItem(TOKEN_KEY, access_token);
    setState({ token: access_token, user, loading: false, favoriteIds: new Set(), activeAlertsCount: 0 });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setState({ token: null, user: null, loading: false, favoriteIds: new Set(), activeAlertsCount: 0 });
  }, []);

  const updateAlertCount = useCallback((n: number) => {
    setState(s => ({ ...s, activeAlertsCount: n }));
  }, []);

  const toggleFavorite = useCallback(async (apartmentId: number) => {
    setState(prev => {
      if (!prev.token) return prev;
      const next = new Set(prev.favoriteIds);
      if (next.has(apartmentId)) {
        next.delete(apartmentId);
        api.removeFavorite(prev.token, apartmentId).catch(() => {
          // rollback on failure
          setState(s => ({ ...s, favoriteIds: new Set(Array.from(s.favoriteIds).concat(apartmentId)) }));
        });
      } else {
        next.add(apartmentId);
        api.addFavorite(prev.token, apartmentId).catch(() => {
          // rollback on failure
          setState(s => {
            const rb = new Set(s.favoriteIds);
            rb.delete(apartmentId);
            return { ...s, favoriteIds: rb };
          });
        });
      }
      return { ...prev, favoriteIds: next };
    });
  }, []);

  const isFavorite = useCallback(
    (apartmentId: number) => state.favoriteIds.has(apartmentId),
    [state.favoriteIds],
  );

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, toggleFavorite, isFavorite, updateAlertCount }}>
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
