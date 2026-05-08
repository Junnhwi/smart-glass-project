import * as SecureStore from 'expo-secure-store';
import React, { createContext, useContext, useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { logoutAuthSession } from '../../networking/api';

export type AuthProviderName = 'password' | 'google';

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
  isHydrating: boolean;
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

const buildAuthUser = (input: SignInInput): AuthUser => {
  const userId = normalizeText(input.userId);
  const deviceId = normalizeText(input.deviceId);
  const authToken = normalizeText(input.authToken);

  if (!userId) {
    throw new Error('userId is required');
  }
  if (!authToken) {
    throw new Error('authToken is required');
  }

  const displayName = normalizeText(input.displayName) || userId;
  const email = normalizeText(input.email) || null;
  const refreshToken = normalizeText(input.refreshToken) || null;

  return {
    userId,
    deviceId: deviceId || null,
    displayName,
    authToken,
    refreshToken,
    email,
    authProvider: input.authProvider || 'password',
  };
};

const parseStoredAuthUser = (rawValue: string | null): AuthUser | null => {
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue) as SignInInput | null;
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }
    return buildAuthUser(parsed);
  } catch {
    return null;
  }
};

const readStoredAuthUser = (): AuthUser | null => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return null;
  }

  try {
    return parseStoredAuthUser(window.localStorage.getItem(AUTH_STORAGE_KEY));
  } catch {
    return null;
  }
};

const persistAuthUser = async (user: AuthUser | null) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    try {
      if (!user) {
        await SecureStore.deleteItemAsync(AUTH_STORAGE_KEY);
        return;
      }

      await SecureStore.setItemAsync(AUTH_STORAGE_KEY, JSON.stringify(user));
    } catch {
      // Ignore device storage failures in favor of keeping the in-memory session alive.
    }
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

const restorePersistedAuthUser = async (): Promise<AuthUser | null> => {
  if (Platform.OS === 'web') {
    return readStoredAuthUser();
  }

  try {
    const rawValue = await SecureStore.getItemAsync(AUTH_STORAGE_KEY);
    return parseStoredAuthUser(rawValue);
  } catch {
    return null;
  }
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(() =>
    readStoredAuthUser()
  );
  const [isHydrating, setIsHydrating] = useState(Platform.OS !== 'web');

  useEffect(() => {
    if (Platform.OS === 'web') {
      setIsHydrating(false);
      return;
    }

    let isActive = true;

    void (async () => {
      const restoredUser = await restorePersistedAuthUser();
      if (!isActive) {
        return;
      }

      setCurrentUser(restoredUser);
      setIsHydrating(false);
    })();

    return () => {
      isActive = false;
    };
  }, []);

  const signIn = (input: SignInInput) => {
    const nextUser = buildAuthUser(input);
    setCurrentUser(nextUser);
    void persistAuthUser(nextUser);
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
      void persistAuthUser(nextUser);
      return nextUser;
    });
  };

  const signOut = async () => {
    const activeUser = currentUser;
    setCurrentUser(null);
    void persistAuthUser(null);

    if (!activeUser) {
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
      value={{
        currentUser,
        isHydrating,
        signIn,
        setCurrentDevice,
        signOut,
      }}
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
