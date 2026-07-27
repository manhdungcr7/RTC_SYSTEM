"""
Nap 4 nhanh embedding (MetaCLIP-2, BEiT-3, DINOv3, PE-Core) + capemb tu
aic-system/artifacts/ vao Milvus (docker-compose o aic-system/docker/). Moi nhanh
= 1 collection rieng.

DEDUP: L25_a1/L25_b la BAN SAO 100% cua L25_a (da xac nhan frame_idx khop tuyet doi
tung (video,n) — TransNetV2 chay deterministic). Script nay GIU dong dau tien, BO
dong trung, dua tren feat_index.parquet (khong dua tren video prefix, vi frame khong
trung giua cac video khac nhau).

RESUME-SAFE (may 15GB RAM tung OOM giua chung nhieu lan khi insert):
  - Nhanh da nap DU (flush roi dem lai cho chinh xac) -> BO QUA, khong lam lai.
  - capemb (dim 2560, nang nhat, hay OOM nhat): neu dang co san 1 phan -> chi
    insert PHAN CON THIEU (query id da co, tru di), khong insert lai tu dau.

Chay: python aic-system/indexing/load_to_milvus.py
Yeu cau: pip install pymilvus ; docker compose -f aic-system/docker/docker-compose.yml up -d
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pymilvus import MilvusClient, DataType

ARTIFACTS = Path("F:/AI_Challenge_Video_Image_Retrieval/aic-system/artifacts")
MILVUS_URI = "http://localhost:19530"

# (thu_muc_artifact, ten_file_npy, ten_collection, mo_ta)
BRANCHES = [
    ("emb", "feat_metaclip2.npy", "metaclip2", "nhanh CHINH (da ngu, khong dich)"),
    ("emb_beit3", "feat_beit3.npy", "beit3", "ensemble, loi cho QA"),
    ("emb_dinov3", "feat_dinov3.npy", "dinov3", "tim anh giong (image-similarity)"),  # da sua fp32, sach NaN
    ("emb_pecore", "feat_pecore.npy", "pecore", "nhanh CHI TIET (PE-Core-L14-336)"),
]


def load_dedup_mask(index_paths):
    """Doc feat_index.parquet cua nhanh dau tien, tra ve (keep_positions, index_dedup).
    Kiem tra CHEO tat ca cac nhanh con lai co CUNG thu tu (video,n) truoc khi tai su
    dung chung 1 mask — khong gia dinh mu."""
    ref_df = pd.read_parquet(index_paths[0])
    for p in index_paths[1:]:
        df = pd.read_parquet(p)
        if not (df["video"].values == ref_df["video"].values).all() or \
           not (df["n"].values == ref_df["n"].values).all():
            raise RuntimeError(
                f"LOI: {p} co thu tu (video,n) KHAC voi {index_paths[0]} — "
                f"KHONG the dung chung 1 mask dedup. Can xu ly rieng tung nhanh.")
    print(f"  --> {len(index_paths)} feat_index.parquet cung thu tu, dung chung 1 mask dedup.")

    dup_mask = ref_df.duplicated(subset=["video", "n"], keep="first")
    keep_positions = np.where(~dup_mask.values)[0]
    index_dedup = ref_df.iloc[keep_positions].reset_index(drop=True)
    print(f"  --> {len(ref_df):,} dong goc -> {len(index_dedup):,} dong sau dedup "
          f"(bo {dup_mask.sum():,} dong trung L25_a1/L25_b)")
    return keep_positions, index_dedup


def flushed_count(client, coll_name):
    """So dong THAT SU (sau flush) — get_collection_stats co the bao so cu/lag neu
    chua flush, tung gay hieu lam 'nap thieu' trong khi thuc ra da du."""
    if not client.has_collection(coll_name):
        return 0
    client.flush(coll_name)
    return int(client.get_collection_stats(coll_name)["row_count"])


def main():
    index_paths = [ARTIFACTS / d / "feat_index.parquet" for d, _, _, _ in BRANCHES]
    print("=" * 60, "\n[1/3] Tinh dedup mask (dung chung cho ca 4 nhanh)\n", "=" * 60)
    keep_positions, index_dedup = load_dedup_mask(index_paths)
    n_orig = pd.read_parquet(index_paths[0]).shape[0]
    n_expected = len(index_dedup)

    ids = [f"{v}:{n:06d}" for v, n in zip(index_dedup["video"], index_dedup["n"])]
    videos = index_dedup["video"].tolist()
    ns = index_dedup["n"].astype(int).tolist()
    frame_idxs = index_dedup["frame_idx"].astype(int).tolist()

    print("=" * 60, "\n[2/3] Ket noi Milvus\n", "=" * 60)
    client = MilvusClient(uri=MILVUS_URI)
    print(f"  --> ket noi {MILVUS_URI} OK")

    print("=" * 60, "\n[3/3] Nap tung nhanh\n", "=" * 60)
    for artifact_dir, npy_name, coll_name, desc in BRANCHES:
        print(f"\n--- {coll_name} ({desc}) ---")

        n_have = flushed_count(client, coll_name)
        if n_have == n_expected:
            print(f"  --> da co du {n_have:,} dong -> BO QUA (khong lam lai).")
            continue

        npy_path = ARTIFACTS / artifact_dir / npy_name
        info = json.load(open(ARTIFACTS / artifact_dir / "emb_info.json", encoding="utf-8"))
        dim = info["dim"]

        vecs_all = np.load(npy_path)
        assert vecs_all.shape[0] == n_orig, \
            f"{npy_path}: {vecs_all.shape[0]} dong nhung feat_index goc co {n_orig} dong"
        vecs = vecs_all[keep_positions].astype(np.float32)  # milvus can float32 cho vector insert
        print(f"  {npy_path.name}: {vecs_all.shape} -> dedup {vecs.shape} (hien co {n_have:,}, se lam lai tu dau)")

        if client.has_collection(coll_name):
            print(f"  collection '{coll_name}' co {n_have:,}/{n_expected:,} (khong khop) -> xoa lam lai")
            client.drop_collection(coll_name)

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=32)
        schema.add_field("video", DataType.VARCHAR, max_length=32)
        schema.add_field("n", DataType.INT64)
        schema.add_field("frame_idx", DataType.INT64)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)

        index_params = client.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="HNSW", metric_type="COSINE",
                                params={"M": 16, "efConstruction": 200})

        client.create_collection(coll_name, schema=schema, index_params=index_params)

        BATCH = 1000  # ha tu 5000 — may chi co 15GB RAM, tung OOM ("Cannot allocate memory") o batch lon
        n_total = len(ids)
        for bi in range(0, n_total, BATCH):
            rows = [
                {"id": ids[i], "video": videos[i], "n": ns[i], "frame_idx": frame_idxs[i],
                 "vector": vecs[i]}
                for i in range(bi, min(bi + BATCH, n_total))
            ]
            client.insert(coll_name, rows)
            print(f"  insert {min(bi+BATCH, n_total):,}/{n_total:,}", end="\r")
        print(f"\n  --> '{coll_name}': {n_total:,} vector da nap.")

    # ==================== capemb (rieng: dim khac, khong co frame_idx san) ====================
    print("=" * 60, "\n[capemb] Nap rieng — RESUME-SAFE (chi insert phan con thieu)\n", "=" * 60)
    cap_dir = ARTIFACTS / "cap_emb"
    cap_vecs = np.load(cap_dir / "feat_capemb.npy").astype(np.float32)
    cap_index = pd.read_parquet(cap_dir / "feat_index.parquet")  # chi co video,n
    cap_info = json.load(open(cap_dir / "cap_emb_info.json", encoding="utf-8"))
    assert cap_vecs.shape[0] == len(cap_index), "feat_capemb.npy va feat_index.parquet lech dong"
    assert not cap_index.duplicated(subset=["video", "n"]).any(), "cap_emb index co key trung"

    # join frame_idx tu index_dedup (nguon tham chieu) theo (video,n) — KHONG gia dinh
    # cung thu tu, vi cap_emb sinh doc lap tren Kaggle khac.
    cap_index = cap_index.reset_index().rename(columns={"index": "pos"})
    joined = cap_index.merge(index_dedup[["video", "n", "frame_idx"]], on=["video", "n"], how="left")
    n_missing_key = joined["frame_idx"].isna().sum()
    if n_missing_key:
        print(f"  !!! CANH BAO: {n_missing_key} dong cap_emb khong khop key voi index chinh — bo qua.")
        joined = joined.dropna(subset=["frame_idx"])
    joined["id"] = [f"{r.video}:{int(r.n):06d}" for r in joined.itertuples()]

    coll_name, dim = "capemb", cap_info["dim"]
    n_expected_cap = len(joined)
    n_have = flushed_count(client, coll_name)

    if n_have == n_expected_cap:
        print(f"  --> capemb da co du {n_have:,} dong -> BO QUA.")
    else:
        if n_have == 0:
            print(f"  --> capemb chua co gi, tao collection moi.")
            schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=32)
            schema.add_field("video", DataType.VARCHAR, max_length=32)
            schema.add_field("n", DataType.INT64)
            schema.add_field("frame_idx", DataType.INT64)
            schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
            index_params = client.prepare_index_params()
            index_params.add_index(field_name="vector", index_type="HNSW", metric_type="COSINE",
                                    params={"M": 16, "efConstruction": 200})
            client.create_collection(coll_name, schema=schema, index_params=index_params)
            todo = joined
        else:
            print(f"  --> capemb da co {n_have:,}/{n_expected_cap:,} — truy van id da co de CHI insert phan thieu.")
            existing_ids = set()
            it = client.query_iterator(coll_name, output_fields=["id"], batch_size=5000)
            while True:
                batch = it.next()
                if not batch:
                    break
                existing_ids.update(d["id"] for d in batch)
            it.close()
            print(f"  --> da tim thay {len(existing_ids):,} id co san trong Milvus.")
            todo = joined[~joined["id"].isin(existing_ids)]
            print(f"  --> con thieu {len(todo):,} dong, se insert tiep (khong lam lai tu dau).")

        BATCH = 500  # capemb dim=2560 (nang hon 4 nhanh kia) — ha manh hon de tranh OOM
        n_total = len(todo)
        for bi in range(0, n_total, BATCH):
            chunk = todo.iloc[bi:bi + BATCH]
            rows = [
                {"id": r.id, "video": r.video, "n": int(r.n),
                 "frame_idx": int(r.frame_idx), "vector": cap_vecs[int(r.pos)]}
                for r in chunk.itertuples()
            ]
            client.insert(coll_name, rows)
            print(f"  insert {min(bi+BATCH, n_total):,}/{n_total:,}", end="\r")
        print(f"\n  --> 'capemb': +{n_total:,} vector moi da nap (tong nen la {n_expected_cap:,}).")

    print("\n>>> XONG. Xem qua Attu UI: http://localhost:8000 (dang tat de do RAM — bat lai bang "
          "'docker compose start attu' khi can xem).")


if __name__ == "__main__":
    main()
