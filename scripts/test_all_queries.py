"""Chạy tất cả query trong queries/query-p1-groupA/ qua backend thật (đang chạy ở
:8080), in tóm tắt top kết quả + phát hiện lỗi. KHÔNG cần model (chỉ gọi HTTP)."""
import glob
import json
import re
import sys
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8080"
QDIR = Path("F:/AI_Challenge_Video_Image_Retrieval/queries/query-p1-groupA")

_EVENT_RE = re.compile(r"^\s*E(\d+)\s*[:.\-]\s*(.+)$", re.IGNORECASE)


def parse_trake(text: str):
    events, ctx = [], []
    for line in text.splitlines():
        m = _EVENT_RE.match(line)
        if m:
            events.append(m.group(2).strip())
        elif line.strip():
            ctx.append(line.strip())
    return " ".join(ctx), events


results = []
for fp in sorted(QDIR.glob("*.txt"), key=lambda p: (p.stem.split("-")[-1], int(p.stem.split("-")[2]))):
    name = fp.stem
    kind = name.rsplit("-", 1)[-1]
    text = fp.read_text(encoding="utf-8")
    print(f"\n{'='*70}\n{name} ({kind})\n{'='*70}")
    print(text[:200].replace("\n", " ") + ("..." if len(text) > 200 else ""))

    try:
        if kind == "trake":
            ctx, events = parse_trake(text)
            r = requests.post(f"{BASE}/temporal", json={
                "events": events, "context": ctx, "topk": 5, "per_event": 1500,
            }, timeout=120)
            r.raise_for_status()
            data = r.json()
            cands = data["candidates"]
            print(f"  -> {len(cands)} ứng viên. Top 3:")
            for c in cands[:3]:
                ns = [h["n"] for h in c["hits"]]
                print(f"     {c['video']} score={c['total_score']:.3f} frames(n)={ns}")
            results.append((name, kind, "OK", len(cands)))
        else:
            r = requests.post(f"{BASE}/search", json={
                "query": text.strip(), "kind": kind, "topk": 10, "use_expansion": True,
            }, timeout=120)
            r.raise_for_status()
            data = r.json()
            hits = data["hits"]
            print(f"  -> {len(hits)} kết quả. Top 5:")
            for h in hits[:5]:
                print(f"     {h['video']}:{h['n']:03d} score={h['score']:.4f}  {h['thumb_url']}")
            results.append((name, kind, "OK", len(hits)))
    except Exception as e:
        print(f"  !!! LOI: {type(e).__name__}: {e}")
        results.append((name, kind, f"ERROR: {type(e).__name__}", 0))

print(f"\n\n{'='*70}\nTOM TAT\n{'='*70}")
for name, kind, status, n in results:
    flag = "  <<<< LOI" if status != "OK" else ""
    print(f"  {name:28s} {kind:6s} {status:10s} n={n}{flag}")

n_err = sum(1 for _, _, s, _ in results if s != "OK")
print(f"\n{len(results)} query, {n_err} loi.")
