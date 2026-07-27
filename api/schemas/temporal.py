from pydantic import BaseModel

from api.schemas.search import SearchHit


class TemporalRequest(BaseModel):
    events: list[str]
    context: str = ""
    topk: int = 100
    per_event: int = 1500


class TemporalCandidate(BaseModel):
    video: str
    total_score: float
    hits: list[SearchHit]   # 1 hit / sự kiện, đúng thứ tự E1..En


class TemporalResponse(BaseModel):
    candidates: list[TemporalCandidate]
