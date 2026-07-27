import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.repositories.es_repo import EsRepo

er = EsRepo()

for term in ["củ năng", "đậu hủ", "đậu phụ", "nấm"]:
    res = er.es.search(
        index="aic_frames",
        query={"match": {"ocr_text": term}},
        size=10,
    )
    hits = res["hits"]["hits"]
    print(f"\n=== '{term}' -> {res['hits']['total']['value']} tong, top 10: ===")
    for h in hits:
        print(f"  {h['_id']}  score={h['_score']:.2f}")
