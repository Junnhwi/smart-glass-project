import React, { createContext, useContext, useState } from 'react';

import { logoutAuthSession } from '../../networking/api';

export type AuthProviderName = 'demo' | 'password' | 'google';

export type AuthUser = {
  userId: string;
  deviceId: string;
  displayName: string;
  authToken: string;
  refreshToken?: string | null;
  email?: string | null;
  authProvider: AuthProviderName;
};

type SignInInput = {
  userId: string;
  deviceId: string;
  displayName?: string | null;
  authToken?: string | null;
  refreshToken?: string | null;
  email?: string | null;
  authProvider?: AuthProviderName;
};

type AuthContextValue = {
  currentUser: AuthUser | null;
  signIn: (input: SignInInput) => void;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const normalizeText = (value: string | null | undefined) =>
  String(value ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');

const buildDemoAuthToken = (userId: string) => `demo-user:${userId}`;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  const signIn = (input: SignInInput) => {
    const userId = normalizeText(input.userId);
    const deviceId = normalizeText(input.deviceId);
    if (!userId) {
      throw new Error('userId is required');
    }
    if (!deviceId) {
      throw new Error('deviceId is required');
    }

    const displayName = normalizeText(input.displayName) || userId;
    const authToken =
      normalizeText(input.authToken) || buildDemoAuthToken(userId);
    const email = normalizeText(input.email) || null;
    const refreshToken = normalizeText(input.refreshToken) || null;
    const authProvider =
      input.authProvider || (input.authToken ? 'password' : 'demo');

    setCurrentUser({
      userId,
      deviceId,
      displayName,
      authToken,
      refreshToken,
      email,
      authProvider,
    });
  };

  const signOut = async () => {
    const activeUser = currentUser;
    setCurrentUser(null);

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
    <AuthContext.Provider value={{ currentUser, signIn, signOut }}>
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
