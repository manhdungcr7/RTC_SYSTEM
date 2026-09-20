"""Hợp đồng nhập kế hoạch truy vấn do một GPT mạnh tạo bên ngoài RTC.

RTC không tự coi nội dung này là chân lý: endpoint validate chuẩn hoá dữ liệu, giới
hạn kích thước và sửa cặp neo trước khi frontend đưa kế hoạch vào Search/Temporal.
Không có API key, URL GPT hay nội dung hội thoại nào được lưu ở đây.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class QueryPlanContext(BaseModel):
    vi: str = ""
    en: str = ""

    @model_validator(mode="after")
    def clean_text(self):
        self.vi = self.vi.strip()
        self.en = self.en.strip()
        return self


class QueryPlanEvent(BaseModel):
    vi: str = ""
    en: str = ""
    anchor: bool = False
    visual_keywords: list[str] = Field(default_factory=list)
    ocr: str = ""
    asr: str = ""

    @field_validator("visual_keywords", mode="before")
    @classmethod
    def keywords_from_text(cls, value):
        if isinstance(value, str):
            return [x.strip() for x in value.split(",") if x.strip()]
        return value or []

    @model_validator(mode="after")
    def clean_and_require_text(self):
        self.vi = self.vi.strip()
        self.en = self.en.strip()
        self.ocr = self.ocr.strip()
        self.asr = self.asr.strip()
        self.visual_keywords = list(dict.fromkeys(
            str(x).strip() for x in self.visual_keywords if str(x).strip()
        ))[:12]
        if not self.vi and not self.en:
            raise ValueError("mỗi sự kiện phải có bản tiếng Việt hoặc tiếng Anh")
        return self


class VisualQueryPlan(BaseModel):
    """Kế hoạch trung lập với nhãn đề: chỉ tối ưu việc tìm đúng video/frame."""

    original_query: str = ""
    context: QueryPlanContext = Field(default_factory=QueryPlanContext)
    events: list[QueryPlanEvent] = Field(min_length=1, max_length=8)
    search_clauses: list[str] = Field(default_factory=list)
    search_clauses_en: list[str] = Field(default_factory=list)
    distinctive_features: list[str] = Field(default_factory=list)
    possible_confusions: list[str] = Field(default_factory=list)
    ocr_queries: list[str] = Field(default_factory=list)
    asr_queries: list[str] = Field(default_factory=list)
    recommended_mode: Literal["search", "temporal"] | None = None
    max_gap_s: float | None = Field(default=120, ge=0, le=3600)

    @field_validator("context", mode="before")
    @classmethod
    def context_from_string(cls, value):
        if isinstance(value, str):
            return {"vi": value, "en": ""}
        return value

    @field_validator("events", mode="before")
    @classmethod
    def events_from_strings(cls, value):
        if isinstance(value, list):
            return [{"vi": x} if isinstance(x, str) else x for x in value]
        return value

    @field_validator(
        "search_clauses", "search_clauses_en", "distinctive_features",
        "possible_confusions", "ocr_queries", "asr_queries", mode="before",
    )
    @classmethod
    def list_from_text(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class QueryPlanImportRequest(BaseModel):
    plan: dict[str, Any]


class QueryPlanValidationResponse(BaseModel):
    plan: VisualQueryPlan
    warnings: list[str] = Field(default_factory=list)
