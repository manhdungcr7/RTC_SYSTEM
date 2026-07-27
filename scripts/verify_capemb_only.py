import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

t0 = time.time()
from core.query_encoders import CapEmbEncoder
ce = CapEmbEncoder()
print(f"nap xong {time.time()-t0:.1f}s")

t0 = time.time()
v = ce.encode(["mot nguoi dang di xe dap tren duong", "tin tuc thoi su buoi toi"])
print(f"encode 2 cau: {time.time()-t0:.2f}s, shape={v.shape}")
print("OK")
