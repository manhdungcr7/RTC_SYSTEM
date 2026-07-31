"""FastAPI app. Startup: nạp 1 lần (KHÔNG per-request) query_encoders (4 model,
vài trăm MB - vài GB), media_index (glob toàn bộ đĩa 1 lần), FAISS/Meilisearch
client — gắn vào app.state cho api/deps.py đọc lại."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from core import config as C
from core.media_index import MediaIndex
from core.query_encoders import QueryEncoders
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[main] nạp FAISS index + kết nối Meilisearch...")
    # FaissRepo chỉ nạp vào RAM đúng các nhánh đang BẬT (ENABLED_BRANCHES) — thay
    # cho việc gọi load_collection()/release_collection() với Milvus trước đây
    # (Milvus tự giữ trạng thái phía server qua các lần restart, dễ lệch với config
    # Python — FAISS không có vấn đề này vì tự nạp lại đúng theo config mỗi lần start).
    app.state.milvus_repo = FaissRepo(settings.FAISS_DIR, enabled_branches=C.ENABLED_BRANCHES)
    app.state.es_repo = MeiliRepo()

    print("[main] build media_index (glob đĩa)...")
    app.state.media_index = MediaIndex().build()

    print("[main] nạp query_encoders (metaclip2/pecore/beit3-bridge/capemb)...")
    app.state.encoders = QueryEncoders().load_all()

    print("[main] sẵn sàng.")
    yield

    app.state.encoders.shutdown()


app = FastAPI(title="AIC Retrieval API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routers import media, search, similar, submit, temporal  # noqa: E402

app.include_router(search.router)
app.include_router(temporal.router)
app.include_router(similar.router)
app.include_router(media.router)
app.include_router(submit.router)


@app.get("/health")
def health():
    return {"status": "ok"}
