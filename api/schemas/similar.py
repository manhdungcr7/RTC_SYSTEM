from pydantic import BaseModel

from api.schemas.search import SearchHit


class SimilarRequest(BaseModel):
    video: str
    n: int
    topk: int = 100


class SimilarResponse(BaseModel):
    hits: list[SearchHit]
