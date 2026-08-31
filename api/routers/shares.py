"""Bang chia se frame noi bo: JSON nhe, phu hop mot nhom thi dau dung chung backend."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import settings

router = APIRouter(prefix="/shares", tags=["shares"])
STORE = settings.ARTIFACTS_ROOT / "shared_frames.json"
_lock = threading.Lock()


class ShareInput(BaseModel):
    author: str = Field(min_length=1, max_length=40)
    question: int = Field(ge=1, le=999)
    kind: Literal["kis", "trake", "qa"]
    note: str = Field(default="", max_length=1000)
    video: str
    n: int = Field(ge=0)
    frame_idx: int = Field(ge=0)
    pts_time: float | None = None


class ShareUpdate(BaseModel):
    author: str | None = Field(default=None, min_length=1, max_length=40)
    question: int | None = Field(default=None, ge=1, le=999)
    kind: Literal["kis", "trake", "qa"] | None = None
    note: str | None = Field(default=None, max_length=1000)


def _read() -> list[dict]:
    if not STORE.exists():
        return []
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _write(items: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(STORE) + ".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE)


@router.get("")
def list_shares():
    with _lock:
        return sorted(_read(), key=lambda x: x["created_at"], reverse=True)


@router.post("", status_code=201)
def create_share(data: ShareInput):
    item = {"id": uuid.uuid4().hex, **data.model_dump(),
            "created_at": datetime.now(timezone.utc).isoformat()}
    with _lock:
        items = _read()
        items.append(item)
        _write(items)
    return item


@router.put("/{share_id}")
def update_share(share_id: str, data: ShareUpdate):
    with _lock:
        items = _read()
        item = next((x for x in items if x["id"] == share_id), None)
        if item is None:
            raise HTTPException(404, "Muc chia se khong ton tai")
        item.update(data.model_dump(exclude_none=True))
        _write(items)
        return item


@router.delete("/{share_id}", status_code=204)
def delete_share(share_id: str):
    with _lock:
        items = _read()
        kept = [x for x in items if x["id"] != share_id]
        if len(kept) == len(items):
            raise HTTPException(404, "Muc chia se khong ton tai")
        _write(kept)
