import React, { useState } from 'react';
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '../context/AuthContext';
import logo from '../icon/logo.png';
import { colors } from '../styles/colors';
import { commonStyles } from '../styles/commonStyles';

const DEMO_ACCOUNTS = [
  {
    label: '기본 데모',
    hint: '현재 이어폰 예시 데이터가 연결된 계정',
    userId: 'user-1',
    displayName: '기본 사용자',
  },
  {
    label: '계약 테스트',
    hint: 'ingest API 저장 확인용 테스트 계정',
    userId: 'contract-test-user',
    displayName: '계약 테스트 사용자',
  },
];

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [userId, setUserId] = useState(DEMO_ACCOUNTS[0].userId);
  const [displayName, setDisplayName] = useState(DEMO_ACCOUNTS[0].displayName);
  const [errorMessage, setErrorMessage] = useState('');

  const handleSubmit = () => {
    const nextUserId = userId.trim();
    if (!nextUserId) {
      setErrorMessage('사용자 ID를 입력해 주세요.');
      return;
    }

    signIn({
      userId: nextUserId,
      displayName,
    });
    setErrorMessage('');
  };

  const applyDemoAccount = (account: (typeof DEMO_ACCOUNTS)[number]) => {
    setUserId(account.userId);
    setDisplayName(account.displayName);
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
            로그인한 사용자 기준으로 검색 기록과 관련 이미지를 연결합니다.
          </Text>
        </View>

        <View style={[commonStyles.card, styles.card]}>
          <Text style={styles.cardTitle}>데모 로그인</Text>
          <Text style={styles.cardDescription}>
            실제 인증 서버를 붙이기 전 단계라, 현재는 사용자 ID를 선택해서
            바로 앱에 진입하는 흐름입니다.
          </Text>

          <View style={styles.demoSection}>
            {DEMO_ACCOUNTS.map((account) => {
              const isSelected = account.userId === userId;

              return (
                <Pressable
                  key={account.userId}
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
                </Pressable>
              );
            })}
          </View>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>사용자 ID</Text>
            <TextInput
              value={userId}
              onChangeText={setUserId}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="예: user-1"
              placeholderTextColor={colors.subText}
              style={styles.input}
            />
          </View>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>표시 이름</Text>
            <TextInput
              value={displayName}
              onChangeText={setDisplayName}
              placeholder="예: 기본 사용자"
              placeholderTextColor={colors.subText}
              style={styles.input}
            />
          </View>

          {errorMessage ? (
            <Text style={styles.errorText}>{errorMessage}</Text>
          ) : null}

          <Pressable style={styles.submitButton} onPress={handleSubmit}>
            <Text style={styles.submitText}>앱 시작하기</Text>
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
  submitText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});
