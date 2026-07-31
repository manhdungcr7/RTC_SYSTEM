"""Dependency provider — đọc singleton đã nạp lúc startup từ app.state, tránh
khởi tạo lại (model/client) mỗi request."""
from __future__ import annotations

from fastapi import Request

from core.media_index import MediaIndex
from core.query_encoders import QueryEncoders
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo


def get_milvus(request: Request) -> FaissRepo:
    """Tên hàm giữ nguyên "get_milvus" dù bên dưới giờ là FaissRepo — tránh phải
    sửa import ở mọi router, chỉ đổi type thật đằng sau."""
    return request.app.state.milvus_repo


def get_es(request: Request) -> MeiliRepo:
    """Tương tự get_milvus — bên dưới giờ là MeiliRepo."""
    return request.app.state.es_repo


def get_encoders(request: Request) -> QueryEncoders:
    return request.app.state.encoders


def get_media_index(request: Request) -> MediaIndex:
    return request.app.state.media_index
