import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";

import { getMe, verifyToken } from "./api";
import { signInWithGoogle } from "./firebaseAuth";
import type { AuthUser, UserProfile } from "./types";

const TOKEN_STORAGE_KEY = "soundcloud_auth_token";

interface AuthContextValue {
  token: string | null;
  user: AuthUser | null;
  profile: UserProfile | null;
  loading: boolean;
  loginWithToken: (idToken: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  setProfile: (profile: UserProfile | null) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function loadSession(idToken: string): Promise<{ user: AuthUser; profile: UserProfile | null }> {
  const user = await verifyToken(idToken);
  try {
    const profile = await getMe(idToken);
    return { user, profile };
  } catch {
    return { user, profile: null };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [user, setUser] = useState<AuthUser | null>(null);
  const [profile, setProfileState] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);

    void loadSession(token)
      .then((session) => {
        if (!active) return;
        setUser(session.user);
        setProfileState(session.profile);
      })
      .catch(() => {
        if (!active) return;
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setToken(null);
        setUser(null);
        setProfileState(null);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [token]);

  async function loginWithToken(idToken: string): Promise<void> {
    const session = await loadSession(idToken);
    localStorage.setItem(TOKEN_STORAGE_KEY, idToken);
    setToken(idToken);
    setUser(session.user);
    setProfileState(session.profile);
  }

  async function loginWithGoogle(): Promise<void> {
    const idToken = await signInWithGoogle();
    await loginWithToken(idToken);
  }

  async function refreshProfile(): Promise<void> {
    if (!token) return;
    const nextProfile = await getMe(token);
    setProfileState(nextProfile);
  }

  function setProfile(nextProfile: UserProfile | null) {
    setProfileState(nextProfile);
  }

  function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setProfileState(null);
  }

  const value = useMemo<AuthContextValue>(
    () => ({ token, user, profile, loading, loginWithToken, loginWithGoogle, refreshProfile, setProfile, logout }),
    [token, user, profile, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return ctx;
}
