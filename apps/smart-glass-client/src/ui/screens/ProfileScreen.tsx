import React, { useEffect, useMemo, useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  ActivityIndicator,
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
import { useAppNavigation } from '../navigation/appNavigation';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

const formatTimestamp = (value?: string | null) => {
  if (!value) {
    return '정보 없음';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
};

export default function ProfileScreen() {
  const navigation = useAppNavigation();
  const { currentUser, getDeviceLabel, setCurrentDevice, setDeviceAlias } =
    useAuth();
  const [devices, setDevices] = useState<UserDevice[]>([]);
  const [registerDeviceId, setRegisterDeviceId] = useState('');
  const [editingDeviceId, setEditingDeviceId] = useState<string | null>(null);
  const [pendingDeviceAlias, setPendingDeviceAlias] = useState('');
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
          : '기기 목록을 불러오지 못했습니다.';
      setErrorMessage(message);
    } finally {
      setIsLoadingDevices(false);
    }
  };

  useEffect(() => {
    void loadDevices();
  }, [currentUser?.authToken, currentUser?.userId]);

  const moveToCaptureWithDevice = (deviceId: string) => {
    setCurrentDevice(deviceId);
    navigation.navigate('Capture');
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
      setStatusMessage('기기를 등록했습니다.');
      await loadDevices();
      moveToCaptureWithDevice(nextDeviceId);
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '기기 등록에 실패했습니다.';
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
        setStatusMessage('현재 선택된 기기를 해제했습니다.');
        return;
      }

      if (nextAction === 'approve') {
        setStatusMessage('기기를 다시 활성화했습니다.');
      }
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '기기 상태를 변경하지 못했습니다.';
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

  const handleHeaderPrimaryAction = () => {
    if (navigation.canGoBack) {
      navigation.goBack();
      return;
    }
    navigation.navigate('Capture');
  };

  const startEditingDeviceAlias = (deviceId: string) => {
    setEditingDeviceId(deviceId);
    setPendingDeviceAlias(getDeviceLabel(deviceId));
    setErrorMessage('');
    setStatusMessage('');
  };

  const resetEditingDeviceAlias = () => {
    setEditingDeviceId(null);
    setPendingDeviceAlias('');
  };

  const handleSaveDeviceAlias = (deviceId: string) => {
    const normalizedAlias = pendingDeviceAlias.trim();
    if (!normalizedAlias) {
      setErrorMessage('기기 이름을 입력해주세요.');
      return;
    }

    setDeviceAlias(deviceId, normalizedAlias);
    setStatusMessage('기기 이름을 저장했습니다.');
    setErrorMessage('');
    resetEditingDeviceAlias();
  };

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable onPress={handleHeaderPrimaryAction}>
          <Text style={styles.headerLink}>
            {navigation.canGoBack ? '뒤로' : '홈'}
          </Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>프로필</Text>

        <Pressable onPress={() => navigation.navigate('Settings')}>
          <Text style={styles.headerLink}>설정</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, commonStyles.contentContainer]}
      >
        <View style={styles.avatar}>
          <Text style={styles.avatarIcon}>
            {(currentUser?.displayName || 'U').slice(0, 1).toUpperCase()}
          </Text>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>이름</Text>
          <View style={styles.inputBox}>
            <Text style={[styles.value, commonStyles.selectableText]}>
              {currentUser?.displayName || '정보 없음'}
            </Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>사용자 ID</Text>
          <View style={styles.inputBox}>
            <Text style={[styles.value, commonStyles.selectableText]}>
              {currentUser?.userId || '정보 없음'}
            </Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>이메일</Text>
          <View style={styles.inputBox}>
            <Text style={[styles.value, commonStyles.selectableText]}>
              {currentUser?.email || '정보 없음'}
            </Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>현재 기기</Text>
          <View style={styles.inputBox}>
            <Text style={[styles.value, commonStyles.selectableText]}>
              {getDeviceLabel(currentUser?.deviceId)}
            </Text>
          </View>
        </View>

        <View style={[commonStyles.card, styles.deviceCard]}>
          <Text style={styles.deviceTitle}>기기 관리</Text>
          <Text style={styles.deviceDescription}>
            스마트글라스 기기를 등록하고 활성화 상태를 관리할 수 있습니다. 기기를
            선택하면 업로드 홈으로 바로 이동합니다.
          </Text>

          {!currentUser?.deviceId ? (
            <View style={styles.calloutBox}>
              <Text style={styles.calloutTitle}>선택된 기기가 없습니다</Text>
              <Text style={styles.calloutText}>
                기기 ID를 등록한 뒤 바로 선택하면 업로드 흐름을 바로 테스트할 수
                있습니다.
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
              <Text style={styles.loadingText}>기기 정보를 불러오는 중입니다.</Text>
            </View>
          ) : null}

          {!isLoadingDevices && devices.length === 0 ? (
            <Text style={styles.emptyText}>등록된 기기가 없습니다.</Text>
          ) : null}

          {currentManagedDevice ? (
            <View style={styles.currentDeviceBanner}>
              <Text style={styles.currentDeviceBannerLabel}>현재 선택된 기기</Text>
              <Text
                style={[
                  styles.currentDeviceBannerValue,
                  commonStyles.selectableText,
                ]}
              >
                {getDeviceLabel(currentManagedDevice.deviceId)} ·{' '}
                {currentManagedDevice.status === 'active'
                  ? '활성'
                  : '비활성'}
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
                  <View style={styles.deviceTitleBlock}>
                    <Text style={styles.deviceAliasText}>
                      {getDeviceLabel(device.deviceId)}
                    </Text>
                    <Text
                      style={[
                        styles.deviceIdSubText,
                        commonStyles.selectableText,
                      ]}
                    >
                      ID: {device.deviceId}
                    </Text>
                  </View>
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
                      {device.status === 'active' ? '활성' : '비활성'}
                    </Text>
                  </View>
                </View>

                {editingDeviceId === device.deviceId ? (
                  <View style={styles.renameEditor}>
                    <TextInput
                      value={pendingDeviceAlias}
                      onChangeText={setPendingDeviceAlias}
                      autoCorrect={false}
                      placeholder="기기 이름"
                      placeholderTextColor={colors.subText}
                      style={styles.renameInput}
                    />
                    <View style={styles.renameActions}>
                      <Pressable
                        style={[
                          styles.renameButton,
                          styles.renameButtonPrimary,
                        ]}
                        onPress={() => {
                          handleSaveDeviceAlias(device.deviceId);
                        }}
                      >
                        <Text
                          style={[
                            styles.renameButtonText,
                            styles.renameButtonTextPrimary,
                          ]}
                        >
                          저장
                        </Text>
                      </Pressable>
                      <Pressable
                        style={[
                          styles.renameButton,
                          styles.renameButtonSecondary,
                        ]}
                        onPress={resetEditingDeviceAlias}
                      >
                        <Text
                          style={[
                            styles.renameButtonText,
                            styles.renameButtonTextSecondary,
                          ]}
                        >
                          취소
                        </Text>
                      </Pressable>
                    </View>
                  </View>
                ) : (
                  <View style={styles.renameInlineRow}>
                    <Pressable
                      style={styles.renameShortcut}
                      onPress={() => {
                        startEditingDeviceAlias(device.deviceId);
                      }}
                    >
                      <Text style={styles.renameShortcutText}>이름 수정</Text>
                    </Pressable>
                  </View>
                )}

                <Text style={styles.deviceMeta}>
                  등록: {formatTimestamp(device.registeredAt)}
                </Text>
                <Text style={styles.deviceMeta}>
                  갱신: {formatTimestamp(device.updatedAt)}
                </Text>
                {device.revokedAt ? (
                  <Text style={styles.deviceMeta}>
                    해제: {formatTimestamp(device.revokedAt)}
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
                        setStatusMessage('현재 기기를 선택했습니다.');
                        setErrorMessage('');
                        moveToCaptureWithDevice(device.deviceId);
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
                          처리 중
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
                        {device.status === 'active' ? '비활성화' : '다시 활성화'}
                      </Text>
                    )}
                  </Pressable>
                </View>
              </View>
            );
          })}
        </View>

        <Text style={styles.syncText}>
          기기 선택 정보는 세션과 함께 저장되어 다음 접속에도 이어집니다.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: 24,
    paddingTop: 24,
    paddingBottom: 32,
  },
  headerLink: {
    minWidth: 40,
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
    textAlign: 'center',
  },
  avatar: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: '#DCEAFE',
    alignSelf: 'center',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 28,
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
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  deviceTitleBlock: {
    flex: 1,
    gap: 3,
  },
  deviceAliasText: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
  },
  deviceIdText: {
    flex: 1,
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
  },
  deviceIdSubText: {
    fontSize: 12,
    color: colors.subText,
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
  renameInlineRow: {
    marginTop: 2,
    flexDirection: 'row',
  },
  renameShortcut: {
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#BFDBFE',
    backgroundColor: '#EFF6FF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  renameShortcutText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  renameEditor: {
    gap: 10,
    marginTop: 2,
  },
  renameInput: {
    height: 42,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    fontSize: 14,
    color: colors.text,
  },
  renameActions: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  renameButton: {
    minHeight: 38,
    paddingHorizontal: 14,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  renameButtonPrimary: {
    backgroundColor: colors.primary,
  },
  renameButtonSecondary: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: colors.border,
  },
  renameButtonText: {
    fontSize: 12,
    fontWeight: '700',
  },
  renameButtonTextPrimary: {
    color: '#FFFFFF',
  },
  renameButtonTextSecondary: {
    color: colors.text,
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
