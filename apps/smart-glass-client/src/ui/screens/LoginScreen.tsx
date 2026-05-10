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
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { exchangeGoogleOauth, startGoogleOauth } from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import logo from '../icon/logo.png';
import { colors } from '../styles/colors';
import { commonStyles } from '../styles/commonStyles';

const normalizeText = (value: string | null | undefined) =>
  String(value ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');

const canUseBrowserBack = () =>
  Platform.OS === 'web' &&
  typeof window !== 'undefined' &&
  window.history.length > 1;

const buildOauthRedirectUri = () => {
  const baseUrl =
    Platform.OS === 'web' && typeof window !== 'undefined'
      ? `${window.location.origin}${window.location.pathname}`
      : 'smart-glass-client://oauth';
  return new URL(baseUrl).toString();
};

const parseOauthCallbackUrl = (url: string) => {
  const parsed = new URL(url);
  return {
    handoffCode: normalizeText(parsed.searchParams.get('oauth_code')),
    oauthError: normalizeText(parsed.searchParams.get('oauth_error')),
    oauthErrorDescription: normalizeText(
      parsed.searchParams.get('oauth_error_description')
    ),
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
  window.history.replaceState({}, document.title, nextUrl.toString());
};

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [canGoBack, setCanGoBack] = useState(canUseBrowserBack);
  const [errorMessage, setErrorMessage] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [isGoogleSubmitting, setIsGoogleSubmitting] = useState(false);

  const signInRef = useRef(signIn);
  const handledOauthCodeRef = useRef('');

  useEffect(() => {
    signInRef.current = signIn;
  }, [signIn]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      return;
    }

    const syncBackAvailability = () => {
      setCanGoBack(canUseBrowserBack());
    };

    syncBackAvailability();
    window.addEventListener('popstate', syncBackAvailability);

    return () => {
      window.removeEventListener('popstate', syncBackAvailability);
    };
  }, []);

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

      if (callbackPayload.oauthError) {
        setStatusMessage('');
        setErrorMessage(
          callbackPayload.oauthErrorDescription ||
            'Google 로그인을 완료하지 못했습니다.'
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

      setIsGoogleSubmitting(true);
      setErrorMessage('');
      setStatusMessage('Google 계정을 확인하고 로그인 정보를 마무리하고 있어요...');

      try {
        const response = await exchangeGoogleOauth({
          handoffCode: callbackPayload.handoffCode,
        });
        signInRef.current({
          userId: response.user.userId,
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
            : 'Google 로그인 토큰을 교환하지 못했습니다.';
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

  const handleGoogleSubmit = async () => {
    if (isGoogleSubmitting) {
      return;
    }

    setIsGoogleSubmitting(true);
    setErrorMessage('');
    setStatusMessage('Google 로그인 페이지로 이동하고 있어요...');

    try {
      const start = await startGoogleOauth({
        redirectUri: buildOauthRedirectUri(),
      });

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.location.assign(start.authorizationUrl);
        return;
      }

      await Linking.openURL(start.authorizationUrl);
      setStatusMessage('브라우저에서 로그인한 뒤 앱으로 다시 돌아오면 이어서 완료됩니다.');
      setIsGoogleSubmitting(false);
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Google 로그인 시작에 실패했습니다.';
      setStatusMessage('');
      setErrorMessage(message);
      setIsGoogleSubmitting(false);
    }
  };

  const handleBrowserBack = () => {
    if (!canUseBrowserBack()) {
      return;
    }
    window.history.back();
  };

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <View style={styles.headerSide}>
          {canGoBack ? (
            <Pressable
              style={styles.headerBackButton}
              onPress={handleBrowserBack}
            >
              <Text style={styles.headerBackText}>뒤로</Text>
            </Pressable>
          ) : null}
        </View>
        <View style={styles.headerCenter}>
          <Image source={logo} style={styles.headerLogo} />
        </View>
        <View style={styles.headerBadge}>
          <Text style={styles.headerBadgeText}>Secure</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={[styles.container, commonStyles.contentContainer]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={[commonStyles.card, styles.heroCard]}>
          <View style={styles.heroTopRow}>
            <View style={styles.logoCircle}>
              <Image source={logo} style={styles.logo} />
            </View>
            <View style={styles.heroCopy}>
              <Text style={styles.heroEyebrow}>Smart Glass</Text>
              <Text style={styles.heroTitle}>Google 계정으로 로그인</Text>
              <Text style={styles.heroSubtitle}>
                실제 Google 계정으로 로그인하면 저장된 기억과 기기 연결 정보를
                같은 계정으로 이어서 사용할 수 있습니다.
              </Text>
            </View>
          </View>

          {statusMessage ? (
            <View style={[styles.feedbackBanner, styles.feedbackBannerSuccess]}>
              <Text style={styles.feedbackSuccessText}>{statusMessage}</Text>
            </View>
          ) : null}
          {errorMessage ? (
            <View style={[styles.feedbackBanner, styles.feedbackBannerError]}>
              <Text style={styles.feedbackErrorText}>{errorMessage}</Text>
            </View>
          ) : null}
        </View>

        <View style={[commonStyles.card, styles.sectionCard]}>
          <View style={styles.sectionHeader}>
            <View>
              <Text style={styles.sectionTitle}>로그인</Text>
              <Text style={styles.sectionDescription}>
                버튼을 누르면 Google 인증 페이지로 이동한 뒤 다시 이 화면으로
                돌아와 로그인이 완료됩니다.
              </Text>
            </View>
            <View style={styles.sectionChip}>
              <Text style={styles.sectionChipText}>OAuth</Text>
            </View>
          </View>

          <Pressable
            style={[
              styles.primaryButton,
              isGoogleSubmitting && styles.primaryButtonDisabled,
            ]}
            onPress={() => {
              void handleGoogleSubmit();
            }}
            disabled={isGoogleSubmitting}
          >
            {isGoogleSubmitting ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color="#FFFFFF" />
                <Text style={styles.primaryButtonText}>연결 중...</Text>
              </View>
            ) : (
              <View style={styles.primaryButtonRow}>
                <View style={styles.primaryButtonBadge}>
                  <Text style={styles.primaryButtonBadgeText}>G</Text>
                </View>
                <Text style={styles.primaryButtonText}>Google로 계속하기</Text>
              </View>
            )}
          </Pressable>
        </View>

        <View style={[commonStyles.card, styles.sectionCard]}>
          <Text style={styles.sectionTitle}>안내</Text>
          <Text style={styles.helpText}>
            브라우저 뒤로가기가 필요한 화면에는 같은 테마의 뒤로 버튼을 함께
            두어 이동 경로를 잃지 않도록 맞춰두었습니다.
          </Text>
          <Text style={styles.helpText}>
            이전 데모 세션이 남아 있더라도 실제 인증 정보가 아니면 자동으로
            복원하지 않도록 정리했습니다.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    paddingHorizontal: 16,
    paddingTop: 18,
    paddingBottom: 28,
    gap: 16,
  },
  headerSide: {
    width: 56,
    justifyContent: 'center',
  },
  headerBackButton: {
    minHeight: 34,
    paddingHorizontal: 12,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#BFDBFE',
    backgroundColor: '#EFF6FF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerBackText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  headerCenter: {
    flex: 1,
    alignItems: 'center',
  },
  headerLogo: {
    width: 38,
    height: 38,
    resizeMode: 'contain',
  },
  headerBadge: {
    minWidth: 56,
    alignItems: 'flex-end',
  },
  headerBadgeText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.primary,
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
  },
  heroCard: {
    gap: 16,
    padding: 18,
  },
  heroTopRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 14,
  },
  heroCopy: {
    flex: 1,
    gap: 4,
  },
  logoCircle: {
    width: 60,
    height: 60,
    borderRadius: 18,
    backgroundColor: '#EFF6FF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  logo: {
    width: 34,
    height: 34,
    resizeMode: 'contain',
  },
  heroEyebrow: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  heroTitle: {
    fontSize: 24,
    fontWeight: '800',
    color: colors.text,
  },
  heroSubtitle: {
    fontSize: 14,
    lineHeight: 21,
    color: colors.subText,
  },
  feedbackBanner: {
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  feedbackBannerSuccess: {
    backgroundColor: '#ECFDF5',
    borderWidth: 1,
    borderColor: '#A7F3D0',
  },
  feedbackBannerError: {
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FECACA',
  },
  feedbackSuccessText: {
    fontSize: 13,
    color: '#047857',
    fontWeight: '600',
  },
  feedbackErrorText: {
    fontSize: 13,
    color: '#B91C1C',
    fontWeight: '600',
  },
  sectionCard: {
    gap: 16,
    padding: 18,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.text,
  },
  sectionDescription: {
    marginTop: 4,
    fontSize: 13,
    lineHeight: 19,
    color: colors.subText,
  },
  sectionChip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: '#DBEAFE',
  },
  sectionChipText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.primary,
  },
  primaryButton: {
    height: 52,
    borderRadius: 14,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonDisabled: {
    opacity: 0.8,
  },
  primaryButtonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  primaryButtonBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.18)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonBadgeText: {
    fontSize: 15,
    fontWeight: '800',
    color: '#FFFFFF',
  },
  primaryButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  helpText: {
    fontSize: 13,
    lineHeight: 20,
    color: colors.subText,
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
});
