"""Nộp một đáp án cho câu DRES hiện tại theo HD-ChungKet-2026.pdf."""
from __future__ import annotations

import hashlib
import json
from threading import Lock
from urllib.parse import quote, urlsplit

import requests
from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas.dres import (DresAnswerRequest, DresConnectRequest,
                              DresCurrentTaskRequest, DresLoginRequest, DresSubmitRequest)
from config import settings
from core.dres import InvalidAnswer, build_answer
from core.media_index import MediaIndex

router = APIRouter(prefix="/dres", tags=["dres"])


class SharedDresSession:
    """Một token cho backend duy nhất; không serialize ra client, đĩa hay backup."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._token: str | None = None
        self._version = 0

    def status(self) -> dict:
        with self._lock:
            return {"connected": self._token is not None, "version": self._version}

    def get(self, expected_version: int | None = None) -> tuple[str, int]:
        with self._lock:
            if not self._token:
                raise HTTPException(409, "Chưa có kết nối DRES chung. Một thành viên cần đăng nhập.")
            if expected_version is not None and expected_version != self._version:
                raise HTTPException(409, "Kết nối DRES đã thay đổi. Tải lại câu hiện tại trước khi nộp.")
            return self._token, self._version

    def set(self, token: str) -> dict:
        with self._lock:
            self._token = token
            self._version += 1
            return {"connected": True, "version": self._version}

    def clear(self, only_token: str | None = None) -> dict:
        with self._lock:
            if only_token is None or self._token == only_token:
                self._token = None
                self._version += 1
            return {"connected": self._token is not None, "version": self._version}


shared_session = SharedDresSession()
_submission_lock = Lock()
_submitted_keys: set[str] = set()


def get_media_index(request: Request) -> MediaIndex:
    return request.app.state.media_index


def _base_url() -> str:
    base = settings.DRES_BASE_URL
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise HTTPException(503, "AIC_DRES_BASE_URL phải là URL HTTPS gốc của DRES.")
    return base


def _call(method: str, path: str, *, session_id: str | None = None,
          body: dict | None = None, expect_json: bool = True) -> object:
    try:
        response = requests.request(
            method, f"{_base_url()}{path}",
            params={"session": session_id} if session_id else None,
            json=body, timeout=(3, 8), allow_redirects=False,
        )
    except requests.RequestException:
        # Exception text của requests có thể chứa ?session=... nên không trả/log.
        raise HTTPException(502, "Không kết nối được DRES.") from None
    if response.status_code == 401:
        if session_id:
            shared_session.clear(only_token=session_id)
        raise HTTPException(401, "DRES từ chối session hoặc thông tin đăng nhập.")
    if not 200 <= response.status_code < 300:
        raise HTTPException(502, f"DRES trả HTTP {response.status_code}; kiểm tra kỳ thi và câu hiện tại.")
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        if expect_json:
            raise HTTPException(502, "DRES trả dữ liệu không phải JSON.") from None
        return None


@router.get("/config")
def config() -> dict:
    return {"base_url": _base_url()}


@router.post("/login")
def login(req: DresLoginRequest) -> dict:
    data = _call("POST", "/api/v2/login", body={
        "username": req.username, "password": req.password,
    })
    if not isinstance(data, dict) or not isinstance(data.get("sessionId"), str) or not data["sessionId"]:
        raise HTTPException(502, "DRES không trả sessionId.")
    token = data["sessionId"]
    _list_evaluations(token)  # Chỉ chia sẻ session đã xác thực được API client.
    with _submission_lock:
        _submitted_keys.clear()
        return shared_session.set(token)


@router.post("/connect")
def connect(req: DresConnectRequest) -> dict:
    _list_evaluations(req.session_id)
    with _submission_lock:
        _submitted_keys.clear()
        return shared_session.set(req.session_id)


@router.get("/session")
def session_status() -> dict:
    return shared_session.status()


@router.post("/disconnect")
def disconnect() -> dict:
    with _submission_lock:
        _submitted_keys.clear()
        return shared_session.clear()


def _list_evaluations(token: str) -> list[dict]:
    data = _call("GET", "/api/v2/client/evaluation/list", session_id=token)
    if not isinstance(data, list):
        raise HTTPException(502, "DRES trả danh sách kỳ thi không hợp lệ.")
    return [
        {"id": str(item["id"]), "name": str(item.get("name", "")),
         "status": str(item.get("status", "")), "type": str(item.get("type", ""))}
        for item in data if isinstance(item, dict) and item.get("id") is not None
    ]


@router.get("/evaluations")
def evaluations() -> list[dict]:
    token, _ = shared_session.get()
    return _list_evaluations(token)


@router.post("/current-task")
def current_task(req: DresCurrentTaskRequest) -> dict:
    token, _ = shared_session.get()
    return _current_task(token, req.evaluation_id)


def _current_task(token: str, evaluation_id: str) -> dict:
    data = _call("GET", f"/api/v2/client/evaluation/currentTask/{quote(evaluation_id, safe='')}",
                 session_id=token)
    if not isinstance(data, dict):
        raise HTTPException(502, "DRES trả thông tin câu hiện tại không hợp lệ.")
    return {"name": str(data.get("name", "")), "task_type": str(data.get("taskType", ""))}


def _answer(req: DresAnswerRequest, media_index: MediaIndex) -> dict:
    try:
        return build_answer(req.kind, req.row, req.n_events, media_index)
    except InvalidAnswer as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/preview")
def preview(req: DresAnswerRequest,
            media_index: MediaIndex = Depends(get_media_index)) -> dict:
    return _answer(req, media_index)


@router.post("/submit")
def submit_one(req: DresSubmitRequest,
               media_index: MediaIndex = Depends(get_media_index)) -> dict:
    payload = _answer(req, media_index)
    with _submission_lock:
        token, version = shared_session.get(req.session_version)
        task = _current_task(token, req.evaluation_id)
        if not task["name"]:
            raise HTTPException(409, "DRES chưa có câu hiện tại để nộp.")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        key = f"{version}:{req.evaluation_id}:{task['name']}:{fingerprint}"
        if key in _submitted_keys:
            raise HTTPException(409, "Đáp án này đã được gửi cho câu DRES hiện tại.")
        data = _call("POST", f"/api/v2/submit/{quote(req.evaluation_id, safe='')}",
                     session_id=token, body=payload, expect_json=False)
        if isinstance(data, dict) and (data.get("status") is False or data.get("success") is False):
            raise HTTPException(502, "DRES từ chối đáp án; kiểm tra câu hiện tại và kết quả đã nộp.")
        _submitted_keys.add(key)
    verdict = data.get("submission") if isinstance(data, dict) else None
    labels = {"CORRECT": "Đúng", "WRONG": "Sai", "INDETERMINATE": "Chưa có kết luận",
              "UNDECIDABLE": "Chưa thể chấm", "PARTIALLY_CORRECT": "Đúng một phần"}
    label = labels.get(verdict)
    message = f"DRES đã nhận đáp án. Kết quả: {label}." if label else "DRES đã nhận đáp án; xem kết quả chấm trên DRES."
    return {"submitted": True, "verdict": verdict if label else None, "message": message}
