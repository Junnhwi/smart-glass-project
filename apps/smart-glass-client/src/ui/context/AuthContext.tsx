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

type StoredAuthSession = {
  user: SignInInput | null;
  deviceAliases?: Record<string, string>;
};

type AuthContextValue = {
  currentUser: AuthUser | null;
  isHydrating: boolean;
  deviceAliases: Record<string, string>;
  signIn: (input: SignInInput) => void;
  setCurrentDevice: (deviceId?: string | null) => void;
  setDeviceAlias: (deviceId: string, alias?: string | null) => void;
  getDeviceLabel: (deviceId?: string | null) => string;
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

const normalizeDeviceAliases = (value: unknown): Record<string, string> => {
  if (!value || typeof value !== 'object') {
    return {};
  }

  return Object.entries(value as Record<string, unknown>).reduce<
    Record<string, string>
  >((acc, [key, rawAlias]) => {
    const normalizedKey = normalizeText(key);
    const normalizedAlias =
      typeof rawAlias === 'string' ? normalizeText(rawAlias) : '';
    if (normalizedKey && normalizedAlias) {
      acc[normalizedKey] = normalizedAlias;
    }
    return acc;
  }, {});
};

const parseStoredAuthSession = (
  rawValue: string | null
): { user: AuthUser | null; deviceAliases: Record<string, string> } => {
  if (!rawValue) {
    return {
      user: null,
      deviceAliases: {},
    };
  }

  try {
    const parsed = JSON.parse(rawValue) as StoredAuthSession | SignInInput | null;
    if (!parsed || typeof parsed !== 'object') {
      return {
        user: null,
        deviceAliases: {},
      };
    }

    if ('user' in parsed || 'deviceAliases' in parsed) {
      const storedSession = parsed as StoredAuthSession;
      return {
        user:
          storedSession.user && typeof storedSession.user === 'object'
            ? buildAuthUser(storedSession.user)
            : null,
        deviceAliases: normalizeDeviceAliases(storedSession.deviceAliases),
      };
    }

    return {
      user: buildAuthUser(parsed as SignInInput),
      deviceAliases: {},
    };
  } catch {
    return {
      user: null,
      deviceAliases: {},
    };
  }
};

const readStoredAuthSession = (): {
  user: AuthUser | null;
  deviceAliases: Record<string, string>;
} => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return {
      user: null,
      deviceAliases: {},
    };
  }

  try {
    return parseStoredAuthSession(window.localStorage.getItem(AUTH_STORAGE_KEY));
  } catch {
    return {
      user: null,
      deviceAliases: {},
    };
  }
};

const persistAuthSession = async ({
  user,
  deviceAliases,
}: {
  user: AuthUser | null;
  deviceAliases: Record<string, string>;
}) => {
  const payload: StoredAuthSession = {
    user,
    deviceAliases,
  };

  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    try {
      if (!user) {
        const hasAliases = Object.keys(deviceAliases).length > 0;
        if (!hasAliases) {
          await SecureStore.deleteItemAsync(AUTH_STORAGE_KEY);
          return;
        }
      }

      await SecureStore.setItemAsync(AUTH_STORAGE_KEY, JSON.stringify(payload));
    } catch {
      // Ignore device storage failures in favor of keeping the in-memory session alive.
    }
    return;
  }

  try {
    if (!user) {
      const hasAliases = Object.keys(deviceAliases).length > 0;
      if (!hasAliases) {
        window.localStorage.removeItem(AUTH_STORAGE_KEY);
        return;
      }
    }
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Ignore browser storage failures in favor of keeping the in-memory session alive.
  }
};

const restorePersistedAuthSession = async (): Promise<{
  user: AuthUser | null;
  deviceAliases: Record<string, string>;
}> => {
  if (Platform.OS === 'web') {
    return readStoredAuthSession();
  }

  try {
    const rawValue = await SecureStore.getItemAsync(AUTH_STORAGE_KEY);
    return parseStoredAuthSession(rawValue);
  } catch {
    return {
      user: null,
      deviceAliases: {},
    };
  }
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const initialSession = readStoredAuthSession();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(
    initialSession.user
  );
  const [deviceAliases, setDeviceAliases] = useState<Record<string, string>>(
    initialSession.deviceAliases
  );
  const [isHydrating, setIsHydrating] = useState(Platform.OS !== 'web');

  useEffect(() => {
    if (Platform.OS === 'web') {
      setIsHydrating(false);
      return;
    }

    let isActive = true;

    void (async () => {
      const restoredSession = await restorePersistedAuthSession();
      if (!isActive) {
        return;
      }

      setCurrentUser(restoredSession.user);
      setDeviceAliases(restoredSession.deviceAliases);
      setIsHydrating(false);
    })();

    return () => {
      isActive = false;
    };
  }, []);

  const signIn = (input: SignInInput) => {
    const nextUser = buildAuthUser(input);
    setCurrentUser(nextUser);
    void persistAuthSession({
      user: nextUser,
      deviceAliases,
    });
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
      void persistAuthSession({
        user: nextUser,
        deviceAliases,
      });
      return nextUser;
    });
  };

  const setDeviceAlias = (deviceId: string, alias?: string | null) => {
    const normalizedDeviceId = normalizeText(deviceId);
    const normalizedAlias = normalizeText(alias);
    if (!normalizedDeviceId) {
      return;
    }

    setDeviceAliases((prev) => {
      const nextAliases = { ...prev };
      if (normalizedAlias) {
        nextAliases[normalizedDeviceId] = normalizedAlias;
      } else {
        delete nextAliases[normalizedDeviceId];
      }

      void persistAuthSession({
        user: currentUser,
        deviceAliases: nextAliases,
      });
      return nextAliases;
    });
  };

  const getDeviceLabel = (deviceId?: string | null) => {
    const normalizedDeviceId = normalizeText(deviceId);
    if (!normalizedDeviceId) {
      return '선택된 기기 없음';
    }

    return deviceAliases[normalizedDeviceId] || normalizedDeviceId;
  };

  const signOut = async () => {
    const activeUser = currentUser;
    setCurrentUser(null);
    void persistAuthSession({
      user: null,
      deviceAliases,
    });

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
        deviceAliases,
        signIn,
        setCurrentDevice,
        setDeviceAlias,
        getDeviceLabel,
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
