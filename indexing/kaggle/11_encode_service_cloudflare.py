"""
================================================================================
KAGGLE NOTEBOOK 11 — ENCODE SERVICE (query-time, KHÔNG phải offline indexing)
================================================================================
KHÁC mọi notebook 01-10 (chạy 1 lần rồi lưu kết quả): notebook này chạy THƯỜNG
TRỰC trong lúc dùng hệ thống — nạp cả 4 model text-encoder (MetaCLIP-2/PE-Core/
BEiT-3/capemb) 1 LẦN, mở 1 API (FastAPI + Cloudflare Tunnel) để backend LOCAL (aic-system/)
gọi sang thay vì tự nạp model (máy dev chỉ 4GB VRAM/15.9GB RAM không đủ nạp cả
4 — xem lý do trong hội thoại: DPC_WATCHDOG_VIOLATION/BSOD khi thử nạp local).

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2 (bắt buộc — chia model qua 2 GPU cho vừa VRAM)
  - Internet    : ON
  - Add Input   : KHÔNG cần dataset nào (model tải thẳng từ HuggingFace/GitHub)

CHẠY: dán cả file vào 1 cell → Run All. Server chạy tới khi notebook bị dừng
(Kaggle: tối đa ~9-12 tiếng/phiên, hoặc tự ngắt nếu rảnh lâu — ĐỦ cho 1 buổi
test/luyện tập, KHÔNG khuyến nghị dùng cho lúc thi thật vì không có SLA).

BẢO MẬT: in ra 1 API_KEY ngẫu nhiên lúc khởi động — copy vào biến môi trường
AIC_REMOTE_ENCODER_KEY ở máy local (config/settings.py đọc lại), tránh người
lạ đoán được URL Cloudflare rồi xài ké GPU miễn phí của bạn.

API:
  POST /encode  {"branch": "metaclip2"|"pecore"|"beit3"|"capemb", "texts": [...]}
                header: X-API-Key: <api_key>
             -> {"vectors": [[...], ...]}   # (n, dim) — KHÔNG pool sẵn (kể cả
                beit3) — phía local tự pool/maxmean, encode service chỉ lo vector
                hoá, giữ hợp đồng API đơn giản/đồng nhất cho cả 4 nhánh.
  POST /encode_image  multipart/form-data, field "file" = ảnh (jpg/png/webp...)
                header: X-API-Key: <api_key>
             -> {"vector": [...]}   # (dim,) — DINOv3, dùng cho "tìm ảnh giống"
                khi người dùng UPLOAD ảnh ngoài (không có sẵn trong index) — xem
                api/routers/similar.py::similar_upload. Encode PHÍA ẢNH duy nhất
                — không có text tower nên không nằm trong /encode.
  GET  /health -> {"status": "ok", "branches": [...], "image_branches": [...]}

DINOv3 là model "gated" trên HuggingFace — cần Kaggle Secret "HF_TOKEN" (Add-ons
-> Secrets -> thêm + bật Attach cho notebook này), giống notebook 04_embed_dinov3.py.
================================================================================
"""
import os
import queue
import re
import secrets
import subprocess
import sys
import threading

import numpy as np

VERSION = "11-encode-service v1"
print(f">>> {VERSION}", flush=True)

TUNNEL_PROVIDER = "cloudflare"
print(">>> Tunnel provider: cloudflare", flush=True)

API_KEY = os.environ.get("AIC_REMOTE_ENCODER_KEY") or secrets.token_urlsafe(24)
print("=" * 70)
print(f"  API_KEY (copy vao AIC_REMOTE_ENCODER_KEY o may local): {API_KEY}")
print("=" * 70, flush=True)


def sh(cmd, check=False):
    print("$", cmd, flush=True)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        if check:
            raise RuntimeError(cmd)
    return r


# ==================== 1. CÀI ĐẶT ====================
print("=" * 70, "\n[1/5] Cai dat goi can thiet\n", "=" * 70, flush=True)
sh(f"{sys.executable} -m pip install -q -U 'transformers>=4.57' 'sentence-transformers>=3.0' "
   f"fastapi uvicorn einops ftfy regex huggingface_hub python-multipart")
# Pillow KHÔNG được để "-U" tự do (bản mới nhất đổi API nội bộ _typing._Ink, phá
# torchvision.utils import ImageDraw -> ImportError khi transformers tải image
# processor bất kỳ, kể cả MetaCLIP-2 không liên quan gì tới DINOv3). Ghim bản ổn
# định GIỐNG indexing/kaggle/02_embed.py/04_embed_dinov3.py — ĐÃ GẶP THẬT lỗi
# này khi thêm pillow không ghim version vào lệnh cài ở trên.
sh(f"{sys.executable} -m pip install -q 'pillow==11.1.0'")

import torch  # noqa: E402

N_GPU = torch.cuda.device_count()
print(f"  So GPU: {N_GPU}", flush=True)
for i in range(N_GPU):
    print(f"    cuda:{i} = {torch.cuda.get_device_name(i)}", flush=True)

# Chia model qua 2 GPU nếu có (T4 x2 = 16GB/cái) — 1 GPU 16GB không đủ nạp cả
# 4 model cùng lúc (~20GB tổng). Chỉ 1 GPU -> tất cả dồn vào đó (T4 16GB đơn lẻ
# vẫn đủ cho TỪNG model một lúc gọi, chỉ hơi chật nếu nạp đồng thời).
if N_GPU >= 2:
    DEV = {"metaclip2": "cuda:0", "pecore": "cuda:0", "dinov3": "cuda:0", "beit3": "cuda:1", "capemb": "cuda:1"}
else:
    dev0 = "cuda:0" if N_GPU >= 1 else "cpu"
    DEV = {"metaclip2": dev0, "pecore": dev0, "dinov3": dev0, "beit3": dev0, "capemb": dev0}
print(f"  Phan bo GPU: {DEV}", flush=True)


# ==================== 2. NAP METACLIP-2 ====================
print("=" * 70, "\n[2/5] Nap MetaCLIP-2\n", "=" * 70, flush=True)
from transformers import AutoModel, AutoProcessor  # noqa: E402

_MC_ID = "facebook/metaclip-2-worldwide-huge-378"
mc_proc = AutoProcessor.from_pretrained(_MC_ID)
mc_model = AutoModel.from_pretrained(_MC_ID, dtype=torch.float32).to(DEV["metaclip2"]).eval()
print(f"  MetaCLIP-2 san sang tren {DEV['metaclip2']}", flush=True)


@torch.no_grad()
def encode_metaclip2(texts: list[str]) -> np.ndarray:
    inp = mc_proc(text=texts, return_tensors="pt", padding=True, truncation=True,
                  max_length=77).to(DEV["metaclip2"])
    out = mc_model.get_text_features(**inp)
    feat = out if torch.is_tensor(out) else (
        getattr(out, "text_embeds", None) if getattr(out, "text_embeds", None) is not None else
        getattr(out, "pooler_output", None) if getattr(out, "pooler_output", None) is not None else
        out.last_hidden_state[:, 0, :])
    feat = feat / feat.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    return feat.float().cpu().numpy().astype(np.float32)


# ==================== 3. NAP PE-CORE ====================
print("=" * 70, "\n[3/5] Nap PE-Core-L14-336\n", "=" * 70, flush=True)
from pathlib import Path  # noqa: E402

PE_SRC = Path("/kaggle/working/pe_src")
CORE = PE_SRC / "core" / "vision_encoder"
CORE.mkdir(parents=True, exist_ok=True)
(PE_SRC / "core" / "__init__.py").touch()
(CORE / "__init__.py").touch()
_BASE = "https://raw.githubusercontent.com/facebookresearch/perception_models/main/core/vision_encoder"
for f in ["pe.py", "transforms.py", "tokenizer.py", "rope.py", "config.py"]:
    sh(f"curl -sL {_BASE}/{f} -o {CORE/f}")
sh(f"curl -sL {_BASE}/bpe_simple_vocab_16e6.txt.gz -o {CORE/'bpe_simple_vocab_16e6.txt.gz'}")
sys.path.insert(0, str(PE_SRC))
import core.vision_encoder.pe as pe  # noqa: E402
import core.vision_encoder.transforms as pe_transforms  # noqa: E402

pc_model = pe.CLIP.from_config("PE-Core-L14-336", pretrained=True).to(DEV["pecore"]).eval()
pc_tokenizer = pe_transforms.get_text_tokenizer(pc_model.context_length)
print(f"  PE-Core san sang tren {DEV['pecore']} (context_length={pc_model.context_length})", flush=True)


@torch.no_grad()
def encode_pecore(texts: list[str]) -> np.ndarray:
    tokens = pc_tokenizer(texts).to(DEV["pecore"])
    feat = pc_model.encode_text(tokens, normalize=True)
    return feat.float().cpu().numpy().astype(np.float32)


# ==================== 3b. NẠP DINOv3 (image-only, cho "tìm ảnh giống" khi upload) ====================
print("=" * 70, "\n[3b/5] Nap DINOv3 (anh gated - can HF_TOKEN)\n", "=" * 70, flush=True)
_hf_token = None
try:
    from kaggle_secrets import UserSecretsClient  # noqa: E402
    _hf_token = UserSecretsClient().get_secret("HF_TOKEN")
except Exception:
    _hf_token = os.environ.get("HF_TOKEN")
if _hf_token:
    from huggingface_hub import login  # noqa: E402
    login(token=_hf_token)
    print("  Da dang nhap HuggingFace bang HF_TOKEN.", flush=True)
else:
    print("  [CANH BAO] KHONG tim thay HF_TOKEN — DINOv3 (gated) se loi 403 khi tai. "
          "Vao Add-ons -> Secrets -> them 'HF_TOKEN' + bat Attach cho notebook nay. "
          "/encode_image se tra loi 503 cho toi khi model nap duoc.", flush=True)

_DINOV3_ID = "facebook/dinov3-vitl16-pretrain-lvd1689m"
dinov3_model = None
dinov3_proc = None
try:
    from transformers import AutoImageProcessor  # noqa: E402
    dinov3_proc = AutoImageProcessor.from_pretrained(_DINOV3_ID)
    # fp16 THUAN gay NaN 100% tren T4 (da xac nhan that o notebook 04) -> fp32.
    dinov3_model = AutoModel.from_pretrained(_DINOV3_ID, dtype=torch.float32).to(DEV["dinov3"]).eval()
    print(f"  DINOv3 san sang tren {DEV['dinov3']} (fp32)", flush=True)
except Exception as e:
    print(f"  [LOI] Khong nap duoc DINOv3 ({type(e).__name__}: {e}) — /encode_image se tra 503.", flush=True)


@torch.no_grad()
def encode_image_dinov3(pil_img) -> np.ndarray:
    inp = dinov3_proc(images=[pil_img], return_tensors="pt").to(DEV["dinov3"])
    out = dinov3_model(**inp)
    feat = getattr(out, "pooler_output", None)
    if feat is None:
        feat = out.last_hidden_state[:, 1:, :].mean(dim=1)
    feat = feat / feat.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    return feat.float().cpu().numpy().astype(np.float32)[0]


# ==================== 4. NAP BEIT-3 ====================
print("=" * 70, "\n[4/5] Nap BEiT-3\n", "=" * 70, flush=True)
import collections.abc as _abc  # noqa: E402
import types as _types  # noqa: E402

_six = _types.ModuleType("torch._six")
_six.container_abcs = _abc
_six.string_classes = (str, bytes)
_six.int_classes = (int,)
_six.inf = float("inf")
_six.nan = float("nan")
sys.modules["torch._six"] = _six

sh("git clone --depth 1 https://github.com/microsoft/unilm.git /kaggle/temp/unilm", check=True)
sh(f"{sys.executable} -m pip install -q timm==0.4.12 torchscale==0.2.0 sentencepiece "
   f"ftfy torchmetrics tensorboardX")

_REL = "https://github.com/addf400/files/releases/download/beit3"
sh(f'wget -q -O /kaggle/temp/beit3_large_patch16_384_coco_retrieval.pth '
   f'"{_REL}/beit3_large_patch16_384_coco_retrieval.pth"')
sh(f'wget -q -O /kaggle/temp/beit3.spm "{_REL}/beit3.spm"')
assert Path("/kaggle/temp/beit3_large_patch16_384_coco_retrieval.pth").stat().st_size > 1_000_000_000, \
    "Tai checkpoint BEiT-3 that bai — kiem tra Internet ON"
assert Path("/kaggle/temp/beit3.spm").stat().st_size > 100_000, \
    "Tai tokenizer beit3.spm that bai"

sys.path.append("/kaggle/temp/unilm/beit3")
import sentencepiece as spm  # noqa: E402
import modeling_finetune  # noqa: E402  (đăng ký kiến trúc @register_model)
from modeling_finetune import beit3_large_patch16_384_retrieval  # noqa: E402

b3_model = beit3_large_patch16_384_retrieval(pretrained=False)
_ck = torch.load("/kaggle/temp/beit3_large_patch16_384_coco_retrieval.pth", map_location="cpu")
b3_model.load_state_dict(_ck.get("model", _ck))
b3_model = b3_model.to(DEV["beit3"]).eval()
b3_sp = spm.SentencePieceProcessor(model_file="/kaggle/temp/beit3.spm")
print(f"  BEiT-3 san sang tren {DEV['beit3']}", flush=True)


def _b3_sp_encode(text: str, maxlen: int = 64) -> list[int]:
    pieces = b3_sp.encode(text, out_type=str)
    ids = []
    for p in pieces:
        sid = b3_sp.piece_to_id(p)
        ids.append(sid + 1 if sid != 0 else 3)
    return [0] + ids[: maxlen - 2] + [2]


@torch.no_grad()
def encode_beit3(texts: list[str]) -> np.ndarray:
    """KHÔNG max-pool ở đây (khác system/beit3_server cũ) — trả (n,D) từng câu,
    để local tự pool giống các nhánh khác, giữ API đồng nhất."""
    out = []
    for t in texts:
        ids = _b3_sp_encode(t)
        pad_n = 64 - len(ids)
        mask = [0] * len(ids) + [1] * pad_n
        ids = ids + [1] * pad_n
        ti = torch.tensor([ids]).to(DEV["beit3"])
        pm = torch.tensor([mask]).to(DEV["beit3"])
        _, lang = b3_model(text_description=ti, padding_mask=pm, only_infer=True)
        v = torch.nn.functional.normalize(lang, dim=-1)
        out.append(v[0].float().cpu().numpy())
    return np.array(out, dtype=np.float32)


# ==================== 5. NAP CAPEMB (Qwen3-Embedding-4B) ====================
print("=" * 70, "\n[5/5] Nap capemb (Qwen3-Embedding-4B)\n", "=" * 70, flush=True)
from sentence_transformers import SentenceTransformer  # noqa: E402

ce_model = SentenceTransformer(
    "Qwen/Qwen3-Embedding-4B", device=DEV["capemb"],
    model_kwargs={"dtype": torch.float16, "attn_implementation": "sdpa"},
    tokenizer_kwargs={"padding_side": "left"},
)
print(f"  capemb san sang tren {DEV['capemb']}, dim={ce_model.get_sentence_embedding_dimension()}", flush=True)


def encode_capemb(texts: list[str]) -> np.ndarray:
    v = ce_model.encode(texts, prompt_name="query", normalize_embeddings=True,
                         show_progress_bar=False, convert_to_numpy=True)
    return v.astype(np.float32)


ENCODERS = {
    "metaclip2": encode_metaclip2,
    "pecore": encode_pecore,
    "beit3": encode_beit3,
    "capemb": encode_capemb,
}

# ==================== 6. FASTAPI + PUBLIC TUNNEL ====================
print("=" * 70, f"\n[6/6] Khoi dong API + {TUNNEL_PROVIDER}\n", "=" * 70, flush=True)
import io  # noqa: E402

from fastapi import FastAPI, File, Header, HTTPException, UploadFile  # noqa: E402
from PIL import Image  # noqa: E402
from pydantic import BaseModel  # noqa: E402

app = FastAPI(title="AIC Encode Service (Kaggle)")


class EncodeRequest(BaseModel):
    branch: str
    texts: list[str]


@app.get("/health")
def health():
    return {"status": "ok", "branches": list(ENCODERS.keys()),
             "image_branches": ["dinov3"] if dinov3_model is not None else []}


@app.post("/encode")
def encode(req: EncodeRequest, x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(401, "sai API key")
    fn = ENCODERS.get(req.branch)
    if fn is None:
        raise HTTPException(400, f"branch '{req.branch}' khong ton tai (co: {list(ENCODERS.keys())})")
    if not req.texts:
        return {"vectors": []}
    vecs = fn(req.texts)
    return {"vectors": vecs.tolist()}


@app.post("/encode_image")
async def encode_image(file: UploadFile = File(...), x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(401, "sai API key")
    if dinov3_model is None:
        raise HTTPException(503, "DINOv3 chua nap duoc (kiem tra Kaggle Secret HF_TOKEN + Attach)")
    raw = await file.read()
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        raise HTTPException(400, f"khong doc duoc anh: {e}")
    vec = encode_image_dinov3(img)
    return {"vector": vec.tolist()}


def _run_server():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


threading.Thread(target=_run_server, daemon=True).start()


def _start_cloudflare_quick_tunnel() -> tuple[str, subprocess.Popen]:
    """Tai cloudflared va mo Quick Tunnel ngau nhien *.trycloudflare.com."""
    cloudflared = "/kaggle/working/cloudflared"
    sh("curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/"
       f"cloudflared-linux-amd64 -o {cloudflared}", check=True)
    sh(f"chmod +x {cloudflared}", check=True)

    proc = subprocess.Popen(
        [cloudflared, "tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()

    def _read_output():
        assert proc.stdout is not None
        for line in proc.stdout:
            print(f"[cloudflared] {line.rstrip()}", flush=True)
            lines.put(line)

    threading.Thread(target=_read_output, daemon=True).start()
    for _ in range(90):
        if proc.poll() is not None:
            raise RuntimeError(f"cloudflared dung som voi ma {proc.returncode}")
        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            continue
        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if match:
            return match.group(0), proc
    proc.terminate()
    raise RuntimeError("Qua 90 giay van khong nhan duoc URL tu Cloudflare Quick Tunnel")


public_url, _tunnel_process = _start_cloudflare_quick_tunnel()
print("=" * 70)
print(f"  URL PUBLIC (dan vao AIC_REMOTE_ENCODER_URL o may local): {public_url}")
print(f"  API_KEY (dan vao AIC_REMOTE_ENCODER_KEY o may local)   : {API_KEY}")
print("=" * 70, flush=True)

# Giu notebook song — Kaggle tu ngat khi het gio/ranh lau, khong can vong lap
# vo han "chong ngat" (di nguoc quy dinh su dung hop ly).
import time  # noqa: E402
while True:
    time.sleep(60)
