"""POST /search — multi-signal search. Orchestrate: query_service (clause/dịch) ->
query_encoders (vector hoá) -> FAISS (metaclip2/beit3/pecore/capemb/dinov3) +
Meilisearch (ocr/asr/objects, qua es_repo/asr_align) -> core.fusion.rrf (trọng
số theo `kind` từ core.config, GHI ĐÈ ĐƯỢC qua req.weights) -> dedup_by_video ->
hydrate metadata -> SearchResponse.

Hỗ trợ NGƯỜI VẬN HÀNH ghi đè tay OCR/ASR/object (req.ocr_query/asr_query/
object_query) — hệ "truyền thống có tương tác": máy tự động hoá là mặc định tốt,
nhưng người biết chính xác cần tìm chữ/lời gì thì phải tự nhập được, bỏ qua bước
đoán tự động (đã đo: LLM/heuristic đôi khi đoán sai hoặc bị pha loãng).

4 tính năng MỚI (theo yêu cầu — xem SearchRequest):
  1) DINOv3 tích hợp CHUNG vào RRF (req.ref_video/ref_n hoặc req.ref_image_b64)
     thay vì chỉ dùng riêng ở /similar.
  2) TRỌNG SỐ ĐỘNG (req.weights) — ghi đè trọng số fusion tại chỗ, không đổi
     mặc định trong core/config.py.
  3) video_scope (lọc video trước, xem api/routers/videos.py) — hạn chế MỌI
     nhánh chỉ search trong 1 tập video đã chọn trước.
  4) strict_text_filter — khi OCR/ASR khớp ĐỘ TIN CẬY CAO (>= ngưỡng), giới hạn
     HẲN các nhánh thị giác vào tập khung hình đã khớp (± sai số) thay vì chỉ
     cộng trọng số RRF như bình thường. Không đủ tin cậy -> tự rơi về fusion mềm.
"""
from __future__ import annotations

import base64
import re

from fastapi import APIRouter, Depends

from api.deps import get_encoders, get_es, get_media_index, get_milvus
from api.schemas.search import SearchHit, SearchRequest, SearchResponse, SignalInfo
from core import config as C
from core import query_service, translate
from core.asr_align import align_segments_to_frames, search_asr_as_frames, search_asr_semantic_as_frames
from core.fusion import Hit, dedup_by_video, maxmean_clauses, rrf
from core.media_index import MediaIndex
from core.query_encoders import QueryEncoders
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo

router = APIRouter()

WIDE_TOPK = 500          # topk mỗi nhánh trước khi RRF — đủ rộng để không bỏ sót
CANDIDATE_POOL = 500      # số ứng viên hydrate metadata sau RRF (trước dedup+cắt topk)


def _expand_frame_margin(ids: set[str], media_index: MediaIndex, margin: int) -> set[str]:
    """Nới thêm `margin` khung lân cận THEO CHỈ SỐ n (khung hình thưa, không phải
    frame_idx gốc) quanh mỗi id đã khớp OCR — mục 4, sai số cho strict filter."""
    by_video: dict[str, set[int]] = {}
    for i in ids:
        v, n = i.rsplit(":", 1)
        by_video.setdefault(v, set()).add(int(n))
    out: set[str] = set()
    for v, target_ns in by_video.items():
        for n, _ in media_index.video_ns_pts(v):
            if any(abs(n - t) <= margin for t in target_ns):
                out.add(f"{v}:{n:06d}")
    return out


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest,
           milvus: FaissRepo = Depends(get_milvus),
           es: MeiliRepo = Depends(get_es),
           encoders: QueryEncoders = Depends(get_encoders),
           media_index: MediaIndex = Depends(get_media_index)) -> SearchResponse:
    kind = req.kind
    query_vi = req.query.strip()
    video_scope = req.video_scope or None

    rank_lists: list[list[str]] = []
    weight_list: list[float] = []
    signals: list[SignalInfo] = []

    def add_signal(name: str, ranks: list[str], weight: float, query_text: str | None = None):
        if not ranks:
            return
        rank_lists.append(ranks)
        weight_list.append(weight)
        signals.append(SignalInfo(name=name, weight=weight, query_text=query_text, n_hits=len(ranks)))

    def use_model(name: str) -> bool:
        return req.models is None or name in req.models

    def w(name: str, default: float) -> float:
        """TRỌNG SỐ ĐỘNG (mục 2) — ghi đè TẠI CHỖ qua req.weights nếu có key
        tương ứng, không đổi giá trị mặc định trong core/config.py."""
        if req.weights and name in req.weights:
            return req.weights[name]
        return default

    # ============ 0. OCR/ASR — TÍNH TRƯỚC (cần cho strict_text_filter mục 4) ============
    ocr_keywords: list[str] = []
    if not req.ocr_query:
        ocr_keywords = query_service.extract_ocr_keywords(query_vi)
        for kw in ocr_keywords:
            add_signal(f"ocr-từ-khoá:{kw}",
                        es.search_frames("ocr_text", kw, WIDE_TOPK, videos=video_scope),
                        w("ocr_keyword", C.OCR_KEYWORD_WEIGHT.get(kind, 1.5)), kw)

    ocr_query_text = req.ocr_query or query_vi
    ocr_scored = es.search_frames_scored_global("ocr_text", ocr_query_text, WIDE_TOPK, videos=video_scope)
    ocr_ranks = [i for i, _ in sorted(ocr_scored.items(), key=lambda kv: -kv[1])]
    if req.ocr_query:
        w_ocr = w("ocr", C.OCR_WEIGHT.get("qa", C.OCR_TEXT_WEIGHT) if kind == "qa" else C.OCR_ADAPTIVE_HIGH_W)
        add_signal("ocr (tay)", ocr_ranks, w_ocr, req.ocr_query)
    else:
        if kind == "qa":
            w_ocr = w("ocr", C.OCR_WEIGHT.get("qa", C.OCR_TEXT_WEIGHT))
        elif re.search(C.OCR_ADAPTIVE_TEXT_CUES, query_vi, re.IGNORECASE):
            w_ocr = w("ocr", C.OCR_ADAPTIVE_HIGH_W)
        else:
            w_ocr = w("ocr", C.OCR_WEIGHT.get(kind, C.OCR_TEXT_WEIGHT))
        add_signal("ocr (tự động)", ocr_ranks, w_ocr, query_vi)

    asr_query_text = req.asr_query or query_vi
    asr_segs_scored = es.search_asr(asr_query_text, WIDE_TOPK, videos=video_scope)
    if req.asr_query:
        asr_ranks = align_segments_to_frames(asr_segs_scored, media_index)
        add_signal("asr (tay)", asr_ranks, w("asr", C.ASR_WEIGHT.get(kind, 0.15)), req.asr_query)
    else:
        asr_paraphrases = query_service.expand_asr_queries(query_vi)
        asr_variant_lists = [search_asr_as_frames(es, media_index, q, WIDE_TOPK, videos=video_scope)
                              for q in [query_vi, *asr_paraphrases]]
        asr_variant_lists = [r for r in asr_variant_lists if r]
        if len(asr_variant_lists) > 1:
            asr_fused = rrf(asr_variant_lists, k=C.RRF_K)
            asr_ranks = [i for i, _ in sorted(asr_fused.items(), key=lambda kv: -kv[1])]
        else:
            asr_ranks = asr_variant_lists[0] if asr_variant_lists else []
        add_signal("asr (tự động, mở rộng)", asr_ranks, w("asr", C.ASR_WEIGHT.get(kind, 0.15)),
                    " | ".join([query_vi, *asr_paraphrases]))

    # ============ 0b. STRICT TEXT FILTER (mục 4) ============
    # OCR/ASR khớp ĐỘ TIN CẬY CAO -> giới hạn HẲN nhánh thị giác vào tập khung
    # hình đã khớp (± sai số), KHÔNG chỉ cộng trọng số RRF như soft fusion phía
    # trên. Không đủ tin cậy (hoặc không bật req.strict_text_filter) -> candidate_ids
    # = None, mọi nhánh thị giác search BÌNH THƯỜNG (rơi về fusion mềm, không lỗi).
    candidate_ids: set[str] | None = None
    if req.strict_text_filter:
        strict_ids: set[str] = set()
        ocr_high = {i for i, s in ocr_scored.items() if s >= C.OCR_FILTER_CONFIDENCE}
        if ocr_high:
            strict_ids |= _expand_frame_margin(ocr_high, media_index, C.OCR_FILTER_MARGIN_FRAMES)
        asr_high = [(v, s, e) for v, s, e, sc in asr_segs_scored if sc >= C.ASR_FILTER_CONFIDENCE]
        if asr_high:
            strict_ids |= set(align_segments_to_frames(
                [(v, s, e, 1.0) for v, s, e in asr_high], media_index, window_s=C.ASR_FILTER_MARGIN_S))
        if strict_ids:
            candidate_ids = strict_ids

    def allowed_ids(collection: str) -> set[str] | None:
        """Tập id cho phép search TRONG (mục 3+4) — candidate_ids (strict, mục 4)
        ƯU TIÊN HƠN video_scope (mục 3) khi cả 2 cùng có (chặt hơn). asr_emb dùng
        id-space KHÁC (segment, không phải frame) -> quy về video rồi giãn lại."""
        if candidate_ids is not None:
            if collection == "asr_emb":
                videos_in = {i.split(":")[0] for i in candidate_ids}
                return milvus.ids_for_videos(collection, list(videos_in))
            return candidate_ids
        if video_scope:
            return milvus.ids_for_videos(collection, video_scope)
        return None

    clauses_mc = query_service.clauses_metaclip2(query_vi, use_expansion=req.use_expansion)
    need_en = (encoders.pecore is not None and use_model("pecore")) or \
              (encoders.beit3 is not None and use_model("beit3"))
    clauses_en = query_service.clauses_en(query_vi) if need_en else []

    # ---- 1. metaclip2 (CHÍNH, đa ngữ, maxmean đa mệnh đề) ----
    if encoders.metaclip2 is not None and use_model("metaclip2"):
        mc_vecs = encoders.metaclip2.encode(clauses_mc)
        mc_scored = maxmean_clauses(mc_vecs, milvus, "metaclip2", allowed_ids=allowed_ids("metaclip2"))
        add_signal("metaclip2", [doc_id for doc_id, _ in mc_scored],
                    w("metaclip2", C.METACLIP2_WEIGHT.get(kind, 1.0)), " | ".join(clauses_mc))

    # ---- 2. pecore (CHI TIẾT, tiếng Anh, maxmean đa mệnh đề — PLACEHOLDER weight) ----
    if encoders.pecore is not None and use_model("pecore"):
        pc_vecs = encoders.pecore.encode(clauses_en)
        pc_scored = maxmean_clauses(pc_vecs, milvus, "pecore", allowed_ids=allowed_ids("pecore"))
        add_signal("pecore", [doc_id for doc_id, _ in pc_scored],
                    w("pecore", C.PECORE_WEIGHT.get(kind, 0.3)), " | ".join(clauses_en))

    # ---- 3. beit3 (ensemble, tiếng Anh, đã max-pool trong bridge server) ----
    if encoders.beit3 is not None and use_model("beit3"):
        beit3_vec = encoders.beit3.encode_one(clauses_en)
        if beit3_vec is not None:
            allowed = allowed_ids("beit3")
            ranks = ([i for i, _ in milvus.search_within_ids("beit3", beit3_vec, allowed, WIDE_TOPK)]
                      if allowed is not None else milvus.search("beit3", beit3_vec, WIDE_TOPK))
            add_signal("beit3", ranks, w("beit3", C.BEIT3_WEIGHT.get(kind, 0.2)), " | ".join(clauses_en))

    # ---- 4. capemb (text-to-caption, đa ngữ, câu ĐẦY ĐỦ không tách/cắt) ----
    # cap_vec (encode 1 lần, prompt_name="query") dùng lại ở mục 4b (asr_emb ngữ
    # nghĩa) khi không ghi đè tay asr_query — tránh encode capemb 2 lần/request.
    w_cap = w("capemb", C.CAPTION_WEIGHT.get(kind, 0.0))
    need_cap_vec = encoders.capemb is not None and (use_model("capemb") or use_model("asr_emb"))
    cap_vec = encoders.capemb.encode([query_vi])[0] if need_cap_vec else None
    if cap_vec is not None and use_model("capemb") and w_cap > 0:
        allowed = allowed_ids("capemb")
        ranks = ([i for i, _ in milvus.search_within_ids("capemb", cap_vec, allowed, WIDE_TOPK)]
                  if allowed is not None else milvus.search("capemb", cap_vec, WIDE_TOPK))
        add_signal("capemb", ranks, w_cap, query_vi)

    # ---- 4b. ASR NGỮ NGHĨA (semantic, nhánh FAISS "asr_emb", Qwen3-Embedding-4B)
    # — bổ sung cho mục 0 (khớp TỪ), không thay thế: câu hỏi có thể diễn đạt khác
    # hẳn từ ngữ ASR thật nói ra (vd "giá xăng tăng" ~ "giá nhiên liệu leo thang").
    # Tự trả [] êm nếu chưa build nhánh (xem indexing/kaggle/12_asr_embed.py) ----
    if cap_vec is not None and use_model("asr_emb") and milvus.has_branch("asr_emb"):
        if req.asr_query:
            semantic_query, semantic_vec = req.asr_query, encoders.capemb.encode([req.asr_query])[0]
        else:
            semantic_query, semantic_vec = query_vi, cap_vec
        add_signal("asr_emb (ngữ nghĩa)",
                    search_asr_semantic_as_frames(milvus, media_index, semantic_vec, WIDE_TOPK),
                    w("asr_emb", C.ASR_EMB_WEIGHT.get(kind, 0.15)), semantic_query)

    # ---- 5. DINOv3 (mục 1 — TÍCH HỢP CHUNG vào /search, không còn tách riêng
    # /similar) — ảnh tham chiếu từ 1 keyframe ĐÃ CÓ SẴN (ref_video/ref_n) HOẶC
    # ảnh UPLOAD ngoài (ref_image_b64, cần REMOTE encoder DINOv3 đang chạy) ----
    ref_vec = None
    ref_label = None
    if req.ref_video and req.ref_n is not None:
        ref_vec = milvus.fetch_vector_by_id("dinov3", f"{req.ref_video}:{req.ref_n:06d}")
        ref_label = f"ref={req.ref_video}:{req.ref_n:06d}"
    elif req.ref_image_b64:
        if encoders.dinov3_image is not None:
            try:
                b64 = req.ref_image_b64.split(",")[-1]   # chấp nhận cả data URI lẫn base64 thuần
                ref_vec = encoders.dinov3_image.encode_image(base64.b64decode(b64))
                ref_label = "ref=ảnh upload"
            except Exception as e:
                print(f"[search] lỗi encode ref_image_b64 ({type(e).__name__}: {e}) -> bỏ qua êm tín hiệu dinov3")
        else:
            print("[search] ref_image_b64 có nhưng KHÔNG có REMOTE encoder DINOv3 -> bỏ qua êm")
    if ref_vec is not None and use_model("dinov3") and milvus.has_branch("dinov3"):
        allowed = allowed_ids("dinov3")
        ranks = ([i for i, _ in milvus.search_within_ids("dinov3", ref_vec, allowed, WIDE_TOPK)]
                  if allowed is not None else milvus.search("dinov3", ref_vec, WIDE_TOPK))
        add_signal("dinov3", ranks, w("dinov3", C.DINOV3_WEIGHT.get(kind, 0.5)), ref_label)

    # ---- 6. object+màu — ƯU TIÊN ghi đè tay (LUÔN bật khi có object_query), không
    # thì tự động (gate regex chặt — chỉ bật khi câu nêu rõ vật+màu) ----
    if req.object_query:
        add_signal("object (tay)", es.search_objects(req.object_query, WIDE_TOPK, videos=video_scope),
                    w("object", C.COLOR_WEIGHT), req.object_query)
    elif C.USE_OBJECT_COLOR and re.search(C.COLOR_CUES, query_vi, re.IGNORECASE):
        color_query = " ".join(translate.vi2en(clauses_mc))
        add_signal("object (tự động)", es.search_objects(color_query, WIDE_TOPK, videos=video_scope),
                    w("object", C.COLOR_WEIGHT), color_query)

    # ---- 7. entity resolution (LLM suy tên riêng -> OCR/ASR, gate confidence=high) ----
    if C.USE_ENTITY_RESOLUTION:
        ent = query_service.resolve_entity(query_vi)
        ents = ent["entities"] if ent and ent.get("confidence") == "high" else []
        if ents:
            eq = " ".join(ents)
            ent_ocr = es.search_frames("ocr_text", eq, WIDE_TOPK, videos=video_scope)
            ent_asr = search_asr_as_frames(es, media_index, eq, WIDE_TOPK, videos=video_scope)
            ent_fused = rrf([r for r in (ent_ocr, ent_asr) if r], k=C.RRF_K)
            if ent_fused:
                ranked = [i for i, _ in sorted(ent_fused.items(), key=lambda kv: -kv[1])]
                add_signal("entity", ranked, w("entity", C.ENTITY_WEIGHT), eq)

    fused = rrf(rank_lists, k=C.RRF_K, weights=weight_list)
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
        strict_filter_applied=candidate_ids is not None,
        strict_filter_pool_size=len(candidate_ids) if candidate_ids is not None else None,
    )
