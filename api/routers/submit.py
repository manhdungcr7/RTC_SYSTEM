"""POST /submit/* — build CSV theo chuẩn Codabench + validate, đóng gói zip.
Port logic từ `core/submit.py` (chính là `system/aic/submit.py` port nguyên)."""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter
from fastapi.responses import FileResponse

from config import settings
from core import submit as S
from api.schemas.submit import SubmitBuildRequest, SubmitBuildResponse, SubmitPackRequest

router = APIRouter(prefix="/submit")

SUBMISSIONS_DIR = settings.ARTIFACTS_ROOT / "submissions"


@router.post("/build", response_model=SubmitBuildResponse)
def build(req: SubmitBuildRequest) -> SubmitBuildResponse:
    errors = S.validate(req.rows, req.kind, req.n_events)
    return SubmitBuildResponse(csv_text=S.to_csv_text(req.rows), errors=errors)


@router.post("/pack")
def pack(req: SubmitPackRequest):
    session_dir = SUBMISSIONS_DIR / f"session_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    for filename, csv_text in req.files.items():
        (session_dir).mkdir(parents=True, exist_ok=True)
        (session_dir / filename).write_text(csv_text, encoding="utf-8", newline="\n")

    zip_path = session_dir.with_suffix(".zip")
    S.pack(session_dir, zip_path)
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)
