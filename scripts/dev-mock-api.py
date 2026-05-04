from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


app = FastAPI(title="smart-glass-dev-mock-api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "smart-glass-dev-mock-api"}


@app.post("/chat")
async def chat(payload: dict) -> dict:
    query = payload.get("query") or ""
    return {
        "answer": (
            f"테스트 응답입니다. '{query}'에 대해 가장 최근 기록은 "
            "책상 위 근처로 표시됩니다."
        ),
        "answerMode": "mock",
        "query": query,
        "totalHits": 1,
        "hits": [
            {
                "memoryId": "mock-memory-earbuds-01",
                "score": 0.9,
                "lexicalScore": 0.9,
                "matchedTerms": ["earbuds", "이어폰"],
                "imageKey": "captures/user-1/mock-earbuds.jpg",
                "imageUrl": "https://picsum.photos/seed/smart-glass-earbuds/480/360",
                "capturedAt": "2026-04-30T09:00:00Z",
                "caption": "이어폰이 책상 위에 놓여 있습니다.",
                "sceneSummary": "책상 위 물건 장면",
                "positionHint": "책상 위",
                "location": {
                    "name": "작업 공간",
                    "address": None,
                    "latitude": None,
                    "longitude": None,
                },
                "detectedObjects": ["이어폰", "책상"],
                "tags": ["이어폰", "책상", "작업 공간"],
            }
        ],
        "citedMemoryIds": ["mock-memory-earbuds-01"],
        "confidence": 0.9,
        "reason": "프론트 연결 확인용 mock 응답입니다.",
    }


@app.post("/media/access-urls")
async def access_urls(payload: dict) -> dict:
    image_keys = payload.get("imageKeys") or []
    return {
        "totalItems": len(image_keys),
        "items": [
            {
                "imageKey": image_key,
                "accessUrl": "https://picsum.photos/seed/smart-glass-earbuds/480/360",
                "expiresAt": "2026-04-30T10:00:00Z",
                "expiresInSec": 300,
            }
            for image_key in image_keys
        ],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)
