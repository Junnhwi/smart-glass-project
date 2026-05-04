import React, { useMemo, useState } from 'react';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  ActivityIndicator,
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
  registerMediaCapture,
  requestMediaUploadAuthorization,
  type CaptureAcceptedResponse,
  type CaptureRegistrationPayload,
  type UploadAuthorizationResponse,
} from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

const DEFAULT_FILE_NAME = 'smart-glass-photo.jpg';

export default function SettingsScreen() {
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [notificationEnabled, setNotificationEnabled] = useState(true);
  const [fileName, setFileName] = useState(DEFAULT_FILE_NAME);
  const [isPreparing, setIsPreparing] = useState(false);
  const [isRegistering, setIsRegistering] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [uploadAuthorization, setUploadAuthorization] =
    useState<UploadAuthorizationResponse | null>(null);
  const [capturePayload, setCapturePayload] =
    useState<CaptureRegistrationPayload | null>(null);
  const [captureResponse, setCaptureResponse] =
    useState<CaptureAcceptedResponse | null>(null);

  const navigation = useNavigation<any>();
  const { currentUser } = useAuth();

  const resolvedFileName = useMemo(() => {
    const normalized = fileName.trim();
    return normalized || DEFAULT_FILE_NAME;
  }, [fileName]);

  const prepareCaptureFlow = async () => {
    if (!currentUser || isPreparing) {
      return;
    }

    setIsPreparing(true);
    setErrorMessage('');
    setCaptureResponse(null);

    try {
      const authorization = await requestMediaUploadAuthorization({
        deviceId: currentUser.deviceId,
        fileName: resolvedFileName,
        contentType: 'image/jpeg',
      });

      if (authorization.status !== 'allowed' || !authorization.userId) {
        throw new Error('Device is not allowed to upload captures.');
      }
      if (!authorization.upload) {
        throw new Error('Upload plan is missing from the authorization response.');
      }

      const payload = buildCaptureRegistrationPayload({
        userId: authorization.userId,
        deviceId: authorization.deviceId,
        uploadPlan: authorization.upload,
      });

      setUploadAuthorization(authorization);
      setCapturePayload(payload);
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Failed to prepare capture upload.';
      setErrorMessage(message);
      setUploadAuthorization(null);
      setCapturePayload(null);
    } finally {
      setIsPreparing(false);
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
          <Text style={styles.captureTitle}>Capture Contract Test</Text>
          <Text style={styles.captureDescription}>
            This prepares the upload plan from `deviceId` and builds the exact
            `/media/captures` payload the client should send after direct upload.
          </Text>

          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>Signed-in Device</Text>
            <Text style={styles.readonlyValue}>
              {currentUser?.deviceId || 'Not connected'}
            </Text>
          </View>

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
              isPreparing && styles.primaryButtonDisabled,
            ]}
            onPress={() => {
              void prepareCaptureFlow();
            }}
            disabled={isPreparing || !currentUser}
          >
            {isPreparing ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" color="#FFFFFF" />
                <Text style={styles.primaryButtonText}>Preparing...</Text>
              </View>
            ) : (
              <Text style={styles.primaryButtonText}>Prepare Upload Plan</Text>
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

          {errorMessage ? (
            <Text style={styles.errorText}>{errorMessage}</Text>
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
                memoryId: {uploadAuthorization.upload.memoryId}
              </Text>
              <Text style={styles.resultText}>
                imageKey: {uploadAuthorization.upload.sourceImage.imageKey}
              </Text>
              <Text style={styles.resultText}>
                capturedAt: {uploadAuthorization.upload.capturedAt}
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
                This only verifies the client-to-API contract. The actual object
                still needs to exist in storage for the worker to succeed later.
              </Text>
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
