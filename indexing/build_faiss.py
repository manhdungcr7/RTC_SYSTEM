"""
Build FAISS index cho 5 nhánh (metaclip2, beit3, dinov3, pecore, capemb) từ
aic-system/artifacts/ — THAY load_to_milvus.py (Milvus quá nặng RAM cho máy dev,
xem core/repositories/faiss_repo.py). Output: aic-system/docker/volumes/faiss/
<branch>/{index.faiss, meta.parquet} — bind-mount thẳng vào backend container,
KHÔNG cần server riêng.

+ 1 nhánh TÙY CHỌN "asr_emb" (semantic ASR — xem core/asr_align.py,
indexing/kaggle/12_asr_embed.py) nếu artifacts/asr_emb/ đã có dữ liệu, bỏ qua
êm nếu chưa (không chặn build 5 nhánh chính).

DEDUP: giống hệt load_to_milvus.py — L25_a1/L25_b là bản sao 100% của L25_a
(TransNetV2 chạy deterministic nên frame_idx khớp tuyệt đối), giữ dòng đầu tiên,
bỏ dòng trùng dựa trên feat_index.parquet.

Chạy: python aic-system/indexing/build_faiss.py
"""
import json
from pathlib import Path

import faiss
import numpy as np
import pandas as pd

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
OUT_DIR = Path(__file__).resolve().parents[1] / "docker" / "volumes" / "faiss"

BRANCHES = [
    ("emb", "feat_metaclip2.npy", "metaclip2", "nhánh CHÍNH (đa ngữ, không dịch)"),
    ("emb_beit3", "feat_beit3.npy", "beit3", "ensemble, lợi cho QA"),
    ("emb_dinov3", "feat_dinov3.npy", "dinov3", "tìm ảnh giống (image-similarity)"),
    ("emb_pecore", "feat_pecore.npy", "pecore", "nhánh CHI TIẾT (PE-Core-L14-336)"),
]


def load_dedup_mask(index_paths: list[Path]) -> tuple[np.ndarray, pd.DataFrame]:
    ref_df = pd.read_parquet(index_paths[0])
    for p in index_paths[1:]:
        df = pd.read_parquet(p)
        if not (df["video"].values == ref_df["video"].values).all() or \
           not (df["n"].values == ref_df["n"].values).all():
            raise RuntimeError(f"LỖI: {p} có thứ tự (video,n) KHÁC {index_paths[0]}")
    dup_mask = ref_df.duplicated(subset=["video", "n"], keep="first")
    keep_positions = np.where(~dup_mask.values)[0]
    index_dedup = ref_df.iloc[keep_positions].reset_index(drop=True)
    print(f"  --> {len(ref_df):,} dòng gốc -> {len(index_dedup):,} dòng sau dedup "
          f"(bỏ {dup_mask.sum():,} dòng trùng L25_a1/L25_b)")
    return keep_positions, index_dedup


def write_branch(branch: str, ids: list[str], videos: list[str], ns: list[int],
                  frame_idxs: list[int], vecs: np.ndarray, extra_cols: dict | None = None):
    out_dir = OUT_DIR / branch
    out_dir.mkdir(parents=True, exist_ok=True)

    vecs = np.ascontiguousarray(vecs, dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms   # đảm bảo unit-norm -> IndexFlatIP (inner product) == cosine

    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, str(out_dir / "index.faiss"))

    meta = pd.DataFrame({"id": ids, "video": videos, "n": ns, "frame_idx": frame_idxs})
    if extra_cols:
        for col, vals in extra_cols.items():
            meta[col] = vals
    meta.to_parquet(out_dir / "meta.parquet", index=False)
    print(f"  --> '{branch}': {index.ntotal:,} vector, dim={vecs.shape[1]} -> {out_dir}")


def main():
    index_paths = [ARTIFACTS / d / "feat_index.parquet" for d, _, _, _ in BRANCHES]
    print("=" * 60, "\n[1/3] Tính dedup mask (dùng chung cho 4 nhánh embedding ảnh)\n", "=" * 60)
    keep_positions, index_dedup = load_dedup_mask(index_paths)
    n_orig = pd.read_parquet(index_paths[0]).shape[0]

    ids = [f"{v}:{n:06d}" for v, n in zip(index_dedup["video"], index_dedup["n"])]
    videos = index_dedup["video"].tolist()
    ns = index_dedup["n"].astype(int).tolist()
    frame_idxs = index_dedup["frame_idx"].astype(int).tolist()

    print("=" * 60, "\n[2/3] Build từng nhánh embedding ảnh\n", "=" * 60)
    for artifact_dir, npy_name, branch, desc in BRANCHES:
        print(f"\n--- {branch} ({desc}) ---")
        npy_path = ARTIFACTS / artifact_dir / npy_name
        vecs_all = np.load(npy_path)
        assert vecs_all.shape[0] == n_orig, \
            f"{npy_path}: {vecs_all.shape[0]} dòng nhưng feat_index gốc có {n_orig} dòng"
        vecs = vecs_all[keep_positions]
        write_branch(branch, ids, videos, ns, frame_idxs, vecs)

    print("=" * 60, "\n[3/3] Build capemb (riêng: dim khác, tự join theo video,n)\n", "=" * 60)
    cap_dir = ARTIFACTS / "cap_emb"
    cap_vecs = np.load(cap_dir / "feat_capemb.npy")
    cap_index = pd.read_parquet(cap_dir / "feat_index.parquet")
    assert cap_vecs.shape[0] == len(cap_index), "feat_capemb.npy và feat_index.parquet lệch dòng"
    assert not cap_index.duplicated(subset=["video", "n"]).any(), "cap_emb index có key trùng"

    cap_index = cap_index.reset_index().rename(columns={"index": "pos"})
    joined = cap_index.merge(index_dedup[["video", "n", "frame_idx"]], on=["video", "n"], how="left")
    n_missing = joined["frame_idx"].isna().sum()
    if n_missing:
        print(f"  !!! CẢNH BÁO: {n_missing} dòng cap_emb không khớp key với index chính — bỏ qua.")
        joined = joined.dropna(subset=["frame_idx"])

    cap_ids = [f"{r.video}:{int(r.n):06d}" for r in joined.itertuples()]
    cap_vecs_dedup = cap_vecs[joined["pos"].values]
    write_branch("capemb", cap_ids, joined["video"].tolist(), joined["n"].astype(int).tolist(),
                 joined["frame_idx"].astype(int).tolist(), cap_vecs_dedup)

    print("=" * 60, "\n[4/4] Build asr_emb (TÙY CHỌN — semantic ASR, xem asr_align.py)\n", "=" * 60)
    asr_dir = ARTIFACTS / "asr_emb"
    asr_npy = asr_dir / "feat_asremb.npy"
    asr_idx_path = asr_dir / "feat_index.parquet"
    if not asr_npy.exists() or not asr_idx_path.exists():
        print(f"  --> bỏ qua: chưa có {asr_npy} (chạy indexing/kaggle/12_asr_embed.py trước).")
    else:
        asr_vecs = np.load(asr_npy)
        asr_index = pd.read_parquet(asr_idx_path)   # cột: video, seg_idx, start, end
        assert asr_vecs.shape[0] == len(asr_index), "feat_asremb.npy và feat_index.parquet lệch dòng"
        asr_ids = [f"{r.video}:seg{int(r.seg_idx):05d}" for r in asr_index.itertuples()]
        n_dummy = [-1] * len(asr_index)   # ASR segment KHÔNG map 1:1 keyframe -> không có n/frame_idx
        write_branch("asr_emb", asr_ids, asr_index["video"].tolist(), n_dummy, n_dummy, asr_vecs,
                     extra_cols={"start": asr_index["start"].astype(float).tolist(),
                                 "end": asr_index["end"].astype(float).tolist()})

    print("\n>>> XONG. Index nằm ở:", OUT_DIR)


if __name__ == "__main__":
    main()
