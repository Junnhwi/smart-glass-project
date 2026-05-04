import React, { createContext, useContext, useState } from 'react';

export type AuthUser = {
  userId: string;
  deviceId: string;
  displayName: string;
  authToken: string;
};

type AuthContextValue = {
  currentUser: AuthUser | null;
  signIn: (input: {
    userId: string;
    deviceId: string;
    displayName?: string | null;
  }) => void;
  signOut: () => void;
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

  const signIn = (input: {
    userId: string;
    deviceId: string;
    displayName?: string | null;
  }) => {
    const userId = normalizeText(input.userId);
    const deviceId = normalizeText(input.deviceId);
    if (!userId) {
      throw new Error('userId is required');
    }
    if (!deviceId) {
      throw new Error('deviceId is required');
    }

    const displayName = normalizeText(input.displayName) || userId;
    setCurrentUser({
      userId,
      deviceId,
      displayName,
      authToken: buildDemoAuthToken(userId),
    });
  };

  const signOut = () => {
    setCurrentUser(null);
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
