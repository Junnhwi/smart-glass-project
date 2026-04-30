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

type MediaBatchAccessUrlResponse = {
  totalItems: number;
  items: MediaAccessUrl[];
};

const postJson = async <TResponse>(
  path: string,
  payload: Record<string, unknown>
): Promise<TResponse> => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Request failed with ${response.status}`);
  }

  return response.json();
};

export const chatWithMemories = async ({
  userId,
  query,
  topK = 3,
}: {
  userId: string;
  query: string;
  topK?: number;
}) => {
  return postJson<MemoryChatResponse>('/chat', {
    userId,
    query,
    topK,
  });
};

export const issueMediaAccessUrls = async ({
  userId,
  imageKeys,
  expiresInSec = 300,
}: {
  userId: string;
  imageKeys: string[];
  expiresInSec?: number;
}) => {
  return postJson<MediaBatchAccessUrlResponse>('/media/access-urls', {
    userId,
    imageKeys,
    expiresInSec,
  });
};
