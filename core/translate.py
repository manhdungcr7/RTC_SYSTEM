"""Dịch query tiếng Việt sang tiếng Anh (fallback envit5 khi không có LLM key).
Port NGUYÊN từ `system/aic/translate.py` — dùng cho nhánh beit3/pecore (chỉ tiếng
Anh). Nhánh metaclip2/capemb đa ngữ, KHÔNG cần module này (xem core/config.py
TRANSLATE_FOR).

VÌ SAO BẮT BUỘC cho beit3/pecore (đo bằng thí nghiệm 2x2 trên SigLIP2, cùng GT):
    CLIP+multilingual  | query VI 0.0500 | query EN 0.0250
    SigLIP2            | query VI 0.0000 | query EN 0.1250  <- gấp ~5x
Bài học: cos(EN,VI) cao của multilingual text encoder KHÔNG đảm bảo retrieval
tiếng Việt chạy được — chỉ benchmark thật mới lộ ra điều này.
"""
from __future__ import annotations

import os
from functools import lru_cache

# Đã thử 3 model, chọn envit5 (VietAI, chuyên Việt-Anh) — xem system/aic/translate.py
# gốc để biết lý do loại NLLB-200/opus-mt.
MODEL = os.environ.get("AIC_MT_MODEL", "VietAI/envit5-translation")
_NEEDS_PREFIX = "envit5" in MODEL


class _RawFastTok:
    """Fallback khi AutoTokenizer hỏng (transformers/tokenizers lệch phiên bản):
    nạp tokenizer.json trực tiếp bằng thư viện `tokenizers`."""

    def __init__(self, tok_json: str, eos_id: int = 1, pad_id: int = 0, max_len: int = 256):
        from tokenizers import Tokenizer
        self.t = Tokenizer.from_file(tok_json)
        self.eos_id, self.pad_id, self.max_len = eos_id, pad_id, max_len

    def __call__(self, texts, return_tensors=None, padding=True, truncation=True):
        import torch
        if isinstance(texts, str):
            texts = [texts]
        seqs = []
        for s in texts:
            ids = self.t.encode(s).ids[:self.max_len - 1] if truncation else self.t.encode(s).ids
            seqs.append(ids + [self.eos_id])
        L = max(len(s) for s in seqs)
        ids = [s + [self.pad_id] * (L - len(s)) for s in seqs]
        att = [[1] * len(s) + [0] * (L - len(s)) for s in seqs]
        return {"input_ids": torch.tensor(ids), "attention_mask": torch.tensor(att)}

    def batch_decode(self, ids, skip_special_tokens=True):
        return [self.t.decode([i for i in row if i not in (self.pad_id, self.eos_id)]
                              ) if skip_special_tokens else self.t.decode(list(row))
                for row in ids.tolist()]


def _load_tok(lo: bool):
    from core import _hfpatch  # noqa: F401
    from transformers import AutoTokenizer
    try:
        return AutoTokenizer.from_pretrained(MODEL, local_files_only=lo)
    except Exception as e:
        import glob
        cands = glob.glob(os.path.expanduser(
            f"~/.cache/huggingface/hub/models--{MODEL.replace('/', '--')}/snapshots/*/tokenizer.json"))
        if not cands:
            raise
        print(f"[translate] AutoTokenizer hỏng ({type(e).__name__}) -> raw tokenizer.json")
        return _RawFastTok(cands[0])


@lru_cache(maxsize=1)
def _mt():
    import torch
    from transformers import AutoModelForSeq2SeqLM
    lo = os.environ.get("AIC_HF_DOWNLOAD", "0") != "1"

    tok = _load_tok(lo)
    m = AutoModelForSeq2SeqLM.from_pretrained(MODEL, local_files_only=lo).eval()
    if any(p.is_meta for p in m.parameters()):
        raise RuntimeError(f"{MODEL}: weight không nạp được (param kẹt trên meta device).")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    m = m.to(dev)
    print(f"[translate] {MODEL} trên {dev}", flush=True)
    return tok, m, torch, dev


@lru_cache(maxsize=4096)
def _cached_one(text: str) -> str:
    return vi2en([text], _bypass_cache=True)[0]


def vi2en(texts, bs: int = 16, _bypass_cache: bool = False) -> list[str]:
    """Dịch list câu tiếng Việt -> tiếng Anh. Có cache vì lúc thi hay hỏi lặp."""
    if isinstance(texts, str):
        texts = [texts]
    if not _bypass_cache and len(texts) == 1:
        return [_cached_one(texts[0])]

    tok, m, torch, dev = _mt()
    src = [f"vi: {t}" if _NEEDS_PREFIX else t for t in texts]
    out = []
    for i in range(0, len(src), bs):
        b = tok(src[i:i + bs], return_tensors="pt", padding=True, truncation=True)
        b = {k: v.to(dev) for k, v in b.items()}
        with torch.no_grad():
            g = m.generate(**b, max_new_tokens=96)
        for x in tok.batch_decode(g, skip_special_tokens=True):
            out.append(x[3:].strip() if x.startswith("en:") else x.strip())
    return out


def available() -> bool:
    try:
        return bool(vi2en(["xin chào"], _bypass_cache=True)[0])
    except Exception:
        return False
