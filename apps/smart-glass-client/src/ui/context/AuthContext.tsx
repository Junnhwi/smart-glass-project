import React, { createContext, useContext, useState } from 'react';
import { Platform } from 'react-native';

import { logoutAuthSession } from '../../networking/api';

export type AuthProviderName = 'demo' | 'password' | 'google';

export type AuthUser = {
  userId: string;
  deviceId?: string | null;
  displayName: string;
  authToken: string;
  refreshToken?: string | null;
  email?: string | null;
  authProvider: AuthProviderName;
};

type SignInInput = {
  userId: string;
  deviceId?: string | null;
  displayName?: string | null;
  authToken?: string | null;
  refreshToken?: string | null;
  email?: string | null;
  authProvider?: AuthProviderName;
};

type AuthContextValue = {
  currentUser: AuthUser | null;
  signIn: (input: SignInInput) => void;
  setCurrentDevice: (deviceId?: string | null) => void;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const AUTH_STORAGE_KEY = 'smart-glass-client.auth-session';

const normalizeText = (value: string | null | undefined) =>
  String(value ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');

const buildDemoAuthToken = (userId: string) => `demo-user:${userId}`;

const buildAuthUser = (input: SignInInput): AuthUser => {
  const userId = normalizeText(input.userId);
  const deviceId = normalizeText(input.deviceId);
  if (!userId) {
    throw new Error('userId is required');
  }

  const displayName = normalizeText(input.displayName) || userId;
  const authToken =
    normalizeText(input.authToken) || buildDemoAuthToken(userId);
  const email = normalizeText(input.email) || null;
  const refreshToken = normalizeText(input.refreshToken) || null;
  const authProvider =
    input.authProvider || (input.authToken ? 'password' : 'demo');

  return {
    userId,
    deviceId: deviceId || null,
    displayName,
    authToken,
    refreshToken,
    email,
    authProvider,
  };
};

const readStoredAuthUser = (): AuthUser | null => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return null;
  }

  try {
    const rawValue = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!rawValue) {
      return null;
    }
    const parsed = JSON.parse(rawValue) as SignInInput | null;
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }
    return buildAuthUser(parsed);
  } catch {
    return null;
  }
};

const persistAuthUser = (user: AuthUser | null) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return;
  }

  try {
    if (!user) {
      window.localStorage.removeItem(AUTH_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
  } catch {
    // Ignore browser storage failures in favor of keeping the in-memory session alive.
  }
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(() =>
    readStoredAuthUser()
  );

  const signIn = (input: SignInInput) => {
    const nextUser = buildAuthUser(input);
    setCurrentUser(nextUser);
    persistAuthUser(nextUser);
  };

  const setCurrentDevice = (deviceId?: string | null) => {
    const normalizedDeviceId = normalizeText(deviceId);

    setCurrentUser((prev) => {
      if (!prev) {
        return prev;
      }

      const nextUser = {
        ...prev,
        deviceId: normalizedDeviceId || null,
      };
      persistAuthUser(nextUser);
      return nextUser;
    });
  };

  const signOut = async () => {
    const activeUser = currentUser;
    setCurrentUser(null);
    persistAuthUser(null);

    if (!activeUser) {
      return;
    }

    const isDemoUser =
      activeUser.authProvider === 'demo' ||
      activeUser.authToken.startsWith('demo-user:');
    if (isDemoUser && !activeUser.refreshToken) {
      return;
    }

    try {
      await logoutAuthSession({
        authToken: activeUser.authToken,
        refreshToken: activeUser.refreshToken,
      });
    } catch {
      // Clear the local session even if the remote logout request fails.
    }
  };

  return (
    <AuthContext.Provider
      value={{ currentUser, signIn, setCurrentDevice, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}
