"""
Gop cac file captions_fixed*.jsonl (tai ve tu 07c_fix_truncated_captions.py, co the
nhieu file neu chia SPLIT nhieu account) VAO 5 file captions_1..5.jsonl goc trong
aic-system/artifacts/caption/ — thay the dong cu (bi cat cut) bang dong moi (day du).

Chay: python aic-system/indexing/merge_caption_fix.py
"""
import json
import glob
from pathlib import Path

CAPTION_DIR = Path("F:/AI_Challenge_Video_Image_Retrieval/aic-system/artifacts/caption")
FIX_DIR = Path("F:/AI_Challenge_Video_Image_Retrieval/aic-system/artifacts/fix")  # dat cac file fix* vao day

# 1. doc tat ca ban sua vao 1 dict {(video,n): cap_moi}
fixes = {}
fix_files = sorted(glob.glob(str(FIX_DIR / "captions_fixed*.jsonl")))
print(f"Tim thay {len(fix_files)} file fix: {fix_files}")
for fp in fix_files:
    with open(fp, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            fixes[(d["video"], d["n"])] = d["cap"]
print(f"Tong so ban sua: {len(fixes):,}")

# 2. doc tung file goc, thay the dong nao co trong fixes, ghi de lai
END_OK = (".", "!", "?", '"', "\u201d")
total_replaced = 0
for i in range(1, 6):
    fp = CAPTION_DIR / f"captions_{i}.jsonl"
    rows = []
    n_replaced = 0
    with open(fp, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            key = (d["video"], d["n"])
            if key in fixes:
                d["cap"] = fixes[key]
                n_replaced += 1
            rows.append(d)
    with open(fp, "w", encoding="utf-8") as f:
        for d in rows:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    total_replaced += n_replaced
    print(f"captions_{i}.jsonl: thay {n_replaced} dong, tong {len(rows)} dong")

print(f"\nTONG DA THAY: {total_replaced:,}")

# 3. kiem tra lai con bao nhieu dong van chua ket thuc dung dau cau
still_broken = 0
total = 0
for i in range(1, 6):
    fp = CAPTION_DIR / f"captions_{i}.jsonl"
    with open(fp, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            total += 1
            if not d["cap"].strip().endswith(END_OK):
                still_broken += 1
print(f"Sau khi gop: con {still_broken}/{total} dong van chua ket thuc dung dau cau "
      f"({still_broken/total*100:.2f}%)")
