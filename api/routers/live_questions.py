"""Shared live question timeline, independent of question.zip and local drafts."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import settings
from core.repositories.live_question_repo import (
    LiveQuestionError, LiveQuestionNotFound, LiveQuestionRepo,
)

router = APIRouter(prefix="/live-questions", tags=["live-questions"])
_repo = LiveQuestionRepo(settings.ARTIFACTS_ROOT / "live_questions.sqlite3")


class QuestionInput(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["kis", "qa", "trake"]
    qa_question: str = Field(default="", max_length=10000)


class QuestionUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    qa_question: str = Field(default="", max_length=10000)


class RevealInput(BaseModel):
    text_vi: str = Field(default="", max_length=30000)
    text_en: str = Field(default="", max_length=30000)


def _error(exc: LiveQuestionError) -> HTTPException:
    return HTTPException(404 if isinstance(exc, LiveQuestionNotFound) else 400, str(exc))


@router.get("")
def list_live_questions():
    return _repo.list_questions()


@router.get("/backup")
def backup_live_questions():
    return _repo.backup()


@router.post("/restore")
def restore_live_questions(snapshot: dict, replace_existing: bool = False):
    try:
        return _repo.restore(snapshot, replace_existing=replace_existing)
    except LiveQuestionError as exc:
        raise _error(exc) from exc


@router.post("", status_code=201)
def create_live_question(data: QuestionInput):
    try:
        return _repo.create_question(**data.model_dump())
    except LiveQuestionError as exc:
        raise _error(exc) from exc


@router.put("/{question_id}")
def update_live_question(question_id: str, data: QuestionUpdate):
    try:
        return _repo.update_question(question_id, **data.model_dump())
    except LiveQuestionError as exc:
        raise _error(exc) from exc


@router.delete("/{question_id}", status_code=204)
def delete_live_question(question_id: str):
    try:
        _repo.delete_question(question_id)
    except LiveQuestionError as exc:
        raise _error(exc) from exc


@router.post("/{question_id}/reveals", status_code=201)
def add_reveal(question_id: str, data: RevealInput):
    try:
        return _repo.add_reveal(question_id, **data.model_dump())
    except LiveQuestionError as exc:
        raise _error(exc) from exc


@router.put("/{question_id}/reveals/{reveal_id}")
def update_reveal(question_id: str, reveal_id: int, data: RevealInput):
    try:
        return _repo.update_reveal(question_id, reveal_id, **data.model_dump())
    except LiveQuestionError as exc:
        raise _error(exc) from exc
