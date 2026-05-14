import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import CaptureScreen from './src/ui/screens/CaptureScreen';
import ChatScreen from './src/ui/screens/ChatScreen';
import HistoryScreen from './src/ui/screens/HistoryScreen';
import ItemLocationScreen from './src/ui/screens/ItemLocationScreen';
import LoginScreen from './src/ui/screens/LoginScreen';
import ProfileScreen from './src/ui/screens/ProfileScreen';
import SettingsScreen from './src/ui/screens/SettingScreen';
import { AuthProvider, useAuth } from './src/ui/context/AuthContext';
import { ItemProvider } from './src/ui/context/ItemContext';
import {
  WebNavigationProvider,
  useAppNavigation,
} from './src/ui/navigation/appNavigation';

type ErrorBoundaryState = {
  errorMessage: string | null;
};

class WebErrorBoundary extends React.Component<
  { children: React.ReactNode },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = {
    errorMessage: null,
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      errorMessage: error?.message || 'Unknown web render error.',
    };
  }

  componentDidCatch(error: Error) {
    console.error('smart-glass-client web render error', error);
  }

  render() {
    if (this.state.errorMessage) {
      return (
        <View style={styles.errorShell}>
          <Text style={styles.errorTitle}>Web client failed to render</Text>
          <Text style={styles.errorMessage}>{this.state.errorMessage}</Text>
        </View>
      );
    }

    return this.props.children;
  }
}

function AuthenticatedWebApp() {
  const navigation = useAppNavigation();
  const currentRouteName = navigation.currentRoute?.name || 'Capture';

  switch (currentRouteName) {
    case 'Capture':
      return <CaptureScreen />;
    case 'History':
      return <HistoryScreen />;
    case 'Profile':
      return <ProfileScreen />;
    case 'Settings':
      return <SettingsScreen />;
    case 'ItemLocation':
      return <ItemLocationScreen />;
    case 'Chat':
    default:
      return <ChatScreen />;
  }
}

function WebAppRoot() {
  const { currentUser, isHydrating } = useAuth();
  const initialRouteName = currentUser?.deviceId ? 'Capture' : 'Profile';

  if (isHydrating) {
    return (
      <View style={styles.loadingShell}>
        <Text style={styles.loadingTitle}>세션을 확인하고 있어요</Text>
        <Text style={styles.loadingMessage}>
          이전에 로그인한 정보를 안전하게 불러오는 중입니다.
        </Text>
      </View>
    );
  }

  if (!currentUser) {
    return <LoginScreen />;
  }

  return (
    <ItemProvider>
      <WebNavigationProvider initialRouteName={initialRouteName}>
        <AuthenticatedWebApp />
      </WebNavigationProvider>
    </ItemProvider>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <WebErrorBoundary>
        <AuthProvider>
          <WebAppRoot />
        </AuthProvider>
      </WebErrorBoundary>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  errorShell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    backgroundColor: '#FFF7ED',
    gap: 12,
  },
  errorTitle: {
    fontSize: 22,
    fontWeight: '800',
    color: '#9A3412',
  },
  errorMessage: {
    fontSize: 14,
    lineHeight: 21,
    color: '#7C2D12',
    textAlign: 'center',
  },
  loadingShell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    backgroundColor: '#F9FAFB',
    gap: 10,
  },
  loadingTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: '#111827',
  },
  loadingMessage: {
    fontSize: 14,
    lineHeight: 21,
    color: '#6B7280',
    textAlign: 'center',
  },
});
