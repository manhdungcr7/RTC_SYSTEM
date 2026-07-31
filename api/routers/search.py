"""POST /search — multi-signal search. Orchestrate: query_service (clause/dịch) ->
query_encoders (vector hoá) -> Milvus (metaclip2/beit3/pecore/capemb) + ES
(ocr/asr/objects, qua es_repo/asr_align) -> core.fusion.rrf (trọng số theo `kind`
từ core.config) -> dedup_by_video -> hydrate metadata -> SearchResponse.

Hỗ trợ NGƯỜI VẬN HÀNH ghi đè tay OCR/ASR/object (req.ocr_query/asr_query/
object_query) — hệ "truyền thống có tương tác": máy tự động hoá là mặc định tốt,
nhưng người biết chính xác cần tìm chữ/lời gì thì phải tự nhập được, bỏ qua bước
đoán tự động (đã đo: LLM/heuristic đôi khi đoán sai hoặc bị pha loãng)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends

from api.deps import get_encoders, get_es, get_media_index, get_milvus
from api.schemas.search import SearchHit, SearchRequest, SearchResponse, SignalInfo
from core import config as C
from core import query_service, translate
from core.asr_align import search_asr_as_frames
from core.fusion import Hit, dedup_by_video, maxmean_clauses, rrf
from core.media_index import MediaIndex
from core.query_encoders import QueryEncoders
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo

router = APIRouter()

WIDE_TOPK = 500          # topk mỗi nhánh trước khi RRF — đủ rộng để không bỏ sót
CANDIDATE_POOL = 500      # số ứng viên hydrate metadata sau RRF (trước dedup+cắt topk)


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest,
           milvus: FaissRepo = Depends(get_milvus),
           es: MeiliRepo = Depends(get_es),
           encoders: QueryEncoders = Depends(get_encoders),
           media_index: MediaIndex = Depends(get_media_index)) -> SearchResponse:
    kind = req.kind
    query_vi = req.query.strip()

    rank_lists: list[list[str]] = []
    weights: list[float] = []
    signals: list[SignalInfo] = []

    def add_signal(name: str, ranks: list[str], weight: float, query_text: str | None = None):
        if not ranks:
            return
        rank_lists.append(ranks)
        weights.append(weight)
        signals.append(SignalInfo(name=name, weight=weight, query_text=query_text, n_hits=len(ranks)))

    clauses_mc = query_service.clauses_metaclip2(query_vi, use_expansion=req.use_expansion)
    # clauses_en chỉ cần khi pecore/beit3 (2 nhánh CHỈ TIẾNG ANH) đang bật — tránh
    # dịch phí công (gọi LLM/envit5) khi cả 2 đang tắt (vd máy dev hạn chế RAM, xem
    # core.config.ENABLED_BRANCHES).
    need_en = encoders.pecore is not None or encoders.beit3 is not None
    clauses_en = query_service.clauses_en(query_vi) if need_en else []

    # ---- 1. metaclip2 (CHÍNH, đa ngữ, maxmean đa mệnh đề) ----
    if encoders.metaclip2 is not None:
        mc_vecs = encoders.metaclip2.encode(clauses_mc)
        mc_scored = maxmean_clauses(mc_vecs, milvus, "metaclip2")
        add_signal("metaclip2", [doc_id for doc_id, _ in mc_scored], 1.0, " | ".join(clauses_mc))

    # ---- 2. pecore (CHI TIẾT, tiếng Anh, maxmean đa mệnh đề — PLACEHOLDER weight) ----
    if encoders.pecore is not None:
        pc_vecs = encoders.pecore.encode(clauses_en)
        pc_scored = maxmean_clauses(pc_vecs, milvus, "pecore")
        add_signal("pecore", [doc_id for doc_id, _ in pc_scored],
                    C.PECORE_WEIGHT.get(kind, 0.3), " | ".join(clauses_en))

    # ---- 3. beit3 (ensemble, tiếng Anh, đã max-pool trong bridge server) ----
    if encoders.beit3 is not None:
        beit3_vec = encoders.beit3.encode_one(clauses_en)
        if beit3_vec is not None:
            add_signal("beit3", milvus.search("beit3", beit3_vec, WIDE_TOPK),
                        C.BEIT3_WEIGHT.get(kind, 0.2), " | ".join(clauses_en))

    # ---- 4. capemb (text-to-caption, đa ngữ, câu ĐẦY ĐỦ không tách/cắt) ----
    w_cap = C.CAPTION_WEIGHT.get(kind, 0.0)
    if encoders.capemb is not None and w_cap > 0:
        cap_vec = encoders.capemb.encode([query_vi])[0]
        add_signal("capemb", milvus.search("capemb", cap_vec, WIDE_TOPK), w_cap, query_vi)

    # ---- 5a. OCR-từ-khoá (LLM trích tên riêng/số liệu ĐÃ NÊU RÕ, tra RIÊNG từng
    # từ khoá rồi fuse RRF) — bỏ qua nếu người dùng đã ghi đè tay ocr_query (khi đó
    # họ đã biết chính xác cần tìm gì, không cần LLM đoán thêm).
    ocr_keywords: list[str] = []
    if not req.ocr_query:
        ocr_keywords = query_service.extract_ocr_keywords(query_vi)
        for kw in ocr_keywords:
            add_signal(f"ocr-từ-khoá:{kw}", es.search_frames("ocr_text", kw, WIDE_TOPK),
                        C.OCR_KEYWORD_WEIGHT.get(kind, 1.5), kw)

    # ---- 5b. OCR — ƯU TIÊN ghi đè tay (req.ocr_query), không thì tự động (nguyên
    # văn câu, thích ứng theo kind + cue trong câu) ----
    if req.ocr_query:
        add_signal("ocr (tay)", es.search_frames("ocr_text", req.ocr_query, WIDE_TOPK),
                    C.OCR_WEIGHT.get("qa", C.OCR_TEXT_WEIGHT) if kind == "qa" else C.OCR_ADAPTIVE_HIGH_W,
                    req.ocr_query)
    else:
        ocr_ranks = es.search_frames("ocr_text", query_vi, WIDE_TOPK)
        if kind == "qa":
            w_ocr = C.OCR_WEIGHT.get("qa", C.OCR_TEXT_WEIGHT)
        elif re.search(C.OCR_ADAPTIVE_TEXT_CUES, query_vi, re.IGNORECASE):
            w_ocr = C.OCR_ADAPTIVE_HIGH_W
        else:
            w_ocr = C.OCR_WEIGHT.get(kind, C.OCR_TEXT_WEIGHT)
        add_signal("ocr (tự động)", ocr_ranks, w_ocr, query_vi)

    # ---- 6. ASR — ƯU TIÊN ghi đè tay, không thì tự động (căn ±2s theo pts_time).
    # Tự động: câu gốc + vài "biến thể giọng bản tin" (query_service.expand_asr_
    # queries, LLM diễn giải lại — ASR THẬT hiếm khi dùng đúng từ câu truy vấn) ->
    # fuse RRF nội bộ thành 1 rank-list, rồi mới add_signal (KHÔNG add từng biến
    # thể riêng — tránh lặp lại lỗi đã gặp với OCR-từ-khoá: nhiều branch trọng số
    # cao cùng lúc dễ áp đảo tín hiệu hình ảnh đúng). ----
    if req.asr_query:
        add_signal("asr (tay)", search_asr_as_frames(es, media_index, req.asr_query, WIDE_TOPK),
                    C.ASR_WEIGHT.get(kind, 0.15), req.asr_query)
    else:
        asr_paraphrases = query_service.expand_asr_queries(query_vi)
        asr_variant_lists = [search_asr_as_frames(es, media_index, q, WIDE_TOPK)
                              for q in [query_vi, *asr_paraphrases]]
        asr_variant_lists = [r for r in asr_variant_lists if r]
        if len(asr_variant_lists) > 1:
            asr_fused = rrf(asr_variant_lists, k=C.RRF_K)
            asr_ranks = [i for i, _ in sorted(asr_fused.items(), key=lambda kv: -kv[1])]
        else:
            asr_ranks = asr_variant_lists[0] if asr_variant_lists else []
        add_signal("asr (tự động, mở rộng)", asr_ranks, C.ASR_WEIGHT.get(kind, 0.15),
                    " | ".join([query_vi, *asr_paraphrases]))

    # ---- 7. object+màu — ƯU TIÊN ghi đè tay (LUÔN bật khi có object_query), không
    # thì tự động (gate regex chặt — chỉ bật khi câu nêu rõ vật+màu) ----
    if req.object_query:
        add_signal("object (tay)", es.search_objects(req.object_query, WIDE_TOPK),
                    C.COLOR_WEIGHT, req.object_query)
    elif C.USE_OBJECT_COLOR and re.search(C.COLOR_CUES, query_vi, re.IGNORECASE):
        color_query = " ".join(translate.vi2en(clauses_mc))
        add_signal("object (tự động)", es.search_objects(color_query, WIDE_TOPK),
                    C.COLOR_WEIGHT, color_query)

    # ---- 8. entity resolution (LLM suy tên riêng -> OCR/ASR, gate confidence=high) ----
    if C.USE_ENTITY_RESOLUTION:
        ent = query_service.resolve_entity(query_vi)
        ents = ent["entities"] if ent and ent.get("confidence") == "high" else []
        if ents:
            eq = " ".join(ents)
            ent_ocr = es.search_frames("ocr_text", eq, WIDE_TOPK)
            ent_asr = search_asr_as_frames(es, media_index, eq, WIDE_TOPK)
            ent_fused = rrf([r for r in (ent_ocr, ent_asr) if r], k=C.RRF_K)
            if ent_fused:
                ranked = [i for i, _ in sorted(ent_fused.items(), key=lambda kv: -kv[1])]
                add_signal("entity", ranked, C.ENTITY_WEIGHT, eq)

    fused = rrf(rank_lists, k=C.RRF_K, weights=weights)
    top_ids = [i for i, _ in sorted(fused.items(), key=lambda kv: -kv[1])[:CANDIDATE_POOL]]
    meta = milvus.fetch_by_ids("metaclip2", top_ids)

    hits = [Hit(id=i, video=meta[i][0], n=meta[i][1], frame_idx=meta[i][2], score=fused[i])
            for i in top_ids if i in meta]
    hits = dedup_by_video(hits, C.DEDUP_DEFAULT)[:req.topk]

    return SearchResponse(
        hits=[SearchHit(id=h.id, video=h.video, n=h.n, frame_idx=h.frame_idx, score=h.score,
                         thumb_url=f"/media/frame/{h.video}/{h.n}",
                         pts_time=media_index.pts_time(h.video, h.n)) for h in hits],
        clauses_metaclip2=clauses_mc,
        clauses_en=clauses_en,
        ocr_keywords=ocr_keywords,
        signals_used=signals,
    )
