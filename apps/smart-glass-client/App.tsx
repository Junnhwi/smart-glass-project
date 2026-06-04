import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import CaptureScreen from './src/ui/screens/CaptureScreen';
import ChatScreen from './src/ui/screens/ChatScreen';
import HistoryScreen from './src/ui/screens/HistoryScreen';
import LoginScreen from './src/ui/screens/LoginScreen';
import ProfileScreen from './src/ui/screens/ProfileScreen';
import SettingsScreen from './src/ui/screens/SettingScreen';
import { CaptureControlProvider } from './src/ui/context/CaptureControlContext';
import { GlassConnectionProvider } from './src/ui/context/GlassConnectionContext';
import { ItemProvider } from './src/ui/context/ItemContext';
import { AuthProvider, useAuth } from './src/ui/context/AuthContext';
import type { RootStackParamList } from './src/ui/navigation/routes';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import ItemLocationScreen from './src/ui/screens/ItemLocationScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();

function AppNavigator() {
  const { currentUser, isHydrating } = useAuth();
  const initialRouteName = currentUser?.deviceId ? 'Capture' : 'Profile';

  if (isHydrating) {
    return (
      <View style={styles.loadingShell}>
        <ActivityIndicator size="small" color="#2563EB" />
        <Text style={styles.loadingText}>세션을 확인하고 있어요.</Text>
      </View>
    );
  }

  if (!currentUser) {
    return (
      <Stack.Navigator id="AuthStack" screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Login" component={LoginScreen} />
      </Stack.Navigator>
    );
  }

  return (
    <ItemProvider>
      <CaptureControlProvider>
        <GlassConnectionProvider>
          <Stack.Navigator
            key={currentUser.userId}
            id="RootStack"
            initialRouteName={initialRouteName}
            screenOptions={{ headerShown: false }}
          >
            <Stack.Screen name="Capture" component={CaptureScreen} />
            <Stack.Screen name="Chat" component={ChatScreen} />
            <Stack.Screen name="History" component={HistoryScreen} />
            <Stack.Screen name="Profile" component={ProfileScreen} />
            <Stack.Screen name="Settings" component={SettingsScreen} />
            <Stack.Screen name="ItemLocation" component={ItemLocationScreen} />
          </Stack.Navigator>
        </GlassConnectionProvider>
      </CaptureControlProvider>
    </ItemProvider>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <NavigationContainer>
          <AppNavigator />
        </NavigationContainer>
      </AuthProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loadingShell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    backgroundColor: '#F9FAFB',
  },
  loadingText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#4B5563',
  },
});
