import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.repositories.es_repo import EsRepo

er = EsRepo()

full_query = ("Đoạn video về một chương trình từ thiện của một câu lạc bộ tên là FANA. "
              "Trong đoạn video có thể thấy câu lạc bộ này đang đi trao quà tại một xã "
              "thuộc tỉnh Khánh Hòa. Hỏi xã này có tên là gì? (tại thời điểm đó)")

ranks = er.search_frames("ocr_text", full_query, 500)
print(f"OCR branch (nguyen cau, top500): {len(ranks)} ket qua")
for v in ("L22_V021:000494", "L22_V021:000491"):
    if v in ranks:
        print(f"  {v} O HANG {ranks.index(v)+1}")
    else:
        print(f"  {v} KHONG CO trong top500")
print("Top 5 OCR branch:", ranks[:5])

print()
ranks2 = er.search_frames("ocr_text", "FANA", 500)
print(f"OCR branch (chi 'FANA'): {ranks2}")
