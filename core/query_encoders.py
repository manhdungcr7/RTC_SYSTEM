"""Singleton loader cho 4 text-encoder — hệ cũ chỉ có 1 (SigLIP2), giờ có
MetaCLIP-2 (đa ngữ, in-process) + PE-Core (in-process, source cache sẵn ở
artifacts/pe_src) + BEiT-3 (subprocess bridge riêng venv timm==0.4.12, tái dùng
`system/beit3_env`+`system/beit3_server` đã validate — KHÔNG cài chung vì rủi ro
xung đột phụ thuộc) + capemb/Qwen3-Embedding-4B (in-process, sentence-transformers).

Load MỘT LẦN lúc FastAPI startup (`QueryEncoders().load_all()`), giữ trong
`app.state` — KHÔNG load lại mỗi request (model vài trăm MB - vài GB).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from threading import Lock

import numpy as np

from config import settings
from core import config as C


class RemoteBranchEncoder:
    """Client gọi qua `indexing/kaggle/11_encode_service.py` (Kaggle GPU + ngrok)
    thay vì nạp model tại chỗ — dùng khi settings.REMOTE_ENCODER_URL được đặt.
    Cùng interface `.encode()` với 3 encoder in-process (MetaClip2/PeCore/CapEmb);
    `.encode_one()` riêng cho beit3 (server KHÔNG pool sẵn — pool max ở đây, giữ
    hành vi giống Beit3BridgeEncoder cũ để router không cần đổi gì)."""

    def __init__(self, base_url: str, api_key: str, branch: str):
        import requests
        self._requests = requests
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.branch = branch

    def _call(self, texts: list[str]) -> np.ndarray:
        r = self._requests.post(
            f"{self.base_url}/encode",
            json={"branch": self.branch, "texts": texts},
            headers={"X-API-Key": self.api_key},
            timeout=60,
        )
        r.raise_for_status()
        return np.array(r.json()["vectors"], dtype=np.float32)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        return self._call(texts)

    def encode_one(self, texts: list[str]) -> np.ndarray | None:
        """Chỉ dùng cho beit3 — pool MAX qua các mệnh đề SAU khi nhận vector thô
        từ server (server không pool sẵn) + bắt lỗi trả None, ĐÚNG hợp đồng cũ
        (api/routers/search.py bỏ qua êm khi None)."""
        if not texts:
            return None
        try:
            vecs = self._call(texts)
        except Exception as e:
            print(f"[query_encoders] remote {self.branch} lỗi ({type(e).__name__}: {e}) -> bỏ qua êm")
            return None
        v = vecs.max(axis=0)
        return v / (np.linalg.norm(v) + 1e-8)


class RemoteImageEncoder:
    """Client gọi `/encode_image` (DINOv3, PHÍA ẢNH — không có text tower) qua
    `indexing/kaggle/11_encode_service.py` — dùng cho "tìm ảnh giống" khi người
    dùng UPLOAD ảnh ngoài chưa có sẵn trong index (khác `/similar` thường, vốn chỉ
    lấy lại vector ĐÃ index sẵn qua `FaissRepo.fetch_vector_by_id`, xem
    api/routers/similar.py). KHÔNG có bản in-process local — backend container
    không cài torch/transformers (nhẹ, xem requirements-docker.txt) nên tính năng
    này CẦN REMOTE_ENCODER_URL đang chạy."""

    def __init__(self, base_url: str, api_key: str):
        import requests
        self._requests = requests
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def encode_image(self, image_bytes: bytes, filename: str = "image.jpg") -> np.ndarray:
        r = self._requests.post(
            f"{self.base_url}/encode_image",
            files={"file": (filename, image_bytes)},
            headers={"X-API-Key": self.api_key},
            timeout=60,
        )
        r.raise_for_status()
        return np.array(r.json()["vector"], dtype=np.float32)

# Cắt token THẬT SỰ diễn ra native trong từng tokenizer (HF processor `truncation=True,
# max_length=...` cho MetaCLIP-2; `SimpleTokenizer.__call__` tự cắt về context_length cho
# PE-Core) — cả hai đều GIỮ ĐẦU câu theo mặc định (chuẩn CLIP: cắt đuôi, giữ [SOT]..đầu
# câu..[EOT]), đúng hướng positional-bias đã nghiên cứu. `core/query_service.py` chỉ cần
# LOG cảnh báo khi 1 mệnh đề vượt ngưỡng, không cần tự cắt lại ở đây.


def _pick_device(torch_module, required_gb: float, name: str) -> str:
    """Chọn cuda/cpu dựa trên VRAM TRỐNG THẬT SỰ (torch.cuda.mem_get_info), không
    chỉ dựa vào cuda.is_available(). ĐO THẬT trên máy dev (RTX 3050 4GB): MetaCLIP-2
    "huge" một mình đã cần ~7.5GB — vượt VRAM, Windows fallback sang RAM hệ thống
    qua PCIe (chậm hơn CPU thường: encode 2 câu mất 9-10s trên "GPU" fallback này,
    so với 3.2s chạy CPU thẳng). Kiểm tra trước tránh rơi vào tình huống "GPU"
    chậm hơn CPU. Trên máy nhiều VRAM hơn (vd thuê 4090 24GB sau này) hàm này tự
    chọn cuda mà KHÔNG cần sửa code — required_gb chỉ là ước lượng bảo thủ."""
    if not torch_module.cuda.is_available():
        return "cpu"
    free_bytes, _ = torch_module.cuda.mem_get_info()
    free_gb = free_bytes / 1e9
    if free_gb >= required_gb:
        return "cuda"
    print(f"[query_encoders] {name}: VRAM trống {free_gb:.1f}GB < cần ~{required_gb}GB "
          f"-> dùng CPU (tránh GPU fallback chậm hơn CPU, đã đo thật).")
    return "cpu"


def _import_pe_core_modules():
    """Source PE-Core (artifacts/pe_src/core/vision_encoder/*) dùng ABSOLUTE import
    'core.vision_encoder.X' — TRÙNG TÊN với package `core` của CHÍNH dự án này (module
    đang chạy đoạn code này chính là core/query_encoders.py!). Nếu import thẳng, Python
    thấy `sys.modules['core']` đã có sẵn (package của ta) và tìm 'vision_encoder' như
    submodule của NÓ (không tồn tại) -> ModuleNotFoundError.

    Hoán đổi TẠM THỜI sys.modules['core'] sang vendor package, import xong khôi phục
    lại ngay (module object trả về vẫn hợp lệ dù bị gỡ khỏi cache — chỉ ẢNH HƯỞNG lúc
    import, không ảnh hưởng object đã lấy được) — làm 1 LẦN lúc startup, không phải
    per-request, nên chấp nhận được."""
    our_core_modules = {k: v for k, v in sys.modules.items() if k == "core" or k.startswith("core.")}
    for k in list(our_core_modules):
        del sys.modules[k]

    pe_src = str(settings.PE_SRC)
    sys.path.insert(0, pe_src)
    try:
        import core.vision_encoder.pe as pe
        import core.vision_encoder.transforms as transforms
    finally:
        for k in list(sys.modules):
            if k == "core" or k.startswith("core."):
                del sys.modules[k]
        sys.modules.update(our_core_modules)
        sys.path.remove(pe_src)
    return pe, transforms


class MetaClip2Encoder:
    """facebook/metaclip-2-worldwide-huge-378 — đa ngữ, KHÔNG cần dịch VI->EN."""

    def __init__(self):
        import torch
        from transformers import AutoModel, AutoProcessor

        self.torch = torch
        self.dev = _pick_device(torch, required_gb=8.0, name="MetaCLIP-2")
        model_id = "facebook/metaclip-2-worldwide-huge-378"
        self.proc = AutoProcessor.from_pretrained(model_id)
        # low_cpu_mem_usage=True: nạp thẳng weight (safetensors, memory-map) vào bộ
        # nhớ đích thay vì tạo 1 bản sao float32 tạm rồi convert — tránh đỉnh RAM
        # gấp đôi lúc nạp. ĐÃ THỬ THẬT: thiếu cờ này gây Segmentation fault khi chạy
        # trong app đầy đủ (FAISS/Meilisearch client + media_index đã chiếm RAM sẵn), dù
        # chạy cô lập một mình vẫn qua được (baseline RAM rảnh hơn).
        self.model = AutoModel.from_pretrained(
            model_id, dtype=torch.float32, low_cpu_mem_usage=True,
        ).to(self.dev).eval()
        print(f"[query_encoders] MetaCLIP-2 sẵn sàng trên {self.dev}")

    def encode(self, texts: list[str]) -> np.ndarray:
        inp = self.proc(text=texts, return_tensors="pt", padding=True,
                         truncation=True, max_length=C.MAX_TOKENS["metaclip2"]).to(self.dev)
        with self.torch.no_grad():
            out = self.model.get_text_features(**inp)
        # KHÔNG dùng `a or b or c` — Tensor nhiều phần tử (batch > 1) làm bool() nổ
        # ("Boolean value of Tensor... ambiguous"). Phải check `is None` tường minh
        # (đúng pattern gốc trong indexing/kaggle/02_embed.py:encode_images).
        if self.torch.is_tensor(out):
            feat = out
        else:
            feat = getattr(out, "text_embeds", None)
            if feat is None:
                feat = getattr(out, "pooler_output", None)
            if feat is None:
                feat = out.last_hidden_state[:, 0, :]
        feat = feat / feat.norm(dim=-1, keepdim=True).clamp_min(1e-8)
        return feat.float().cpu().numpy().astype(np.float32)


class PeCoreEncoder:
    """PE-Core-L14-336 — chỉ tiếng Anh. Source vendored sẵn ở artifacts/pe_src
    (đã tải lúc offline indexing — KHÔNG tải lại từ GitHub)."""

    def __init__(self):
        import torch
        pe, transforms = _import_pe_core_modules()

        self.torch = torch
        self.dev = _pick_device(torch, required_gb=5.0, name="PE-Core")
        self.model = pe.CLIP.from_config("PE-Core-L14-336", pretrained=True).to(self.dev).eval()
        self.tokenizer = transforms.get_text_tokenizer(self.model.context_length)
        print(f"[query_encoders] PE-Core sẵn sàng trên {self.dev} "
              f"(context_length={self.model.context_length})")

    def encode(self, texts: list[str]) -> np.ndarray:
        tokens = self.tokenizer(texts).to(self.dev)   # tự truncate về context_length, giữ đầu
        with self.torch.no_grad():
            feat = self.model.encode_text(tokens, normalize=True)
        return feat.float().cpu().numpy().astype(np.float32)


class Beit3BridgeEncoder:
    """Subprocess thường trực trong venv riêng (timm==0.4.12) — port nguyên logic
    `system/aic/beit3_bridge.py`. Chỉ tiếng Anh, MAX-pool qua các mệnh đề đã ở
    TRONG server (server.py encode() nhận list[str] -> 1 vector 1024 chiều)."""

    def __init__(self):
        self._proc = None
        self._lock = Lock()
        self._broken = False
        self.dim = 1024
        self._start()

    def available(self) -> bool:
        return settings.BEIT3_VENV_PY.exists() and settings.BEIT3_SERVER.exists() and not self._broken

    def _start(self):
        if not self.available():
            self._broken = True
            print("[query_encoders] BEiT-3 bridge KHÔNG có mặt (venv/server thiếu) -> tắt êm")
            return
        try:
            self._proc = subprocess.Popen(
                [str(settings.BEIT3_VENV_PY), str(settings.BEIT3_SERVER)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, cwd=str(settings.BEIT3_SERVER.parent),
            )
            first = self._proc.stdout.readline()
            info = json.loads(first)
            if not info.get("ready"):
                raise RuntimeError(f"server không báo ready: {first!r}")
            self.dim = info["dim"]
            print(f"[query_encoders] BEiT-3 bridge sẵn sàng, dim={self.dim}")
        except Exception as e:
            err = self._proc.stderr.read()[-800:] if self._proc and self._proc.stderr else ""
            print(f"[query_encoders] BEiT-3 bridge KHÔNG khởi động được "
                  f"({type(e).__name__}: {e}) -> tắt êm, hệ thống vẫn chạy không BEiT-3.\n{err}")
            self._proc = None
            self._broken = True

    def encode_one(self, clauses: list[str]) -> np.ndarray | None:
        """1 query (nhiều mệnh đề tiếng Anh) -> (dim,) đã MAX-pool trong server, hoặc
        None nếu bridge hỏng — caller PHẢI bỏ qua êm tín hiệu BEiT-3 khi None."""
        if self._broken:
            return None
        with self._lock:
            if self._proc is None:
                self._start()
            if self._proc is None:
                return None
            try:
                self._proc.stdin.write(json.dumps(clauses) + "\n")
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
                if not line:
                    raise RuntimeError("server đã thoát (stdout đóng)")
                data = json.loads(line)
                if isinstance(data, dict) and "error" in data:
                    print(f"[query_encoders] BEiT-3 lỗi encode: {data['error']}")
                    return None
                return np.array(data, dtype=np.float32)
            except Exception as e:
                print(f"[query_encoders] BEiT-3 mất kết nối ({type(e).__name__}: {e}) -> tắt cho phần còn lại phiên")
                self._proc = None
                self._broken = True
                return None

    def shutdown(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None


class CapEmbEncoder:
    """Qwen3-Embedding-4B qua sentence-transformers — đa ngữ, KHÔNG cắt token (câu
    dài feed nguyên vẹn). Phía document (lúc index) encode KHÔNG prompt; phía query
    dùng prompt_name="query" (template Qwen3-Embedding chính thức cho truy vấn —
    đã ghi chú sẵn trong indexing/kaggle/10_cap_embed.py)."""

    def __init__(self):
        import torch
        from sentence_transformers import SentenceTransformer

        dev = _pick_device(torch, required_gb=9.0, name="capemb")
        # LUÔN fp16 dù chạy CPU: model 4B tham số ở fp32 cần ~16GB RAM chỉ cho trọng
        # số — ĐÃ THỬ THẬT và làm Segmentation fault (OOM cấp hệ điều hành) trên máy
        # dev 15.9GB RAM. fp16 giảm còn ~8GB, đủ chạy. Ưu tiên "chạy được" hơn tốc độ
        # CPU-kernel-fp16 (transformers/torch tự upcast per-op khi cần, không lỗi).
        self.model = SentenceTransformer(
            "Qwen/Qwen3-Embedding-4B", device=dev,
            model_kwargs={"dtype": torch.float16, "attn_implementation": "sdpa",
                          "low_cpu_mem_usage": True},
            processor_kwargs={"padding_side": "left"},
        )
        self.dim = self.model.get_embedding_dimension()
        print(f"[query_encoders] capemb (Qwen3-Embedding-4B) sẵn sàng trên {dev}, dim={self.dim}")

    def encode(self, texts: list[str]) -> np.ndarray:
        v = self.model.encode(texts, prompt_name="query", normalize_embeddings=True,
                               show_progress_bar=False, convert_to_numpy=True)
        return v.astype(np.float32)


class QueryEncoders:
    """Container duy nhất, gắn vào app.state.encoders lúc FastAPI startup."""

    def __init__(self):
        self.metaclip2: MetaClip2Encoder | None = None
        self.pecore: PeCoreEncoder | None = None
        self.beit3: Beit3BridgeEncoder | None = None
        self.capemb: CapEmbEncoder | None = None
        self.dinov3_image: RemoteImageEncoder | None = None   # chỉ có khi dùng REMOTE encoder

    def load_all(self) -> "QueryEncoders":
        """Chỉ nạp encoder có C.ENABLED_BRANCHES[tên]=True — nhánh tắt giữ None,
        caller (api/routers/search.py) PHẢI tự bỏ qua êm khi None (giống cách OCR/
        ASR/beit3-bridge "bỏ qua êm khi thiếu" đã làm trong hệ cũ).

        Nếu settings.REMOTE_ENCODER_URL được đặt (xem indexing/kaggle/
        11_encode_service.py): KHÔNG nạp model local — gọi qua Kaggle GPU + ngrok
        thay thế, rẻ RAM/VRAM máy dev nên có thể bật CẢ 4 nhánh thoải mái."""
        if settings.REMOTE_ENCODER_URL:
            print(f"[query_encoders] dùng REMOTE encoder tại {settings.REMOTE_ENCODER_URL}")
            if not settings.REMOTE_ENCODER_KEY:
                print("[query_encoders] !!! CẢNH BÁO: chưa đặt AIC_REMOTE_ENCODER_KEY -> "
                      "server sẽ từ chối (401) mọi request.")
            url, key = settings.REMOTE_ENCODER_URL, settings.REMOTE_ENCODER_KEY
            if C.ENABLED_BRANCHES.get("metaclip2", True):
                self.metaclip2 = RemoteBranchEncoder(url, key, "metaclip2")
            if C.ENABLED_BRANCHES.get("pecore", True):
                self.pecore = RemoteBranchEncoder(url, key, "pecore")
            if C.ENABLED_BRANCHES.get("beit3", True):
                self.beit3 = RemoteBranchEncoder(url, key, "beit3")
            if C.ENABLED_BRANCHES.get("capemb", True):
                self.capemb = RemoteBranchEncoder(url, key, "capemb")
            if C.ENABLED_BRANCHES.get("dinov3", True):
                self.dinov3_image = RemoteImageEncoder(url, key)
            return self

        if C.ENABLED_BRANCHES.get("metaclip2", True):
            self.metaclip2 = MetaClip2Encoder()
        if C.ENABLED_BRANCHES.get("pecore", True):
            self.pecore = PeCoreEncoder()
        if C.ENABLED_BRANCHES.get("beit3", True):
            self.beit3 = Beit3BridgeEncoder()
        if C.ENABLED_BRANCHES.get("capemb", True):
            self.capemb = CapEmbEncoder()
        return self

    def shutdown(self):
        if isinstance(self.beit3, Beit3BridgeEncoder):
            self.beit3.shutdown()   # RemoteBranchEncoder không có subprocess -> khỏi shutdown
