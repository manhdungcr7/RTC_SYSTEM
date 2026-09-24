"""Merge the published Batch 2 MetaCLIP vectors into the existing RTC FAISS branch.

Builds in a separate directory. It never modifies the live index; deploy the
validated pair of index.faiss/meta.parquet only after the build succeeds.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import faiss
import numpy as np
import pandas as pd


def build(old_dir: Path, batch_dir: Path, out_dir: Path, chunk_size: int = 8192) -> None:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {out_dir}")

    info = json.loads((batch_dir / "emb_info.json").read_text(encoding="utf-8"))
    if info.get("model_id") != "facebook/metaclip-2-worldwide-huge-378":
        raise ValueError(f"Unexpected model: {info.get('model_id')}")

    old_meta = pd.read_parquet(old_dir / "meta.parquet")
    old_index = faiss.read_index(str(old_dir / "index.faiss"))
    if old_index.ntotal != len(old_meta):
        raise ValueError("Existing FAISS index and metadata have different row counts")

    batch_meta = pd.read_parquet(batch_dir / "feat_index.parquet")
    required = {"video", "n", "frame_idx"}
    if not required.issubset(batch_meta.columns):
        raise ValueError(f"Batch metadata lacks columns: {required - set(batch_meta.columns)}")
    vectors = np.load(batch_dir / "feat_metaclip2.npy", mmap_mode="r", allow_pickle=False)
    if vectors.ndim != 2 or vectors.dtype != np.float16:
        raise ValueError(f"Unexpected vector format: {vectors.shape}, {vectors.dtype}")
    if vectors.shape != (len(batch_meta), old_index.d):
        raise ValueError("Batch vector rows/dimension do not match metadata and existing index")
    if len(batch_meta) != int(info["rows"]) or vectors.shape[1] != int(info["feature_dim"]):
        raise ValueError("Batch arrays disagree with emb_info.json")
    if batch_meta["video"].isna().any() or batch_meta["n"].isna().any():
        raise ValueError("Batch metadata contains empty video/n")
    if (batch_meta["n"] < 1).any() or (batch_meta["frame_idx"] < 0).any():
        raise ValueError("Batch metadata has invalid n/frame_idx")
    if batch_meta.duplicated(["video", "n"]).any():
        raise ValueError("Batch metadata has duplicate video/n pairs")
    if not batch_meta[["video", "n"]].equals(
        batch_meta[["video", "n"]].sort_values(["video", "n"]).reset_index(drop=True)
    ):
        raise ValueError("Batch metadata is not sorted by video/n")
    if set(batch_meta["video"]) & set(old_meta["video"]):
        raise ValueError("Batch video names overlap the existing index; refusing to append")

    out_dir.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(vectors), chunk_size):
        end = min(start + chunk_size, len(vectors))
        chunk = np.ascontiguousarray(vectors[start:end], dtype=np.float32)
        if not np.isfinite(chunk).all():
            raise ValueError(f"Non-finite vector in rows {start}:{end}")
        norms = np.linalg.norm(chunk, axis=1)
        if (norms < 0.9).any() or (norms > 1.1).any():
            raise ValueError(f"Unexpected vector norm in rows {start}:{end}")
        faiss.normalize_L2(chunk)
        old_index.add(chunk)
        if end == len(vectors) or end % (chunk_size * 8) == 0:
            print(f"INDEXED {end}/{len(vectors)}", flush=True)

    if old_index.ntotal != len(old_meta) + len(batch_meta):
        raise ValueError("Final index row count is wrong")
    added = batch_meta[["video", "n", "frame_idx"]].copy()
    added.insert(0, "id", added["video"] + ":" + added["n"].map(lambda n: f"{n:06d}"))
    merged_meta = pd.concat([old_meta, added], ignore_index=True)
    if merged_meta["id"].duplicated().any():
        raise ValueError("Merged index has duplicate document IDs")

    faiss.write_index(old_index, str(out_dir / "index.faiss"))
    merged_meta.to_parquet(out_dir / "meta.parquet", index=False)
    del old_index

    check_index = faiss.read_index(str(out_dir / "index.faiss"), faiss.IO_FLAG_MMAP | faiss.IO_FLAG_READ_ONLY)
    check_meta = pd.read_parquet(out_dir / "meta.parquet")
    if check_index.ntotal != len(check_meta) or check_index.d != int(info["feature_dim"]):
        raise ValueError("Written index failed readback validation")
    print(
        f"BUILT rows={check_index.ntotal} videos={check_meta.video.nunique()} "
        f"dim={check_index.d} output={out_dir}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build(args.old, args.batch, args.out)
