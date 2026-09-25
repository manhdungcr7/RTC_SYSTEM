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
from core.query_cache import BranchResultCache, QueryVectorCache
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
    app.state.faiss_repo = FaissRepo(settings.FAISS_DIR, enabled_branches=C.ENABLED_BRANCHES)
    app.state.meili_repo = MeiliRepo()

    print("[main] build media_index (glob đĩa)...")
    app.state.media_index = MediaIndex().build()
    app.state.media_index.warm_remote_maps_async(app.state.faiss_repo.all_videos())

    # LƯU Ý — ĐÃ SỬA LỖI THẬT: TRƯỚC ĐÂY startup tự nạp lại encoder_override.json
    # (bảng Kết nối lần trước) và cho nó THẮNG .env. Hệ quả: mỗi lần Kaggle đổi
    # phiên, người dùng cập nhật đúng .env rồi khởi động lại container, nhưng
    # backend âm thầm dùng key CŨ HƠN từ file override -> 401 Unauthorized mà
    # không ai biết vì sao (mọi nhánh vector chết, OCR/ASR vẫn chạy nên trông như
    # "không ra kết quả" thay vì lỗi rõ ràng). Quy tắc thật của người dùng: sửa
    # .env + khởi động lại LUÔN LÀ NGUỒN CHÂN LÝ. Bảng Kết nối trên UI chỉ dùng để
    # đổi NÓNG giữa phiên (không restart) — không tự nạp lại giá trị cũ ở lần sau.
    from api.routers.config import OVERRIDE_PATH  # noqa: PLC0415
    OVERRIDE_PATH.unlink(missing_ok=True)   # dọn file cũ, tránh gây nhầm lẫn thêm

    print("[main] nạp query_encoders (metaclip2/pecore/beit3-bridge/capemb)...")
    app.state.encoders = QueryEncoders().load_all()

    # 2 tầng cache — điều kiện để kéo fader trọng số phản hồi tức thì (xem
    # core/query_cache.py). Vector cache bền qua restart (lưu đĩa), branch cache
    # chỉ trong RAM theo phiên chạy.
    app.state.vec_cache = QueryVectorCache()
    app.state.branch_cache = BranchResultCache()

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

from api.routers import (config as config_router, dres, live_questions, media, query_plan, search,  # noqa: E402
                          similar, submit, team_submissions, temporal, videos)

app.include_router(search.router)
app.include_router(temporal.router)
app.include_router(query_plan.router)
app.include_router(similar.router)
app.include_router(media.router)
app.include_router(submit.router)
app.include_router(dres.router)
app.include_router(videos.router)
app.include_router(config_router.router)
app.include_router(team_submissions.router)
app.include_router(live_questions.router)


@app.get("/health")
def health():
    """Trạng thái CHI TIẾT của cả 3 phụ thuộc — nguồn cho "bảng Kết nối" trên UI.

    Tách rõ cái gì CẦN GPU và cái gì KHÔNG: mất encoder Kaggle giữa cuộc thi
    KHÔNG được làm chết cả hệ thống — OCR/ASR khớp từ (Meilisearch), phản hồi
    liên quan, Workbench, filmstrip, nộp bài đều vẫn chạy được."""
    import time as _t

    import requests as _rq

    state = app.state
    out: dict = {"status": "ok"}

    # FAISS (in-process, luôn sống nếu app sống)
    repo = getattr(state, "faiss_repo", None)
    if repo is not None:
        out["faiss"] = {"ok": True, "branches": repo.branch_sizes()}

    # Meilisearch
    meili = getattr(state, "meili_repo", None)
    if meili is not None:
        t = _t.time()
        try:
            meili.client.health()
            counts = {}
            for name, idx in (("frames", meili.frames), ("asr", meili.asr), ("videos", meili.videos)):
                try:
                    counts[name] = idx.get_stats().number_of_documents
                except Exception:
                    counts[name] = None
            out["meili"] = {"ok": True, "latency_ms": int((_t.time() - t) * 1000),
                            "docs": counts}
        except Exception as e:
            out["meili"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            out["status"] = "degraded"

    # Encoder từ xa (Kaggle) — CHỈ ảnh hưởng các thao tác cần encode câu/ảnh mới
    if settings.REMOTE_ENCODER_URL:
        t = _t.time()
        try:
            r = _rq.get(f"{settings.REMOTE_ENCODER_URL.rstrip('/')}/health",
                        headers={"X-API-Key": settings.REMOTE_ENCODER_KEY}, timeout=8)
            r.raise_for_status()
            out["encoder"] = {"ok": True, "url": settings.REMOTE_ENCODER_URL,
                              "latency_ms": int((_t.time() - t) * 1000),
                              "detail": r.json()}
        except Exception as e:
            out["encoder"] = {"ok": False, "url": settings.REMOTE_ENCODER_URL,
                              "error": f"{type(e).__name__}: {e}",
                              "note": "Tìm kiếm bằng câu mới sẽ không chạy. "
                                      "Các thao tác không cần GPU vẫn dùng được bình thường."}
            out["status"] = "degraded"
    else:
        out["encoder"] = {"ok": False, "url": None, "note": "chưa cấu hình encoder từ xa"}

    vc = getattr(state, "vec_cache", None)
    bc = getattr(state, "branch_cache", None)
    if vc is not None and bc is not None:
        out["cache"] = {"vector": vc.stats(), "branch": bc.stats()}
    return out
