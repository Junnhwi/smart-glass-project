import type { InferenceItem } from "../../entities/inference/types";

export const mockResults: InferenceItem[] = [
  {
    imageId: "img_001",
    userId: "user_01",
    status: "completed",
    capturedAt: "2026-04-30 14:20",
    processedAt: "2026-04-30 14:21",
    result: {
      objects: ["이어폰", "노트북"],
      location: "책상 위",
      confidence: 0.87,
    },
  },
  {
    imageId: "img_002",
    userId: "user_02",
    status: "pending",
    capturedAt: "2026-04-30 14:18",
  },
  {
    imageId: "img_003",
    userId: "user_01",
    status: "failed",
    capturedAt: "2026-04-30 14:12",
  },
];