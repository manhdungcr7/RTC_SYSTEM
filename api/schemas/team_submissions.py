"""Schema cho bang chia se bai nop giua thanh vien trong nhom."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SharedAnswerInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    csv_text: str = Field(min_length=1, max_length=1_048_576)
    note: str = Field(default="", max_length=2_000)


class ReviewUpdate(BaseModel):
    actor_member_id: str = Field(min_length=4, max_length=64)
    actor_display_name: str = Field(min_length=1, max_length=60)
    note: str | None = Field(default=None, max_length=2_000)
    check_status: Literal["unchecked", "checked", "needs_rework"] | None = None


class ChoiceInput(BaseModel):
    member_id: str = Field(min_length=4, max_length=64)
    actor_member_id: str = Field(min_length=4, max_length=64)
    actor_display_name: str = Field(min_length=1, max_length=60)
