export type VlmTaskStatus = "queued" | "processing" | "success" | "error";

export type VlmModelTask = "caption" | "metadata";

export interface VlmGenerationConfig {
  modelKey?: string;
  quantization?: "none" | "8bit" | "4bit";
  dtype?: "float16" | "bfloat16" | "float32";
  prompt?: string | null;
  maxNewTokens?: number;
  numBeams?: number;
}

export interface VlmSourceImageRef {
  imageKey?: string | null;
  imageUrl?: string | null;
  contentType?: string | null;
}

export interface VlmInferenceRequest {
  requestId: string;
  taskType: VlmModelTask;
  memoryId?: string | null;
  userId: string;
  capturedAt?: string | null;
  sourceImage: VlmSourceImageRef;
  generation?: VlmGenerationConfig;
}

export interface VlmLocationPayload {
  name?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface VlmMetadataPayload {
  caption?: string | null;
  sceneSummary?: string | null;
  detectedObjects: string[];
  tags: string[];
  ocrText?: string | null;
  positionHint?: string | null;
  location?: VlmLocationPayload | null;
}

export interface VlmRuntimeMetrics {
  latencySec?: number | null;
  peakMemoryMb?: number | null;
  loadTimeSec?: number | null;
}

export interface VlmProviderMetadata {
  modelKey?: string | null;
  modelId?: string | null;
  modelFamily?: string | null;
  quantization?: string | null;
  dtype?: string | null;
  provider?: string | null;
  raw?: Record<string, unknown> | null;
}

export interface VlmInferenceSuccess {
  status: "success";
  requestId: string;
  taskType: VlmModelTask;
  memoryId?: string | null;
  userId: string;
  sourceImage: VlmSourceImageRef;
  metadata: VlmMetadataPayload;
  providerMetadata: VlmProviderMetadata;
  runtime: VlmRuntimeMetrics;
}

export interface VlmInferenceError {
  status: "error";
  requestId: string;
  taskType: VlmModelTask;
  memoryId?: string | null;
  userId: string;
  sourceImage: VlmSourceImageRef;
  errorCode: string;
  message: string;
  retryable?: boolean;
  providerMetadata?: VlmProviderMetadata;
}

export type VlmInferenceResult = VlmInferenceSuccess | VlmInferenceError;
