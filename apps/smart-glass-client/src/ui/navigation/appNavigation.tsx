import React, { createContext, useContext, useMemo, useState } from 'react';
import { Platform } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import type { RootStackParamList } from './routes';

type RouteName = keyof RootStackParamList;

type RouteState<T extends RouteName = RouteName> = {
  name: T;
  params?: RootStackParamList[T];
};

type AppNavigationValue = {
  currentRoute?: RouteState;
  navigate: <T extends RouteName>(
    screen: T,
    params?: RootStackParamList[T]
  ) => void;
  goBack: () => void;
};

const WebNavigationContext = createContext<AppNavigationValue | null>(null);

const buildRouteState = <T extends RouteName>(
  name: T,
  params?: RootStackParamList[T]
): RouteState<T> => ({
  name,
  params,
});

export function WebNavigationProvider({
  children,
  initialRouteName,
}: {
  children: React.ReactNode;
  initialRouteName: RouteName;
}) {
  const [history, setHistory] = useState<RouteState[]>([
    buildRouteState(initialRouteName),
  ]);

  const value = useMemo<AppNavigationValue>(() => {
    const currentRoute = history[history.length - 1] || buildRouteState('Chat');

    return {
      currentRoute,
      navigate: (screen, params) => {
        setHistory((prev) => [...prev, buildRouteState(screen, params)]);
      },
      goBack: () => {
        setHistory((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev));
      },
    };
  }, [history]);

  return (
    <WebNavigationContext.Provider value={value}>
      {children}
    </WebNavigationContext.Provider>
  );
}

export function useAppNavigation() {
  if (Platform.OS === 'web') {
    const context = useContext(WebNavigationContext);
    if (!context) {
      throw new Error(
        'useAppNavigation must be used inside a WebNavigationProvider on web.'
      );
    }
    return context;
  }

  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  return {
    currentRoute: undefined,
    navigate: navigation.navigate,
    goBack: navigation.goBack,
  };
}

export function useAppRoute<T extends RouteName>() {
  if (Platform.OS === 'web') {
    const context = useContext(WebNavigationContext);
    if (!context?.currentRoute) {
      throw new Error(
        'useAppRoute must be used inside a WebNavigationProvider on web.'
      );
    }

    return context.currentRoute as RouteState<T>;
  }

  const route = useRoute<RouteProp<RootStackParamList, T>>();
  return {
    name: route.name,
    params: route.params,
  } as RouteState<T>;
}
