import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  ensureUserDeviceRegistration,
  exchangeGoogleOauth,
  startGoogleOauth,
} from '../../networking/api';
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

const normalizeText = (value: string | null | undefined) =>
  String(value ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');

const buildOauthRedirectUri = (deviceId: string) => {
  const baseUrl =
    Platform.OS === 'web' && typeof window !== 'undefined'
      ? `${window.location.origin}${window.location.pathname}`
      : 'smart-glass-client://oauth';
  const url = new URL(baseUrl);
  if (normalizeText(deviceId)) {
    url.searchParams.set('device_id', normalizeText(deviceId));
  }
  return url.toString();
};

const parseOauthCallbackUrl = (url: string) => {
  const parsed = new URL(url);
  return {
    handoffCode: normalizeText(parsed.searchParams.get('oauth_code')),
    oauthError: normalizeText(parsed.searchParams.get('oauth_error')),
    oauthErrorDescription: normalizeText(
      parsed.searchParams.get('oauth_error_description')
    ),
    deviceId: normalizeText(parsed.searchParams.get('device_id')),
  };
};

const clearOauthQueryParamsFromWeb = () => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return;
  }

  const nextUrl = new URL(window.location.href);
  nextUrl.searchParams.delete('oauth_code');
  nextUrl.searchParams.delete('oauth_error');
  nextUrl.searchParams.delete('oauth_error_description');
  nextUrl.searchParams.delete('provider');
  nextUrl.searchParams.delete('device_id');
  window.history.replaceState({}, document.title, nextUrl.toString());
};

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [userId, setUserId] = useState(DEMO_ACCOUNTS[0].userId);
  const [displayName, setDisplayName] = useState(DEMO_ACCOUNTS[0].displayName);
  const [deviceId, setDeviceId] = useState(DEMO_ACCOUNTS[0].deviceId);
  const [googleDeviceId, setGoogleDeviceId] = useState(DEMO_ACCOUNTS[0].deviceId);
  const [errorMessage, setErrorMessage] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGoogleSubmitting, setIsGoogleSubmitting] = useState(false);

  const signInRef = useRef(signIn);
  const latestGoogleDeviceIdRef = useRef(googleDeviceId);
  const handledOauthCodeRef = useRef('');

  useEffect(() => {
    signInRef.current = signIn;
  }, [signIn]);

  useEffect(() => {
    latestGoogleDeviceIdRef.current = googleDeviceId;
  }, [googleDeviceId]);

  useEffect(() => {
    const processOauthCallback = async (url: string | null) => {
      const normalizedUrl = normalizeText(url);
      if (!normalizedUrl) {
        return;
      }

      let callbackPayload: ReturnType<typeof parseOauthCallbackUrl>;
      try {
        callbackPayload = parseOauthCallbackUrl(normalizedUrl);
      } catch {
        return;
      }

      if (callbackPayload.deviceId) {
        setGoogleDeviceId(callbackPayload.deviceId);
      }

      if (callbackPayload.oauthError) {
        setStatusMessage('');
        setErrorMessage(
          callbackPayload.oauthErrorDescription ||
            'Google sign-in could not be completed.'
        );
        setIsGoogleSubmitting(false);
        clearOauthQueryParamsFromWeb();
        return;
      }

      if (!callbackPayload.handoffCode) {
        return;
      }
      if (handledOauthCodeRef.current === callbackPayload.handoffCode) {
        return;
      }
      handledOauthCodeRef.current = callbackPayload.handoffCode;

      const resolvedDeviceId =
        callbackPayload.deviceId || latestGoogleDeviceIdRef.current;
      if (!normalizeText(resolvedDeviceId)) {
        setStatusMessage('');
        setErrorMessage('Device ID is required to finish Google sign-in.');
        setIsGoogleSubmitting(false);
        clearOauthQueryParamsFromWeb();
        return;
      }

      setIsGoogleSubmitting(true);
      setErrorMessage('');
      setStatusMessage('Completing Google sign-in...');

      try {
        const response = await exchangeGoogleOauth({
          handoffCode: callbackPayload.handoffCode,
          deviceId: resolvedDeviceId,
        });
        signInRef.current({
          userId: response.user.userId,
          deviceId: resolvedDeviceId,
          displayName: response.user.displayName,
          email: response.user.email,
          authToken: response.accessToken,
          refreshToken: response.refreshToken,
          authProvider: 'google',
        });
      } catch (error) {
        const message =
          error instanceof Error && error.message
            ? error.message
            : 'Failed to finish Google sign-in.';
        setStatusMessage('');
        setErrorMessage(message);
        setIsGoogleSubmitting(false);
      } finally {
        clearOauthQueryParamsFromWeb();
      }
    };

    void (async () => {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        await processOauthCallback(window.location.href);
        return;
      }
      const initialUrl = await Linking.getInitialURL();
      await processOauthCallback(initialUrl);
    })();

    const subscription = Linking.addEventListener('url', (event) => {
      void processOauthCallback(event.url);
    });

    return () => {
      subscription.remove();
    };
  }, []);

  const handleDemoSubmit = async () => {
    if (isSubmitting || isGoogleSubmitting) {
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
    setStatusMessage('');

    try {
      await ensureUserDeviceRegistration({
        userId: nextUserId,
        deviceId: nextDeviceId,
      });
      signIn({
        userId: nextUserId,
        deviceId: nextDeviceId,
        displayName,
        authProvider: 'demo',
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

  const handleGoogleSubmit = async () => {
    if (isSubmitting || isGoogleSubmitting) {
      return;
    }

    const nextDeviceId = googleDeviceId.trim();
    if (!nextDeviceId) {
      setErrorMessage('Device ID is required for Google sign-in.');
      return;
    }

    setIsGoogleSubmitting(true);
    setErrorMessage('');
    setStatusMessage('Opening Google sign-in...');

    try {
      const redirectUri = buildOauthRedirectUri(nextDeviceId);
      const start = await startGoogleOauth({ redirectUri });

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.location.assign(start.authorizationUrl);
        return;
      }

      await Linking.openURL(start.authorizationUrl);
      setStatusMessage('Waiting for Google sign-in to finish...');
      setIsGoogleSubmitting(false);
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Failed to start Google sign-in.';
      setStatusMessage('');
      setErrorMessage(message);
      setIsGoogleSubmitting(false);
    }
  };

  const applyDemoAccount = (account: (typeof DEMO_ACCOUNTS)[number]) => {
    setUserId(account.userId);
    setDisplayName(account.displayName);
    setDeviceId(account.deviceId);
    setGoogleDeviceId(account.deviceId);
    setErrorMessage('');
    setStatusMessage('');
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
            Sign in with Google or use a demo account before opening the memory
            experience.
          </Text>
        </View>

        <View style={[commonStyles.card, styles.card]}>
          <Text style={styles.cardTitle}>Google Sign-In</Text>
          <Text style={styles.cardDescription}>
            Secure sign-in creates or links your account, then registers the
            selected smart-glass device for this session.
          </Text>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>Device ID</Text>
            <TextInput
              value={googleDeviceId}
              onChangeText={setGoogleDeviceId}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="eg. glass-001"
              placeholderTextColor={colors.subText}
              style={styles.input}
            />
          </View>

          <Pressable
            style={[
              styles.googleButton,
              isGoogleSubmitting && styles.googleButtonDisabled,
            ]}
            onPress={() => {
              void handleGoogleSubmit();
            }}
            disabled={isGoogleSubmitting}
          >
            {isGoogleSubmitting ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color={colors.text} />
                <Text style={styles.googleButtonText}>Google Sign-In</Text>
              </View>
            ) : (
              <View style={styles.googleButtonRow}>
                <View style={styles.googleBadge}>
                  <Text style={styles.googleBadgeText}>G</Text>
                </View>
                <Text style={styles.googleButtonText}>Continue with Google</Text>
              </View>
            )}
          </Pressable>

          {statusMessage ? (
            <Text style={styles.statusText}>{statusMessage}</Text>
          ) : null}
          {errorMessage ? (
            <Text style={styles.errorText}>{errorMessage}</Text>
          ) : null}
        </View>

        <View style={[commonStyles.card, styles.card]}>
          <Text style={styles.cardTitle}>Demo Login</Text>
          <Text style={styles.cardDescription}>
            This path still works for local contract checks and quick end-to-end
            testing without a real Google account.
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

          <Pressable
            style={[
              styles.submitButton,
              isSubmitting && styles.submitButtonDisabled,
            ]}
            onPress={() => {
              void handleDemoSubmit();
            }}
            disabled={isSubmitting || isGoogleSubmitting}
          >
            {isSubmitting ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color="#FFFFFF" />
                <Text style={styles.submitText}>Registering...</Text>
              </View>
            ) : (
              <Text style={styles.submitText}>Get Started with Demo</Text>
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
  googleButton: {
    height: 52,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  googleButtonDisabled: {
    opacity: 0.8,
  },
  googleButtonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  googleBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#F3F4F6',
    alignItems: 'center',
    justifyContent: 'center',
  },
  googleBadgeText: {
    fontSize: 15,
    fontWeight: '800',
    color: '#EA4335',
  },
  googleButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
  },
  statusText: {
    fontSize: 13,
    color: '#047857',
    fontWeight: '600',
  },
  errorText: {
    fontSize: 13,
    color: '#DC2626',
    fontWeight: '500',
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
  loadingRow: {
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
