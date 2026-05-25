import React, { useEffect, useMemo, useState, useRef } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Button,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  listRecentMemories,
  requestMediaUploadAuthorization,
  buildCaptureRegistrationPayload,
  registerMediaCapture,
  getCaptureTaskStatus,
  uploadAuthorizedCaptureSource,
  type MemoryRecentItem,
} from '../../networking/api';
import SideBar from '../components/SideBar';
import { useAuth } from '../context/AuthContext';
import { useAppNavigation } from '../navigation/appNavigation';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

const AUTO_SYNC_REFRESH_MS = 3000;

const SERVICE_UUID = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
const CHARACTERISTIC_UUID_RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';
const CHARACTERISTIC_UUID_TX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';

const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8002';

const STATUS_LABELS: Record<string, string> = {
  idle: '대기 중',
  connecting: '글래스 연결 중',
  connected: '글래스 연결 완료',
  capturing: '촬영 요청 전송 중',
  receiving: '이미지 수신 중',
  ready: '이미지 수신 완료',
  requestingUpload: '업로드 URL 요청 중',
  uploading: 'Object Storage 업로드 중',
  registering: '캡처 등록 중',
  polling: '추론 결과 대기 중',
  completed: '추론 완료',
  failed: '오류 발생',
};


const QUICK_ACTIONS = [
  {
    route: 'Chat' as const,
    label: '채팅으로 바로 질문',
    description: '저장된 기억이 생기면 채팅에서 바로 위치나 물건을 물어볼 수 있습니다.',
  },
  {
    route: 'History' as const,
    label: '최근 기억 확인',
    description: '방금 저장된 장면과 이전 기록을 시간순으로 빠르게 확인할 수 있습니다.',
  },
  {
    route: 'Profile' as const,
    label: '기기 연결 관리',
    description: '현재 기기 선택, 등록 상태, 페어링 상태를 여기서 바로 관리할 수 있습니다.',
  },
];

const AUTO_FLOW_STEPS = [
  '안경 촬영',
  '블루투스 또는 앱 전송',
  '서버 업로드',
  '자동 추론',
  '캡션/객체/위치 저장',
  '채팅에서 질의',
];

const formatTimestamp = (value?: string | null) => {
  if (!value) {
    return '아직 기록 없음';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
};

export default function CaptureScreen() {
  const navigation = useAppNavigation();
  const { currentUser, getDeviceLabel } = useAuth();

  const [sidebarVisible, setSidebarVisible] = useState(false);
  const [isLoadingRecent, setIsLoadingRecent] = useState(false);
  const [recentMemories, setRecentMemories] = useState<MemoryRecentItem[]>([]);
  const [errorMessage, setErrorMessage] = useState('');
  const [pipelineErrorMessage, setPipelineErrorMessage] = useState('');

  const hasSelectedDevice = Boolean(currentUser?.deviceId);
  const selectedDeviceLabel = getDeviceLabel(currentUser?.deviceId);
  const latestMemory = recentMemories[0] || null;


  const [status, setStatus] = useState('idle');
  const [capturedFile, setCapturedFile] = useState<File | null>(null);
  const [inferenceResult, setInferenceResult] = useState<any>(null);

  const rxRef = useRef<any>(null);
  const txRef = useRef<any>(null);
  const chunksRef = useRef<Uint8Array[]>([]);

  const isBusy = [
    'connecting',
    'capturing',
    'receiving',
    'requestingUpload',
    'uploading',
    'registering',
    'polling',
  ].includes(status);


  const syncStatus = useMemo(() => {
    if (!currentUser) {
      return {
        label: '로그인 필요',
        tone: 'muted' as const,
        description: '로그인 후 자동 동기화 상태를 확인할 수 있습니다.',
      };
    }

    if (!hasSelectedDevice) {
      return {
        label: '기기 선택 필요',
        tone: 'warning' as const,
        description: '자동 업로드를 시작하려면 먼저 현재 사용할 기기를 선택해야 합니다.',
      };
    }

    if (!latestMemory) {
      return {
        label: '자동 동기화 대기 중',
        tone: 'ready' as const,
        description: '하드웨어에서 사진이 들어오면 자동으로 업로드와 추론이 진행됩니다.',
      };
    }

    return {
      label: '자동 처리 정상',
      tone: 'ready' as const,
      description: '최근 저장된 기억이 확인되었습니다. 새 촬영이 들어오면 같은 흐름으로 자동 처리됩니다.',
    };
  }, [currentUser, hasSelectedDevice, latestMemory]);


  const connectGlass = async () => {
    try {
      setPipelineErrorMessage('');
      setStatus('connecting');

      const bluetooth = (navigator as any).bluetooth;

      if (!bluetooth) {
        throw new Error('이 브라우저는 Web Bluetooth를 지원하지 않습니다.');
      }

      // const device = await bluetooth.requestDevice({
      //   acceptAllDevices: true,
      //   optionalServices: [SERVICE_UUID],
      // });
      const device = await bluetooth.requestDevice({
        filters: [
          {
            services: [SERVICE_UUID],
          },
        ],
        optionalServices: [SERVICE_UUID],
      });

      const server = await device.gatt?.connect();

      if (!server) {
        throw new Error('GATT 서버 연결에 실패했습니다.');
      }

      const service = await server.getPrimaryService(SERVICE_UUID);

      const rx = await service.getCharacteristic(CHARACTERISTIC_UUID_RX);
      const tx = await service.getCharacteristic(CHARACTERISTIC_UUID_TX);

      rxRef.current = rx;
      txRef.current = tx;

      await tx.startNotifications();

      tx.addEventListener('characteristicvaluechanged', handleChunkReceived);

      setStatus('connected');
    } catch (error) {
      console.error('BLE 연결 오류:', error);

      setStatus('failed');
      setPipelineErrorMessage(
        error instanceof Error ? error.message : '글래스 연결에 실패했습니다.'
      );
    } 
  }

  const handleChunkReceived = (event: Event) => {
    const characteristic = event.target as any;
    const value = characteristic.value;

    if (!value) return;

    const chunk = new Uint8Array(value.buffer);
    chunksRef.current.push(chunk);

    const len = chunk.length;

    // JPEG 종료 바이트: FF D9
    if (
      len >= 2 &&
      chunk[len - 2] === 0xff &&
      chunk[len - 1] === 0xd9
    ) {
      const blobParts = chunksRef.current.map((chunk) => {
        const copied = new Uint8Array(chunk.byteLength);
        copied.set(chunk);
        return copied.buffer;
      });

      const blob = new Blob(blobParts, {
        type: 'image/jpeg',
      });

      const file = new File([blob], `capture-${Date.now()}.jpg`, {
        type: 'image/jpeg',
      });

      setCapturedFile(file);
      setStatus('ready');

      void uploadAndRegisterCapture(file);
    }
  }

  const requestCapture = async () => {
    if (!rxRef.current) {
      setPipelineErrorMessage('글래스가 연결되지 않았습니다.');
      return;
    }

    try {
      setPipelineErrorMessage('');
      chunksRef.current = [];

      setStatus('capturing');

      const encoder = new TextEncoder();

      await rxRef.current.writeValue(
        encoder.encode('1')
      );

      setStatus('receiving');
    } catch (error) {
      setStatus('failed');

      setPipelineErrorMessage(
        error instanceof Error
          ? error.message
          : '촬영 요청 실패'
      );
    }
  };

  const uploadAndRegisterCapture = async (fileToUpload?: File) => {
    const targetFile = fileToUpload ?? capturedFile;

    if (!targetFile) {
      setPipelineErrorMessage('업로드할 이미지가 없습니다.');
      return;
    }

    if (!currentUser?.userId) {
      setPipelineErrorMessage('로그인 사용자 정보가 없습니다.');
      return;
    }

    if (!currentUser?.deviceId) {
      setPipelineErrorMessage('선택된 기기가 없습니다.');
      return;
    }

    try {
      setPipelineErrorMessage('');
      setStatus('requestingUpload');

      const capturedAt = new Date().toISOString();

      const uploadAuthorization = await requestMediaUploadAuthorization({
        deviceId: currentUser.deviceId,
        contentType: targetFile.type,
        fileName: targetFile.name,
        capturedAt,
      });

      if (uploadAuthorization.status !== 'allowed' || !uploadAuthorization.upload) {
        throw new Error('업로드가 허용되지 않았습니다.');
      }

      const uploadPlan = uploadAuthorization.upload;


      setStatus('uploading');

      await uploadAuthorizedCaptureSource({
        uploadPlan,
        body: targetFile,
        contentType: targetFile.type,
      });

      setStatus('registering');

      const registrationPayload = buildCaptureRegistrationPayload({
        userId: currentUser.userId,
        deviceId: currentUser.deviceId,
        uploadPlan,
      });

      const capture = await registerMediaCapture(registrationPayload);

      setStatus('polling');

      if (capture.taskId) {
        void pollTask(capture.taskId);
      } else {
        setStatus('completed');
      }
    } catch (error) {
      setStatus('failed');
      setPipelineErrorMessage(
        error instanceof Error ? error.message : '업로드/캡처 등록 실패'
      );
    }
  };

  const pollTask = async (taskId: string) => {
    try {
      const timer = setInterval(async () => {
        try {
          const data = await getCaptureTaskStatus(taskId);

          if (data.status === 'completed' || data.status === 'partial') {
            clearInterval(timer);
            setInferenceResult(data);
            setStatus('completed');
          }

          if (data.status === 'failed') {
            clearInterval(timer);
            setStatus('failed');
            setPipelineErrorMessage('추론 실패');
          }
        } catch (error) {
          clearInterval(timer);
          setStatus('failed');
          setPipelineErrorMessage(
            error instanceof Error ? error.message : '추론 상태 조회 실패'
          );
        }
      }, 2000);
    } catch (error) {
      setStatus('failed');
      setPipelineErrorMessage(
        error instanceof Error ? error.message : '추론 상태 조회 실패'
      );
    }
  };
  
  const loadRecentMemories = async ({ silent = false } = {}) => {
    if (!currentUser?.authToken || !currentUser.userId) {
      setRecentMemories([]);
      return;
    }

    if (!silent) {
      setIsLoadingRecent(true);
      setErrorMessage('');
    }

    try {
      const response = await listRecentMemories({
        authToken: currentUser.authToken,
        userId: currentUser.userId,
        limit: 4,
      });
      setRecentMemories(response.items);
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '최근 기억을 불러오지 못했습니다.';
      if (!silent) {
        setErrorMessage(message);
      }
    } finally {
      if (!silent) {
        setIsLoadingRecent(false);
      }
    }
  };

  useEffect(() => {
    void loadRecentMemories();
  }, [currentUser?.authToken, currentUser?.userId]);
  
  useEffect(() => {
    if (!currentUser?.authToken || !currentUser.userId) {
      return;
    }

    const interval = setInterval(() => {
      void loadRecentMemories({ silent: true });
    }, AUTO_SYNC_REFRESH_MS);

    return () => {
      clearInterval(interval);
    };
  }, [currentUser?.authToken, currentUser?.userId]);

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable
          style={styles.headerAction}
          onPress={() => setSidebarVisible(true)}
        >
          <Text style={styles.headerActionText}>≡</Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>자동 동기화 홈</Text>

        <Pressable
          style={[styles.headerAction, styles.headerActionSecondary]}
          onPress={() => navigation.navigate('Chat')}
        >
          <Text style={styles.headerActionSecondaryText}>채팅</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, commonStyles.contentContainer]}
      >
        <View style={[commonStyles.card, styles.heroCard]}>
          <Text style={styles.heroEyebrow}>SMART GLASS</Text>
          <Text style={styles.heroTitle}>
            촬영한 장면이 자동으로 정리되고 있습니다
          </Text>
          <Text style={styles.heroDescription}>
            연결된 기기에서 들어온 사진은 순서대로 정리되어 저장됩니다.
            최근 상태를 확인하고, 저장된 기억은 채팅과 기록 화면에서 바로 이어서 볼 수 있습니다.
          </Text>

          <View style={styles.metaRow}>
            <View style={styles.metaChip}>
              <Text style={styles.metaLabel}>현재 계정</Text>
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

        <View
          style={[
            commonStyles.card,
            styles.statusCard,
            syncStatus.tone === 'warning'
              ? styles.statusCardWarning
              : syncStatus.tone === 'ready'
                ? styles.statusCardReady
                : styles.statusCardMuted,
          ]}
        >
          <Text style={styles.statusLabel}>상태</Text>
          <Text style={styles.statusTitle}>{syncStatus.label}</Text>
          <Text style={styles.statusDescription}>{syncStatus.description}</Text>
          {!hasSelectedDevice ? (
            <Pressable
              style={styles.inlinePrimaryButton}
              onPress={() => navigation.navigate('Profile')}
            >
              <Text style={styles.inlinePrimaryButtonText}>기기 선택하러 가기</Text>
            </Pressable>
          ) : null}
        </View>

        <View style={[commonStyles.card, styles.workflowCard]}>
          <Text style={styles.sectionTitle}>처리 흐름</Text>
          <Text style={styles.sectionDescription}>
            연결된 기기에서 사진이 들어오면 아래 흐름으로 자동 정리됩니다.
          </Text>
          <View style={styles.stepList}>
            {AUTO_FLOW_STEPS.map((step, index) => (
              <View key={step} style={styles.stepChip}>
                <Text style={styles.stepChipText}>
                  {index + 1}. {step}
                </Text>
              </View>
            ))}
          </View>
        </View>

        <View style={styles.pipelineCard}>
          <Text style={styles.pipelineTitle}>글래스 캡처 파이프라인</Text>

          <Text style={styles.pipelineStatus}>
            현재 상태: {STATUS_LABELS[status] ?? status}
          </Text>
          
          <View style={styles.pipelineButtonGroup}>
            <Button 
              title="글래스 연결"
              onPress={connectGlass}
              disabled={isBusy}
            />

            <Button
              title="촬영 요청"
              onPress={requestCapture}
              disabled={status !== 'connected'||isBusy}
            />
          </View>

          {capturedFile && (
            <Text style={styles.pipelineText}>
              수신 파일: {capturedFile.name}
            </Text>
          )}

          {pipelineErrorMessage ? (
            <Text style={styles.pipelineError}>{pipelineErrorMessage}</Text>
          ) : null}

          {inferenceResult && (
            <Text style={styles.pipelineText}>
              {JSON.stringify(inferenceResult, null, 2)}
            </Text>
          )}
        </View>

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

        <View style={[commonStyles.card, styles.recentCard]}>
          <View style={styles.sectionHeader}>
            <View>
              <Text style={styles.sectionTitle}>최근 장면</Text>
              <Text style={styles.sectionDescription}>
                최근에 정리된 장면을 여기에서 바로 확인할 수 있습니다.
              </Text>
            </View>
            <Pressable
              style={styles.refreshButton}
              onPress={() => {
                void loadRecentMemories();
              }}
              disabled={isLoadingRecent}
            >
              <Text style={styles.refreshButtonText}>새로고침</Text>
            </Pressable>
          </View>

          {isLoadingRecent ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator size="small" color={colors.primary} />
              <Text style={styles.loadingText}>최근 기억을 확인하는 중입니다.</Text>
            </View>
          ) : null}

          {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}

          {!isLoadingRecent && recentMemories.length === 0 ? (
            <Text style={styles.emptyText}>
              아직 정리된 장면이 없습니다.
            </Text>
          ) : null}

          {recentMemories.map((memory) => (
            <View key={memory.memoryId} style={styles.memoryRow}>
              <Text style={styles.memoryTitle}>
                {memory.caption || memory.sceneSummary || '캡션 생성 대기 중'}
              </Text>
              {memory.sceneSummary ? (
                <Text style={styles.memorySummary}>{memory.sceneSummary}</Text>
              ) : null}
              <Text style={styles.memoryMeta}>
                저장 시각: {formatTimestamp(memory.capturedAt)}
              </Text>
              {memory.positionHint ? (
                <Text style={styles.memoryMeta}>위치 힌트: {memory.positionHint}</Text>
              ) : null}
              {memory.detectedObjects.length ? (
                <Text style={styles.memoryMeta}>
                  감지 객체: {memory.detectedObjects.join(', ')}
                </Text>
              ) : null}
            </View>
          ))}
        </View>
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
  statusCard: {
    gap: 10,
  },
  statusCardReady: {
    backgroundColor: '#F0FDF4',
    borderColor: '#BBF7D0',
  },
  statusCardWarning: {
    backgroundColor: '#FFF7ED',
    borderColor: '#FED7AA',
  },
  statusCardMuted: {
    backgroundColor: '#F8FAFC',
    borderColor: colors.border,
  },
  statusLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  statusTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: colors.text,
  },
  statusDescription: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.subText,
  },
  workflowCard: {
    gap: 14,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
  },
  sectionDescription: {
    marginTop: 4,
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
    backgroundColor: '#EFF6FF',
  },
  stepChipText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  quickActionGrid: {
    gap: 12,
  },
  quickActionCard: {
    gap: 8,
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
  recentCard: {
    gap: 14,
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
  loadingRow: {
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
    lineHeight: 19,
    color: colors.subText,
  },
  memoryRow: {
    padding: 14,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: '#F8FAFC',
    gap: 6,
  },
  memoryTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
  },
  memorySummary: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.text,
  },
  memoryMeta: {
    fontSize: 12,
    color: colors.subText,
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
  errorText: {
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
    color: '#B91C1C',
  },

  pipelineCard: {
    marginTop: 16,
    padding: 16,
    borderRadius: 16,
    backgroundColor: '#ffffff',
    gap: 10,
  },
  pipelineTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  pipelineStatus: {
    fontSize: 14,
    fontWeight: '600',
  },
  pipelineButtonGroup: {
    gap: 8,
  },
  pipelineText: {
    fontSize: 13,
  },
  pipelineError: {
    fontSize: 13,
    color: 'red',
  },

});
