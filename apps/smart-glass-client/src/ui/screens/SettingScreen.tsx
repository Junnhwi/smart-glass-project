import * as ImagePicker from 'expo-image-picker';
import React, { useMemo, useState } from 'react';
import { useNavigation } from '@react-navigation/native';
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
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

const DEFAULT_FILE_NAME = 'smart-glass-photo.jpg';

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
    throw new Error('Failed to read the selected image file.');
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

  const navigation = useNavigation<any>();
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
          throw new Error('Media library permission is required to choose a photo.');
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
        throw new Error('No image was selected.');
      }

      if (asset.type && asset.type !== 'image') {
        throw new Error('Please choose an image file.');
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
          : 'Failed to choose a photo.';
      setErrorMessage(message);
    } finally {
      setIsPicking(false);
    }
  };

  const uploadSelectedPhoto = async () => {
    if (!currentUser || !selectedAsset || isUploading) {
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
        throw new Error('Device is not allowed to upload captures.');
      }
      if (!authorization.upload) {
        throw new Error('Upload plan is missing from the authorization response.');
      }
      if (!authorization.upload.uploadUrl) {
        throw new Error('Upload URL is missing from the authorization response.');
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
      setUploadMessage('Photo uploaded to object storage and ready for capture registration.');
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Failed to upload the selected photo.';
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
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Failed to register capture.';
      setErrorMessage(message);
      setCaptureResponse(null);
    } finally {
      setIsRegistering(false);
    }
  };

  const refreshTaskStatus = async () => {
    if (!captureResponse?.taskId || isPollingTask) {
      return;
    }

    setIsPollingTask(true);
    setErrorMessage('');

    try {
      const response = await getCaptureTaskStatus(captureResponse.taskId);
      setCaptureTaskStatus(response);
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Failed to refresh capture task status.';
      setErrorMessage(message);
    } finally {
      setIsPollingTask(false);
    }
  };

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable onPress={() => navigation.goBack()}>
          <Text style={styles.backButton}>{'<'}</Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>Settings</Text>

        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.item}>
          <Text style={styles.label}>Voice Input</Text>
          <Switch value={voiceEnabled} onValueChange={setVoiceEnabled} />
        </View>

        <View style={styles.item}>
          <Text style={styles.label}>Notifications</Text>
          <Switch
            value={notificationEnabled}
            onValueChange={setNotificationEnabled}
          />
        </View>

        <View style={[commonStyles.card, styles.captureCard]}>
          <Text style={styles.captureTitle}>Real Capture Upload Test</Text>
          <Text style={styles.captureDescription}>
            Choose a real image, request upload authorization from `deviceId`,
            upload the bytes to object storage, and then queue `/media/captures`.
          </Text>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>Signed-in Device</Text>
            <Text style={styles.readonlyValue}>
              {currentUser?.deviceId || 'Not connected'}
            </Text>
          </View>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>Selected Photo</Text>
            {selectedAsset ? (
              <View style={styles.assetCard}>
                <Image
                  source={{ uri: selectedAsset.uri }}
                  style={styles.previewImage}
                  resizeMode="cover"
                />
                <Text style={styles.resultText}>
                  fileName: {selectedAsset.fileName || resolvedFileName}
                </Text>
                <Text style={styles.resultText}>
                  mimeType: {resolvedContentType}
                </Text>
                <Text style={styles.resultText}>
                  size: {formatFileSize(selectedAsset.fileSize) || 'Unknown'}
                </Text>
              </View>
            ) : (
              <Text style={styles.emptyStateText}>
                Choose an image first so we can upload real bytes to object storage.
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
                <Text style={styles.secondaryButtonText}>Choosing...</Text>
              </View>
            ) : (
              <Text style={styles.secondaryButtonText}>Choose Photo</Text>
            )}
          </Pressable>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>Upload File Name</Text>
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
              (!selectedAsset || isUploading) && styles.primaryButtonDisabled,
            ]}
            onPress={() => {
              void uploadSelectedPhoto();
            }}
            disabled={!selectedAsset || isUploading || !currentUser}
          >
            {isUploading ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color="#FFFFFF" />
                <Text style={styles.primaryButtonText}>Uploading...</Text>
              </View>
            ) : (
              <Text style={styles.primaryButtonText}>Upload to Storage</Text>
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
                <Text style={styles.secondaryButtonText}>Registering...</Text>
              </View>
            ) : (
              <Text style={styles.secondaryButtonText}>Queue Capture</Text>
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
                <Text style={styles.secondaryButtonText}>Refreshing...</Text>
              </View>
            ) : (
              <Text style={styles.secondaryButtonText}>Refresh Task Status</Text>
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
              <Text style={styles.resultTitle}>Upload Plan</Text>
              <Text style={styles.resultText}>
                userId: {uploadAuthorization.userId}
              </Text>
              <Text style={styles.resultText}>
                captureId: {uploadAuthorization.upload.captureId}
              </Text>
              <Text style={styles.resultText}>
                imageKey: {uploadAuthorization.upload.sourceImage.imageKey}
              </Text>
              <Text style={styles.resultText}>
                expiresAt: {uploadAuthorization.upload.expiresAt}
              </Text>
            </View>
          ) : null}

          {capturePayload ? (
            <View style={styles.resultBox}>
              <Text style={styles.resultTitle}>Capture Payload</Text>
              <Text style={styles.resultText}>
                deviceId: {capturePayload.deviceId}
              </Text>
              <Text style={styles.resultText}>
                requestId: {capturePayload.requestId}
              </Text>
              <Text style={styles.resultText}>
                imageKey: {capturePayload.sourceImage.imageKey}
              </Text>
            </View>
          ) : null}

          {captureResponse ? (
            <View style={styles.resultBox}>
              <Text style={styles.resultTitle}>Queue Result</Text>
              <Text style={styles.resultText}>taskId: {captureResponse.taskId}</Text>
              <Text style={styles.resultText}>
                workerStatus: {captureResponse.worker.status}
              </Text>
              <Text style={styles.resultHint}>
                The source image is now uploaded, so the queued worker can read it
                from object storage on the backend side.
              </Text>
            </View>
          ) : null}

          {captureTaskStatus ? (
            <View style={styles.resultBox}>
              <Text style={styles.resultTitle}>Task Status</Text>
              <Text style={styles.resultText}>
                status: {captureTaskStatus.status}
              </Text>
              <Text style={styles.resultText}>
                workerStatus: {captureTaskStatus.worker.status}
              </Text>
              <Text style={styles.resultText}>
                memoryStore: {captureTaskStatus.memoryStore?.status || 'pending'}
              </Text>
              {captureTaskStatus.worker.error ? (
                <Text style={styles.errorText}>
                  workerError: {captureTaskStatus.worker.error}
                </Text>
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
});
