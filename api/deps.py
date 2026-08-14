"""Dependency provider — đọc singleton đã nạp lúc startup từ app.state, tránh
khởi tạo lại (model/client) mỗi request."""
from __future__ import annotations

from fastapi import Request

from core.media_index import MediaIndex
from core.query_cache import BranchResultCache, QueryVectorCache
from core.query_encoders import QueryEncoders
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo


def get_faiss(request: Request) -> FaissRepo:
    """Tên hàm giữ nguyên "get_faiss" dù bên dưới giờ là FaissRepo — tránh phải
    sửa import ở mọi router, chỉ đổi type thật đằng sau."""
    return request.app.state.faiss_repo


def get_meili(request: Request) -> MeiliRepo:
    """Tương tự get_faiss — bên dưới giờ là MeiliRepo."""
    return request.app.state.meili_repo


def get_encoders(request: Request) -> QueryEncoders:
    return request.app.state.encoders


def get_media_index(request: Request) -> MediaIndex:
    return request.app.state.media_index


def get_vec_cache(request: Request) -> QueryVectorCache:
    """Cache vector truy vấn (lưu đĩa) — xem core/query_cache.py."""
    return request.app.state.vec_cache


def get_branch_cache(request: Request) -> BranchResultCache:
    """Cache kết quả từng nhánh (RAM) — cho phép đổi trọng số mà không chạy lại."""
    return request.app.state.branch_cache
