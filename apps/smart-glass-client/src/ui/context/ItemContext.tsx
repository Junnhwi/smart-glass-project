import React, { createContext, useContext, useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { useAuth } from './AuthContext';

type ItemData = {
  count: number;
  lastTime: number;
};

type ItemContextType = {
  itemCounts: Record<string, ItemData>;
  addItem: (item: string) => void;
};

const ItemContext = createContext<ItemContextType | null>(null);

const buildStorageKey = (userId: string) =>
  `smart-glass-client.item-history.${userId}`;

const readStoredItemCounts = (userId: string): Record<string, ItemData> => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return {};
  }

  try {
    const rawValue = window.localStorage.getItem(buildStorageKey(userId));
    if (!rawValue) {
      return {};
    }

    const parsed = JSON.parse(rawValue) as Record<string, ItemData> | null;
    if (!parsed || typeof parsed !== 'object') {
      return {};
    }

    return Object.entries(parsed).reduce<Record<string, ItemData>>(
      (acc, [item, value]) => {
        if (
          !value ||
          typeof value !== 'object' ||
          typeof value.count !== 'number' ||
          typeof value.lastTime !== 'number'
        ) {
          return acc;
        }

        acc[item] = {
          count: value.count,
          lastTime: value.lastTime,
        };
        return acc;
      },
      {}
    );
  } catch {
    return {};
  }
};

const persistItemCounts = (
  userId: string,
  itemCounts: Record<string, ItemData>
) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(
      buildStorageKey(userId),
      JSON.stringify(itemCounts)
    );
  } catch {
    // Ignore browser storage failures and keep in-memory history available.
  }
};

export const ItemProvider = ({ children }: { children: React.ReactNode }) => {
  const { currentUser } = useAuth();
  const [itemCounts, setItemCounts] = useState<Record<string, ItemData>>({});

  useEffect(() => {
    if (!currentUser?.userId) {
      setItemCounts({});
      return;
    }

    setItemCounts(readStoredItemCounts(currentUser.userId));
  }, [currentUser?.userId]);

  const addItem = (item: string) => {
    if (!currentUser?.userId) {
      return;
    }

    setItemCounts((prev) => {
      const existing = prev[item];
      const nextItemCounts = {
        ...prev,
        [item]: {
          count: existing ? existing.count + 1 : 1,
          lastTime: Date.now(),
        },
      };

      persistItemCounts(currentUser.userId, nextItemCounts);
      return nextItemCounts;
    });
  };

  return (
    <ItemContext.Provider value={{ itemCounts, addItem }}>
      {children}
    </ItemContext.Provider>
  );
};

export const useItemContext = () => {
  const context = useContext(ItemContext);

  if (!context) {
    throw new Error('ItemContext 사용 오류');
  }

  return context;
};
