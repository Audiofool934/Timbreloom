from pydantic import BaseModel, Field


class HistoryRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160, pattern=r"\S")


class TranscriptSegmentPatch(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=10_000)


class TranscriptPatch(BaseModel):
    segments: list[TranscriptSegmentPatch] = Field(min_length=1, max_length=2_000)


class GeminiTransformRequest(BaseModel):
    segment_id: str = Field(min_length=1, max_length=64)
    task: str = Field(min_length=1, max_length=32)
    target_language: str = Field(default="", max_length=80)
    confirm_cloud: bool = False


class DubProjectCreateRequest(BaseModel):
    transcript_id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=160)
    target_language: str = Field(default="auto", max_length=32)
    default_voice_id: str | None = Field(default=None, max_length=64)


class DubSegmentPatch(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    active_text: str | None = Field(default=None, max_length=200_000)
    voice_id: str | None = Field(default=None, max_length=64)
    role_id: str | None = Field(default=None, max_length=64)
    gain: float | None = Field(default=None, ge=0.0, le=2.0)
    start: float | None = Field(default=None, ge=0.0)
    end: float | None = Field(default=None, ge=0.0)
    fit_mode: str | None = Field(default=None, max_length=16)


class DubProjectPatch(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    target_language: str | None = Field(default=None, max_length=32)
    segments: list[DubSegmentPatch] = Field(default_factory=list, max_length=2_000)


class DubJobCreateRequest(BaseModel):
    mode: str = Field(default="all", max_length=16)
    segment_ids: list[str] = Field(default_factory=list, max_length=2_000)


class DubExportRequest(BaseModel):
    original_audio_gain: float = Field(default=0.0, ge=0.0, le=1.0)


class DubRoleRequest(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    voice_id: str | None = Field(default=None, max_length=64)


class DubSplitRequest(BaseModel):
    split_at: float = Field(ge=0.0)


class DubMergeRequest(BaseModel):
    segment_ids: list[str] = Field(min_length=2, max_length=2_000)


class GeminiBatchRequest(BaseModel):
    segment_ids: list[str] = Field(min_length=1, max_length=50)
    task: str = Field(min_length=1, max_length=32)
    target_language: str = Field(default="", max_length=80)
    confirm_cloud: bool = False
