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
