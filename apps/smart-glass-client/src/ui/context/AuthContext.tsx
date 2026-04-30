import React, { createContext, useContext, useState } from 'react';

export type AuthUser = {
  userId: string;
  displayName: string;
};

type AuthContextValue = {
  currentUser: AuthUser | null;
  signIn: (input: { userId: string; displayName?: string | null }) => void;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const normalizeText = (value: string | null | undefined) =>
  String(value ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  const signIn = (input: { userId: string; displayName?: string | null }) => {
    const userId = normalizeText(input.userId);
    if (!userId) {
      throw new Error('userId is required');
    }

    const displayName = normalizeText(input.displayName) || userId;
    setCurrentUser({ userId, displayName });
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
