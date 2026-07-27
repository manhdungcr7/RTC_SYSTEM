"""Dependency provider — đọc singleton đã nạp lúc startup từ app.state, tránh
khởi tạo lại (model/client) mỗi request."""
from __future__ import annotations

from fastapi import Request

from core.media_index import MediaIndex
from core.query_encoders import QueryEncoders
from core.repositories.es_repo import EsRepo
from core.repositories.milvus_repo import MilvusRepo


def get_milvus(request: Request) -> MilvusRepo:
    return request.app.state.milvus_repo


def get_es(request: Request) -> EsRepo:
    return request.app.state.es_repo


def get_encoders(request: Request) -> QueryEncoders:
    return request.app.state.encoders


def get_media_index(request: Request) -> MediaIndex:
    return request.app.state.media_index
