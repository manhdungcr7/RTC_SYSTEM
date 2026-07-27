import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.query_service import split_clauses
from core.repositories.es_repo import EsRepo

er = EsRepo()

full_query = ("Đoạn video về một chương trình từ thiện của một câu lạc bộ tên là FANA. "
              "Trong đoạn video có thể thấy câu lạc bộ này đang đi trao quà tại một xã "
              "thuộc tỉnh Khánh Hòa. Hỏi xã này có tên là gì? (tại thời điểm đó)")

clauses = split_clauses(full_query)
print("Menh de:", clauses)
for c in clauses:
    ranks = er.search_frames("ocr_text", c, 500)
    hit = "L22_V021:000494" in ranks or "L22_V021:000491" in ranks
    pos = ranks.index("L22_V021:000494") + 1 if "L22_V021:000494" in ranks else (
        ranks.index("L22_V021:000491") + 1 if "L22_V021:000491" in ranks else None)
    print(f"  {c!r}\n    -> L22_V021 co trong top500? {hit} (hang {pos}) | top3={ranks[:3]}")
