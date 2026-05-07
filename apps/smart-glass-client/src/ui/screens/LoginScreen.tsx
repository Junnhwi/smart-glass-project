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

import {
  createUser,
  exchangeGoogleOauth,
  startGoogleOauth,
} from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import logo from '../icon/logo.png';
import { colors } from '../styles/colors';
import { commonStyles } from '../styles/commonStyles';

const DEMO_ACCOUNTS = [
  {
    label: '기본 데모',
    hint: '빠르게 확인할 때 사용해요.',
    userId: 'user-1',
    displayName: '기본 사용자',
  },
  {
    label: '계약 테스트',
    hint: '연동 확인용 계정이에요.',
    userId: 'contract-test-user',
    displayName: '계약 테스트 사용자',
  },
];

const normalizeText = (value: string | null | undefined) =>
  String(value ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');

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
  const [selectedDemoAccount, setSelectedDemoAccount] = useState(
    DEMO_ACCOUNTS[0]
  );
  const [errorMessage, setErrorMessage] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [isDemoSubmitting, setIsDemoSubmitting] = useState(false);
  const [isGoogleSubmitting, setIsGoogleSubmitting] = useState(false);

  const signInRef = useRef(signIn);
  const handledOauthCodeRef = useRef('');

  useEffect(() => {
    signInRef.current = signIn;
  }, [signIn]);

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
            '구글 로그인을 완료하지 못했어요.'
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
      setStatusMessage('로그인 정보를 확인하고 있어요...');

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
            : '구글 로그인 처리를 완료하지 못했어요.';
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
    if (isDemoSubmitting || isGoogleSubmitting) {
      return;
    }

    setIsGoogleSubmitting(true);
    setErrorMessage('');
    setStatusMessage('구글 로그인 화면으로 이동할게요...');

    try {
      const start = await startGoogleOauth({
        redirectUri: buildOauthRedirectUri(),
      });

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.location.assign(start.authorizationUrl);
        return;
      }

      await Linking.openURL(start.authorizationUrl);
      setStatusMessage('로그인 완료를 기다리고 있어요...');
      setIsGoogleSubmitting(false);
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '구글 로그인을 시작하지 못했어요.';
      setStatusMessage('');
      setErrorMessage(message);
      setIsGoogleSubmitting(false);
    }
  };

  const handleDemoSubmit = async () => {
    if (isDemoSubmitting || isGoogleSubmitting) {
      return;
    }

    setIsDemoSubmitting(true);
    setErrorMessage('');
    setStatusMessage('데모 계정으로 들어가는 중이에요...');

    try {
      await createUser({ userId: selectedDemoAccount.userId });
      signIn({
        userId: selectedDemoAccount.userId,
        displayName: selectedDemoAccount.displayName,
        authProvider: 'demo',
      });
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '데모 계정으로 들어가지 못했어요.';
      setStatusMessage('');
      setErrorMessage(message);
      setIsDemoSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <View style={styles.headerSide} />
        <View style={styles.headerCenter}>
          <Image source={logo} style={styles.headerLogo} />
        </View>
        <View style={styles.headerBadge}>
          <Text style={styles.headerBadgeText}>로그인</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        <View style={[commonStyles.card, styles.heroCard]}>
          <View style={styles.heroTopRow}>
            <View style={styles.logoCircle}>
              <Image source={logo} style={styles.logo} />
            </View>
            <View style={styles.heroCopy}>
              <Text style={styles.heroEyebrow}>1단계</Text>
              <Text style={styles.heroTitle}>로그인</Text>
              <Text style={styles.heroSubtitle}>
                로그인 후, 기기 등록은 프로필에서 진행해요
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
              <Text style={styles.sectionTitle}>구글</Text>
              <Text style={styles.sectionDescription}>
                로그인 후 프로필에서 기기를 등록하세요!
              </Text>
            </View>
            <View style={styles.sectionChip}>
              <Text style={styles.sectionChipText}>권장</Text>
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
                <Text style={styles.primaryButtonText}>이동 중...</Text>
              </View>
            ) : (
              <View style={styles.primaryButtonRow}>
                <View style={styles.primaryButtonBadge}>
                  <Text style={styles.primaryButtonBadgeText}>G</Text>
                </View>
                <Text style={styles.primaryButtonText}>구글로 시작하기</Text>
              </View>
            )}
          </Pressable>
        </View>

        <View style={[commonStyles.card, styles.sectionCard]}>
          <View style={styles.sectionHeader}>
            <View>
              <Text style={styles.sectionTitle}>데모 로그인</Text>
              <Text style={styles.sectionDescription}>
                빠르게 둘러볼 수 있는 테스트용 로그인입니다.
              </Text>
            </View>
            <View style={[styles.sectionChip, styles.sectionChipMuted]}>
              <Text style={[styles.sectionChipText, styles.sectionChipTextMuted]}>
                선택
              </Text>
            </View>
          </View>

          <View style={styles.demoSection}>
            {DEMO_ACCOUNTS.map((account) => {
              const isSelected = account.userId === selectedDemoAccount.userId;

              return (
                <Pressable
                  key={account.userId}
                  onPress={() => {
                    setSelectedDemoAccount(account);
                    setErrorMessage('');
                    setStatusMessage('');
                  }}
                  style={[
                    styles.demoCard,
                    isSelected && styles.demoCardSelected,
                  ]}
                >
                  <View style={styles.demoCardTopRow}>
                    <View style={styles.demoCardTextBlock}>
                      <Text style={styles.demoLabel}>{account.label}</Text>
                      <Text style={styles.demoHint}>{account.hint}</Text>
                    </View>
                    <View
                      style={[
                        styles.demoSelectionDot,
                        isSelected && styles.demoSelectionDotActive,
                      ]}
                    />
                  </View>
                  <View style={styles.demoMetaRow}>
                    <Text style={styles.demoMetaLabel}>계정</Text>
                    <Text style={styles.demoMetaValue}>{account.userId}</Text>
                  </View>
                </Pressable>
              );
            })}
          </View>

          <Pressable
            style={[
              styles.secondaryButton,
              isDemoSubmitting && styles.secondaryButtonDisabled,
            ]}
            onPress={() => {
              void handleDemoSubmit();
            }}
            disabled={isDemoSubmitting || isGoogleSubmitting}
          >
            {isDemoSubmitting ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color={colors.primary} />
                <Text style={styles.secondaryButtonText}>준비 중...</Text>
              </View>
            ) : (
              <Text style={styles.secondaryButtonText}>데모로 둘러보기</Text>
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
    paddingHorizontal: 16,
    paddingTop: 18,
    paddingBottom: 28,
    gap: 16,
  },
  headerSide: {
    width: 56,
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
  sectionChipMuted: {
    backgroundColor: '#F3F4F6',
  },
  sectionChipText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.primary,
  },
  sectionChipTextMuted: {
    color: '#4B5563',
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
  demoSection: {
    gap: 10,
  },
  demoCard: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    backgroundColor: '#F8FAFC',
    gap: 8,
  },
  demoCardSelected: {
    borderColor: colors.primary,
    backgroundColor: '#EFF6FF',
  },
  demoCardTopRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  demoCardTextBlock: {
    flex: 1,
    gap: 5,
  },
  demoLabel: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
  },
  demoHint: {
    fontSize: 13,
    lineHeight: 18,
    color: colors.subText,
  },
  demoSelectionDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: '#CBD5E1',
    backgroundColor: '#FFFFFF',
    marginTop: 2,
  },
  demoSelectionDotActive: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  demoMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  demoMetaLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.subText,
  },
  demoMetaValue: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.text,
  },
  secondaryButton: {
    height: 50,
    borderRadius: 14,
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryButtonDisabled: {
    opacity: 0.75,
  },
  secondaryButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.primary,
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
});
