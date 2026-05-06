const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8002';

export type MemoryLocation = {
  name?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
};

export type MemorySearchHit = {
  memoryId: string;
  score: number;
  lexicalScore: number;
  matchedTerms: string[];
  imageKey?: string | null;
  imageUrl?: string | null;
  capturedAt?: string | null;
  caption?: string | null;
  sceneSummary?: string | null;
  positionHint?: string | null;
  location: MemoryLocation;
  detectedObjects: string[];
  tags: string[];
};

export type MemoryChatResponse = {
  answer: string;
  answerMode: string;
  query: string;
  totalHits: number;
  hits: MemorySearchHit[];
  citedMemoryIds: string[];
  confidence?: number | null;
  reason?: string | null;
};

export type MediaAccessUrl = {
  imageKey: string;
  accessUrl: string;
  expiresAt: string;
  expiresInSec: number;
};

export type CaptureSourceImageSnapshot = {
  imageKey: string;
  imageUrl?: string | null;
  contentType?: string | null;
  fileName?: string | null;
};

export type UploadAuthorizationPlan = {
  method: 'direct';
  captureId: string;
  requestId: string;
  memoryId: string;
  taskType: 'caption' | 'metadata';
  capturedAt: string;
  uploadUrl: string;
  expiresAt: string;
  expiresInSec: number;
  sourceImage: CaptureSourceImageSnapshot;
};

export type UploadAuthorizationResponse = {
  status: 'allowed' | 'blocked';
  deviceId: string;
  userId?: string | null;
  upload?: UploadAuthorizationPlan | null;
};

export type CaptureRegistrationPayload = {
  captureId: string;
  requestId: string;
  memoryId: string;
  userId: string;
  deviceId: string;
  taskType: 'caption' | 'metadata';
  capturedAt: string;
  sourceImage: CaptureSourceImageSnapshot;
};

export type CaptureAcceptedResponse = {
  status: 'accepted';
  service: 'api-server';
  taskId: string;
  capture: {
    captureId: string;
    requestId: string;
    memoryId: string;
    userId: string;
    taskType: 'caption' | 'metadata';
    capturedAt: string;
    sourceImage: CaptureSourceImageSnapshot;
  };
  worker: {
    taskId: string | null;
    status: 'queued' | 'running' | 'retrying' | 'success' | 'error' | 'timeout';
  };
};

export type CaptureWorkerMetadata = {
  caption?: string | null;
  sceneSummary?: string | null;
  detectedObjects?: string[];
  tags?: string[];
  positionHint?: string | null;
  location?: MemoryLocation;
};

export type CaptureWorkerResult = {
  requestId?: string;
  taskType?: 'caption' | 'metadata';
  memoryId?: string;
  userId?: string;
  capturedAt?: string;
  sourceImage?: CaptureSourceImageSnapshot;
  metadata?: CaptureWorkerMetadata;
  pipelineOutput?: {
    scene_summary?: string | null;
    location_context?: string | null;
  };
};

export type CaptureTaskStatusResponse = {
  status: 'queued' | 'running' | 'retrying' | 'completed' | 'partial' | 'failed';
  service: 'api-server';
  taskId: string;
  worker: {
    taskId: string | null;
    status: 'queued' | 'running' | 'retrying' | 'success' | 'error' | 'timeout';
    result?: CaptureWorkerResult | null;
    error?: string | null;
  };
  memoryStore?: {
    backend: string;
    status: 'success' | 'error' | 'skipped';
    storedCount?: number | null;
    totalUserMemories?: Record<string, number>;
    error?: string | null;
  } | null;
};

type MediaBatchAccessUrlResponse = {
  totalItems: number;
  items: MediaAccessUrl[];
};

export type UserCreateResponse = {
  status: 'created';
  userId: string;
  createdAt: string;
};

export type DeviceRegistrationResponse = {
  status: 'registered';
  userId: string;
  deviceId: string;
  registeredAt: string;
};

export type UserDevice = {
  userId: string;
  deviceId: string;
  status: 'active' | 'revoked';
  registeredAt: string;
  approvedAt?: string | null;
  revokedAt?: string | null;
  updatedAt?: string | null;
};

export type UserDeviceListResponse = {
  status: 'ok';
  userId: string;
  totalDevices: number;
  items: UserDevice[];
};

export type AuthUserPayload = {
  userId: string;
  email: string;
  displayName: string;
  role: 'user' | 'admin';
  status: 'active' | 'disabled';
  createdAt: string;
  lastLoginAt?: string | null;
};

export type AuthTokenResponse = {
  status: 'authenticated';
  tokenType: 'Bearer';
  accessToken: string;
  refreshToken: string;
  expiresInSec: number;
  refreshExpiresInSec: number;
  user: AuthUserPayload;
};

export type AuthLogoutResponse = {
  status: 'logged_out';
  revokedAccessToken: boolean;
  revokedRefreshToken: boolean;
};

export type GoogleOauthStartResponse = {
  provider: 'google';
  authorizationUrl: string;
  state: string;
  expiresAt: string;
};

const buildErrorMessage = async (response: Response) => {
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

const postJson = async <TResponse>(
  path: string,
  payload: Record<string, unknown>,
  options?: { authToken?: string }
): Promise<TResponse> => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (options?.authToken) {
    headers.Authorization = `Bearer ${options.authToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await buildErrorMessage(response));
  }

  return response.json();
};

export const createUser = async ({ userId }: { userId: string }) => {
  return postJson<UserCreateResponse>('/users', {
    userId,
  });
};

export const registerUserDevice = async ({
  userId,
  deviceId,
}: {
  userId: string;
  deviceId: string;
}) => {
  return postJson<DeviceRegistrationResponse>(
    `/users/${encodeURIComponent(userId)}/devices`,
    {
      deviceId,
    }
  );
};

export const ensureUserDeviceRegistration = async ({
  userId,
  deviceId,
}: {
  userId: string;
  deviceId: string;
}) => {
  const user = await createUser({ userId });
  const device = await registerUserDevice({
    userId: user.userId,
    deviceId,
  });
  return {
    user,
    device,
  };
};

export const listUserDevices = async ({
  authToken,
  userId,
}: {
  authToken: string;
  userId: string;
}) => {
  const response = await fetch(
    `${API_BASE_URL}/users/${encodeURIComponent(userId)}/devices`,
    {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error(await buildErrorMessage(response));
  }

  return response.json() as Promise<UserDeviceListResponse>;
};

export const approveUserDevice = async ({
  authToken,
  userId,
  deviceId,
}: {
  authToken: string;
  userId: string;
  deviceId: string;
}) => {
  return postJson<UserDevice>(
    `/users/${encodeURIComponent(userId)}/devices/${encodeURIComponent(deviceId)}/approve`,
    {},
    { authToken }
  );
};

export const revokeUserDevice = async ({
  authToken,
  userId,
  deviceId,
}: {
  authToken: string;
  userId: string;
  deviceId: string;
}) => {
  return postJson<UserDevice>(
    `/users/${encodeURIComponent(userId)}/devices/${encodeURIComponent(deviceId)}/revoke`,
    {},
    { authToken }
  );
};

export const startGoogleOauth = async ({
  redirectUri,
}: {
  redirectUri: string;
}) => {
  return postJson<GoogleOauthStartResponse>('/auth/oauth/google/start', {
    redirectUri,
  });
};

export const exchangeGoogleOauth = async ({
  handoffCode,
  deviceId,
}: {
  handoffCode: string;
  deviceId?: string;
}) => {
  return postJson<AuthTokenResponse>('/auth/oauth/google/exchange', {
    handoffCode,
    deviceId,
  });
};

export const logoutAuthSession = async ({
  authToken,
  refreshToken,
}: {
  authToken?: string | null;
  refreshToken?: string | null;
}) => {
  return postJson<AuthLogoutResponse>(
    '/auth/logout',
    {
      refreshToken: refreshToken || undefined,
    },
    { authToken: authToken || undefined }
  );
};

export const chatWithMemories = async ({
  authToken,
  userId,
  query,
  topK = 3,
}: {
  authToken: string;
  userId: string;
  query: string;
  topK?: number;
}) => {
  return postJson<MemoryChatResponse>(
    '/chat',
    {
      userId,
      query,
      topK,
    },
    { authToken }
  );
};

export const issueMediaAccessUrls = async ({
  authToken,
  userId,
  imageKeys,
  expiresInSec = 300,
}: {
  authToken: string;
  userId: string;
  imageKeys: string[];
  expiresInSec?: number;
}) => {
  return postJson<MediaBatchAccessUrlResponse>(
    '/media/access-urls',
    {
      userId,
      imageKeys,
      expiresInSec,
    },
    { authToken }
  );
};

export const requestMediaUploadAuthorization = async ({
  deviceId,
  captureId,
  requestId,
  memoryId,
  taskType = 'metadata',
  capturedAt,
  fileName,
  imageKey,
  contentType,
}: {
  deviceId: string;
  captureId?: string;
  requestId?: string;
  memoryId?: string;
  taskType?: 'caption' | 'metadata';
  capturedAt?: string;
  fileName?: string;
  imageKey?: string;
  contentType?: string;
}) => {
  return postJson<UploadAuthorizationResponse>('/media/upload-authorizations', {
    deviceId,
    captureId,
    requestId,
    memoryId,
    taskType,
    capturedAt,
    fileName,
    imageKey,
    contentType,
  });
};

export const buildCaptureRegistrationPayload = ({
  userId,
  deviceId,
  uploadPlan,
}: {
  userId: string;
  deviceId: string;
  uploadPlan: UploadAuthorizationPlan;
}): CaptureRegistrationPayload => {
  return {
    captureId: uploadPlan.captureId,
    requestId: uploadPlan.requestId,
    memoryId: uploadPlan.memoryId,
    userId,
    deviceId,
    taskType: uploadPlan.taskType,
    capturedAt: uploadPlan.capturedAt,
    sourceImage: uploadPlan.sourceImage,
  };
};

export const registerMediaCapture = async (
  payload: CaptureRegistrationPayload
) => {
  return postJson<CaptureAcceptedResponse>('/media/captures', payload);
};

export const getCaptureTaskStatus = async (taskId: string) => {
  const response = await fetch(
    `${API_BASE_URL}/media/captures/tasks/${encodeURIComponent(taskId)}`
  );

  if (!response.ok) {
    throw new Error(await buildErrorMessage(response));
  }

  return response.json() as Promise<CaptureTaskStatusResponse>;
};

export const uploadAuthorizedCaptureSource = async ({
  uploadPlan,
  body,
  contentType,
}: {
  uploadPlan: UploadAuthorizationPlan;
  body: Blob;
  contentType?: string;
}) => {
  const resolvedContentType = (
    contentType ||
    uploadPlan.sourceImage.contentType ||
    ''
  ).trim();
  const headers: Record<string, string> = {};
  if (resolvedContentType) {
    headers['Content-Type'] = resolvedContentType;
  }

  const response = await fetch(uploadPlan.uploadUrl, {
    method: 'PUT',
    headers,
    body,
  });

  if (!response.ok) {
    const rawText = await response.text();
    throw new Error(rawText || `Upload failed with ${response.status}`);
  }

  return {
    imageKey: uploadPlan.sourceImage.imageKey,
  };
};
