"""
Nạp OCR + object + caption (theo từng keyframe) + ASR (theo từng video) từ
aic-system/artifacts/ vào Meilisearch — THAY load_to_es.py (Elasticsearch cần
heap JVM 1-2GB, nặng cho máy dev; xem core/repositories/meili_repo.py).

Khác load_to_es.py 1 chỗ: field `objects` không còn ghép token "cls_grid_color"
làm 1 từ (đó là workaround cho ES whitespace-analyzer) — ở đây lưu 3 phần
cls/grid/color là CÁC TỪ RIÊNG trong field, search từ thường là đủ nhờ tokenizer
từ-thật của Meilisearch (không cần wildcard).

Chạy: pip install meilisearch
      docker run -d -p 7700:7700 -v <dir>:/meili_data getmeili/meilisearch:v1.11
      python aic-system/indexing/build_meili.py
"""
import glob
import json
import time
from pathlib import Path

import meilisearch

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
MEILI_URL = "http://localhost:7700"
MEILI_KEY = ""


def build_frames():
    """Gộp ocr + caption + objects theo (video,n). Giống hệt logic load_to_es.py."""
    frames = {}
    print("  đọc OCR...")
    for fp in glob.glob(str(ARTIFACTS / "ocr" / "ocr_[1-9]*.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                key = (d["video"], d["n"])
                # "_mid" = primary key Meilisearch (chỉ chữ/số/-/_ — không được dùng
                # ":" như "id" thật). "id" giữ định dạng "{video}:{n:06d}" GIỐNG HỆT
                # id bên FAISS để core.fusion.rrf() khớp đúng document giữa các nhánh.
                frames[key] = {"_mid": f"{d['video']}_{d['n']:06d}", "id": f"{d['video']}:{d['n']:06d}",
                               "video": d["video"], "n": d["n"],
                               "frame_idx": d["frame_idx"], "ocr_text": d.get("texts", ""),
                               "caption": "", "objects": ""}
    print(f"  --> {len(frames):,} frame từ OCR (đã dedup sẵn)")

    print("  đọc caption (dedup: giữ bản đầu tiên)...")
    n_cap_dup = 0
    for fp in sorted(glob.glob(str(ARTIFACTS / "caption" / "captions_*.jsonl"))):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                key = (d["video"], d["n"])
                if key not in frames:
                    continue
                if frames[key]["caption"]:
                    n_cap_dup += 1
                    continue
                frames[key]["caption"] = d.get("cap", "")
    print(f"  --> bỏ qua {n_cap_dup:,} dòng caption trùng (L25_a1/L25_b)")

    print("  đọc objects (dedup: giữ bản đầu tiên; lưu cls/grid/color CÁCH TỪ RIÊNG)...")
    n_obj_dup = 0
    with open(ARTIFACTS / "objects" / "objects_all.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            key = (d["video"], d["n"])
            if key not in frames:
                continue
            if frames[key]["objects"]:
                n_obj_dup += 1
                continue
            words = []
            for o in d.get("objects", []):
                words += [o["cls"].replace(" ", "-"), o["grid"], o["color"]]
            frames[key]["objects"] = " ".join(words)
    print(f"  --> bỏ qua {n_obj_dup:,} dòng objects trùng (L25_a1/L25_b)")

    return list(frames.values())


def build_asr():
    """Đọc 3 file asr_all.jsonl, dedup theo VIDEO (giữ bản đầu tiên)."""
    seen_videos = set()
    docs = []
    n_dup = 0
    for i in (1, 2, 3):
        fp = ARTIFACTS / f"asr_{i}" / "asr_all.jsonl"
        if not fp.exists():
            continue
        with open(fp, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                video = d["video"]
                if video in seen_videos:
                    n_dup += 1
                    continue
                seen_videos.add(video)
                for seg in d.get("segments", []):
                    # _mid chỉ cần DUY NHẤT, không cần đọc lại ở đâu khác (asr trả
                    # (video,start,end,score) trực tiếp, không qua id) -> dùng số thứ
                    # tự toàn cục, tránh mọi vấn đề ký tự không hợp lệ (":", ".").
                    docs.append({"_mid": len(docs), "video": video,
                                 "start": seg["s"], "end": seg["e"], "text": seg["t"]})
    print(f"  --> {len(seen_videos):,} video ASR (bỏ {n_dup} video trùng L25_a1/L25_b), "
          f"{len(docs):,} đoạn ASR")
    return docs


def wait_task(client, task_info):
    """Chờ task xong VÀ kiểm tra status — Meilisearch KHÔNG raise exception khi 1
    task fail (vd document identifier không hợp lệ), chỉ trả status="failed" trong
    kết quả -> phải tự kiểm tra, nếu không sẽ ngỡ thành công trong khi 0 dòng được
    nạp (đã gặp thật lúc build lần đầu — id "video:n" có dấu ":" bị Meilisearch từ chối)."""
    task = client.wait_for_task(task_info.task_uid, timeout_in_ms=600_000)
    if task.status == "failed":
        raise RuntimeError(f"Meilisearch task {task_info.task_uid} THẤT BẠI: {task.error}")
    return task


def main():
    client = meilisearch.Client(MEILI_URL, MEILI_KEY or None)
    print("Meilisearch health:", client.health())

    print("=" * 60, "\n[1/4] Gom dữ liệu frame (OCR+caption+objects)\n", "=" * 60)
    frame_docs = build_frames()

    print("=" * 60, "\n[2/4] Gom dữ liệu ASR\n", "=" * 60)
    asr_docs = build_asr()

    print("=" * 60, "\n[3/4] Tạo index + cấu hình\n", "=" * 60)
    for name in ("aic_frames", "aic_asr"):
        try:
            wait_task(client, client.delete_index(name))
        except Exception:
            pass
    wait_task(client, client.create_index("aic_frames", {"primaryKey": "_mid"}))
    wait_task(client, client.create_index("aic_asr", {"primaryKey": "_mid"}))

    frames_idx = client.index("aic_frames")
    # `id`/`n` filterable: cần cho get_frame_docs() (lấy caption/OCR của đúng 1 tập
    # khung hình để hiện nội dung cạnh kết quả) và all_ocr_for_video() (Workbench).
    wait_task(client, frames_idx.update_filterable_attributes(["video", "id", "n"]))
    wait_task(client, frames_idx.update_searchable_attributes(["ocr_text", "caption", "objects"]))

    asr_idx = client.index("aic_asr")
    # `start`/`end` filterable: cần cho asr_segments_for_video() (lời thoại quanh
    # 1 khung hình) và all_asr_for_video() (transcript đầy đủ trong Workbench).
    wait_task(client, asr_idx.update_filterable_attributes(["video", "start", "end"]))
    wait_task(client, asr_idx.update_searchable_attributes(["text"]))

    print("=" * 60, "\n[4/4] Bulk index (batch 5000)\n", "=" * 60)
    t0 = time.time()
    BATCH = 5000
    for bi in range(0, len(frame_docs), BATCH):
        wait_task(client, frames_idx.add_documents(frame_docs[bi:bi + BATCH]))
        print(f"  aic_frames: {min(bi+BATCH, len(frame_docs)):,}/{len(frame_docs):,}", end="\r")
    print(f"\n  --> nạp {len(frame_docs):,} doc vào 'aic_frames' ({time.time()-t0:.1f}s)")

    t0 = time.time()
    for bi in range(0, len(asr_docs), BATCH):
        wait_task(client, asr_idx.add_documents(asr_docs[bi:bi + BATCH]))
        print(f"  aic_asr: {min(bi+BATCH, len(asr_docs)):,}/{len(asr_docs):,}", end="\r")
    print(f"\n  --> nạp {len(asr_docs):,} doc vào 'aic_asr' ({time.time()-t0:.1f}s)")

    print("\n>>> XONG.")


if __name__ == "__main__":
    main()
