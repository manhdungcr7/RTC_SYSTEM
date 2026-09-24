"""Các request tạm thời cho DRES; sessionId không được lưu vào database."""
from typing import Literal

from pydantic import BaseModel, Field


class DresLoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class DresConnectRequest(BaseModel):
    session_id: str = Field(min_length=1)


class DresCurrentTaskRequest(BaseModel):
    evaluation_id: str = Field(min_length=1)


class DresAnswerRequest(BaseModel):
    kind: Literal["kis", "qa", "trake"]
    row: list[str | int]
    n_events: int | None = Field(default=None, ge=1)


class DresSubmitRequest(DresAnswerRequest):
    evaluation_id: str = Field(min_length=1)
    session_version: int = Field(ge=1)
