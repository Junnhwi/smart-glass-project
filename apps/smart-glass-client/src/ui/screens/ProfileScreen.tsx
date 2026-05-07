import React, { useEffect, useMemo, useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
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

import {
  approveUserDevice,
  listUserDevices,
  registerUserDevice,
  revokeUserDevice,
  type UserDevice,
} from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import logo from '../icon/logo.png';
import { useAppNavigation } from '../navigation/appNavigation';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

const formatTimestamp = (value?: string | null) => {
  if (!value) {
    return '없음';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
};

export default function ProfileScreen() {
  const navigation = useAppNavigation();
  const { currentUser, setCurrentDevice } = useAuth();
  const [devices, setDevices] = useState<UserDevice[]>([]);
  const [registerDeviceId, setRegisterDeviceId] = useState('');
  const [isLoadingDevices, setIsLoadingDevices] = useState(false);
  const [isRegisteringDevice, setIsRegisteringDevice] = useState(false);
  const [isUpdatingDeviceId, setIsUpdatingDeviceId] = useState<string | null>(
    null
  );
  const [errorMessage, setErrorMessage] = useState('');
  const [statusMessage, setStatusMessage] = useState('');

  const loadDevices = async () => {
    if (!currentUser) {
      setDevices([]);
      return;
    }

    setIsLoadingDevices(true);
    setErrorMessage('');
    try {
      const response = await listUserDevices({
        authToken: currentUser.authToken,
        userId: currentUser.userId,
      });
      setDevices(response.items);
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '기기 정보를 불러오지 못했어요.';
      setErrorMessage(message);
    } finally {
      setIsLoadingDevices(false);
    }
  };

  useEffect(() => {
    void loadDevices();
  }, [currentUser?.authToken, currentUser?.userId]);

  const moveToChatWithDevice = (deviceId: string) => {
    setCurrentDevice(deviceId);
    navigation.navigate('Chat');
  };

  const handleRegisterDevice = async () => {
    if (!currentUser || isRegisteringDevice) {
      return;
    }

    const nextDeviceId = registerDeviceId.trim();
    if (!nextDeviceId) {
      setErrorMessage('기기 ID를 입력해주세요.');
      return;
    }

    setIsRegisteringDevice(true);
    setErrorMessage('');
    setStatusMessage('');
    try {
      await registerUserDevice({
        userId: currentUser.userId,
        deviceId: nextDeviceId,
      });
      setRegisterDeviceId('');
      setStatusMessage('기기를 등록했어요.');
      await loadDevices();
      moveToChatWithDevice(nextDeviceId);
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '기기 등록에 실패했어요.';
      setErrorMessage(message);
    } finally {
      setIsRegisteringDevice(false);
    }
  };

  const handleDeviceStatusChange = async (
    device: UserDevice,
    nextAction: 'approve' | 'revoke'
  ) => {
    if (!currentUser || isUpdatingDeviceId) {
      return;
    }

    setIsUpdatingDeviceId(device.deviceId);
    setErrorMessage('');
    setStatusMessage('');

    try {
      const updated =
        nextAction === 'approve'
          ? await approveUserDevice({
              authToken: currentUser.authToken,
              userId: currentUser.userId,
              deviceId: device.deviceId,
            })
          : await revokeUserDevice({
              authToken: currentUser.authToken,
              userId: currentUser.userId,
              deviceId: device.deviceId,
            });

      setDevices((prev) =>
        prev.map((item) =>
          item.deviceId === updated.deviceId ? updated : item
        )
      );

      if (nextAction === 'revoke' && currentUser.deviceId === device.deviceId) {
        setCurrentDevice(null);
        setStatusMessage('현재 기기를 비활성화했어요.');
      }
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '기기 상태를 바꾸지 못했어요.';
      setErrorMessage(message);
    } finally {
      setIsUpdatingDeviceId(null);
    }
  };

  const currentManagedDevice = useMemo(() => {
    if (!currentUser?.deviceId) {
      return null;
    }

    return (
      devices.find((device) => device.deviceId === currentUser.deviceId) || null
    );
  }, [currentUser?.deviceId, devices]);

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable
          style={styles.homeButton}
          onPress={() => navigation.navigate('Chat')}
        >
          <Image source={logo} style={styles.homeLogo} />
        </Pressable>

        <Text style={commonStyles.headerTitle}>프로필</Text>

        <View style={{ width: 28 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.avatar}>
          <Text style={styles.avatarIcon}>
            {(currentUser?.displayName || 'U').slice(0, 1).toUpperCase()}
          </Text>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>이름</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>
              {currentUser?.displayName || '없음'}
            </Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>사용자 ID</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>{currentUser?.userId || '없음'}</Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>이메일</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>{currentUser?.email || '없음'}</Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>현재 기기</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>
              {currentUser?.deviceId || '선택된 기기가 없어요'}
            </Text>
          </View>
        </View>

        <View style={[commonStyles.card, styles.deviceCard]}>
          <Text style={styles.deviceTitle}>기기 등록</Text>
          <Text style={styles.deviceDescription}>
            기기를 등록하거나, 이미 등록된 기기 중 하나를 선택하세요.
          </Text>

          {!currentUser?.deviceId ? (
            <View style={styles.calloutBox}>
              <Text style={styles.calloutTitle}>기기를 먼저 연결해주세요</Text>
              <Text style={styles.calloutText}>
                기기 ID를 등록하거나 아래 목록에서 선택하면 돼요.
              </Text>
            </View>
          ) : null}

          <View style={styles.registerRow}>
            <TextInput
              value={registerDeviceId}
              onChangeText={setRegisterDeviceId}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="예: glass-001"
              placeholderTextColor={colors.subText}
              style={styles.registerInput}
            />
            <Pressable
              style={[
                styles.registerButton,
                isRegisteringDevice && styles.registerButtonDisabled,
              ]}
              onPress={() => {
                void handleRegisterDevice();
              }}
              disabled={isRegisteringDevice}
            >
              {isRegisteringDevice ? (
                <ActivityIndicator size="small" color="#FFFFFF" />
              ) : (
                <Text style={styles.registerButtonText}>등록</Text>
              )}
            </Pressable>
          </View>

          {statusMessage ? (
            <Text style={styles.statusText}>{statusMessage}</Text>
          ) : null}
          {errorMessage ? (
            <Text style={styles.errorText}>{errorMessage}</Text>
          ) : null}

          <View style={styles.deviceHeader}>
            <Text style={styles.deviceListTitle}>등록된 기기</Text>
            <Pressable
              style={styles.refreshButton}
              onPress={() => {
                void loadDevices();
              }}
              disabled={isLoadingDevices}
            >
              <Text style={styles.refreshButtonText}>새로고침</Text>
            </Pressable>
          </View>

          {isLoadingDevices ? (
            <View style={styles.loadingBox}>
              <ActivityIndicator size="small" color={colors.primary} />
              <Text style={styles.loadingText}>기기 정보를 불러오는 중...</Text>
            </View>
          ) : null}

          {!isLoadingDevices && devices.length === 0 ? (
            <Text style={styles.emptyText}>아직 등록된 기기가 없어요.</Text>
          ) : null}

          {currentManagedDevice ? (
            <View style={styles.currentDeviceBanner}>
              <Text style={styles.currentDeviceBannerLabel}>
                현재 선택된 기기
              </Text>
              <Text style={styles.currentDeviceBannerValue}>
                {currentManagedDevice.deviceId} ·{' '}
                {currentManagedDevice.status === 'active' ? '사용 중' : '비활성'}
              </Text>
            </View>
          ) : null}

          {devices.map((device) => {
            const isBusy = isUpdatingDeviceId === device.deviceId;
            const isCurrentDevice = currentUser?.deviceId === device.deviceId;
            const nextAction =
              device.status === 'active' ? 'revoke' : 'approve';

            return (
              <View
                key={`${device.userId}:${device.deviceId}`}
                style={[
                  styles.deviceRow,
                  isCurrentDevice && styles.deviceRowCurrent,
                ]}
              >
                <View style={styles.deviceRowTop}>
                  <Text style={styles.deviceIdText}>{device.deviceId}</Text>
                  <View
                    style={[
                      styles.statusChip,
                      device.status === 'active'
                        ? styles.statusChipActive
                        : styles.statusChipRevoked,
                    ]}
                  >
                    <Text
                      style={[
                        styles.statusChipText,
                        device.status === 'active'
                          ? styles.statusChipTextActive
                          : styles.statusChipTextRevoked,
                      ]}
                    >
                      {device.status === 'active' ? '사용 중' : '비활성'}
                    </Text>
                  </View>
                </View>

                <Text style={styles.deviceMeta}>
                  등록: {formatTimestamp(device.registeredAt)}
                </Text>
                <Text style={styles.deviceMeta}>
                  수정: {formatTimestamp(device.updatedAt)}
                </Text>
                {device.revokedAt ? (
                  <Text style={styles.deviceMeta}>
                    비활성화: {formatTimestamp(device.revokedAt)}
                  </Text>
                ) : null}

                <View style={styles.deviceActions}>
                  {device.status === 'active' ? (
                    <Pressable
                      style={[
                        styles.sessionButton,
                        isCurrentDevice && styles.sessionButtonSelected,
                      ]}
                      onPress={() => {
                        setStatusMessage('현재 기기를 바꿨어요.');
                        setErrorMessage('');
                        moveToChatWithDevice(device.deviceId);
                      }}
                    >
                      <Text
                        style={[
                          styles.sessionButtonText,
                          isCurrentDevice && styles.sessionButtonTextSelected,
                        ]}
                      >
                        {isCurrentDevice ? '선택됨' : '이 기기 사용'}
                      </Text>
                    </Pressable>
                  ) : null}

                  <Pressable
                    style={[
                      styles.deviceActionButton,
                      device.status === 'active'
                        ? styles.deviceActionButtonDanger
                        : styles.deviceActionButtonPrimary,
                      isBusy && styles.deviceActionButtonDisabled,
                    ]}
                    onPress={() => {
                      void handleDeviceStatusChange(device, nextAction);
                    }}
                    disabled={isBusy}
                  >
                    {isBusy ? (
                      <View style={styles.buttonLoadingRow}>
                        <ActivityIndicator
                          size="small"
                          color={
                            device.status === 'active' ? '#991B1B' : '#FFFFFF'
                          }
                        />
                        <Text
                          style={[
                            styles.deviceActionText,
                            device.status === 'active'
                              ? styles.deviceActionTextDanger
                              : styles.deviceActionTextPrimary,
                          ]}
                        >
                          변경 중...
                        </Text>
                      </View>
                    ) : (
                      <Text
                        style={[
                          styles.deviceActionText,
                          device.status === 'active'
                            ? styles.deviceActionTextDanger
                            : styles.deviceActionTextPrimary,
                        ]}
                      >
                        {device.status === 'active' ? '비활성화' : '재활성화'}
                      </Text>
                    )}
                  </Pressable>
                </View>
              </View>
            );
          })}
        </View>

        <Text style={styles.syncText}>
          여기서 고른 기기로 업로드와 추론이 진행돼요.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: 24,
    paddingTop: 36,
    paddingBottom: 32,
  },
  homeButton: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  homeLogo: {
    width: 28,
    height: 28,
    resizeMode: 'contain',
  },
  avatar: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: '#DCEAFE',
    alignSelf: 'center',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 36,
  },
  avatarIcon: {
    fontSize: 36,
    fontWeight: '700',
    color: colors.primary,
  },
  fieldGroup: {
    marginBottom: 16,
  },
  label: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 8,
  },
  inputBox: {
    minHeight: 46,
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: colors.border,
    justifyContent: 'center',
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  value: {
    fontSize: 15,
    color: colors.text,
  },
  deviceCard: {
    marginTop: 12,
    gap: 14,
  },
  deviceTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
  },
  deviceDescription: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.subText,
  },
  calloutBox: {
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#FFF7ED',
    borderWidth: 1,
    borderColor: '#FED7AA',
    gap: 4,
  },
  calloutTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#C2410C',
  },
  calloutText: {
    fontSize: 12,
    lineHeight: 18,
    color: '#9A3412',
  },
  registerRow: {
    flexDirection: 'row',
    gap: 10,
  },
  registerInput: {
    flex: 1,
    height: 46,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    fontSize: 14,
    color: colors.text,
  },
  registerButton: {
    minWidth: 100,
    height: 46,
    borderRadius: 12,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  registerButtonDisabled: {
    opacity: 0.75,
  },
  registerButtonText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  statusText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#047857',
  },
  errorText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#DC2626',
  },
  deviceHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  deviceListTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
  },
  refreshButton: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: '#EFF6FF',
  },
  refreshButtonText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  loadingBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  loadingText: {
    fontSize: 13,
    color: colors.subText,
  },
  emptyText: {
    fontSize: 13,
    color: colors.subText,
  },
  currentDeviceBanner: {
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
    gap: 4,
  },
  currentDeviceBannerLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  currentDeviceBannerValue: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.text,
  },
  deviceRow: {
    padding: 14,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: '#F8FAFC',
    gap: 6,
  },
  deviceRowCurrent: {
    borderColor: '#93C5FD',
    backgroundColor: '#F8FBFF',
  },
  deviceRowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  deviceIdText: {
    flex: 1,
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
  },
  statusChip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
  },
  statusChipActive: {
    backgroundColor: '#DCFCE7',
  },
  statusChipRevoked: {
    backgroundColor: '#FEE2E2',
  },
  statusChipText: {
    fontSize: 12,
    fontWeight: '700',
  },
  statusChipTextActive: {
    color: '#166534',
  },
  statusChipTextRevoked: {
    color: '#991B1B',
  },
  deviceMeta: {
    fontSize: 12,
    color: colors.subText,
  },
  deviceActions: {
    marginTop: 8,
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  sessionButton: {
    minHeight: 42,
    borderRadius: 12,
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#BFDBFE',
    backgroundColor: '#EFF6FF',
  },
  sessionButtonSelected: {
    borderColor: colors.primary,
    backgroundColor: '#DBEAFE',
  },
  sessionButtonText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
  },
  sessionButtonTextSelected: {
    color: colors.text,
  },
  deviceActionButton: {
    minHeight: 42,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
  },
  deviceActionButtonPrimary: {
    backgroundColor: colors.primary,
  },
  deviceActionButtonDanger: {
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FECACA',
  },
  deviceActionButtonDisabled: {
    opacity: 0.75,
  },
  deviceActionText: {
    fontSize: 13,
    fontWeight: '700',
  },
  deviceActionTextPrimary: {
    color: '#FFFFFF',
  },
  deviceActionTextDanger: {
    color: '#991B1B',
  },
  buttonLoadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  syncText: {
    fontSize: 12,
    color: colors.subText,
    textAlign: 'right',
    marginTop: 16,
    lineHeight: 18,
  },
});
