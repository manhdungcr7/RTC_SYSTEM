"""
Nap OCR + object + caption (theo tung keyframe) va ASR (theo tung video) tu
aic-system/artifacts/ vao Elasticsearch (docker-compose o aic-system/docker/).

2 index:
  aic_frames  — 1 doc / (video,n): ocr_text (ngram fuzzy), caption (text thuong),
                objects (token VISIONE-style "cls_grid_color")
  aic_asr     — 1 doc / doan ASR: video, start, end, text (ngram fuzzy). KHONG gop
                san vao tung frame (frame-align ±2s de o tang query-time, linh hoat
                hon la bake cung 1 cua so co dinh luc index).

DEDUP: L25_a1/L25_b la ban sao 100% cua L25_a (video, khong phai frame nhu Milvus) —
giu ban ghi DAU TIEN gap, bo cac ban sau cho cung (video,n) [frames] / video [asr].

Chay: pip install elasticsearch
      docker compose -f aic-system/docker/docker-compose.yml up -d
      python aic-system/indexing/load_to_es.py
"""
import glob
import json
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

ARTIFACTS = Path("F:/AI_Challenge_Video_Image_Retrieval/aic-system/artifacts")
ES_URL = "http://localhost:9200"

NGRAM_ANALYZER = {
    "analysis": {
        "analyzer": {"ngram_analyzer": {"type": "custom", "tokenizer": "ngram_tokenizer",
                                         "filter": ["lowercase"]}},
        "tokenizer": {"ngram_tokenizer": {"type": "ngram", "min_gram": 2, "max_gram": 5,
                                           "token_chars": ["letter", "digit"]}},
    },
    "max_ngram_diff": 5,
}

FRAMES_MAPPING = {
    "properties": {
        "video": {"type": "keyword"},
        "n": {"type": "integer"},
        "frame_idx": {"type": "integer"},
        "ocr_text": {"type": "text", "analyzer": "ngram_analyzer", "search_analyzer": "standard"},
        "caption": {"type": "text"},
        "objects": {"type": "text", "analyzer": "whitespace"},
    }
}

ASR_MAPPING = {
    "properties": {
        "video": {"type": "keyword"},
        "start": {"type": "float"},
        "end": {"type": "float"},
        "text": {"type": "text", "analyzer": "ngram_analyzer", "search_analyzer": "standard"},
    }
}


def build_frames():
    """Gop ocr + caption + objects theo (video,n). OCR da dedup san (khong co
    L25_a1/L25_b tu dau) -> dung OCR lam nguon frame_idx/danh sach key goc.
    Caption/objects dedup bang cach GIU ban dau tien gap cho moi key."""
    frames = {}
    print("  doc OCR...")
    for fp in glob.glob(str(ARTIFACTS / "ocr" / "ocr_[1-9]*.jsonl")):  # chi khop ocr_1..N.jsonl, tranh file la nhu ocr_fixed.jsonl
        with open(fp, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                key = (d["video"], d["n"])
                frames[key] = {"video": d["video"], "n": d["n"], "frame_idx": d["frame_idx"],
                                "ocr_text": d.get("texts", ""), "caption": "", "objects": ""}
    print(f"  --> {len(frames):,} frame tu OCR (da dedup san)")

    print("  doc caption (dedup: giu ban dau tien)...")
    n_cap_dup = 0
    for fp in sorted(glob.glob(str(ARTIFACTS / "caption" / "captions_*.jsonl"))):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                key = (d["video"], d["n"])
                if key not in frames:
                    continue  # ngoai 167,850 key OCR (khong nen xay ra, phong ho)
                if frames[key]["caption"]:
                    n_cap_dup += 1
                    continue
                frames[key]["caption"] = d.get("cap", "")
    print(f"  --> bo qua {n_cap_dup:,} dong caption trung (L25_a1/L25_b)")

    print("  doc objects (dedup: giu ban dau tien)...")
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
            tokens = [f"{o['cls']}_{o['grid']}_{o['color']}".replace(" ", "-") for o in d.get("objects", [])]
            frames[key]["objects"] = " ".join(tokens)
    print(f"  --> bo qua {n_obj_dup:,} dong objects trung (L25_a1/L25_b)")

    return list(frames.values())


def build_asr():
    """Doc 3 file asr_all.jsonl, dedup theo VIDEO (giu ban dau tien), tach thanh
    danh sach doc segment (video,start,end,text)."""
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
                    docs.append({"video": video, "start": seg["s"], "end": seg["e"], "text": seg["t"]})
    print(f"  --> {len(seen_videos):,} video ASR (bo {n_dup} video trung L25_a1/L25_b), "
          f"{len(docs):,} doan ASR")
    return docs


def recreate_index(es, name, mapping, settings=None):
    if es.indices.exists(index=name):
        es.indices.delete(index=name)
    body = {"mappings": mapping}
    if settings:
        body["settings"] = settings
    es.indices.create(index=name, body=body)


def bulk_index(es, index_name, docs, id_fn):
    actions = ({"_index": index_name, "_id": id_fn(d), "_source": d} for d in docs)
    ok, errors = helpers.bulk(es, actions, chunk_size=2000, request_timeout=120)
    if errors:
        print(f"  !!! {len(errors)} loi khi bulk index vao {index_name}")
    print(f"  --> nap {ok:,} doc vao '{index_name}'")


def main():
    es = Elasticsearch(ES_URL)
    print(f"ES ping: {es.ping()}")

    print("=" * 60, "\n[1/4] Gom du lieu frame (OCR+caption+objects)\n", "=" * 60)
    frame_docs = build_frames()

    print("=" * 60, "\n[2/4] Gom du lieu ASR\n", "=" * 60)
    asr_docs = build_asr()

    print("=" * 60, "\n[3/4] Tao index\n", "=" * 60)
    recreate_index(es, "aic_frames", FRAMES_MAPPING, NGRAM_ANALYZER)
    recreate_index(es, "aic_asr", ASR_MAPPING, NGRAM_ANALYZER)

    print("=" * 60, "\n[4/4] Bulk index\n", "=" * 60)
    bulk_index(es, "aic_frames", frame_docs, lambda d: f"{d['video']}:{d['n']:06d}")
    bulk_index(es, "aic_asr", asr_docs, lambda d: f"{d['video']}:{d['start']}:{d['end']}")

    print("\n>>> XONG.")


if __name__ == "__main__":
    main()
