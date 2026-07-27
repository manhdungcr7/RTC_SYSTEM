"""
Gop file ocr_fixed.jsonl (tai ve tu 09c_fix_truncated_ocr.py) VAO 5 file
ocr_1..5.jsonl goc trong aic-system/artifacts/ocr/ — thay the dong cu (bi cat
cut o MAX_TOK=64) bang dong moi (MAX_TOK=200, day du hon).

Chay: python aic-system/indexing/merge_ocr_fix.py
"""
import json
import glob
from pathlib import Path

OCR_DIR = Path("F:/AI_Challenge_Video_Image_Retrieval/aic-system/artifacts/ocr")
FIX_DIR = Path("F:/AI_Challenge_Video_Image_Retrieval/aic-system/artifacts/ocr_fix")  # dat ocr_fixed.jsonl vao day

# 1. doc ban sua vao 1 dict {(video,n): texts_moi}
fixes = {}
fix_files = sorted(glob.glob(str(FIX_DIR / "ocr_fixed*.jsonl")))
print(f"Tim thay {len(fix_files)} file fix: {fix_files}")
for fp in fix_files:
    with open(fp, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            fixes[(d["video"], d["n"])] = d["texts"]
print(f"Tong so ban sua: {len(fixes):,}")

# 2. doc tung file goc, thay the dong nao co trong fixes, ghi de lai
total_replaced = 0
for i in range(1, 6):
    fp = OCR_DIR / f"ocr_{i}.jsonl"
    if not fp.exists():
        continue
    rows = []
    n_replaced = 0
    with open(fp, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            key = (d["video"], d["n"])
            if key in fixes:
                d["texts"] = fixes[key]
                n_replaced += 1
            rows.append(d)
    with open(fp, "w", encoding="utf-8") as f:
        for d in rows:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    total_replaced += n_replaced
    print(f"ocr_{i}.jsonl: thay {n_replaced} dong, tong {len(rows)} dong")

print(f"\nTONG DA THAY: {total_replaced:,} / {len(fixes):,} ban sua")
