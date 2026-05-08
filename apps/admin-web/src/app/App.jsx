import { useEffect, useMemo, useState } from 'react';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8002';
const STORAGE_KEY = 'smart-glass-admin.session';
const SHARED_ADMIN_EMAIL = 'team-admin@smartglass.local';
const SHARED_ADMIN_PASSWORD = 'TeamAdmin123!';

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
  } catch {}

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

export default function App() {
  const [email, setEmail] = useState(SHARED_ADMIN_EMAIL);
  const [password, setPassword] = useState(SHARED_ADMIN_PASSWORD);
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

  const authToken = session?.accessToken || '';
  const selectedUser =
    users.find((user) => user.userId === selectedUserId) || null;

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

  const loadUsers = async () => {
    if (!authToken) {
      setUsers([]);
      return;
    }

    setIsLoadingUsers(true);
    setError('');
    try {
      const response = await requestJson('/admin/auth/users?limit=100', {
        token: authToken,
      });
      setUsers(response.items || []);
      setSelectedUserId((prev) => {
        if (prev && response.items?.some((item) => item.userId === prev)) {
          return prev;
        }
        return response.items?.[0]?.userId || '';
      });
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : '사용자 목록을 불러오지 못했습니다.'
      );
    } finally {
      setIsLoadingUsers(false);
    }
  };

  const loadUserDevices = async (userId) => {
    if (!authToken || !userId) {
      setSelectedUserDevices([]);
      return;
    }

    setIsLoadingDevices(true);
    setError('');
    try {
      const response = await requestJson(
        `/admin/users/${encodeURIComponent(userId)}/devices`,
        { token: authToken }
      );
      setSelectedUserDevices(response.items || []);
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : '기기 목록을 불러오지 못했습니다.'
      );
    } finally {
      setIsLoadingDevices(false);
    }
  };

  const loadPendingPairings = async () => {
    if (!authToken) {
      setPendingPairings([]);
      return;
    }

    setIsLoadingPairings(true);
    setError('');
    try {
      const response = await requestJson(
        '/admin/device-pairings?status=pending&limit=100',
        {
          token: authToken,
        }
      );
      setPendingPairings(response.items || []);
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : '페어링 요청을 불러오지 못했습니다.'
      );
    } finally {
      setIsLoadingPairings(false);
    }
  };

  const loadMemoryLogs = async ({ userId = selectedUserId, type = logFilter } = {}) => {
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

    setIsLoadingLogs(true);
    setError('');
    try {
      const response = await requestJson(
        `/admin/memory-query-logs?${query.toString()}`,
        {
          token: authToken,
        }
      );
      setMemoryLogs(response.items || []);
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : '검색 및 채팅 로그를 불러오지 못했습니다.'
      );
    } finally {
      setIsLoadingLogs(false);
    }
  };

  useEffect(() => {
    if (!authToken) {
      return;
    }

    void loadUsers();
    void loadPendingPairings();
    void loadMemoryLogs({ userId: '', type: 'all' });
  }, [authToken]);

  useEffect(() => {
    if (!selectedUserId) {
      setSelectedUserDevices([]);
      return;
    }

    void loadUserDevices(selectedUserId);
    void loadMemoryLogs({ userId: selectedUserId, type: logFilter });
  }, [authToken, selectedUserId]);

  useEffect(() => {
    if (!authToken) {
      return;
    }

    void loadMemoryLogs({ userId: selectedUserId, type: logFilter });
  }, [authToken, logFilter]);

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

      setSession({
        accessToken: response.accessToken,
        refreshToken: response.refreshToken,
        user: response.user,
      });
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
    setSession(null);
    setUsers([]);
    setSelectedUserId('');
    setSelectedUserDevices([]);
    setPendingPairings([]);
    setMemoryLogs([]);
    setFeedback('관리자 세션을 종료했습니다.');
    setError('');
  };

  const handleDeviceAction = async (userId, deviceId, action) => {
    const actionKey = `${userId}:${deviceId}:${action}`;
    setBusyActionKey(actionKey);
    setError('');
    setFeedback('');
    try {
      await requestJson(
        `/admin/users/${encodeURIComponent(userId)}/devices/${encodeURIComponent(deviceId)}/${action}`,
        {
          method: 'POST',
          token: authToken,
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
      await requestJson(
        `/admin/device-pairings/${encodeURIComponent(pairingCode)}/${action}`,
        {
          method: 'POST',
          token: authToken,
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

  const userSummary = useMemo(() => {
    const activeUsers = users.filter((user) => user.status === 'active').length;
    const adminUsers = users.filter((user) => user.role === 'admin').length;
    return {
      totalUsers: users.length,
      activeUsers,
      adminUsers,
      pendingPairings: pendingPairings.length,
    };
  }, [pendingPairings.length, users]);

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
            <span className="stat-label">관리자 수</span>
            <strong>{userSummary.adminUsers}</strong>
          </div>
        </div>
      </header>

      <main className="dashboard-grid">
        <section className="panel login-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Shared Admin</p>
              <h2>공용 관리자 로그인</h2>
            </div>
            {session?.user ? (
              <button className="ghost-button" onClick={handleLogout}>
                로그아웃
              </button>
            ) : null}
          </div>

          <div className="session-summary">
            <p className="session-title">팀 공용 계정</p>
            <p className="mono">{SHARED_ADMIN_EMAIL}</p>
            <p className="mono">{SHARED_ADMIN_PASSWORD}</p>
          </div>

          <form className="login-form" onSubmit={handleLogin}>
            <label className="field">
              <span>이메일</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder={SHARED_ADMIN_EMAIL}
              />
            </label>
            <label className="field">
              <span>비밀번호</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={SHARED_ADMIN_PASSWORD}
              />
            </label>
            <button className="primary-button" type="submit" disabled={isLoggingIn}>
              {isLoggingIn ? '연결 중...' : '관리자 로그인'}
            </button>
          </form>

          {session?.user ? (
            <div className="session-summary">
              <p className="session-title">{session.user.displayName}</p>
              <p>{session.user.email}</p>
              <p>
                역할: <strong>{session.user.role}</strong>
              </p>
            </div>
          ) : (
            <p className="muted-copy">
              위 공용 계정으로 로그인하면 사용자 목록, 기기 승인, 검색/채팅 로그
              패널이 열립니다.
            </p>
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
            {users.map((user) => (
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
            {!isLoadingUsers && users.length === 0 ? (
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
                      <strong>{device.deviceId}</strong>
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
