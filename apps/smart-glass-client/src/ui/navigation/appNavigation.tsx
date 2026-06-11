import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
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
  canGoBack: boolean;
  transitionDirection: 1 | -1;
};

const WebNavigationContext = createContext<AppNavigationValue | null>(null);
const WEB_HISTORY_STATE_KEY = 'smartGlassRoute';
const WEB_HISTORY_INDEX_KEY = 'smartGlassRouteIndex';

const ROUTE_NAMES: RouteName[] = [
  'Login',
  'Capture',
  'Chat',
  'History',
  'Profile',
  'Settings',
  'ItemLocation',
];

const buildRouteState = <T extends RouteName>(
  name: T,
  params?: RootStackParamList[T]
): RouteState<T> => ({
  name,
  params,
});

const isKnownRouteName = (value: string | null | undefined): value is RouteName =>
  Boolean(value && ROUTE_NAMES.includes(value as RouteName));

const getWindowRouteState = (
  fallbackRouteName: RouteName
): RouteState<RouteName> => {
  if (typeof window === 'undefined') {
    return buildRouteState(fallbackRouteName);
  }

  const stateRoute = (window.history.state || {})[
    WEB_HISTORY_STATE_KEY
  ] as RouteState<RouteName> | undefined;
  if (stateRoute?.name && isKnownRouteName(stateRoute.name)) {
    return buildRouteState(
      stateRoute.name,
      stateRoute.params as RootStackParamList[RouteName]
    );
  }

  const hash = window.location.hash.replace(/^#/, '');
  const searchParams = new URLSearchParams(hash);
  const routeName = searchParams.get('route');
  if (!isKnownRouteName(routeName)) {
    return buildRouteState(fallbackRouteName);
  }

  if (routeName === 'ItemLocation') {
    const itemName = searchParams.get('itemName') || undefined;
    return buildRouteState('ItemLocation', itemName ? { itemName } : undefined);
  }

  return buildRouteState(routeName);
};

const buildWebUrl = (route: RouteState<RouteName>) => {
  if (typeof window === 'undefined') {
    return '';
  }

  const hashParams = new URLSearchParams();
  hashParams.set('route', route.name);
  if (route.name === 'ItemLocation' && route.params?.itemName) {
    hashParams.set('itemName', route.params.itemName);
  }

  const nextHash = hashParams.toString();
  return `${window.location.pathname}${window.location.search}${
    nextHash ? `#${nextHash}` : ''
  }`;
};

export function WebNavigationProvider({
  children,
  initialRouteName,
}: {
  children: React.ReactNode;
  initialRouteName: RouteName;
}) {
  const [currentRoute, setCurrentRoute] = useState<RouteState<RouteName>>(() =>
    getWindowRouteState(initialRouteName)
  );
  const [canGoBack, setCanGoBack] = useState(() =>
    typeof window !== 'undefined' ? window.history.length > 1 : false
  );
  const [transitionDirection, setTransitionDirection] = useState<1 | -1>(1);
  const routeIndexRef = useRef(0);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const resolvedRoute = getWindowRouteState(initialRouteName);
    const initialIndex =
      typeof window.history.state?.[WEB_HISTORY_INDEX_KEY] === 'number'
        ? window.history.state[WEB_HISTORY_INDEX_KEY]
        : 0;
    routeIndexRef.current = initialIndex;
    setCurrentRoute(resolvedRoute);
    window.history.replaceState(
      {
        ...(window.history.state || {}),
        [WEB_HISTORY_STATE_KEY]: resolvedRoute,
        [WEB_HISTORY_INDEX_KEY]: initialIndex,
      },
      document.title,
      buildWebUrl(resolvedRoute)
    );
    setCanGoBack(window.history.length > 1);

    const handlePopState = () => {
      const nextIndex =
        typeof window.history.state?.[WEB_HISTORY_INDEX_KEY] === 'number'
          ? window.history.state[WEB_HISTORY_INDEX_KEY]
          : Math.max(0, routeIndexRef.current - 1);
      setTransitionDirection(nextIndex < routeIndexRef.current ? -1 : 1);
      routeIndexRef.current = nextIndex;
      setCurrentRoute(getWindowRouteState(initialRouteName));
      setCanGoBack(window.history.length > 1);
    };

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, [initialRouteName]);

  const value = useMemo<AppNavigationValue>(() => {
    return {
      currentRoute,
      transitionDirection,
      navigate: (screen, params) => {
        if (typeof window === 'undefined') {
          setTransitionDirection(1);
          setCurrentRoute(buildRouteState(screen, params));
          return;
        }

        const nextRoute = buildRouteState(screen, params);
        const nextIndex = routeIndexRef.current + 1;
        routeIndexRef.current = nextIndex;
        setTransitionDirection(1);
        window.history.pushState(
          {
            ...(window.history.state || {}),
            [WEB_HISTORY_STATE_KEY]: nextRoute,
            [WEB_HISTORY_INDEX_KEY]: nextIndex,
          },
          document.title,
          buildWebUrl(nextRoute)
        );
        setCurrentRoute(nextRoute);
        setCanGoBack(window.history.length > 1);
      },
      goBack: () => {
        if (typeof window === 'undefined') {
          return;
        }
        if (window.history.length > 1) {
          setTransitionDirection(-1);
          window.history.back();
        }
      },
      canGoBack,
    };
  }, [canGoBack, currentRoute, transitionDirection]);

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
    canGoBack: navigation.canGoBack(),
    transitionDirection: 1 as const,
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
