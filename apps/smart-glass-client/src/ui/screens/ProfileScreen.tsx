import React, { useEffect, useMemo, useState } from 'react';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  approveUserDevice,
  listUserDevices,
  revokeUserDevice,
  type UserDevice,
} from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

const formatTimestamp = (value?: string | null) => {
  if (!value) {
    return 'Not available';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
};

export default function ProfileScreen() {
  const navigation = useNavigation<any>();
  const { currentUser } = useAuth();
  const [devices, setDevices] = useState<UserDevice[]>([]);
  const [isLoadingDevices, setIsLoadingDevices] = useState(false);
  const [isUpdatingDeviceId, setIsUpdatingDeviceId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState('');

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
          : 'Failed to load device information.';
      setErrorMessage(message);
    } finally {
      setIsLoadingDevices(false);
    }
  };

  useEffect(() => {
    void loadDevices();
  }, [currentUser?.authToken, currentUser?.userId]);

  const handleDeviceStatusChange = async (
    device: UserDevice,
    nextAction: 'approve' | 'revoke'
  ) => {
    if (!currentUser || isUpdatingDeviceId) {
      return;
    }

    setIsUpdatingDeviceId(device.deviceId);
    setErrorMessage('');
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
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Failed to update the device status.';
      setErrorMessage(message);
    } finally {
      setIsUpdatingDeviceId(null);
    }
  };

  const currentManagedDevice = useMemo(() => {
    if (!currentUser) {
      return null;
    }
    return (
      devices.find((device) => device.deviceId === currentUser.deviceId) || null
    );
  }, [currentUser, devices]);

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable onPress={() => navigation.goBack()}>
          <Text style={styles.backButton}>{'<'}</Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>Profile</Text>

        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.avatar}>
          <Text style={styles.avatarIcon}>
            {(currentUser?.displayName || 'U').slice(0, 1).toUpperCase()}
          </Text>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Display Name</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>
              {currentUser?.displayName || 'Not set'}
            </Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>User ID</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>{currentUser?.userId || 'Not set'}</Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Email</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>{currentUser?.email || 'Not connected'}</Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Device ID</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>
              {currentUser?.deviceId || 'Not connected'}
            </Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Sign-In Method</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>
              {currentUser?.authProvider
                ? currentUser.authProvider[0].toUpperCase() +
                  currentUser.authProvider.slice(1)
                : 'Unknown'}
            </Text>
          </View>
        </View>

        <View style={[commonStyles.card, styles.deviceCard]}>
          <View style={styles.deviceHeader}>
            <Text style={styles.deviceTitle}>Registered Devices</Text>
            <Pressable
              style={styles.refreshButton}
              onPress={() => {
                void loadDevices();
              }}
              disabled={isLoadingDevices}
            >
              <Text style={styles.refreshButtonText}>Refresh</Text>
            </Pressable>
          </View>

          <Text style={styles.deviceDescription}>
            You can temporarily block capture uploads from a device without
            deleting your account.
          </Text>

          {errorMessage ? (
            <Text style={styles.errorText}>{errorMessage}</Text>
          ) : null}

          {isLoadingDevices ? (
            <View style={styles.loadingBox}>
              <ActivityIndicator size="small" color={colors.primary} />
              <Text style={styles.loadingText}>Loading devices...</Text>
            </View>
          ) : null}

          {!isLoadingDevices && devices.length === 0 ? (
            <Text style={styles.emptyText}>
              No registered devices were found for this account yet.
            </Text>
          ) : null}

          {currentManagedDevice ? (
            <View style={styles.currentDeviceBanner}>
              <Text style={styles.currentDeviceBannerLabel}>Current Device</Text>
              <Text style={styles.currentDeviceBannerValue}>
                {currentManagedDevice.deviceId} · {currentManagedDevice.status}
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
                      {device.status === 'active' ? 'Active' : 'Revoked'}
                    </Text>
                  </View>
                </View>

                <Text style={styles.deviceMeta}>
                  Registered: {formatTimestamp(device.registeredAt)}
                </Text>
                <Text style={styles.deviceMeta}>
                  Updated: {formatTimestamp(device.updatedAt)}
                </Text>
                {device.revokedAt ? (
                  <Text style={styles.deviceMeta}>
                    Revoked: {formatTimestamp(device.revokedAt)}
                  </Text>
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
                        color={device.status === 'active' ? '#991B1B' : '#FFFFFF'}
                      />
                      <Text
                        style={[
                          styles.deviceActionText,
                          device.status === 'active'
                            ? styles.deviceActionTextDanger
                            : styles.deviceActionTextPrimary,
                        ]}
                      >
                        Updating...
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
                      {device.status === 'active'
                        ? 'Deactivate Device'
                        : 'Reactivate Device'}
                    </Text>
                  )}
                </Pressable>
              </View>
            );
          })}
        </View>

        <Text style={styles.syncText}>
          Search and media requests follow the signed-in user, and capture
          uploads only work while the selected smart-glass device stays active.
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
  deviceHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  deviceTitle: {
    fontSize: 18,
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
  deviceDescription: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.subText,
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
  errorText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#DC2626',
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
  deviceActionButton: {
    marginTop: 6,
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
  backButton: {
    fontSize: 24,
    color: colors.text,
    width: 24,
    lineHeight: 24,
  },
});
