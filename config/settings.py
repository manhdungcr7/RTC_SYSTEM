"""Hằng số HẠ TẦNG (FAISS/Meilisearch/đường dẫn). Trọng số fusion/thuật toán nằm ở
core/config.py — tách riêng để 1 file là "hạ tầng" (đổi khi đổi máy/port) và 1
file là "kiến thức đo được" (đổi khi có bằng chứng mới).

ĐÃ ĐỔI (từ Milvus+Elasticsearch): máy dev RAM không đủ chạy ổn định Milvus (kèm
etcd+MinIO) — đo thật nhiều lần Milvus báo "healthy" nhưng nội bộ đã OOM
("Cannot allocate memory"), treo mọi truy vấn. Ở quy mô AIC (167,850 vector/nhánh)
FAISS in-process (không cần server riêng) + Meilisearch (nhẹ hơn ES, không cần
heap JVM) là lựa chọn hợp lý hơn cho 1 laptop cá nhân — xem PIPELINE.md."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # aic-system/
DATA_ROOT = ROOT / "data"
ARTIFACTS_ROOT = ROOT / "artifacts"

# ---- FAISS ----
# Env-overridable: trong container Docker, index FAISS được bind-mount vào 1
# đường dẫn cố định (vd /faiss) khác layout máy dev — xem docker/docker-compose.yml.
FAISS_DIR = Path(os.environ.get("AIC_FAISS_DIR", str(ROOT / "docker" / "volumes" / "faiss")))
COLLECTIONS = {
    "metaclip2": "metaclip2",   # nhánh CHÍNH, đa ngữ (không dịch)
    "beit3": "beit3",           # ensemble, lợi QA, chỉ tiếng Anh
    "pecore": "pecore",         # nhánh CHI TIẾT, chỉ tiếng Anh
    "dinov3": "dinov3",         # image-similarity thuần, không có text tower
    "capemb": "capemb",         # text-to-caption, Qwen3-Embedding-4B, đa ngữ
}

# ---- Meilisearch ----
MEILI_URL = os.environ.get("AIC_MEILI_URL", "http://localhost:7700")
MEILI_KEY = os.environ.get("AIC_MEILI_KEY", "")
MEILI_INDEX_FRAMES = "aic_frames"
MEILI_INDEX_ASR = "aic_asr"
MEILI_INDEX_VIDEOS = "aic_videos"   # lọc video trước (mục 3) — xem indexing/build_video_index.py

# ---- Media (đã có sẵn trên đĩa, KHÔNG cần tải lại) ----
# DATA_ROOT/ARTIFACTS_ROOT cũng env-overridable — trong container Docker, data thật
# được bind-mount vào 1 đường dẫn cố định (vd /data, /artifacts) khác layout máy dev.
DATA_ROOT = Path(os.environ.get("AIC_DATA_ROOT", str(DATA_ROOT)))
ARTIFACTS_ROOT = Path(os.environ.get("AIC_ARTIFACTS_ROOT", str(ARTIFACTS_ROOT)))
KEYFRAME_GLOB = "raw_*/**/keyframes/*"      # đệ quy — 2 layout khác nhau giữa các shard
MAPS_GLOB = "raw_*/**/maps/*.csv"
VIDEOS_DIR = DATA_ROOT / "videos_full" / "videos"

# ---- BEiT-3 query bridge (subprocess riêng, venv timm==0.4.12 cũ — tái dùng
# hạ tầng đã validate ở system/, KHÔNG copy lại checkpoint 1GB+) ----
LEGACY_SYSTEM_ROOT = ROOT.parent / "system"
BEIT3_VENV_PY = LEGACY_SYSTEM_ROOT / "beit3_env" / "Scripts" / "python.exe"
BEIT3_SERVER = LEGACY_SYSTEM_ROOT / "beit3_server" / "server.py"

# ---- PE-Core source (đã cache sẵn lúc indexing, KHÔNG tải lại từ GitHub) ----
PE_SRC = ARTIFACTS_ROOT / "pe_src"

# ---- LLM query-processing cache (port từ system/aic/llm.py) ----
LLM_CACHE_PATH = ARTIFACTS_ROOT / "llm_cache.json"

# ---- API ----
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
API_HOST = "0.0.0.0"
API_PORT = 8080

# ---- Remote encode service (tùy chọn — xem indexing/kaggle/11_encode_service.py) ----
# Đặt AIC_REMOTE_ENCODER_URL (URL ngrok in ra lúc notebook Kaggle khởi động) thì
# QueryEncoders.load_all() sẽ GỌI QUA đó thay vì nạp model nặng tại chỗ — máy dev
# 4GB VRAM/15.9GB RAM không đủ nạp cả 4 model cùng lúc (đã đo thật: gây BSOD).
# Để trống (mặc định) -> nạp local như cũ (chỉ nhánh metaclip2, xem ENABLED_BRANCHES).
REMOTE_ENCODER_URL = os.environ.get("AIC_REMOTE_ENCODER_URL", "").strip() or None
REMOTE_ENCODER_KEY = os.environ.get("AIC_REMOTE_ENCODER_KEY", "").strip()
