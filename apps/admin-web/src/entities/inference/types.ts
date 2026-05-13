export type InferenceStatus = "completed" | "pending" | "failed";

export type InferenceItem = {
  imageId: string;
  userId: string;
  status: InferenceStatus;
  capturedAt: string;
  processedAt?: string;
  result?: {
    objects: string[];
    location: string;
    confidence: number;
  };
};