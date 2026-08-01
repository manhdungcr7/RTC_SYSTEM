"""
Build index Meilisearch `aic_videos` — LỌC VIDEO TRƯỚC (mục 3, tính năng "RAG
lọc video"). Gộp theo TỪNG VIDEO: toàn bộ transcript ASR + toàn bộ caption của
mọi keyframe + tiêu đề/kênh (metadata BTC) thành 1 document text lớn, cộng
`category` suy từ kênh YouTube (core.config.VIDEO_CATEGORY_MAP — BTC KHÔNG cung
cấp trường category tường minh, đã kiểm tra thật 873/873 file metadata).

Đây là bản KEYWORD (Meilisearch full-text, chạy được NGAY, không cần Kaggle).
Bản NGỮ NGHĨA thật (embedding, RAG đúng nghĩa) là bước NÂNG CẤP TÙY CHỌN — xem
indexing/kaggle/13_video_embed.py (encode Qwen3-Embedding-4B document-side, y
hệt pattern 10_cap_embed.py/12_asr_embed.py) — CHƯA bắt buộc, hệ thống dùng bản
keyword này trước.

Nguồn dữ liệu (đã có sẵn local, không cần tải thêm):
  artifacts/asr_1,2,3/asr_all.jsonl      — transcript ASR (dedup theo VIDEO)
  artifacts/caption/captions_*.jsonl     — caption từng keyframe (dedup theo video,n)
  artifacts/media_info/media-info/*.json — metadata BTC (author/title/...)

Chạy: python aic-system/indexing/build_video_index.py
"""
import glob
import json
from pathlib import Path

import meilisearch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import VIDEO_CATEGORY_MAP  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
MEILI_URL = "http://localhost:7700"
MEILI_KEY = ""


def load_media_info() -> dict[str, dict]:
    out = {}
    for fp in glob.glob(str(ARTIFACTS / "media_info" / "**" / "*.json"), recursive=True):
        video = Path(fp).stem
        with open(fp, encoding="utf-8") as f:
            out[video] = json.load(f)
    print(f"  --> {len(out):,} video có metadata BTC")
    return out


def load_asr_text() -> dict[str, str]:
    """Giống build_meili.py::build_asr() — dedup theo VIDEO, gộp text các đoạn."""
    seen_videos = set()
    out: dict[str, list[str]] = {}
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
                out[video] = [seg["t"] for seg in d.get("segments", [])]
    print(f"  --> {len(seen_videos):,} video có ASR (bỏ {n_dup} video trùng L25_a1/L25_b)")
    return {v: " ".join(texts) for v, texts in out.items()}


def load_caption_text() -> dict[str, str]:
    """Dedup theo (video,n) GIỐNG build_meili.py::build_frames() phần caption."""
    seen: set[tuple[str, int]] = set()
    out: dict[str, list[str]] = {}
    n_dup = 0
    for fp in sorted(glob.glob(str(ARTIFACTS / "caption" / "captions_*.jsonl"))):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                key = (d["video"], d["n"])
                if key in seen:
                    n_dup += 1
                    continue
                seen.add(key)
                out.setdefault(d["video"], []).append(d.get("cap", ""))
    print(f"  --> {len(out):,} video có caption (bỏ {n_dup:,} dòng trùng L25_a1/L25_b)")
    return {v: " ".join(caps) for v, caps in out.items()}


def wait_task(client, task_info):
    task = client.wait_for_task(task_info.task_uid, timeout_in_ms=600_000)
    if task.status == "failed":
        raise RuntimeError(f"Meilisearch task {task_info.task_uid} THẤT BẠI: {task.error}")
    return task


def main():
    print("=" * 60, "\n[1/4] Đọc metadata BTC (author/title -> category)\n", "=" * 60)
    media_info = load_media_info()

    print("=" * 60, "\n[2/4] Gộp ASR theo video\n", "=" * 60)
    asr_text = load_asr_text()

    print("=" * 60, "\n[3/4] Gộp caption theo video\n", "=" * 60)
    cap_text = load_caption_text()

    print("=" * 60, "\n[4/4] Build document + nạp Meilisearch\n", "=" * 60)
    all_videos = set(media_info) | set(asr_text) | set(cap_text)
    docs = []
    n_no_category = 0
    for video in sorted(all_videos):
        meta = media_info.get(video, {})
        author = meta.get("author", "")
        category = VIDEO_CATEGORY_MAP.get(author)
        if category is None:
            category = "Khác"
            n_no_category += 1
        title = meta.get("title", "")
        text = " ".join([title, asr_text.get(video, ""), cap_text.get(video, "")]).strip()
        docs.append({"video": video, "author": author, "category": category,
                      "title": title, "text": text})
    print(f"  --> {len(docs):,} video document ({n_no_category} không xác định được kênh -> 'Khác')")

    client = meilisearch.Client(MEILI_URL, MEILI_KEY or None)
    print("Meilisearch health:", client.health())
    try:
        wait_task(client, client.delete_index("aic_videos"))
    except Exception:
        pass
    wait_task(client, client.create_index("aic_videos", {"primaryKey": "video"}))
    idx = client.index("aic_videos")
    wait_task(client, idx.update_filterable_attributes(["category", "author"]))
    wait_task(client, idx.update_searchable_attributes(["title", "text"]))

    BATCH = 200
    for bi in range(0, len(docs), BATCH):
        wait_task(client, idx.add_documents(docs[bi:bi + BATCH]))
        print(f"  aic_videos: {min(bi+BATCH, len(docs))}/{len(docs)}", end="\r")
    print(f"\n  --> nạp {len(docs):,} doc vào 'aic_videos'")
    print("\n>>> XONG.")


if __name__ == "__main__":
    main()
