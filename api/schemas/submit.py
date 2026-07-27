from typing import Literal

from pydantic import BaseModel


class SubmitBuildRequest(BaseModel):
    kind: Literal["kis", "qa", "trake"]
    rows: list[list]           # đã đúng dạng [[video,frame_idx], ...] hoặc kèm answer/nhiều frame
    n_events: int | None = None


class SubmitBuildResponse(BaseModel):
    csv_text: str
    errors: list[str]


class SubmitPackRequest(BaseModel):
    files: dict[str, str]      # {"query-p1-1-kis.csv": "<csv text>", ...}
