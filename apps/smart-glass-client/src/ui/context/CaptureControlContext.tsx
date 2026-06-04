import React, { createContext, useContext, useEffect, useState } from 'react';

import {
  getCaptureControl,
  updateCaptureControl,
  type CaptureControl,
} from '../../networking/api';
import { useAuth } from './AuthContext';

type RefreshOptions = {
  silent?: boolean;
};

type CaptureControlContextValue = {
  captureControl: CaptureControl | null;
  isLoadingCaptureControl: boolean;
  isUpdatingCaptureControl: boolean;
  captureControlError: string;
  refreshCaptureControl: (options?: RefreshOptions) => Promise<CaptureControl | null>;
  setCaptureControlEnabled: (enabled: boolean) => Promise<CaptureControl | null>;
};

const CaptureControlContext =
  createContext<CaptureControlContextValue | null>(null);

const DEFAULT_CAPTURE_INTERVAL_SEC = 300;

const getErrorMessage = (error: unknown, fallbackMessage: string) =>
  error instanceof Error && error.message ? error.message : fallbackMessage;

const isExpiredTokenError = (error: unknown) =>
  error instanceof Error &&
  error.message.toLowerCase().includes('access token has expired');

export function CaptureControlProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { currentUser, refreshSession } = useAuth();
  const [captureControl, setCaptureControl] = useState<CaptureControl | null>(
    null
  );
  const [isLoadingCaptureControl, setIsLoadingCaptureControl] = useState(false);
  const [isUpdatingCaptureControl, setIsUpdatingCaptureControl] = useState(false);
  const [captureControlError, setCaptureControlError] = useState('');

  const resolveAuthSession = async () => {
    if (!currentUser?.authToken || !currentUser.userId || !currentUser.deviceId) {
      return null;
    }

    return {
      authToken: currentUser.authToken,
      userId: currentUser.userId,
      deviceId: currentUser.deviceId,
    };
  };

  const refreshCaptureControl = async ({ silent = false }: RefreshOptions = {}) => {
    const session = await resolveAuthSession();
    if (!session) {
      setCaptureControl(null);
      return null;
    }

    if (!silent) {
      setIsLoadingCaptureControl(true);
      setCaptureControlError('');
    }

    try {
      let response: CaptureControl;
      try {
        response = await getCaptureControl(session);
      } catch (error) {
        if (!isExpiredTokenError(error)) {
          throw error;
        }

        const refreshedUser = await refreshSession();
        if (!refreshedUser?.authToken || !refreshedUser.deviceId) {
          throw error;
        }
        response = await getCaptureControl({
          authToken: refreshedUser.authToken,
          userId: refreshedUser.userId,
          deviceId: refreshedUser.deviceId,
        });
      }

      setCaptureControl(response);
      return response;
    } catch (error) {
      const message = getErrorMessage(
        error,
        '자동 촬영 설정을 불러오지 못했습니다.'
      );
      if (!silent) {
        setCaptureControlError(message);
      }
      return null;
    } finally {
      if (!silent) {
        setIsLoadingCaptureControl(false);
      }
    }
  };

  const setCaptureControlEnabled = async (enabled: boolean) => {
    const session = await resolveAuthSession();
    if (!session) {
      setCaptureControl(null);
      setCaptureControlError('현재 선택된 기기가 없습니다.');
      return null;
    }

    setIsUpdatingCaptureControl(true);
    setCaptureControlError('');

    try {
      const intervalSec =
        captureControl?.intervalSec || DEFAULT_CAPTURE_INTERVAL_SEC;
      let response: CaptureControl;
      try {
        response = await updateCaptureControl({
          ...session,
          enabled,
          intervalSec,
        });
      } catch (error) {
        if (!isExpiredTokenError(error)) {
          throw error;
        }

        const refreshedUser = await refreshSession();
        if (!refreshedUser?.authToken || !refreshedUser.deviceId) {
          throw error;
        }
        response = await updateCaptureControl({
          authToken: refreshedUser.authToken,
          userId: refreshedUser.userId,
          deviceId: refreshedUser.deviceId,
          enabled,
          intervalSec,
        });
      }

      setCaptureControl(response);
      return response;
    } catch (error) {
      setCaptureControlError(
        getErrorMessage(error, '자동 촬영 설정을 변경하지 못했습니다.')
      );
      return null;
    } finally {
      setIsUpdatingCaptureControl(false);
    }
  };

  useEffect(() => {
    void refreshCaptureControl();
  }, [currentUser?.authToken, currentUser?.userId, currentUser?.deviceId]);

  return (
    <CaptureControlContext.Provider
      value={{
        captureControl,
        isLoadingCaptureControl,
        isUpdatingCaptureControl,
        captureControlError,
        refreshCaptureControl,
        setCaptureControlEnabled,
      }}
    >
      {children}
    </CaptureControlContext.Provider>
  );
}

export function useCaptureControl() {
  const context = useContext(CaptureControlContext);

  if (!context) {
    throw new Error(
      'useCaptureControl must be used within a CaptureControlProvider'
    );
  }

  return context;
}
