"""Nạp TỪNG encoder một (không load_all() 1 lần) để thấy rõ VRAM/RAM tiêu tốn ở
đâu nếu có sự cố — chạy: cd aic-system && python scripts/verify_encoders.py"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch


def gpu_mb():
    if not torch.cuda.is_available():
        return "no-cuda"
    return f"{torch.cuda.memory_allocated() / 1e6:.0f}MB alloc / {torch.cuda.memory_reserved() / 1e6:.0f}MB reserved"


print("=" * 60, "\n[1] MetaCLIP-2\n", "=" * 60)
t0 = time.time()
from core.query_encoders import MetaClip2Encoder
mc = MetaClip2Encoder()
print(f"  nap xong {time.time()-t0:.1f}s | GPU: {gpu_mb()}")
v = mc.encode(["a person riding a bicycle", "tin tức thời sự buổi tối"])
print(f"  encode shape: {v.shape}, norm: {(v**2).sum(-1)**0.5}")

print("=" * 60, "\n[2] PE-Core\n", "=" * 60)
t0 = time.time()
from core.query_encoders import PeCoreEncoder
pc = PeCoreEncoder()
print(f"  nap xong {time.time()-t0:.1f}s | GPU: {gpu_mb()}")
v = pc.encode(["a person riding a bicycle", "evening news broadcast"])
print(f"  encode shape: {v.shape}")

print("=" * 60, "\n[3] BEiT-3 bridge (subprocess)\n", "=" * 60)
t0 = time.time()
from core.query_encoders import Beit3BridgeEncoder
b3 = Beit3BridgeEncoder()
print(f"  available={b3.available()} | nap xong {time.time()-t0:.1f}s")
v = b3.encode_one(["a person riding a bicycle"])
print(f"  encode: {None if v is None else v.shape}")
b3.shutdown()

print("=" * 60, "\n[4] capemb (Qwen3-Embedding-4B)\n", "=" * 60)
t0 = time.time()
from core.query_encoders import CapEmbEncoder
ce = CapEmbEncoder()
print(f"  nap xong {time.time()-t0:.1f}s | GPU: {gpu_mb()}")
v = ce.encode(["một người đang đi xe đạp trên đường"])
print(f"  encode shape: {v.shape}")

print("\n>>> TAT CA ENCODER NAP + ENCODE OK.")
