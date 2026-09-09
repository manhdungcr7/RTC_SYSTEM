"""API cho bang chia se bai nop cua nhom.

Ban nhap cua tung browser van local. Router nay chi luu noi dung duoc nguoi dung
chu dong chia se va du lieu cau hoi da import tu question.zip.
"""
from __future__ import annotations

import io
import json
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from api.schemas.team_submissions import ChoiceInput, ReviewUpdate, SharedAnswerInput
from config import settings
from core.repositories.team_submission_repo import (
    MAX_BACKUP_ZIP_BYTES,
    MAX_QUESTION_ZIP_BYTES,
    BatchConflictError,
    TeamSubmissionError,
    TeamSubmissionNotFoundError,
    TeamSubmissionRepo,
)


router = APIRouter(prefix="/team-submissions", tags=["team-submissions"])
_repo = TeamSubmissionRepo(settings.ARTIFACTS_ROOT / "team_submission.sqlite3")


def _http_error(exc: TeamSubmissionError) -> HTTPException:
    if isinstance(exc, BatchConflictError):
        return HTTPException(409, str(exc))
    if isinstance(exc, TeamSubmissionNotFoundError):
        return HTTPException(404, str(exc))
    return HTTPException(400, str(exc))


async def _read_upload(upload: UploadFile, max_bytes: int, label: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(256 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, f"{label} vuot gioi han {max_bytes // (1024 * 1024)} MB.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/batches/import-questions")
async def import_questions(file: UploadFile = File(...), replace_existing: bool = Form(False)):
    raw = await _read_upload(file, MAX_QUESTION_ZIP_BYTES, "question.zip")
    try:
        batch, imported = _repo.import_questions(raw, replace_existing=replace_existing)
        return {"imported": imported, "batch": batch}
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc


@router.get("/batches")
def list_batches():
    return _repo.list_batches()


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: str):
    try:
        return _repo.delete_batch(batch_id)
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str):
    try:
        return _repo.get_batch(batch_id)
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc


@router.put("/batches/{batch_id}/questions/{question_number}/answers/{member_id}")
def share_answer(batch_id: str, question_number: int, member_id: str, data: SharedAnswerInput):
    try:
        return _repo.upsert_answer(
            batch_id=batch_id, question_number=question_number, member_id=member_id,
            display_name=data.display_name, csv_text=data.csv_text, note=data.note,
        )
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc


@router.patch("/batches/{batch_id}/questions/{question_number}/answers/{member_id}")
def update_answer(batch_id: str, question_number: int, member_id: str, data: ReviewUpdate):
    try:
        return _repo.patch_answer(
            batch_id=batch_id, question_number=question_number, member_id=member_id,
            actor_member_id=data.actor_member_id, actor_display_name=data.actor_display_name,
            note=data.note, check_status=data.check_status,
        )
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc


@router.delete("/batches/{batch_id}/questions/{question_number}/answers/{member_id}")
def delete_answer(batch_id: str, question_number: int, member_id: str):
    try:
        return _repo.delete_answer(
            batch_id=batch_id, question_number=question_number, member_id=member_id,
        )
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc


@router.put("/batches/{batch_id}/questions/{question_number}/choice")
def choose_answer(batch_id: str, question_number: int, data: ChoiceInput):
    try:
        return _repo.choose_answer(
            batch_id=batch_id, question_number=question_number, member_id=data.member_id,
            actor_member_id=data.actor_member_id, actor_display_name=data.actor_display_name,
        )
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc


@router.delete("/batches/{batch_id}/questions/{question_number}/choice")
def clear_choice(batch_id: str, question_number: int):
    try:
        return _repo.clear_choice(batch_id=batch_id, question_number=question_number)
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc


@router.get("/batches/{batch_id}/backup")
def download_backup(batch_id: str):
    try:
        snapshot = _repo.backup_batch(batch_id)
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(snapshot, ensure_ascii=False, indent=2))
    out.seek(0)
    return StreamingResponse(
        out, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{batch_id}-team-backup.zip"'},
    )


@router.post("/restore")
async def restore_backup(file: UploadFile = File(...), replace_existing: bool = Form(False)):
    raw = await _read_upload(file, MAX_BACKUP_ZIP_BYTES, "backup ZIP")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
            if names != ["manifest.json"]:
                raise TeamSubmissionError("Backup phai chi chua mot file manifest.json.")
            if archive.getinfo("manifest.json").file_size > 5 * 1024 * 1024:
                raise TeamSubmissionError("manifest.json qua lon.")
            snapshot = json.loads(archive.read("manifest.json").decode("utf-8"))
            if not isinstance(snapshot, dict):
                raise TeamSubmissionError("manifest.json phai la mot doi tuong JSON.")
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, TeamSubmissionError) as exc:
        raise HTTPException(400, "Backup ZIP khong hop le.") from exc
    try:
        return {"batch": _repo.restore_batch(snapshot, replace_existing=replace_existing)}
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc


@router.post("/batches/{batch_id}/export")
def export_submission(batch_id: str):
    try:
        payload = _repo.export_submission_zip(batch_id)
    except TeamSubmissionError as exc:
        raise _http_error(exc) from exc
    return StreamingResponse(
        io.BytesIO(payload), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="submission.zip"'},
    )
