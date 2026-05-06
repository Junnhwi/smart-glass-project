import * as ImagePicker from 'expo-image-picker';
import React, { useEffect, useMemo, useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';

import {
  buildCaptureRegistrationPayload,
  getCaptureTaskStatus,
  registerMediaCapture,
  requestMediaUploadAuthorization,
  uploadAuthorizedCaptureSource,
  type CaptureAcceptedResponse,
  type CaptureRegistrationPayload,
  type CaptureTaskStatusResponse,
  type UploadAuthorizationResponse,
} from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import { useAppNavigation } from '../navigation/appNavigation';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

const DEFAULT_FILE_NAME = 'smart-glass-photo.jpg';
const TASK_POLL_INTERVAL_MS = 2500;

const isTerminalTaskStatus = (
  status?: CaptureTaskStatusResponse['status'] | null
) => {
  return status === 'completed' || status === 'partial' || status === 'failed';
};

const inferMimeTypeFromFileName = (value: string) => {
  const normalized = value.trim().toLowerCase();
  if (normalized.endsWith('.png')) {
    return 'image/png';
  }
  if (normalized.endsWith('.webp')) {
    return 'image/webp';
  }
  if (normalized.endsWith('.gif')) {
    return 'image/gif';
  }
  if (normalized.endsWith('.heic')) {
    return 'image/heic';
  }
  if (normalized.endsWith('.heif')) {
    return 'image/heif';
  }
  return 'image/jpeg';
};

const formatFileSize = (value?: number) => {
  if (!value || value <= 0) {
    return null;
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

const buildUploadBody = async (asset: ImagePicker.ImagePickerAsset) => {
  if (asset.file) {
    return asset.file;
  }

  const localResponse = await fetch(asset.uri);
  if (!localResponse.ok) {
    throw new Error('선택한 사진을 읽지 못했어요.');
  }
  return localResponse.blob();
};

export default function SettingsScreen() {
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [notificationEnabled, setNotificationEnabled] = useState(true);
  const [fileName, setFileName] = useState(DEFAULT_FILE_NAME);
  const [selectedAsset, setSelectedAsset] =
    useState<ImagePicker.ImagePickerAsset | null>(null);
  const [isPicking, setIsPicking] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isRegistering, setIsRegistering] = useState(false);
  const [isPollingTask, setIsPollingTask] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [uploadMessage, setUploadMessage] = useState('');
  const [uploadAuthorization, setUploadAuthorization] =
    useState<UploadAuthorizationResponse | null>(null);
  const [capturePayload, setCapturePayload] =
    useState<CaptureRegistrationPayload | null>(null);
  const [captureResponse, setCaptureResponse] =
    useState<CaptureAcceptedResponse | null>(null);
  const [captureTaskStatus, setCaptureTaskStatus] =
    useState<CaptureTaskStatusResponse | null>(null);

  const navigation = useAppNavigation();
  const { currentUser } = useAuth();

  const resolvedFileName = useMemo(() => {
    const normalized = fileName.trim();
    return normalized || DEFAULT_FILE_NAME;
  }, [fileName]);

  const resolvedContentType = useMemo(() => {
    return (
      selectedAsset?.mimeType?.trim() || inferMimeTypeFromFileName(resolvedFileName)
    );
  }, [resolvedFileName, selectedAsset?.mimeType]);

  const workerMetadata = captureTaskStatus?.worker.result?.metadata || null;
  const captureIsFinished = isTerminalTaskStatus(captureTaskStatus?.status);
  const canOpenChat =
    captureTaskStatus?.memoryStore?.status === 'success' ||
    captureTaskStatus?.status === 'completed';
  const hasSelectedDevice = Boolean(currentUser?.deviceId);

  const choosePhoto = async () => {
    if (isPicking) {
      return;
    }

    setIsPicking(true);
    setErrorMessage('');

    try {
      if (Platform.OS !== 'web') {
        const permission =
          await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!permission.granted) {
          throw new Error('사진을 선택하려면 앨범 권한이 필요해요.');
        }
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: false,
        quality: 1,
      });

      if (result.canceled) {
        return;
      }

      const asset = result.assets[0];
      if (!asset) {
        throw new Error('선택한 사진이 없어요.');
      }

      if (asset.type && asset.type !== 'image') {
        throw new Error('이미지 파일만 선택할 수 있어요.');
      }

      setSelectedAsset(asset);
      setUploadAuthorization(null);
      setCapturePayload(null);
      setCaptureResponse(null);
      setCaptureTaskStatus(null);
      setUploadMessage('');
      if (asset.fileName?.trim()) {
        setFileName(asset.fileName.trim());
      }
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '사진을 고르지 못했어요.';
      setErrorMessage(message);
    } finally {
      setIsPicking(false);
    }
  };

  const uploadSelectedPhoto = async () => {
    if (!currentUser || !currentUser.deviceId || !selectedAsset || isUploading) {
      return;
    }

    setIsUploading(true);
    setErrorMessage('');
    setUploadMessage('');
    setCaptureResponse(null);
    setCaptureTaskStatus(null);

    try {
      const authorization = await requestMediaUploadAuthorization({
        deviceId: currentUser.deviceId,
        fileName: resolvedFileName,
        contentType: resolvedContentType,
      });

      if (authorization.status !== 'allowed' || !authorization.userId) {
        throw new Error('이 기기로는 업로드할 수 없어요.');
      }
      if (!authorization.upload) {
        throw new Error('업로드 정보를 받지 못했어요.');
      }
      if (!authorization.upload.uploadUrl) {
        throw new Error('업로드 주소를 받지 못했어요.');
      }

      const body = await buildUploadBody(selectedAsset);
      await uploadAuthorizedCaptureSource({
        uploadPlan: authorization.upload,
        body,
        contentType: resolvedContentType,
      });

      const payload = buildCaptureRegistrationPayload({
        userId: authorization.userId,
        deviceId: authorization.deviceId,
        uploadPlan: authorization.upload,
      });

      setUploadAuthorization(authorization);
      setCapturePayload(payload);
      setUploadMessage('사진 업로드가 끝났어요. 이제 캡처를 등록하면 돼요.');
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '사진 업로드에 실패했어요.';
      setErrorMessage(message);
      setUploadAuthorization(null);
      setCapturePayload(null);
      setUploadMessage('');
    } finally {
      setIsUploading(false);
    }
  };

  const queueCapture = async () => {
    if (!capturePayload || isRegistering) {
      return;
    }

    setIsRegistering(true);
    setErrorMessage('');

    try {
      const response = await registerMediaCapture(capturePayload);
      setCaptureResponse(response);
      setCaptureTaskStatus(null);
      setUploadMessage('캡처를 등록했어요. 추론이 끝나길 기다리는 중이에요.');
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '캡처 등록에 실패했어요.';
      setErrorMessage(message);
      setCaptureResponse(null);
    } finally {
      setIsRegistering(false);
    }
  };

  const refreshTaskStatus = async (options?: { silent?: boolean }) => {
    if (!captureResponse?.taskId || isPollingTask) {
      return;
    }

    setIsPollingTask(true);
    if (!options?.silent) {
      setErrorMessage('');
    }

    try {
      const response = await getCaptureTaskStatus(captureResponse.taskId);
      setCaptureTaskStatus(response);
      if (response.memoryStore?.status === 'success') {
        setUploadMessage('처리가 끝났고 메모리 저장도 완료됐어요.');
      }
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '처리 상태를 불러오지 못했어요.';
      setErrorMessage(message);
    } finally {
      setIsPollingTask(false);
    }
  };

  useEffect(() => {
    if (!captureResponse?.taskId) {
      return;
    }
    if (isPollingTask || captureIsFinished) {
      return;
    }

    const timer = setTimeout(() => {
      void refreshTaskStatus({ silent: true });
    }, captureTaskStatus ? TASK_POLL_INTERVAL_MS : 1000);

    return () => {
      clearTimeout(timer);
    };
  }, [
    captureIsFinished,
    captureResponse?.taskId,
    captureTaskStatus,
    isPollingTask,
  ]);

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable onPress={() => navigation.goBack()}>
          <Text style={styles.backButton}>{'<'}</Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>설정</Text>

        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.item}>
          <Text style={styles.label}>음성 입력</Text>
          <Switch value={voiceEnabled} onValueChange={setVoiceEnabled} />
        </View>

        <View style={styles.item}>
          <Text style={styles.label}>알림</Text>
          <Switch
            value={notificationEnabled}
            onValueChange={setNotificationEnabled}
          />
        </View>

        <View style={[commonStyles.card, styles.captureCard]}>
          <Text style={styles.captureTitle}>수동 업로드</Text>
          <Text style={styles.captureDescription}>
            사진을 올리고 캡처를 등록할 수 있어요.
          </Text>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>현재 기기</Text>
            <Text style={styles.readonlyValue}>
              {currentUser?.deviceId || '선택된 기기가 없어요'}
            </Text>
          </View>

          {!hasSelectedDevice ? (
            <View style={styles.deviceWarningBox}>
              <Text style={styles.deviceWarningTitle}>기기 등록이 필요해요</Text>
              <Text style={styles.deviceWarningText}>
                프로필에서 기기를 등록한 뒤 다시 시도해주세요.
              </Text>
            </View>
          ) : null}

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>선택한 사진</Text>
            {selectedAsset ? (
              <View style={styles.assetCard}>
                <Image
                  source={{ uri: selectedAsset.uri }}
                  style={styles.previewImage}
                  resizeMode="cover"
                />
                <Text style={styles.resultText}>
                  파일명: {selectedAsset.fileName || resolvedFileName}
                </Text>
                <Text style={styles.resultText}>
                  형식: {resolvedContentType}
                </Text>
                <Text style={styles.resultText}>
                  크기: {formatFileSize(selectedAsset.fileSize) || '알 수 없음'}
                </Text>
              </View>
            ) : (
              <Text style={styles.emptyStateText}>
                사진을 고르면 바로 업로드할 수 있어요.
              </Text>
            )}
          </View>

          <Pressable
            style={[
              styles.secondaryButton,
              isPicking && styles.secondaryButtonDisabled,
            ]}
            onPress={() => {
              void choosePhoto();
            }}
            disabled={isPicking}
          >
            {isPicking ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color={colors.primary} />
                <Text style={styles.secondaryButtonText}>불러오는 중...</Text>
              </View>
            ) : (
              <Text style={styles.secondaryButtonText}>사진 선택</Text>
            )}
          </Pressable>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>업로드 파일명</Text>
            <TextInput
              value={fileName}
              onChangeText={setFileName}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder={DEFAULT_FILE_NAME}
              placeholderTextColor={colors.subText}
              style={styles.input}
            />
          </View>

          <Pressable
            style={[
              styles.primaryButton,
              (!selectedAsset || isUploading || !hasSelectedDevice) &&
                styles.primaryButtonDisabled,
            ]}
            onPress={() => {
              void uploadSelectedPhoto();
            }}
            disabled={!selectedAsset || isUploading || !currentUser || !hasSelectedDevice}
          >
            {isUploading ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color="#FFFFFF" />
                <Text style={styles.primaryButtonText}>업로드 중...</Text>
              </View>
            ) : (
              <Text style={styles.primaryButtonText}>스토리지 업로드</Text>
            )}
          </Pressable>

          <Pressable
            style={[
              styles.secondaryButton,
              (!capturePayload || isRegistering) && styles.secondaryButtonDisabled,
            ]}
            onPress={() => {
              void queueCapture();
            }}
            disabled={!capturePayload || isRegistering}
          >
            {isRegistering ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color={colors.primary} />
                <Text style={styles.secondaryButtonText}>등록 중...</Text>
              </View>
            ) : (
              <Text style={styles.secondaryButtonText}>캡처 등록</Text>
            )}
          </Pressable>

          <Pressable
            style={[
              styles.secondaryButton,
              (!captureResponse?.taskId || isPollingTask) &&
                styles.secondaryButtonDisabled,
            ]}
            onPress={() => {
              void refreshTaskStatus();
            }}
            disabled={!captureResponse?.taskId || isPollingTask}
          >
            {isPollingTask ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color={colors.primary} />
                <Text style={styles.secondaryButtonText}>불러오는 중...</Text>
              </View>
            ) : (
              <Text style={styles.secondaryButtonText}>
                상태 새로고침
              </Text>
            )}
          </Pressable>

          {errorMessage ? (
            <Text style={styles.errorText}>{errorMessage}</Text>
          ) : null}

          {uploadMessage ? (
            <Text style={styles.successText}>{uploadMessage}</Text>
          ) : null}

          {uploadAuthorization?.upload ? (
            <View style={styles.resultBox}>
              <Text style={styles.resultTitle}>업로드 정보</Text>
              <Text style={styles.resultText}>
                사용자: {uploadAuthorization.userId}
              </Text>
              <Text style={styles.resultText}>
                캡처 ID: {uploadAuthorization.upload.captureId}
              </Text>
              <Text style={styles.resultText}>
                이미지 키: {uploadAuthorization.upload.sourceImage.imageKey}
              </Text>
              <Text style={styles.resultText}>
                만료: {uploadAuthorization.upload.expiresAt}
              </Text>
            </View>
          ) : null}

          {capturePayload ? (
            <View style={styles.resultBox}>
              <Text style={styles.resultTitle}>등록 정보</Text>
              <Text style={styles.resultText}>
                기기 ID: {capturePayload.deviceId}
              </Text>
              <Text style={styles.resultText}>
                요청 ID: {capturePayload.requestId}
              </Text>
              <Text style={styles.resultText}>
                이미지 키: {capturePayload.sourceImage.imageKey}
              </Text>
            </View>
          ) : null}

          {captureResponse ? (
            <View style={styles.resultBox}>
              <Text style={styles.resultTitle}>등록 결과</Text>
              <Text style={styles.resultText}>작업 ID: {captureResponse.taskId}</Text>
              <Text style={styles.resultText}>
                워커 상태: {captureResponse.worker.status}
              </Text>
              <Text style={styles.resultText}>
                처리: {captureIsFinished ? '완료' : '진행 중'}
              </Text>
              <Text style={styles.resultHint}>
                업로드한 사진이 워커에서 처리 가능한 상태예요.
              </Text>
            </View>
          ) : null}

          {captureTaskStatus ? (
            <View style={styles.resultBox}>
              <Text style={styles.resultTitle}>처리 상태</Text>
              <Text style={styles.resultText}>
                상태: {captureTaskStatus.status}
              </Text>
              <Text style={styles.resultText}>
                워커 상태: {captureTaskStatus.worker.status}
              </Text>
              <Text style={styles.resultText}>
                저장 상태: {captureTaskStatus.memoryStore?.status || '대기'}
              </Text>
              {captureTaskStatus.memoryStore?.storedCount !== undefined ? (
                <Text style={styles.resultText}>
                  저장 수: {captureTaskStatus.memoryStore.storedCount ?? 0}
                </Text>
              ) : null}
              {currentUser &&
              captureTaskStatus.memoryStore?.totalUserMemories?.[currentUser.userId] !==
                undefined ? (
                <Text style={styles.resultText}>
                  전체 메모리:{' '}
                  {
                    captureTaskStatus.memoryStore.totalUserMemories[
                      currentUser.userId
                    ]
                  }
                </Text>
              ) : null}
              {workerMetadata?.caption ? (
                <Text style={styles.resultText}>
                  설명: {workerMetadata.caption}
                </Text>
              ) : null}
              {workerMetadata?.sceneSummary ? (
                <Text style={styles.resultText}>
                  장면 요약: {workerMetadata.sceneSummary}
                </Text>
              ) : null}
              {workerMetadata?.detectedObjects?.length ? (
                <Text style={styles.resultText}>
                  물체: {workerMetadata.detectedObjects.join(', ')}
                </Text>
              ) : null}
              {workerMetadata?.positionHint ? (
                <Text style={styles.resultText}>
                  위치 힌트: {workerMetadata.positionHint}
                </Text>
              ) : null}
              {captureTaskStatus.worker.error ? (
                <Text style={styles.errorText}>
                  워커 오류: {captureTaskStatus.worker.error}
                </Text>
              ) : null}
              {captureTaskStatus.memoryStore?.error ? (
                <Text style={styles.errorText}>
                  저장 오류: {captureTaskStatus.memoryStore.error}
                </Text>
              ) : null}
              {canOpenChat ? (
                <Pressable
                  style={styles.inlineAction}
                  onPress={() => navigation.navigate('Chat')}
                >
                  <Text style={styles.inlineActionText}>채팅 열기</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: 16,
    gap: 12,
  },
  item: {
    backgroundColor: '#FFFFFF',
    padding: 16,
    borderRadius: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  label: {
    fontSize: 16,
    color: colors.text,
  },
  backButton: {
    fontSize: 20,
    color: '#111827',
    width: 24,
  },
  captureCard: {
    gap: 14,
  },
  captureTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
  },
  captureDescription: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.subText,
  },
  fieldGroup: {
    gap: 8,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.text,
  },
  readonlyValue: {
    fontSize: 14,
    color: colors.text,
  },
  deviceWarningBox: {
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#FFF7ED',
    borderWidth: 1,
    borderColor: '#FED7AA',
    gap: 4,
  },
  deviceWarningTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#C2410C',
  },
  deviceWarningText: {
    fontSize: 12,
    lineHeight: 18,
    color: '#9A3412',
  },
  input: {
    height: 46,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    fontSize: 14,
    color: colors.text,
  },
  assetCard: {
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: colors.border,
    gap: 6,
  },
  previewImage: {
    width: '100%',
    height: 180,
    borderRadius: 10,
    backgroundColor: '#E5E7EB',
  },
  emptyStateText: {
    fontSize: 13,
    lineHeight: 18,
    color: colors.subText,
  },
  primaryButton: {
    height: 46,
    borderRadius: 12,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonDisabled: {
    opacity: 0.75,
  },
  primaryButtonText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  secondaryButton: {
    height: 46,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: '#EFF6FF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryButtonDisabled: {
    opacity: 0.6,
  },
  secondaryButtonText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.primary,
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  errorText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#DC2626',
  },
  successText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#047857',
  },
  resultBox: {
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: colors.border,
    gap: 4,
  },
  resultTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 4,
  },
  resultText: {
    fontSize: 12,
    color: colors.text,
  },
  resultHint: {
    marginTop: 6,
    fontSize: 12,
    lineHeight: 17,
    color: colors.subText,
  },
  inlineAction: {
    marginTop: 8,
    alignSelf: 'flex-start',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: '#DBEAFE',
  },
  inlineActionText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
});
