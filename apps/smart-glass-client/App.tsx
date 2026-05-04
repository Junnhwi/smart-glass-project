import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import ChatScreen from './src/ui/screens/ChatScreen';
import HistoryScreen from './src/ui/screens/HistoryScreen';
import LoginScreen from './src/ui/screens/LoginScreen';
import ProfileScreen from './src/ui/screens/ProfileScreen';
import SettingsScreen from './src/ui/screens/SettingScreen';
import { ItemProvider } from './src/ui/context/ItemContext';
import { AuthProvider, useAuth } from './src/ui/context/AuthContext';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import ItemLocationScreen from './src/ui/screens/ItemLocationScreen';

export type RootStackParamList = {
  Login: undefined;
  Chat: undefined;
  History: undefined;
  Profile: undefined;
  Settings: undefined;
  ItemLocation: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

function AppNavigator() {
  const { currentUser } = useAuth();

  if (!currentUser) {
    return (
      <Stack.Navigator id="AuthStack" screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Login" component={LoginScreen} />
      </Stack.Navigator>
    );
  }

  return (
    <ItemProvider>
      <Stack.Navigator
        key={currentUser.userId}
        id="RootStack"
        initialRouteName="Chat"
        screenOptions={{ headerShown: false }}
      >
        <Stack.Screen name="Chat" component={ChatScreen} />
        <Stack.Screen name="History" component={HistoryScreen} />
        <Stack.Screen name="Profile" component={ProfileScreen} />
        <Stack.Screen name="Settings" component={SettingsScreen} />
        <Stack.Screen name="ItemLocation" component={ItemLocationScreen} />
      </Stack.Navigator>
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
