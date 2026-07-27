import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch

t0 = time.time()
from core.query_encoders import MetaClip2Encoder
mc = MetaClip2Encoder()
print(f"nap xong {time.time()-t0:.1f}s | GPU alloc: {torch.cuda.memory_allocated()/1e6:.0f}MB / reserved: {torch.cuda.memory_reserved()/1e6:.0f}MB")

t0 = time.time()
v = mc.encode(["a person riding a bicycle", "tin tuc thoi su buoi toi"])
print(f"encode 2 cau: {time.time()-t0:.2f}s, shape={v.shape}, norm={(v**2).sum(-1)**0.5}")
print("OK")
