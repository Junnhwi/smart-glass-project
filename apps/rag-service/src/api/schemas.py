from pydantic import BaseModel, ConfigDict, Field, validator


class MemoryLocationPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class MemoryRecordPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

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

    @validator("memory_id", "user_id")
    def validate_non_blank_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class IndexMemoriesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    memories: list[MemoryRecordPayload] = Field(default_factory=list)


class IndexMemoriesResponse(BaseModel):
    indexed_count: int
    total_user_memories: dict[str, int]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    user_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)

    @validator("user_id", "query")
    def validate_non_blank_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


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
