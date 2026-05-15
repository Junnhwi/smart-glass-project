import React from 'react';
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '../context/AuthContext';
import { useAppNavigation } from '../navigation/appNavigation';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

const sessionStorageLabel =
  Platform.OS === 'web' ? '브라우저 로컬 세션' : '기기 보안 저장소';

const authProviderLabel = (provider?: string | null) => {
  switch (provider) {
    case 'google':
      return 'Google';
    case 'password':
      return 'Password';
    default:
      return 'Unknown';
  }
};

export default function SettingsScreen() {
  const navigation = useAppNavigation();
  const { currentUser, getDeviceLabel, signOut } = useAuth();

  const handleHeaderPrimaryAction = () => {
    if (navigation.canGoBack) {
      navigation.goBack();
      return;
    }
    navigation.navigate('Capture');
  };

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable onPress={handleHeaderPrimaryAction}>
          {navigation.canGoBack ? (
            <Text style={styles.headerIcon}>{'<'}</Text>
          ) : (
            <Text style={styles.headerLink}>홈</Text>
          )}
        </Pressable>

        <Text style={commonStyles.headerTitle}>설정</Text>

        <Pressable onPress={() => navigation.navigate('Profile')}>
          <Text style={styles.headerLink}>프로필</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, commonStyles.contentContainer]}
      >
        <View style={[commonStyles.card, styles.heroCard]}>
          <Text style={styles.heroEyebrow}>세션 관리</Text>
          <Text style={styles.heroTitle}>
            로그인 상태와 현재 기기 연결을 한곳에서 확인하세요
          </Text>
          <Text style={styles.heroDescription}>
            앱은 현재 로그인 정보를 {sessionStorageLabel}에 보관해 다음 실행에서도
            바로 이어서 사용할 수 있습니다. 다른 계정으로 전환하거나 Google
            로그인 화면으로 돌아가고 싶다면 아래 계정 전환 버튼을 사용하면 됩니다.
          </Text>
        </View>

        <View style={[commonStyles.card, styles.sectionCard]}>
          <Text style={styles.sectionTitle}>현재 계정</Text>

          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>이름</Text>
            <Text style={[styles.infoValue, commonStyles.selectableText]}>
              {currentUser?.displayName || '정보 없음'}
            </Text>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>사용자 ID</Text>
            <Text style={[styles.infoValue, commonStyles.selectableText]}>
              {currentUser?.userId || '정보 없음'}
            </Text>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>이메일</Text>
            <Text style={[styles.infoValue, commonStyles.selectableText]}>
              {currentUser?.email || '정보 없음'}
            </Text>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>로그인 방식</Text>
            <Text style={styles.infoValue}>
              {authProviderLabel(currentUser?.authProvider)}
            </Text>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>현재 기기</Text>
            <Text style={[styles.infoValue, commonStyles.selectableText]}>
              {getDeviceLabel(currentUser?.deviceId)}
            </Text>
          </View>
        </View>

        <View style={[commonStyles.card, styles.sectionCard]}>
          <Text style={styles.sectionTitle}>바로가기</Text>

          <Pressable
            style={styles.secondaryButton}
            onPress={() => navigation.navigate('Capture')}
          >
            <Text style={styles.secondaryButtonText}>업로드 홈으로 이동</Text>
          </Pressable>

          <Pressable
            style={styles.secondaryButton}
            onPress={() => navigation.navigate('Profile')}
          >
            <Text style={styles.secondaryButtonText}>기기 관리 열기</Text>
          </Pressable>

          <Pressable
            style={styles.secondaryButton}
            onPress={() => navigation.navigate('History')}
          >
            <Text style={styles.secondaryButtonText}>최근 기록 보기</Text>
          </Pressable>

          <Pressable
            style={styles.secondaryButton}
            onPress={() => {
              void signOut();
            }}
          >
            <Text style={styles.secondaryButtonText}>다른 계정으로 로그인</Text>
          </Pressable>
        </View>

        <Pressable
          style={styles.logoutButton}
          onPress={() => {
            void signOut();
          }}
        >
          <Text style={styles.logoutButtonText}>로그아웃</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: 16,
    paddingTop: 18,
    paddingBottom: 28,
    gap: 16,
  },
  headerLink: {
    minWidth: 40,
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
    textAlign: 'center',
  },
  headerIcon: {
    width: 24,
    fontSize: 24,
    color: colors.text,
    textAlign: 'center',
  },
  heroCard: {
    gap: 10,
    backgroundColor: '#F8FBFF',
  },
  heroEyebrow: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  heroTitle: {
    fontSize: 24,
    lineHeight: 32,
    fontWeight: '800',
    color: colors.text,
  },
  heroDescription: {
    fontSize: 14,
    lineHeight: 21,
    color: colors.subText,
  },
  sectionCard: {
    gap: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
  },
  infoRow: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
    gap: 4,
  },
  infoLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.subText,
  },
  infoValue: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.text,
  },
  secondaryButton: {
    minHeight: 48,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#BFDBFE',
    backgroundColor: '#EFF6FF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.primary,
  },
  logoutButton: {
    minHeight: 50,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FECACA',
  },
  logoutButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#991B1B',
  },
});
