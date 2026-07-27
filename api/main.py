"""FastAPI app. Startup: nạp 1 lần (KHÔNG per-request) query_encoders (4 model,
vài trăm MB - vài GB), media_index (glob toàn bộ đĩa 1 lần), Milvus/ES client —
gắn vào app.state cho api/deps.py đọc lại."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from core import config as C
from core.media_index import MediaIndex
from core.query_encoders import QueryEncoders
from core.repositories.es_repo import EsRepo
from core.repositories.milvus_repo import MilvusRepo


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[main] khởi tạo Milvus/ES repo...")
    app.state.milvus_repo = MilvusRepo()
    app.state.es_repo = EsRepo()

    # Đồng bộ trạng thái load/release Milvus theo ENABLED_BRANCHES hiện tại — Milvus
    # GIỮ trạng thái load/release qua các lần restart server (state phía server, không
    # phải phía client Python) nên PHẢI tự đồng bộ cả 2 chiều, không chỉ release nhánh
    # tắt: nhánh nào đó từng bị release ở lần chạy trước (RAM hạn chế) mà giờ BẬT lại
    # (vd đang dùng remote encoder qua Kaggle) vẫn ở trạng thái "not loaded" nếu không
    # load_collection() lại — ĐÃ GẶP THẬT: pecore lỗi "collection not loaded" dù
    # ENABLED_BRANCHES đã bật, vì lần chạy trước release rồi chưa ai load lại.
    for branch, enabled in C.ENABLED_BRANCHES.items():
        if branch == "metaclip2":
            continue   # nhánh bắt buộc, không bao giờ release
        coll = settings.COLLECTIONS.get(branch)
        if not coll or not app.state.milvus_repo.client.has_collection(coll):
            continue
        if enabled:
            app.state.milvus_repo.client.load_collection(coll)
            print(f"[main] load_collection('{coll}') — nhánh '{branch}' đang bật")
        else:
            app.state.milvus_repo.client.release_collection(coll)
            print(f"[main] release_collection('{coll}') — nhánh '{branch}' đang tắt")

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
