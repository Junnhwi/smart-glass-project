import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

import {
  buildCaptureRegistrationPayload,
  getCaptureTaskStatus,
  recordCaptureEvent,
  registerMediaCapture,
  registerUserDevice,
  requestMediaUploadAuthorization,
  uploadAuthorizedCaptureSource,
  type CaptureEventType,
} from '../../networking/api';
import { useAuth } from './AuthContext';
import { useCaptureControl } from './CaptureControlContext';

const DEFAULT_CAPTURE_INTERVAL_SEC = 300;

const SERVICE_UUID = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
const CHARACTERISTIC_UUID_RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';
const CHARACTERISTIC_UUID_TX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';
const GLASS_DEVICE_NAME = 'XIAO_BLE_CAM';

const CAPTURE_BUSY_STATUSES = new Set([
  'connecting',
  'capturing',
  'receiving',
  'requestingUpload',
  'uploading',
  'registering',
  'polling',
]);

export const STATUS_LABELS: Record<string, string> = {
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

type GlassConnectionContextValue = {
  status: string;
  capturedFile: File | null;
  inferenceResult: any;
  pipelineErrorMessage: string;
  hasGlassConnection: boolean;
  isBusy: boolean;
  completedCaptureCount: number;
  connectGlass: () => Promise<void>;
  requestCapture: () => Promise<void>;
};

const GlassConnectionContext =
  createContext<GlassConnectionContextValue | null>(null);

export const isCaptureStatusBusy = (value: string) =>
  CAPTURE_BUSY_STATUSES.has(value);

const flattenChunks = (chunks: Uint8Array[]) => {
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
  const merged = new Uint8Array(totalLength);
  let offset = 0;

  chunks.forEach((chunk) => {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  });

  return merged;
};

const extractJpegBytes = (bytes: Uint8Array) => {
  let startIndex = -1;
  let endIndex = -1;

  for (let index = 0; index < bytes.length - 1; index += 1) {
    if (startIndex === -1 && bytes[index] === 0xff && bytes[index + 1] === 0xd8) {
      startIndex = index;
    }

    if (startIndex !== -1 && bytes[index] === 0xff && bytes[index + 1] === 0xd9) {
      endIndex = index + 2;
      break;
    }
  }

  if (startIndex === -1 || endIndex === -1) {
    throw new Error('수신된 데이터에서 JPEG 이미지를 찾지 못했습니다.');
  }

  return bytes.slice(startIndex, endIndex);
};

const normalizeDeviceId = (value?: string | null) =>
  String(value ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join('-');

const resolveBluetoothDeviceId = (device: any) =>
  normalizeDeviceId(device?.name) ||
  normalizeDeviceId(device?.id) ||
  GLASS_DEVICE_NAME;

const isExpiredTokenError = (error: unknown) =>
  error instanceof Error &&
  error.message.toLowerCase().includes('access token has expired');

const getErrorMessage = (error: unknown, fallbackMessage: string) =>
  error instanceof Error && error.message ? error.message : fallbackMessage;

export function GlassConnectionProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const {
    currentUser,
    refreshSession,
    setCurrentDevice,
    setDeviceAlias,
  } = useAuth();
  const {
    captureControl,
    refreshCaptureControl,
  } = useCaptureControl();

  const [status, setStatus] = useState('idle');
  const [capturedFile, setCapturedFile] = useState<File | null>(null);
  const [inferenceResult, setInferenceResult] = useState<any>(null);
  const [pipelineErrorMessage, setPipelineErrorMessage] = useState('');
  const [completedCaptureCount, setCompletedCaptureCount] = useState(0);
  const [hasGlassConnection, setHasGlassConnection] = useState(false);

  const rxRef = useRef<any>(null);
  const txRef = useRef<any>(null);
  const deviceRef = useRef<any>(null);
  const chunksRef = useRef<Uint8Array[]>([]);
  const lastReceivedByteRef = useRef<number | null>(null);
  const isTxNotificationStartedRef = useRef(false);
  const txNotificationListenerRef = useRef<((event: Event) => void) | null>(
    null
  );
  const deviceDisconnectListenerRef = useRef<((event: Event) => void) | null>(
    null
  );
  const connectedDeviceIdRef = useRef<string | null>(null);
  const statusRef = useRef(status);
  const autoCaptureTimerRef = useRef<ReturnType<typeof setInterval> | null>(
    null
  );
  const autoCaptureStartKeyRef = useRef<string | null>(null);

  const isBusy = isCaptureStatusBusy(status);

  const clearAutoCaptureTimer = () => {
    if (!autoCaptureTimerRef.current) {
      return;
    }
    clearInterval(autoCaptureTimerRef.current);
    autoCaptureTimerRef.current = null;
  };

  const clearGlassConnection = async ({
    disconnectGatt = false,
    message,
  }: {
    disconnectGatt?: boolean;
    message?: string;
  } = {}) => {
    clearAutoCaptureTimer();

    if (txRef.current && txNotificationListenerRef.current) {
      txRef.current.removeEventListener(
        'characteristicvaluechanged',
        txNotificationListenerRef.current
      );
    }

    if (txRef.current && isTxNotificationStartedRef.current) {
      try {
        await txRef.current.stopNotifications();
      } catch {
        // 이미 연결이 끊긴 characteristic이면 무시합니다.
      }
    }

    if (deviceRef.current && deviceDisconnectListenerRef.current) {
      deviceRef.current.removeEventListener?.(
        'gattserverdisconnected',
        deviceDisconnectListenerRef.current
      );
    }

    if (disconnectGatt && deviceRef.current?.gatt?.connected) {
      try {
        deviceRef.current.gatt.disconnect();
      } catch {
        // 브라우저/기기 상태에 따라 disconnect가 실패할 수 있어 무시합니다.
      }
    }

    rxRef.current = null;
    txRef.current = null;
    deviceRef.current = null;
    connectedDeviceIdRef.current = null;
    txNotificationListenerRef.current = null;
    deviceDisconnectListenerRef.current = null;
    isTxNotificationStartedRef.current = false;
    chunksRef.current = [];
    lastReceivedByteRef.current = null;
    autoCaptureStartKeyRef.current = null;
    setHasGlassConnection(false);
    setStatus('idle');

    if (message) {
      setPipelineErrorMessage(message);
    }
  };

  const registerAndSelectGlassDevice = async (deviceId: string) => {
    if (!currentUser?.authToken || !currentUser.userId) {
      return;
    }

    let authToken = currentUser.authToken;
    let userId = currentUser.userId;

    try {
      await registerUserDevice({
        authToken,
        userId,
        deviceId,
      });
    } catch (error) {
      if (!isExpiredTokenError(error)) {
        throw error;
      }

      const refreshedUser = await refreshSession();
      if (!refreshedUser) {
        throw error;
      }

      authToken = refreshedUser.authToken;
      userId = refreshedUser.userId;
      await registerUserDevice({
        authToken,
        userId,
        deviceId,
      });
    }

    setCurrentDevice(deviceId);
    setDeviceAlias(deviceId, GLASS_DEVICE_NAME);
  };

  const pollTask = async (taskId: string) => {
    const timer = setInterval(async () => {
      try {
        const data = await getCaptureTaskStatus(taskId);

        if (data.status === 'completed' || data.status === 'partial') {
          clearInterval(timer);
          setInferenceResult(data);
          setStatus('completed');
          setCompletedCaptureCount((count) => count + 1);
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

    const selectedDeviceId = connectedDeviceIdRef.current;

    if (!selectedDeviceId) {
      setPipelineErrorMessage('연결된 글래스 기기가 없습니다.');
      return;
    }

    if (currentUser.deviceId && currentUser.deviceId !== selectedDeviceId) {
      setPipelineErrorMessage(
        '현재 선택된 기기와 연결된 글래스가 다릅니다. 글래스를 다시 연결해 주세요.'
      );
      return;
    }

    try {
      setPipelineErrorMessage('');
      setStatus('requestingUpload');

      const capturedAt = new Date().toISOString();

      let uploadAuthorization: Awaited<
        ReturnType<typeof requestMediaUploadAuthorization>
      >;

      try {
        uploadAuthorization = await requestMediaUploadAuthorization({
          deviceId: selectedDeviceId,
          contentType: targetFile.type,
          fileName: targetFile.name,
          capturedAt,
        });
      } catch (error) {
        throw new Error(
          `업로드 허가 요청 실패: ${getErrorMessage(error, 'API 서버에 연결하지 못했습니다.')}`
        );
      }

      if (uploadAuthorization.status !== 'allowed' || !uploadAuthorization.upload) {
        throw new Error('업로드가 허용되지 않았습니다.');
      }

      const uploadPlan = uploadAuthorization.upload;

      setStatus('uploading');

      try {
        await uploadAuthorizedCaptureSource({
          uploadPlan,
          body: targetFile,
          contentType: targetFile.type,
        });
      } catch (error) {
        throw new Error(
          `Object Storage 업로드 실패: ${getErrorMessage(
            error,
            '브라우저에서 presigned URL로 업로드하지 못했습니다.'
          )}`
        );
      }

      setStatus('registering');

      const registrationPayload = buildCaptureRegistrationPayload({
        userId: currentUser.userId,
        deviceId: selectedDeviceId,
        uploadPlan,
      });

      let capture: Awaited<ReturnType<typeof registerMediaCapture>>;
      try {
        capture = await registerMediaCapture(registrationPayload);
      } catch (error) {
        throw new Error(
          `캡처 등록 실패: ${getErrorMessage(error, 'API 서버에 연결하지 못했습니다.')}`
        );
      }

      setStatus('polling');

      if (capture.taskId) {
        await pollTask(capture.taskId);
      } else {
        setStatus('completed');
        setCompletedCaptureCount((count) => count + 1);
      }
    } catch (error) {
      setStatus('failed');
      setPipelineErrorMessage(
        error instanceof Error ? error.message : '업로드/캡처 등록 실패'
      );
    }
  };

  const handleChunkReceived = (event: Event) => {
    const characteristic = event.target as any;
    const value = characteristic.value;

    if (!value) return;

    const chunk = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    chunksRef.current.push(chunk);

    const len = chunk.length;

    if (len === 0) return;

    const lastIndex = len - 1;
    const hasJpegEndMarker =
      (len >= 2 &&
        chunk[len - 2] === 0xff &&
        chunk[len - 1] === 0xd9) ||
      (lastReceivedByteRef.current === 0xff && chunk[0] === 0xd9);

    lastReceivedByteRef.current = chunk[lastIndex];

    if (hasJpegEndMarker) {
      let jpegBytes: Uint8Array;

      try {
        jpegBytes = extractJpegBytes(flattenChunks(chunksRef.current));
      } catch (error) {
        chunksRef.current = [];
        lastReceivedByteRef.current = null;
        setStatus('failed');
        setPipelineErrorMessage(
          error instanceof Error ? error.message : '수신된 이미지 데이터가 올바르지 않습니다.'
        );
        return;
      }

      const copied = new Uint8Array(jpegBytes.byteLength);
      copied.set(jpegBytes);

      const blob = new Blob([copied.buffer] as BlobPart[], {
        type: 'image/jpeg',
      });

      const file = new File([blob], `capture-${Date.now()}.jpg`, {
        type: 'image/jpeg',
      });

      setCapturedFile(file);
      setStatus('ready');
      chunksRef.current = [];
      lastReceivedByteRef.current = null;

      void uploadAndRegisterCapture(file);
    }
  };

  const connectGlass = async () => {
    try {
      setPipelineErrorMessage('');
      setStatus('connecting');

      const bluetooth = (navigator as any).bluetooth;

      if (!bluetooth) {
        throw new Error('이 브라우저는 Web Bluetooth를 지원하지 않습니다.');
      }

      await clearGlassConnection({ disconnectGatt: true });
      setStatus('connecting');
      setPipelineErrorMessage('');

      const device = await bluetooth.requestDevice({
        filters: [
          {
            name: GLASS_DEVICE_NAME,
          },
        ],
        optionalServices: [SERVICE_UUID],
      });
      const connectedDeviceId = resolveBluetoothDeviceId(device);
      connectedDeviceIdRef.current = connectedDeviceId;
      deviceRef.current = device;

      const handleDeviceDisconnected = (event: Event) => {
        if (event.target !== deviceRef.current) {
          return;
        }

        rxRef.current = null;
        txRef.current = null;
        deviceRef.current = null;
        connectedDeviceIdRef.current = null;
        txNotificationListenerRef.current = null;
        deviceDisconnectListenerRef.current = null;
        isTxNotificationStartedRef.current = false;
        chunksRef.current = [];
        lastReceivedByteRef.current = null;
        setHasGlassConnection(false);
        setStatus('idle');
      };
      deviceDisconnectListenerRef.current = handleDeviceDisconnected;
      device.addEventListener?.(
        'gattserverdisconnected',
        handleDeviceDisconnected
      );

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
      txNotificationListenerRef.current = handleChunkReceived;

      isTxNotificationStartedRef.current = true;
      await registerAndSelectGlassDevice(connectedDeviceId);

      setHasGlassConnection(true);
      setStatus('connected');
    } catch (error) {
      console.error('BLE 연결 오류:', error);

      setHasGlassConnection(false);
      setStatus('failed');
      setPipelineErrorMessage(
        error instanceof Error ? error.message : '글래스 연결에 실패했습니다.'
      );
    }
  };

  const requestCapture = async () => {
    if (!rxRef.current) {
      setPipelineErrorMessage('글래스가 연결되지 않았습니다.');
      return;
    }

    const connectedDeviceId = connectedDeviceIdRef.current;
    if (
      currentUser?.deviceId &&
      connectedDeviceId &&
      currentUser.deviceId !== connectedDeviceId
    ) {
      setPipelineErrorMessage(
        '현재 선택된 기기와 연결된 글래스가 다릅니다. 글래스를 다시 연결해 주세요.'
      );
      return;
    }

    try {
      setPipelineErrorMessage('');
      chunksRef.current = [];
      lastReceivedByteRef.current = null;

      setStatus('capturing');

      const encoder = new TextEncoder();

      await rxRef.current.writeValue(encoder.encode('1'));

      setStatus('receiving');
    } catch (error) {
      setStatus('failed');

      setPipelineErrorMessage(
        error instanceof Error ? error.message : '촬영 요청 실패'
      );
    }
  };

  const runAutoCapture = async (eventType: CaptureEventType) => {
    if (!captureControl?.enabled) {
      return;
    }

    if (!currentUser?.authToken || !currentUser.userId || !currentUser.deviceId) {
      return;
    }

    const connectedDeviceId = connectedDeviceIdRef.current;
    if (!connectedDeviceId || connectedDeviceId !== currentUser.deviceId) {
      return;
    }

    if (!rxRef.current) {
      if (eventType === 'start_capture') {
        setPipelineErrorMessage(
          '자동 촬영이 켜져 있습니다. 글래스를 연결하면 촬영을 시작합니다.'
        );
      }
      return;
    }

    if (isCaptureStatusBusy(statusRef.current)) {
      return;
    }

    try {
      setPipelineErrorMessage('');
      let authToken = currentUser.authToken;
      let userId = currentUser.userId;
      let deviceId = connectedDeviceId;

      let eventResponse: Awaited<ReturnType<typeof recordCaptureEvent>>;
      try {
        eventResponse = await recordCaptureEvent({
          authToken,
          userId,
          deviceId,
          eventType,
        });
      } catch (error) {
        if (!isExpiredTokenError(error)) {
          throw error;
        }

        const refreshedUser = await refreshSession();
        if (
          !refreshedUser?.authToken ||
          refreshedUser.deviceId !== connectedDeviceId
        ) {
          throw error;
        }
        authToken = refreshedUser.authToken;
        userId = refreshedUser.userId;
        eventResponse = await recordCaptureEvent({
          authToken,
          userId,
          deviceId,
          eventType,
        });
      }

      if (!eventResponse.shouldCapture) {
        void refreshCaptureControl({ silent: true });
        return;
      }

      void refreshCaptureControl({ silent: true });
      await requestCapture();
    } catch (error) {
      setPipelineErrorMessage(
        getErrorMessage(error, '자동 촬영 이벤트를 처리하지 못했습니다.')
      );
    }
  };

  useEffect(() => {
    const connectedDeviceId = connectedDeviceIdRef.current;
    if (!connectedDeviceId || connectedDeviceId === currentUser?.deviceId) {
      return;
    }

    void clearGlassConnection({
      disconnectGatt: true,
      message:
        '선택된 기기가 변경되어 기존 글래스 연결을 정리했습니다. 새 기기로 다시 연결해 주세요.',
    });
  }, [currentUser?.deviceId]);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  useEffect(() => {
    clearAutoCaptureTimer();

    if (!captureControl?.enabled || !currentUser?.deviceId) {
      return;
    }

    const intervalSec = Math.max(
      60,
      captureControl.intervalSec || DEFAULT_CAPTURE_INTERVAL_SEC
    );
    const scheduleAfterSec =
      captureControl.lastCaptureEventAt &&
      typeof captureControl.nextCaptureAfterSec === 'number'
        ? Math.max(1, captureControl.nextCaptureAfterSec)
        : intervalSec;

    autoCaptureTimerRef.current = setInterval(() => {
      void runAutoCapture('scheduled_capture');
    }, scheduleAfterSec * 1000);

    return () => {
      clearAutoCaptureTimer();
    };
  }, [
    captureControl?.enabled,
    captureControl?.intervalSec,
    captureControl?.lastCaptureEventAt,
    captureControl?.nextCaptureAfterSec,
    currentUser?.authToken,
    currentUser?.deviceId,
    currentUser?.userId,
  ]);

  useEffect(() => {
    if (!captureControl?.enabled || !currentUser?.deviceId) {
      autoCaptureStartKeyRef.current = null;
      return;
    }

    if (!rxRef.current || isCaptureStatusBusy(statusRef.current)) {
      return;
    }

    const startKey = [
      currentUser.userId,
      currentUser.deviceId,
      captureControl.updatedAt || 'enabled',
    ].join(':');

    if (autoCaptureStartKeyRef.current === startKey) {
      return;
    }

    autoCaptureStartKeyRef.current = startKey;
    void runAutoCapture('start_capture');
  }, [
    captureControl?.enabled,
    captureControl?.updatedAt,
    currentUser?.deviceId,
    currentUser?.userId,
    status,
  ]);

  useEffect(() => {
    return () => {
      void clearGlassConnection({ disconnectGatt: false });
    };
  }, []);

  return (
    <GlassConnectionContext.Provider
      value={{
        status,
        capturedFile,
        inferenceResult,
        pipelineErrorMessage,
        hasGlassConnection,
        isBusy,
        completedCaptureCount,
        connectGlass,
        requestCapture,
      }}
    >
      {children}
    </GlassConnectionContext.Provider>
  );
}

export function useGlassConnection() {
  const context = useContext(GlassConnectionContext);

  if (!context) {
    throw new Error(
      'useGlassConnection must be used within a GlassConnectionProvider'
    );
  }

  return context;
}
