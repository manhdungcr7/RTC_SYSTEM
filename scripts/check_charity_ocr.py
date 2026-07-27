import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.repositories.es_repo import EsRepo

er = EsRepo()

terms = [
    "FANA", "Khánh Hòa", "mồ côi", "COVID-19", "COVID",
    "trao kinh phí", "hỗ trợ trẻ em", "bệnh viện", "Xuân 2024",
]
for t in terms:
    res = er.es.search(index="aic_frames", query={"match": {"ocr_text": t}}, size=5)
    total = res["hits"]["total"]["value"]
    top = [(h["_id"], round(h["_score"], 2)) for h in res["hits"]["hits"]]
    print(f"{t!r}: tong={total}, top5={top}")
