import * as ImagePicker from 'expo-image-picker';
import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
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
import SideBar from '../components/SideBar';
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

const QUICK_ACTIONS = [
  {
    route: 'Chat' as const,
    label: '기억에게 묻기',
    description: '지갑, 이어폰, 가방처럼 찾고 싶은 물건을 바로 질문해보세요.',
  },
  {
    route: 'History' as const,
    label: '최근 기록 보기',
    description: '방금 저장된 장면과 이전 추론 결과를 시간순으로 확인할 수 있어요.',
  },
  {
    route: 'Profile' as const,
    label: '기기 연결 관리',
    description: '현재 사용할 기기를 바꾸거나 새 기기를 등록할 수 있어요.',
  },
];

export default function CaptureScreen() {
  const navigation = useAppNavigation();
  const { currentUser } = useAuth();

  const [sidebarVisible, setSidebarVisible] = useState(false);
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

  const resolvedFileName = useMemo(() => {
    const normalized = fileName.trim();
    return normalized || DEFAULT_FILE_NAME;
  }, [fileName]);

  const resolvedContentType = useMemo(() => {
    return (
      selectedAsset?.mimeType?.trim() ||
      inferMimeTypeFromFileName(resolvedFileName)
    );
  }, [resolvedFileName, selectedAsset?.mimeType]);

  const workerMetadata = captureTaskStatus?.worker.result?.metadata || null;
  const captureIsFinished = isTerminalTaskStatus(captureTaskStatus?.status);
  const captureCompleted =
    captureTaskStatus?.memoryStore?.status === 'success' ||
    captureTaskStatus?.status === 'completed';
  const hasSelectedDevice = Boolean(currentUser?.deviceId);
  const selectedDeviceLabel = currentUser?.deviceId || '선택된 기기가 없어요';

  const workflowSteps = [
    { label: '사진 선택', isDone: Boolean(selectedAsset) },
    { label: '스토리지 업로드', isDone: Boolean(capturePayload) },
    { label: '캡처 등록', isDone: Boolean(captureResponse) },
    { label: '기억 저장', isDone: Boolean(captureCompleted) },
  ];

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
      if (!authorization.upload?.uploadUrl) {
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
      setUploadMessage(
        '사진 업로드가 끝났어요. 아래에서 캡처 등록을 눌러 기억 저장을 이어가세요.'
      );
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
      setUploadMessage('캡처를 등록했어요. 추론이 끝나면 자동으로 상태를 갱신할게요.');
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
        setUploadMessage('기억 저장까지 완료됐어요. 이제 채팅에서 바로 질문할 수 있어요.');
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
        <Pressable
          style={styles.headerAction}
          onPress={() => setSidebarVisible(true)}
        >
          <Text style={styles.headerActionText}>≡</Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>업로드 홈</Text>

        <Pressable
          style={[styles.headerAction, styles.headerActionSecondary]}
          onPress={() => navigation.navigate('Chat')}
        >
          <Text style={styles.headerActionSecondaryText}>질문</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, commonStyles.contentContainer]}
      >
        <View style={[commonStyles.card, styles.heroCard]}>
          <Text style={styles.heroEyebrow}>핵심 작업</Text>
          <Text style={styles.heroTitle}>사진을 올리고 바로 기억으로 저장하세요</Text>
          <Text style={styles.heroDescription}>
            현재 선택된 기기로 업로드 권한을 확인하고, 캡처 등록과 결과 확인까지
            한 화면에서 이어서 진행할 수 있어요.
          </Text>

          <View style={styles.metaRow}>
            <View style={styles.metaChip}>
              <Text style={styles.metaLabel}>사용자</Text>
              <Text style={styles.metaValue}>
                {currentUser?.displayName || currentUser?.userId || '로그인 필요'}
              </Text>
            </View>
            <View style={styles.metaChip}>
              <Text style={styles.metaLabel}>현재 기기</Text>
              <Text style={styles.metaValue}>{selectedDeviceLabel}</Text>
            </View>
          </View>
        </View>

        {!hasSelectedDevice ? (
          <View style={[commonStyles.card, styles.warningCard]}>
            <Text style={styles.warningTitle}>먼저 기기를 연결해주세요</Text>
            <Text style={styles.warningDescription}>
              업로드 권한은 선택된 기기를 기준으로 발급돼요. 프로필에서 사용할
              기기를 고른 뒤 다시 돌아오면 바로 업로드를 시작할 수 있어요.
            </Text>
            <Pressable
              style={styles.inlinePrimaryButton}
              onPress={() => navigation.navigate('Profile')}
            >
              <Text style={styles.inlinePrimaryButtonText}>기기 연결하러 가기</Text>
            </Pressable>
          </View>
        ) : null}

        <View style={styles.quickActionGrid}>
          {QUICK_ACTIONS.map((action) => (
            <Pressable
              key={action.route}
              style={[commonStyles.card, styles.quickActionCard]}
              onPress={() => navigation.navigate(action.route)}
            >
              <Text style={styles.quickActionTitle}>{action.label}</Text>
              <Text style={styles.quickActionDescription}>
                {action.description}
              </Text>
            </Pressable>
          ))}
        </View>

        <View style={[commonStyles.card, styles.workflowCard]}>
          <Text style={styles.sectionTitle}>업로드 진행 상태</Text>
          <View style={styles.stepList}>
            {workflowSteps.map((step) => (
              <View
                key={step.label}
                style={[
                  styles.stepChip,
                  step.isDone && styles.stepChipCompleted,
                ]}
              >
                <Text
                  style={[
                    styles.stepChipText,
                    step.isDone && styles.stepChipTextCompleted,
                  ]}
                >
                  {step.label}
                </Text>
              </View>
            ))}
          </View>
        </View>

        <View style={[commonStyles.card, styles.workflowCard]}>
          <Text style={styles.sectionTitle}>1. 사진 선택</Text>
          <Text style={styles.sectionDescription}>
            저장하고 싶은 장면이나 물건 사진을 선택해 주세요. 선택 후 파일명은
            수정할 수 있어요.
          </Text>

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
                <Text style={styles.resultText}>형식: {resolvedContentType}</Text>
                <Text style={styles.resultText}>
                  크기: {formatFileSize(selectedAsset.fileSize) || '알 수 없음'}
                </Text>
              </View>
            ) : (
              <Text style={styles.emptyStateText}>
                아직 선택한 사진이 없어요. 먼저 사진을 골라 주세요.
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
        </View>

        <View style={[commonStyles.card, styles.workflowCard]}>
          <Text style={styles.sectionTitle}>2. 업로드와 캡처 등록</Text>
          <Text style={styles.sectionDescription}>
            사진을 스토리지에 올린 뒤 캡처로 등록하면 추론 작업이 큐에 들어가요.
          </Text>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>현재 기기</Text>
            <Text style={styles.readonlyValue}>{selectedDeviceLabel}</Text>
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
                <Text style={styles.secondaryButtonText}>상태 확인 중...</Text>
              </View>
            ) : (
              <Text style={styles.secondaryButtonText}>상태 새로고침</Text>
            )}
          </Pressable>

          {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}
          {uploadMessage ? (
            <Text style={styles.successText}>{uploadMessage}</Text>
          ) : null}
        </View>

        {uploadAuthorization?.upload ? (
          <View style={[commonStyles.card, styles.resultBox]}>
            <Text style={styles.resultTitle}>업로드 정보</Text>
            <Text style={styles.resultText}>사용자: {uploadAuthorization.userId}</Text>
            <Text style={styles.resultText}>
              캡처 ID: {uploadAuthorization.upload.captureId}
            </Text>
            <Text style={styles.resultText}>
              이미지 키: {uploadAuthorization.upload.sourceImage.imageKey}
            </Text>
            <Text style={styles.resultText}>만료: {uploadAuthorization.upload.expiresAt}</Text>
          </View>
        ) : null}

        {captureResponse ? (
          <View style={[commonStyles.card, styles.resultBox]}>
            <Text style={styles.resultTitle}>작업 상태</Text>
            <Text style={styles.resultText}>작업 ID: {captureResponse.taskId}</Text>
            <Text style={styles.resultText}>
              워커 상태: {captureTaskStatus?.worker.status || captureResponse.worker.status}
            </Text>
            <Text style={styles.resultText}>
              처리 상태: {captureTaskStatus?.status || 'queued'}
            </Text>
            {captureTaskStatus?.memoryStore?.storedCount !== undefined ? (
              <Text style={styles.resultText}>
                저장 수: {captureTaskStatus.memoryStore.storedCount ?? 0}
              </Text>
            ) : null}
            {workerMetadata?.caption ? (
              <Text style={styles.resultText}>설명: {workerMetadata.caption}</Text>
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
            {captureTaskStatus?.worker.error ? (
              <Text style={styles.errorText}>
                워커 오류: {captureTaskStatus.worker.error}
              </Text>
            ) : null}
            {captureTaskStatus?.memoryStore?.error ? (
              <Text style={styles.errorText}>
                저장 오류: {captureTaskStatus.memoryStore.error}
              </Text>
            ) : null}
            {captureCompleted ? (
              <Pressable
                style={styles.inlinePrimaryButton}
                onPress={() => navigation.navigate('Chat')}
              >
                <Text style={styles.inlinePrimaryButtonText}>
                  방금 저장한 기억 질문하기
                </Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}
      </ScrollView>

      <SideBar
        visible={sidebarVisible}
        onClose={() => setSidebarVisible(false)}
      />
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
  headerAction: {
    minWidth: 40,
    height: 36,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerActionSecondary: {
    paddingHorizontal: 12,
    backgroundColor: '#EFF6FF',
  },
  headerActionText: {
    fontSize: 20,
    color: colors.text,
  },
  headerActionSecondaryText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
  },
  heroCard: {
    gap: 12,
    backgroundColor: '#F8FBFF',
  },
  heroEyebrow: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  heroTitle: {
    fontSize: 26,
    lineHeight: 34,
    fontWeight: '800',
    color: colors.text,
  },
  heroDescription: {
    fontSize: 14,
    lineHeight: 21,
    color: colors.subText,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  metaChip: {
    minWidth: 140,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 14,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#DBEAFE',
    gap: 3,
  },
  metaLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.primary,
  },
  metaValue: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.text,
  },
  warningCard: {
    gap: 12,
    backgroundColor: '#FFF7ED',
    borderColor: '#FED7AA',
  },
  warningTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#9A3412',
  },
  warningDescription: {
    fontSize: 13,
    lineHeight: 19,
    color: '#9A3412',
  },
  quickActionGrid: {
    gap: 12,
  },
  quickActionCard: {
    gap: 8,
    backgroundColor: '#FFFFFF',
  },
  quickActionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
  },
  quickActionDescription: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.subText,
  },
  workflowCard: {
    gap: 14,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
  },
  sectionDescription: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.subText,
  },
  stepList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  stepChip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: '#F3F4F6',
  },
  stepChipCompleted: {
    backgroundColor: '#DBEAFE',
  },
  stepChipText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#4B5563',
  },
  stepChipTextCompleted: {
    color: colors.primary,
  },
  fieldGroup: {
    gap: 8,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.text,
  },
  readonlyValue: {
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
    height: 200,
    borderRadius: 12,
    backgroundColor: colors.border,
  },
  emptyStateText: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.subText,
  },
  input: {
    height: 48,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    fontSize: 14,
    color: colors.text,
  },
  primaryButton: {
    minHeight: 50,
    borderRadius: 14,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonDisabled: {
    opacity: 0.65,
  },
  primaryButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  secondaryButton: {
    minHeight: 50,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#BFDBFE',
    backgroundColor: '#EFF6FF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryButtonDisabled: {
    opacity: 0.65,
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
  inlinePrimaryButton: {
    alignSelf: 'flex-start',
    minHeight: 42,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  inlinePrimaryButtonText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  successText: {
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
    color: '#047857',
  },
  errorText: {
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
    color: '#B91C1C',
  },
  resultBox: {
    gap: 6,
  },
  resultTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
  },
  resultText: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.text,
  },
});
