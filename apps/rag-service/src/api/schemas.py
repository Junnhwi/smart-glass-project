from pydantic import BaseModel, ConfigDict, Field


class MemoryLocationPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class MemoryRecordPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    image_key: str | None = None
    image_url: str | None = None
    captured_at: str | None = None
    caption: str | None = None
    scene_summary: str | None = None
    detected_objects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    ocr_text: str | None = None
    note: str | None = None
    position_hint: str | None = None
    location: MemoryLocationPayload = Field(default_factory=MemoryLocationPayload)


class IndexMemoriesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memories: list[MemoryRecordPayload] = Field(default_factory=list)


class IndexMemoriesResponse(BaseModel):
    indexed_count: int
    total_user_memories: dict[str, int]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class ChatRequest(SearchRequest):
    conversation_id: str | None = None


class SearchHitPayload(BaseModel):
    memory_id: str
    score: float
    lexical_score: float
    matched_terms: list[str]
    image_key: str | None = None
    image_url: str | None = None
    captured_at: str | None = None
    caption: str | None = None
    scene_summary: str | None = None
    position_hint: str | None = None
    location: MemoryLocationPayload
    detected_objects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    total_hits: int
    hits: list[SearchHitPayload]


class ChatResponse(BaseModel):
    answer: str
    answer_mode: str
    query: str
    total_hits: int
    hits: list[SearchHitPayload]
