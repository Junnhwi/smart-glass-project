import React, { useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ensureUserDeviceRegistration } from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import logo from '../icon/logo.png';
import { colors } from '../styles/colors';
import { commonStyles } from '../styles/commonStyles';

const DEMO_ACCOUNTS = [
  {
    label: 'Default Demo',
    hint: 'Connects the default user to the demo smart-glass device.',
    userId: 'user-1',
    displayName: 'Default User',
    deviceId: 'glass-001',
  },
  {
    label: 'Contract Test',
    hint: 'Uses the integration account for API contract checks.',
    userId: 'contract-test-user',
    displayName: 'Contract Tester',
    deviceId: 'glass-contract-001',
  },
];

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [userId, setUserId] = useState(DEMO_ACCOUNTS[0].userId);
  const [displayName, setDisplayName] = useState(DEMO_ACCOUNTS[0].displayName);
  const [deviceId, setDeviceId] = useState(DEMO_ACCOUNTS[0].deviceId);
  const [errorMessage, setErrorMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (isSubmitting) {
      return;
    }

    const nextUserId = userId.trim();
    const nextDeviceId = deviceId.trim();
    if (!nextUserId) {
      setErrorMessage('User ID is required.');
      return;
    }
    if (!nextDeviceId) {
      setErrorMessage('Device ID is required.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage('');

    try {
      await ensureUserDeviceRegistration({
        userId: nextUserId,
        deviceId: nextDeviceId,
      });
      signIn({
        userId: nextUserId,
        deviceId: nextDeviceId,
        displayName,
      });
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Failed to register user and device.';
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const applyDemoAccount = (account: (typeof DEMO_ACCOUNTS)[number]) => {
    setUserId(account.userId);
    setDisplayName(account.displayName);
    setDeviceId(account.deviceId);
    setErrorMessage('');
  };

  return (
    <SafeAreaView style={commonStyles.screen}>
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.brandBlock}>
          <View style={styles.logoCircle}>
            <Image source={logo} style={styles.logo} />
          </View>
          <Text style={styles.brandTitle}>Smart Glass</Text>
          <Text style={styles.brandSubtitle}>
            Sign in with a demo user and registered device before opening the
            memory experience.
          </Text>
        </View>

        <View style={[commonStyles.card, styles.card]}>
          <Text style={styles.cardTitle}>Demo Login</Text>
          <Text style={styles.cardDescription}>
            This step now creates the user and registers the smart-glass device
            on the API server before entering the app.
          </Text>

          <View style={styles.demoSection}>
            {DEMO_ACCOUNTS.map((account) => {
              const isSelected =
                account.userId === userId && account.deviceId === deviceId;

              return (
                <Pressable
                  key={`${account.userId}:${account.deviceId}`}
                  onPress={() => applyDemoAccount(account)}
                  style={[
                    styles.demoCard,
                    isSelected && styles.demoCardSelected,
                  ]}
                >
                  <View style={styles.demoCardTop}>
                    <Text style={styles.demoLabel}>{account.label}</Text>
                    <Text style={styles.demoId}>{account.userId}</Text>
                  </View>
                  <Text style={styles.demoHint}>{account.hint}</Text>
                  <Text style={styles.demoDeviceId}>{account.deviceId}</Text>
                </Pressable>
              );
            })}
          </View>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>User ID</Text>
            <TextInput
              value={userId}
              onChangeText={setUserId}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="eg. user-1"
              placeholderTextColor={colors.subText}
              style={styles.input}
            />
          </View>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>Display Name</Text>
            <TextInput
              value={displayName}
              onChangeText={setDisplayName}
              placeholder="eg. Default User"
              placeholderTextColor={colors.subText}
              style={styles.input}
            />
          </View>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>Device ID</Text>
            <TextInput
              value={deviceId}
              onChangeText={setDeviceId}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="eg. glass-001"
              placeholderTextColor={colors.subText}
              style={styles.input}
            />
          </View>

          {errorMessage ? (
            <Text style={styles.errorText}>{errorMessage}</Text>
          ) : null}

          <Pressable
            style={[
              styles.submitButton,
              isSubmitting && styles.submitButtonDisabled,
            ]}
            onPress={() => {
              void handleSubmit();
            }}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <View style={styles.submitLoadingRow}>
                <ActivityIndicator size="small" color="#FFFFFF" />
                <Text style={styles.submitText}>Registering...</Text>
              </View>
            ) : (
              <Text style={styles.submitText}>Get Started</Text>
            )}
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingVertical: 28,
    justifyContent: 'center',
    gap: 20,
  },
  brandBlock: {
    alignItems: 'center',
    gap: 10,
  },
  logoCircle: {
    width: 78,
    height: 78,
    borderRadius: 39,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  logo: {
    width: 42,
    height: 42,
    resizeMode: 'contain',
  },
  brandTitle: {
    fontSize: 24,
    fontWeight: '800',
    color: colors.text,
  },
  brandSubtitle: {
    fontSize: 14,
    lineHeight: 21,
    color: colors.subText,
    textAlign: 'center',
    maxWidth: 320,
  },
  card: {
    gap: 18,
    padding: 20,
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.text,
  },
  cardDescription: {
    fontSize: 14,
    lineHeight: 21,
    color: colors.subText,
  },
  demoSection: {
    gap: 10,
  },
  demoCard: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    backgroundColor: '#F8FAFC',
    gap: 6,
  },
  demoCardSelected: {
    borderColor: colors.primary,
    backgroundColor: '#EFF6FF',
  },
  demoCardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  demoLabel: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
  },
  demoId: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary,
  },
  demoHint: {
    fontSize: 13,
    lineHeight: 18,
    color: colors.subText,
  },
  demoDeviceId: {
    fontSize: 12,
    fontWeight: '600',
    color: '#1D4ED8',
  },
  fieldGroup: {
    gap: 8,
  },
  fieldLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.text,
  },
  input: {
    height: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    fontSize: 15,
    color: colors.text,
  },
  errorText: {
    fontSize: 13,
    color: '#DC2626',
    fontWeight: '500',
  },
  submitButton: {
    height: 50,
    borderRadius: 14,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submitButtonDisabled: {
    opacity: 0.75,
  },
  submitLoadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  submitText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});
