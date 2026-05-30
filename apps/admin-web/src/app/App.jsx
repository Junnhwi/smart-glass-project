import { useEffect, useMemo, useRef, useState } from 'react';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || '/api';
const STORAGE_KEY = 'smart-glass-admin.session';
const AUTO_REFRESH_INTERVAL_MS = 3000;
const TASK_POLL_INTERVAL_MS = 3000;
const TASK_POLL_MAX_ATTEMPTS = 100;

const formatTime = (value) => {
  if (!value) {
    return '정보 없음';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
};

const buildErrorMessage = async (response) => {
  const rawText = await response.text();
  if (!rawText) {
    return `Request failed with ${response.status}`;
  }

  try {
    const parsed = JSON.parse(rawText);
    if (typeof parsed?.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail.trim();
    }
  } catch {
    // Preserve non-JSON error bodies returned by proxies and upstream services.
  }

  return rawText;
};

const requestJson = async (path, { method = 'GET', token, body } = {}) => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    throw new Error(await buildErrorMessage(response));
  }

  return response.json();
};

const requestRefreshToken = async (refreshToken) => {
  return requestJson('/auth/refresh', {
    method: 'POST',
    body: {
      refreshToken,
    },
  });
};

export default function App() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [session, setSession] = useState(() => {
    if (typeof window === 'undefined') {
      return null;
    }
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedUserDevices, setSelectedUserDevices] = useState([]);
  const [pendingPairings, setPendingPairings] = useState([]);
  const [memoryLogs, setMemoryLogs] = useState([]);
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [isLoadingDevices, setIsLoadingDevices] = useState(false);
  const [isLoadingPairings, setIsLoadingPairings] = useState(false);
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);
  const [busyActionKey, setBusyActionKey] = useState('');
  const [logFilter, setLogFilter] = useState('all');
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadDeviceId, setUploadDeviceId] = useState('');
  const [uploadStatus, setUploadStatus] = useState('대기 중');
  const [uploadResult, setUploadResult] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const refreshPromiseRef = useRef(null);

  const authToken = session?.accessToken || '';
  const buildSessionBundle = (response) => {
    const now = Date.now();
    return {
      accessToken: response.accessToken,
      refreshToken: response.refreshToken,
      accessTokenExpiresAt: new Date(
        now + (response.expiresInSec || 0) * 1000
      ).toISOString(),
      refreshTokenExpiresAt: new Date(
        now + (response.refreshExpiresInSec || 0) * 1000
      ).toISOString(),
      user: response.user,
    };
  };
  const clearSessionState = (feedbackMessage = '', errorMessage = '') => {
    setSession(null);
    setUsers([]);
    setSelectedUserId('');
    setSelectedUserDevices([]);
    setPendingPairings([]);
    setMemoryLogs([]);
    setFeedback(feedbackMessage);
    setError(errorMessage);
  };
  const refreshSession = async () => {
    if (!session?.refreshToken) {
      clearSessionState('', '세션이 만료되었습니다. 다시 로그인해 주세요.');
      throw new Error('세션이 만료되었습니다. 다시 로그인해 주세요.');
    }

    if (refreshPromiseRef.current) {
      return refreshPromiseRef.current;
    }

    refreshPromiseRef.current = requestRefreshToken(session.refreshToken)
      .then((response) => {
        if (response.user?.role !== 'admin') {
          throw new Error('관리자 세션만 자동 연장할 수 있습니다.');
        }
        const nextSession = buildSessionBundle(response);
        setSession(nextSession);
        return nextSession;
      })
      .catch((nextError) => {
        clearSessionState('', '세션이 만료되었습니다. 다시 로그인해 주세요.');
        throw nextError;
      })
      .finally(() => {
        refreshPromiseRef.current = null;
      });

    return refreshPromiseRef.current;
  };
  const authRequest = async (path, options = {}) => {
    const perform = async (token) =>
      requestJson(path, {
        ...options,
        token,
      });

    try {
      return await perform(authToken);
    } catch (nextError) {
      const message =
        nextError instanceof Error ? nextError.message.toLowerCase() : '';
      const shouldRefresh =
        message.includes('401') ||
        message.includes('unauthorized') ||
        message.includes('invalid or expired token');

      if (!shouldRefresh) {
        throw nextError;
      }

      const nextSession = await refreshSession();
      return perform(nextSession.accessToken);
    }
  };
  const visibleUsers = useMemo(() => {
    const currentAdminUserId = session?.user?.userId || '';
    return users.filter((user) => user.userId !== currentAdminUserId);
  }, [session?.user?.userId, users]);
  const selectedUser =
    visibleUsers.find((user) => user.userId === selectedUserId) || null;
  const activeUploadDevices = useMemo(
    () => selectedUserDevices.filter((device) => device.status === 'active'),
    [selectedUserDevices]
  );

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    if (!session) {
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  }, [session]);

  useEffect(() => {
    if (!session?.refreshToken) {
      return;
    }

    const expiresAt = session.accessTokenExpiresAt
      ? new Date(session.accessTokenExpiresAt).getTime()
      : NaN;
    if (!Number.isFinite(expiresAt)) {
      return;
    }

    const refreshDelayMs = Math.max(expiresAt - Date.now() - 60_000, 5_000);
    const timer = window.setTimeout(() => {
      void refreshSession().catch((nextError) => {
        setError(
          nextError instanceof Error
            ? nextError.message
            : '세션을 자동으로 연장하지 못했습니다.'
        );
      });
    }, refreshDelayMs);

    return () => {
      window.clearTimeout(timer);
    };
    // refreshSession intentionally follows the current session snapshot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.accessTokenExpiresAt, session?.refreshToken]);

  const loadUsers = async ({ silent = false } = {}) => {
    if (!authToken) {
      setUsers([]);
      return;
    }

    if (!silent) {
      setIsLoadingUsers(true);
      setError('');
    }
    try {
      const response = await authRequest('/admin/auth/users?limit=100');
      setUsers(response.items || []);
      setSelectedUserId((prev) => {
        const visibleItems = (response.items || []).filter(
          (item) => item.userId !== session?.user?.userId
        );
        if (prev && visibleItems.some((item) => item.userId === prev)) {
          return prev;
        }
        return visibleItems[0]?.userId || '';
      });
    } catch (nextError) {
      if (!silent) {
        setError(
          nextError instanceof Error
            ? nextError.message
            : '사용자 목록을 불러오지 못했습니다.'
        );
      }
    } finally {
      if (!silent) {
        setIsLoadingUsers(false);
      }
    }
  };

  const loadUserDevices = async (userId, { silent = false } = {}) => {
    if (!authToken || !userId) {
      setSelectedUserDevices([]);
      return;
    }

    if (!silent) {
      setIsLoadingDevices(true);
      setError('');
    }
    try {
      const response = await authRequest(
        `/admin/users/${encodeURIComponent(userId)}/devices`
      );
      setSelectedUserDevices(response.items || []);
    } catch (nextError) {
      if (!silent) {
        setError(
          nextError instanceof Error
            ? nextError.message
            : '기기 목록을 불러오지 못했습니다.'
        );
      }
    } finally {
      if (!silent) {
        setIsLoadingDevices(false);
      }
    }
  };

  const loadPendingPairings = async ({ silent = false } = {}) => {
    if (!authToken) {
      setPendingPairings([]);
      return;
    }

    if (!silent) {
      setIsLoadingPairings(true);
      setError('');
    }
    try {
      const response = await authRequest(
        '/admin/device-pairings?status=pending&limit=100'
      );
      setPendingPairings(response.items || []);
    } catch (nextError) {
      if (!silent) {
        setError(
          nextError instanceof Error
            ? nextError.message
            : '페어링 요청을 불러오지 못했습니다.'
        );
      }
    } finally {
      if (!silent) {
        setIsLoadingPairings(false);
      }
    }
  };

  const loadMemoryLogs = async ({
    userId = selectedUserId,
    type = logFilter,
    silent = false,
  } = {}) => {
    if (!authToken) {
      setMemoryLogs([]);
      return;
    }

    const query = new URLSearchParams();
    if (userId) {
      query.set('userId', userId);
    }
    if (type && type !== 'all') {
      query.set('queryType', type);
    }
    query.set('limit', '50');

    if (!silent) {
      setIsLoadingLogs(true);
      setError('');
    }
    try {
      const response = await authRequest(
        `/admin/memory-query-logs?${query.toString()}`
      );
      setMemoryLogs(response.items || []);
    } catch (nextError) {
      if (!silent) {
        setError(
          nextError instanceof Error
            ? nextError.message
            : '검색 및 채팅 로그를 불러오지 못했습니다.'
        );
      }
    } finally {
      if (!silent) {
        setIsLoadingLogs(false);
      }
    }
  };

  useEffect(() => {
    if (!authToken) {
      return;
    }

    void loadUsers();
    void loadPendingPairings();
    void loadMemoryLogs({ userId: '', type: 'all' });
    // Loader functions intentionally use the session bound to this auth token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authToken]);

  useEffect(() => {
    if (!selectedUserId) {
      setSelectedUserDevices([]);
      setUploadDeviceId('');
      return;
    }

    void loadUserDevices(selectedUserId);
    void loadMemoryLogs({ userId: selectedUserId, type: logFilter });
    // A user selection change is the only trigger needed for this refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authToken, selectedUserId]);

  useEffect(() => {
    if (
      uploadDeviceId &&
      activeUploadDevices.some((device) => device.deviceId === uploadDeviceId)
    ) {
      return;
    }
    setUploadDeviceId(activeUploadDevices[0]?.deviceId || '');
  }, [activeUploadDevices, uploadDeviceId]);

  useEffect(() => {
    if (!authToken) {
      return;
    }

    void loadMemoryLogs({ userId: selectedUserId, type: logFilter });
    // selectedUserId is refreshed by the dedicated selection effect above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authToken, logFilter]);

  useEffect(() => {
    if (!authToken) {
      return;
    }

    const interval = window.setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return;
      }

      void loadUsers({ silent: true });
      void loadPendingPairings({ silent: true });
      void loadMemoryLogs({
        userId: selectedUserId,
        type: logFilter,
        silent: true,
      });

      if (selectedUserId) {
        void loadUserDevices(selectedUserId, { silent: true });
      }
    }, AUTO_REFRESH_INTERVAL_MS);

    return () => {
      window.clearInterval(interval);
    };
    // Interval callbacks intentionally capture the latest visible selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authToken, logFilter, selectedUserId]);

  const handleLogin = async (event) => {
    event.preventDefault();
    if (isLoggingIn) {
      return;
    }

    setIsLoggingIn(true);
    setError('');
    setFeedback('');

    try {
      const response = await requestJson('/auth/login', {
        method: 'POST',
        body: {
          email,
          password,
        },
      });

      if (response.user?.role !== 'admin') {
        throw new Error('관리자 권한이 있는 계정으로 로그인해주세요.');
      }

      setSession(buildSessionBundle(response));
      setFeedback('관리자 세션이 연결되었습니다.');
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : '로그인하지 못했습니다.'
      );
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = () => {
    clearSessionState('관리자 세션을 종료했습니다.');
  };

  const handleDeviceAction = async (userId, deviceId, action) => {
    const actionKey = `${userId}:${deviceId}:${action}`;
    setBusyActionKey(actionKey);
    setError('');
    setFeedback('');
    try {
      await authRequest(
        `/admin/users/${encodeURIComponent(userId)}/devices/${encodeURIComponent(deviceId)}/${action}`,
        {
          method: 'POST',
          body: {},
        }
      );
      setFeedback(
        action === 'approve'
          ? '기기를 다시 활성화했습니다.'
          : '기기를 비활성화했습니다.'
      );
      await loadUserDevices(userId);
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : '기기 상태를 바꾸지 못했습니다.'
      );
    } finally {
      setBusyActionKey('');
    }
  };

  const handlePairingAction = async (pairingCode, action) => {
    setBusyActionKey(`${pairingCode}:${action}`);
    setError('');
    setFeedback('');
    try {
      await authRequest(
        `/admin/device-pairings/${encodeURIComponent(pairingCode)}/${action}`,
        {
          method: 'POST',
          body: {},
        }
      );
      setFeedback(
        action === 'approve'
          ? `페어링 ${pairingCode} 를 승인했습니다.`
          : `페어링 ${pairingCode} 를 거절했습니다.`
      );
      await loadPendingPairings();
      if (selectedUserId) {
        await loadUserDevices(selectedUserId);
        await loadMemoryLogs({ userId: selectedUserId, type: logFilter });
      }
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : '페어링 요청을 처리하지 못했습니다.'
      );
    } finally {
      setBusyActionKey('');
    }
  };

  const pollCaptureTask = async (taskId) => {
    for (let attempt = 0; attempt < TASK_POLL_MAX_ATTEMPTS; attempt += 1) {
      const task = await requestJson(
        `/media/captures/tasks/${encodeURIComponent(taskId)}`
      );
      setUploadResult(task);
      setUploadStatus(`추론 상태: ${task.status}`);
      if (['completed', 'partial', 'failed'].includes(task.status)) {
        return task;
      }
      await new Promise((resolve) => {
        window.setTimeout(resolve, TASK_POLL_INTERVAL_MS);
      });
    }
    throw new Error('추론 결과 대기 시간이 초과되었습니다.');
  };

  const handleUpload = async () => {
    if (!selectedUser?.userId) {
      setError('업로드할 사용자를 선택해 주세요.');
      return;
    }
    if (!uploadDeviceId) {
      setError('선택한 사용자의 활성 기기가 필요합니다.');
      return;
    }
    if (!uploadFile) {
      setError('업로드할 이미지 파일을 선택해 주세요.');
      return;
    }

    setIsUploading(true);
    setError('');
    setFeedback('');
    setUploadResult(null);

    try {
      const capturedAt = new Date().toISOString();
      setUploadStatus('업로드 허용 요청 중');
      const authorization = await requestJson('/media/upload-authorizations', {
        method: 'POST',
        body: {
          deviceId: uploadDeviceId,
          taskType: 'metadata',
          capturedAt,
          fileName: uploadFile.name,
          contentType: uploadFile.type || undefined,
        },
      });
      if (authorization.status !== 'allowed' || !authorization.upload) {
        throw new Error('선택한 기기의 업로드가 허용되지 않았습니다.');
      }

      const uploadPlan = authorization.upload;
      const contentType =
        uploadFile.type || uploadPlan.sourceImage?.contentType || '';
      setUploadStatus('Object Storage 업로드 중');
      const uploadResponse = await fetch(uploadPlan.uploadUrl, {
        method: 'PUT',
        headers: contentType ? { 'Content-Type': contentType } : {},
        body: uploadFile,
      });
      if (!uploadResponse.ok) {
        throw new Error(
          (await uploadResponse.text()) ||
            `Object Storage upload failed with ${uploadResponse.status}`
        );
      }

      setUploadStatus('캡처 등록 중');
      const capture = await requestJson('/media/captures', {
        method: 'POST',
        body: {
          captureId: uploadPlan.captureId,
          requestId: uploadPlan.requestId,
          memoryId: uploadPlan.memoryId,
          userId: authorization.userId,
          deviceId: authorization.deviceId,
          taskType: uploadPlan.taskType,
          capturedAt: uploadPlan.capturedAt,
          sourceImage: uploadPlan.sourceImage,
        },
      });
      setUploadResult(capture);
      setUploadStatus(`추론 상태: ${capture.worker?.status || 'queued'}`);

      if (capture.taskId) {
        const task = await pollCaptureTask(capture.taskId);
        if (task.status === 'failed') {
          throw new Error(task.worker?.error || '추론 작업이 실패했습니다.');
        }
      }

      setFeedback('이미지 업로드와 추론 저장이 완료되었습니다.');
      await loadMemoryLogs({ userId: selectedUser.userId, type: logFilter });
    } catch (nextError) {
      setUploadStatus('업로드 또는 추론 실패');
      setError(
        nextError instanceof Error
          ? nextError.message
          : '이미지 업로드를 완료하지 못했습니다.'
      );
    } finally {
      setIsUploading(false);
    }
  };

  const userSummary = useMemo(() => {
    const activeUsers = visibleUsers.filter((user) => user.status === 'active').length;
    const failedLogs = memoryLogs.filter((log) => log.totalHits === 0).length;
    return {
      totalUsers: visibleUsers.length,
      activeUsers,
      pendingPairings: pendingPairings.length,
      failedLogs,
    };
  }, [memoryLogs, pendingPairings.length, visibleUsers]);

  return (
    <div className="admin-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Smart Glass Ops</p>
          <h1>기기 승인과 사용자 로그를 한 화면에서 관리</h1>
          <p className="hero-copy">
            공용 관리자 계정으로 로그인한 뒤 사용자별 기기 상태, 페어링 승인,
            채팅과 검색 기록까지 바로 확인할 수 있는 운영 콘솔입니다.
          </p>
        </div>
        <div className="hero-stats">
          <div className="stat-card">
            <span className="stat-label">등록 사용자</span>
            <strong>{userSummary.totalUsers}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-label">활성 사용자</span>
            <strong>{userSummary.activeUsers}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-label">대기 페어링</span>
            <strong>{userSummary.pendingPairings}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-label">실패 로그 수</span>
            <strong>{userSummary.failedLogs}</strong>
          </div>
        </div>
      </header>

      <main className="dashboard-grid">
        <section className="panel login-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Shared Admin</p>
              <h2>{session?.user ? '관리자 세션' : '공용 관리자 로그인'}</h2>
            </div>
            {session?.user ? (
              <button className="ghost-button" onClick={handleLogout}>
                로그아웃
              </button>
            ) : null}
          </div>

          <div className="session-summary">
            <p className="session-title">관리자 전용 로그인</p>
            <p className="muted-copy">
              배포 환경에서 bootstrap한 관리자 계정으로 로그인하세요.
            </p>
          </div>

          {session?.user ? (
            <div className="session-summary">
              <p className="session-title">{session.user.displayName}</p>
              <p>{session.user.email}</p>
              <p>
                역할: <strong>{session.user.role}</strong>
              </p>
              <p>
                상태: <strong>연결됨</strong>
              </p>
            </div>
          ) : (
            <>
              <form className="login-form" onSubmit={handleLogin}>
                <label className="field">
                  <span>이메일</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="admin@example.com"
                  />
                </label>
                <label className="field">
                  <span>비밀번호</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="관리자 비밀번호"
                  />
                </label>
                <button className="primary-button" type="submit" disabled={isLoggingIn}>
                  {isLoggingIn ? '연결 중...' : '관리자 로그인'}
                </button>
              </form>

              <p className="muted-copy">
                로그인하면 사용자 목록, 기기 승인, 검색/채팅 로그 패널이 열립니다.
              </p>
            </>
          )}

          {feedback ? <div className="feedback success">{feedback}</div> : null}
          {error ? <div className="feedback error">{error}</div> : null}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">User Directory</p>
              <h2>사용자 목록</h2>
            </div>
            <button
              className="ghost-button"
              onClick={() => {
                void loadUsers();
              }}
              disabled={!authToken || isLoadingUsers}
            >
              새로고침
            </button>
          </div>

          {isLoadingUsers ? (
            <p className="muted-copy">사용자를 불러오는 중입니다.</p>
          ) : null}

          <div className="user-list">
            {visibleUsers.map((user) => (
              <button
                key={user.userId}
                className={`user-item ${selectedUserId === user.userId ? 'selected' : ''}`}
                onClick={() => setSelectedUserId(user.userId)}
                type="button"
              >
                <div>
                  <strong>{user.displayName}</strong>
                  <p>{user.email}</p>
                  <p className="mono">{user.userId}</p>
                </div>
                <div className="user-badges">
                  <span className={`pill ${user.status === 'active' ? 'active' : 'danger'}`}>
                    {user.status}
                  </span>
                  <span className="pill neutral">{user.role}</span>
                </div>
              </button>
            ))}
            {!isLoadingUsers && visibleUsers.length === 0 ? (
              <p className="muted-copy">관리자 세션을 연결하면 사용자 목록이 표시됩니다.</p>
            ) : null}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Pairing Queue</p>
              <h2>대기 중인 페어링</h2>
            </div>
            <button
              className="ghost-button"
              onClick={() => {
                void loadPendingPairings();
              }}
              disabled={!authToken || isLoadingPairings}
            >
              새로고침
            </button>
          </div>

          {isLoadingPairings ? (
            <p className="muted-copy">페어링 요청을 불러오는 중입니다.</p>
          ) : null}

          <div className="pairing-list">
            {pendingPairings.map((pairing) => (
              <article key={pairing.pairingCode} className="pairing-card">
                <div className="pairing-card-top">
                  <div>
                    <strong>{pairing.deviceId}</strong>
                    <p className="mono">코드: {pairing.pairingCode}</p>
                  </div>
                  <span className="pill warning">pending</span>
                </div>
                <p className="meta-line">사용자: {pairing.userId}</p>
                <p className="meta-line">생성: {formatTime(pairing.createdAt)}</p>
                <p className="meta-line">만료: {formatTime(pairing.expiresAt)}</p>
                <div className="inline-actions">
                  <button
                    className="primary-button compact"
                    onClick={() => {
                      void handlePairingAction(pairing.pairingCode, 'approve');
                    }}
                    disabled={busyActionKey === `${pairing.pairingCode}:approve`}
                    type="button"
                  >
                    승인
                  </button>
                  <button
                    className="ghost-button compact danger-text"
                    onClick={() => {
                      void handlePairingAction(pairing.pairingCode, 'reject');
                    }}
                    disabled={busyActionKey === `${pairing.pairingCode}:reject`}
                    type="button"
                  >
                    거절
                  </button>
                </div>
              </article>
            ))}
            {!isLoadingPairings && pendingPairings.length === 0 ? (
              <p className="muted-copy">현재 승인 대기 중인 페어링 요청이 없습니다.</p>
            ) : null}
          </div>
        </section>

        <section className="panel wide-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Device Control</p>
              <h2>{selectedUser ? `${selectedUser.displayName}의 기기` : '사용자 기기 상태'}</h2>
            </div>
            {selectedUser ? (
              <button
                className="ghost-button"
                onClick={() => {
                  void loadUserDevices(selectedUser.userId);
                }}
                disabled={!authToken || isLoadingDevices}
              >
                새로고침
              </button>
            ) : null}
          </div>

          {selectedUser ? (
            <div className="selected-user-summary">
              <div>
                <strong>{selectedUser.displayName}</strong>
                <p>{selectedUser.email}</p>
              </div>
              <div className="user-badges">
                <span className={`pill ${selectedUser.status === 'active' ? 'active' : 'danger'}`}>
                  {selectedUser.status}
                </span>
                <span className="pill neutral">{selectedUser.role}</span>
              </div>
            </div>
          ) : (
            <p className="muted-copy">
              왼쪽 목록에서 사용자를 선택하면 연결된 기기를 볼 수 있습니다.
            </p>
          )}

          <div className="device-table">
            {selectedUserDevices.map((device) => {
              const revokeKey = `${device.userId}:${device.deviceId}:revoke`;
              const approveKey = `${device.userId}:${device.deviceId}:approve`;
              return (
                <article key={`${device.userId}:${device.deviceId}`} className="device-card">
                  <div className="device-card-top">
                    <div>
                      <strong>{device.displayName || device.deviceId}</strong>
                      {device.displayName ? (
                        <p className="meta-line mono">ID: {device.deviceId}</p>
                      ) : null}
                      <p className="meta-line">등록: {formatTime(device.registeredAt)}</p>
                    </div>
                    <span className={`pill ${device.status === 'active' ? 'active' : 'danger'}`}>
                      {device.status}
                    </span>
                  </div>
                  <p className="meta-line">승인: {formatTime(device.approvedAt)}</p>
                  <p className="meta-line">갱신: {formatTime(device.updatedAt)}</p>
                  <div className="inline-actions">
                    {device.status === 'active' ? (
                      <button
                        className="ghost-button compact danger-text"
                        onClick={() => {
                          void handleDeviceAction(device.userId, device.deviceId, 'revoke');
                        }}
                        disabled={busyActionKey === revokeKey}
                        type="button"
                      >
                        비활성화
                      </button>
                    ) : (
                      <button
                        className="primary-button compact"
                        onClick={() => {
                          void handleDeviceAction(device.userId, device.deviceId, 'approve');
                        }}
                        disabled={busyActionKey === approveKey}
                        type="button"
                      >
                        다시 활성화
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
            {selectedUser && !isLoadingDevices && selectedUserDevices.length === 0 ? (
              <p className="muted-copy">이 사용자에게 등록된 기기가 아직 없습니다.</p>
            ) : null}
          </div>
        </section>

        <section className="panel wide-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Capture Pipeline</p>
              <h2>이미지 업로드 및 추론</h2>
            </div>
            <span className="pill neutral">{uploadStatus}</span>
          </div>

          <div className="upload-grid">
            <div className="login-form">
              <label className="field">
                <span>대상 사용자</span>
                <input value={selectedUser?.displayName || ''} disabled />
              </label>
              <label className="field">
                <span>활성 기기</span>
                <select
                  className="log-filter"
                  value={uploadDeviceId}
                  onChange={(event) => setUploadDeviceId(event.target.value)}
                >
                  <option value="">활성 기기를 선택하세요</option>
                  {activeUploadDevices.map((device) => (
                    <option key={device.deviceId} value={device.deviceId}>
                      {device.displayName || device.deviceId}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>이미지 파일</span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(event) => {
                    setUploadFile(event.target.files?.[0] || null);
                    setUploadResult(null);
                    setUploadStatus('대기 중');
                  }}
                />
              </label>
              <button
                className="primary-button"
                type="button"
                onClick={() => {
                  void handleUpload();
                }}
                disabled={!authToken || isUploading}
              >
                {isUploading ? '업로드 및 추론 진행 중' : '업로드 및 추론 실행'}
              </button>
              <p className="muted-copy">
                선택한 사용자의 활성 기기로 presigned PUT 업로드 후 Celery task를
                polling합니다.
              </p>
            </div>
            <pre className="result-json">
              {uploadResult
                ? JSON.stringify(uploadResult, null, 2)
                : '업로드 후 task 상태와 결과가 표시됩니다.'}
            </pre>
          </div>
        </section>

        <section className="panel wide-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Search And Chat Logs</p>
              <h2>
                {selectedUser
                  ? `${selectedUser.displayName}의 검색/채팅 로그`
                  : '최근 검색/채팅 로그'}
              </h2>
            </div>
            <div className="user-badges">
              <select
                className="log-filter"
                value={logFilter}
                onChange={(event) => setLogFilter(event.target.value)}
              >
                <option value="all">전체</option>
                <option value="search">검색만</option>
                <option value="chat">채팅만</option>
              </select>
              <button
                className="ghost-button"
                onClick={() => {
                  void loadMemoryLogs({ userId: selectedUserId, type: logFilter });
                }}
                disabled={!authToken || isLoadingLogs}
              >
                새로고침
              </button>
            </div>
          </div>

          {isLoadingLogs ? (
            <p className="muted-copy">로그를 불러오는 중입니다.</p>
          ) : null}

          <div className="device-table">
            {memoryLogs.map((log) => (
              <article key={log.logId} className="device-card">
                <div className="device-card-top">
                  <div>
                    <strong>{log.queryText}</strong>
                    <p className="meta-line">사용자: {log.userId}</p>
                  </div>
                  <span
                    className={`pill ${log.queryType === 'chat' ? 'warning' : 'neutral'}`}
                  >
                    {log.queryType}
                  </span>
                </div>
                <p className="meta-line">시간: {formatTime(log.createdAt)}</p>
                <p className="meta-line">검색 결과 수: {log.totalHits}</p>
                {log.answerMode ? (
                  <p className="meta-line">응답 모드: {log.answerMode}</p>
                ) : null}
                {log.answerText ? (
                  <p className="meta-line">답변: {log.answerText}</p>
                ) : null}
                {Array.isArray(log.citedMemoryIds) && log.citedMemoryIds.length > 0 ? (
                  <p className="meta-line mono">
                    기억 ID: {log.citedMemoryIds.join(', ')}
                  </p>
                ) : null}
              </article>
            ))}
            {!isLoadingLogs && memoryLogs.length === 0 ? (
              <p className="muted-copy">표시할 검색/채팅 로그가 없습니다.</p>
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}
