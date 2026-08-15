"""POST /search — truy vấn đa tín hiệu.

TRIẾT LÝ (mục 0 bản thiết kế — "hệ thống truyền thống, người dùng chủ động"):
  P1 Không có số nào vô hình — mọi trọng số áp dụng đều trả về trong signals_used.
  P2 Mọi tín hiệu có công tắc riêng — req.signals[branch].enabled/weight.
  P3 Xếp hạng phải giải thích được — req.explain=True trả phân rã từng nhánh +
     từng mệnh đề cho TỪNG khung hình (nguồn cho bảng "Vì sao").
  P4 Tự động = ĐỀ XUẤT, không phải quyết định — LLM chỉ tách mệnh đề rồi trả ra
     cho người dùng sửa; OCR/ASR KHÔNG có đường tự động nào, chỉ chạy khi người
     dùng tự gõ.
  P5 Luôn còn một đường thủ công — xem /videos/*, Workbench, đồng hồ frame_idx.

TƯƠNG THÍCH: trường "phẳng" cũ (ocr_query/asr_query/weights/video_scope...) vẫn
chạy y như trước. Trường có cấu trúc mới (ocr/asr/signals/clauses/negative/
feedback...) THẮNG trường cũ khi có mặt — xem các hàm _resolve_* bên dưới.

TỐC ĐỘ: mọi lần encode đi qua QueryVectorCache (lưu đĩa) và mọi kết quả nhánh đi
qua BranchResultCache (RAM). Nhờ đó khi người dùng CHỈ kéo fader trọng số, không
nhánh nào phải chạy lại — phản hồi dưới ~50ms. Không có 2 cache này thì bàn trộn
tín hiệu vô dụng trên thực tế (mỗi lần chỉnh phải chờ Kaggle vài giây).
"""
from __future__ import annotations

import base64
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from fastapi import APIRouter, Depends

from api.deps import (get_branch_cache, get_encoders, get_meili, get_media_index,
                      get_faiss, get_vec_cache)
from api.schemas.search import (AsrConfig, BranchContribution, BranchRanking, ClauseScore,
                                 FrameContent, HitExplain, OcrConfig, SearchHit,
                                 SearchRequest, SearchResponse, SignalInfo)
from core import config as C
from core import query_service, translate
from core.asr_align import align_segments_to_frames
from core.fusion import (Hit, dedup_by_time, dedup_by_video, fuse_with_explain,
                          maxmean_clauses_detailed, rocchio)
from core.media_index import MediaIndex
from core.query_cache import BranchResultCache, QueryVectorCache, scope_signature, vector_hash
from core.query_encoders import QueryEncoders
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo

router = APIRouter()

WIDE_TOPK = 500          # topk mỗi nhánh trước khi gộp
CANDIDATE_POOL = 500     # số ứng viên hydrate metadata sau khi gộp
BRANCH_LIST_TOPK = 60    # số kết quả trả về cho MỖI nhánh khi bật branch_lists

# Nhánh VECTOR (có encoder + index FAISS) — phân biệt với nhánh CHỮ (ocr/asr/object).
VECTOR_BRANCHES = ("metaclip2", "pecore", "beit3", "capemb", "dinov3", "asr_emb")


# ==================== chuẩn hoá cấu hình: mới > cũ > mặc định ====================

def _resolve_ocr(req: SearchRequest) -> OcrConfig:
    if req.ocr is not None:
        return req.ocr
    return OcrConfig(query=req.ocr_query or "",
                      mode="filter" if req.strict_text_filter else "score")


def _resolve_asr(req: SearchRequest) -> AsrConfig:
    if req.asr is not None:
        return req.asr
    return AsrConfig(query=req.asr_query or "",
                      mode="filter" if req.strict_text_filter else "score")


def _resolve_scope(req: SearchRequest) -> tuple[list[str] | None, bool]:
    """Trả (danh sách video, có đảo ngược không). Đảo ngược = LOẠI TRỪ nhóm này."""
    if req.scope is not None:
        return (req.scope.video_ids or None), req.scope.invert
    return (req.video_scope or None), False


def _branch_on(req: SearchRequest, name: str) -> bool:
    """Nhánh có được BẬT không. Ưu tiên: signals (mới) > models (cũ) > mặc định bật."""
    if req.signals is not None and name in req.signals:
        return req.signals[name].enabled
    if req.models is not None:
        return name in req.models
    return True


def _branch_weight(req: SearchRequest, name: str, default: float) -> float:
    """Trọng số áp dụng. Ưu tiên: signals (mới) > weights (cũ) > mặc định theo kind."""
    if req.signals is not None and name in req.signals:
        w = req.signals[name].weight
        if w is not None:
            return w
    if req.weights and name in req.weights:
        return req.weights[name]
    return default


def _expand_frame_margin(ids: set[str], media_index: MediaIndex, margin: int) -> set[str]:
    """Nới thêm `margin` khung lân cận theo chỉ số n quanh mỗi khung đã khớp OCR —
    chống trường hợp OCR trượt 1-2 khung do mờ/chuyển cảnh."""
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


def _align_scored(segments, media_index, window_before: float, window_after: float
                   ) -> list[tuple[str, float]]:
    """Align đoạn ASR -> khung hình, GIỮ ĐIỂM (align_segments_to_frames chỉ trả id).
    Cửa sổ BẤT ĐỐI XỨNG: lời dẫn thường đi TRƯỚC hình minh hoạ trong tin tức, nên
    `window_after` (sau khi đoạn nói kết thúc) thường cần rộng hơn `window_before`."""
    best: dict[str, float] = {}
    for video, start, end, score in segments:
        lo, hi = start - window_before, end + window_after
        for n, pts in media_index.video_ns_pts(video):
            if lo <= pts <= hi:
                doc_id = f"{video}:{n:06d}"
                if score > best.get(doc_id, -1.0):
                    best[doc_id] = score
    return sorted(best.items(), key=lambda kv: -kv[1])


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest,
           faiss: FaissRepo = Depends(get_faiss),
           meili: MeiliRepo = Depends(get_meili),
           encoders: QueryEncoders = Depends(get_encoders),
           media_index: MediaIndex = Depends(get_media_index),
           vec_cache: QueryVectorCache = Depends(get_vec_cache),
           branch_cache: BranchResultCache = Depends(get_branch_cache)) -> SearchResponse:
    t0 = time.time()
    kind = req.kind
    query_vi = req.query.strip()
    ocr_cfg = _resolve_ocr(req)
    asr_cfg = _resolve_asr(req)
    scope_videos, scope_invert = _resolve_scope(req)
    fusion_method = req.fusion.method if req.fusion else "rrf"
    fusion_k = req.fusion.k if req.fusion else C.RRF_K

    # scope đảo ngược: quy về danh sách video ĐƯỢC PHÉP (bù của tập bị loại)
    if scope_videos and scope_invert:
        scope_videos = sorted(set(faiss.all_videos()) - set(scope_videos))

    # (tên nhánh, [(id, điểm thô)], trọng số) — nguồn cho cả gộp điểm lẫn explain
    signal_data: list[tuple[str, list[tuple[str, float]], float]] = []
    signals_info: list[SignalInfo] = []

    def add_signal(name: str, label: str, scored: list[tuple[str, float]],
                   weight: float, query_text: str | None = None):
        if not scored:
            return
        signal_data.append((name, scored, weight))
        signals_info.append(SignalInfo(name=label, weight=weight,
                                        query_text=query_text, n_hits=len(scored)))

    # ============ 0. OCR / ASR — CHỈ khi người dùng TỰ GÕ (P4) ============
    ocr_scored: dict[str, float] = {}
    if ocr_cfg.query.strip():
        ocr_scored = meili.search_frames_scored_match("ocr_text", ocr_cfg.query, WIDE_TOPK,
                                                     videos=scope_videos)
        add_signal("ocr", "OCR (chữ trên hình)",
                    sorted(ocr_scored.items(), key=lambda kv: -kv[1]),
                    _branch_weight(req, "ocr", C.OCR_WEIGHT.get(kind, C.OCR_TEXT_WEIGHT)),
                    ocr_cfg.query)

    asr_segs: list[tuple[str, float, float, float]] = []
    if asr_cfg.query.strip() and asr_cfg.lexical:
        asr_segs = meili.search_asr_scored_match(asr_cfg.query, WIDE_TOPK,
                                               videos=scope_videos, match="contains")
        add_signal("asr", "ASR (khớp từ)",
                    _align_scored(asr_segs, media_index,
                                   asr_cfg.window_before, asr_cfg.window_after),
                    _branch_weight(req, "asr", C.ASR_WEIGHT.get(kind, 0.15)), asr_cfg.query)

    # ============ 0b. LỌC CỨNG theo OCR/ASR ============
    # Khớp độ tin cậy CAO -> giới hạn HẲN các nhánh khác vào tập đã khớp (± sai số)
    # thay vì chỉ cộng điểm. Không đủ tin cậy -> tự rơi về gộp mềm, không lỗi.
    candidate_ids: set[str] | None = None
    strict_ids: set[str] = set()
    if ocr_cfg.mode == "filter" and ocr_scored:
        high = {i for i, s in ocr_scored.items() if s >= C.OCR_FILTER_CONFIDENCE}
        if high:
            strict_ids |= _expand_frame_margin(high, media_index, C.OCR_FILTER_MARGIN_FRAMES)
    if asr_cfg.mode == "filter" and asr_segs:
        high_segs = [(v, s, e) for v, s, e, sc in asr_segs if sc >= C.ASR_FILTER_CONFIDENCE]
        if high_segs:
            strict_ids |= set(align_segments_to_frames(
                [(v, s, e, 1.0) for v, s, e in high_segs], media_index,
                window_s=max(asr_cfg.window_after, C.ASR_FILTER_MARGIN_S)))
    if strict_ids:
        candidate_ids = strict_ids

    scope_sig = scope_signature(scope_videos, candidate_ids)

    def allowed_ids(branch: str) -> set[str] | None:
        """Tập id được phép tìm trong. Lọc cứng (chặt hơn) THẮNG phạm vi video."""
        if candidate_ids is not None:
            if branch == "asr_emb":
                videos_in = {i.split(":")[0] for i in candidate_ids}
                return faiss.ids_for_videos(branch, list(videos_in))
            return candidate_ids
        if scope_videos:
            return faiss.ids_for_videos(branch, scope_videos)
        return None

    def vector_search(branch: str, vec: np.ndarray, topk: int = WIDE_TOPK
                      ) -> list[tuple[str, float]]:
        """Tìm 1 nhánh vector, ĐI QUA CACHE. Khoá cache gồm cả nội dung vector và
        phạm vi — nên đổi trọng số KHÔNG làm mất cache, còn đổi câu/phạm vi thì có."""
        key = BranchResultCache.key(branch, vector_hash(vec), scope_sig, topk)

        def _compute():
            allowed = allowed_ids(branch)
            if allowed is not None:
                return faiss.search_within_ids(branch, vec, allowed, topk)
            return faiss.search_scored(branch, vec, topk)
        return branch_cache.get_or_compute(key, _compute)

    def encode_cached(branch: str, texts: list[str], encoder) -> np.ndarray:
        return vec_cache.encode_cached(branch, texts, encoder.encode)

    # ============ 1. Mệnh đề thị giác (LLM chỉ ĐỀ XUẤT — P4) ============
    if req.clauses is not None:
        clauses_mc = [c.text for c in req.clauses if c.enabled and c.text.strip()]
        clause_w = [c.weight for c in req.clauses if c.enabled and c.text.strip()]
    else:
        clauses_mc = query_service.clauses_metaclip2(query_vi, use_expansion=req.use_expansion)
        clause_w = None

    need_en = ((encoders.pecore is not None and _branch_on(req, "pecore")) or
               (encoders.beit3 is not None and _branch_on(req, "beit3")))
    if need_en:
        clauses_en = query_service.clauses_en(query_vi)
        # Bản dịch do NGƯỜI DÙNG ghi đè thắng bản dịch tự động (P4) — điểm mù lớn
        # nếu để dịch chạy ngầm: dịch sai thì 2 nhánh PE-Core/BEiT-3 hỏng lặng lẽ.
        if req.translations:
            clauses_en = [req.translations.get(i, t) for i, t in enumerate(clauses_en)]
    else:
        clauses_en = []

    alpha = req.clause_fusion.alpha if req.clause_fusion else C.MAXMEAN_ALPHA
    fb = req.feedback
    per_clause_scores: dict[str, list[float]] = {}

    # ---- Encode SONG SONG cho mọi nhánh cần encoder từ xa ----
    # Mỗi lần gọi Kaggle qua ngrok mất ~2-5 giây. Chạy tuần tự 4 nhánh là 4 lần
    # chờ cộng dồn (đo thật: ~19s). Chúng độc lập hoàn toàn nên gọi song song —
    # tổng thời gian rút về xấp xỉ lần gọi CHẬM NHẤT thay vì tổng của tất cả.
    # Nhánh nào đã có trong cache thì trả về ngay, không tốn lượt gọi mạng nào.
    encode_jobs: dict[str, tuple[str, list[str], object]] = {}
    if encoders.metaclip2 is not None and _branch_on(req, "metaclip2") and clauses_mc:
        encode_jobs["metaclip2"] = ("metaclip2", clauses_mc, encoders.metaclip2)
    if encoders.pecore is not None and _branch_on(req, "pecore") and clauses_en:
        encode_jobs["pecore"] = ("pecore", clauses_en, encoders.pecore)
    need_cap_vec = encoders.capemb is not None and query_vi and (
        _branch_on(req, "capemb") or _branch_on(req, "asr_emb"))
    if need_cap_vec:
        encode_jobs["capemb"] = ("capemb", [query_vi], encoders.capemb)

    # BEiT-3 gộp nhiều mệnh đề thành 1 vector NGAY PHÍA SERVER (khác 3 nhánh trên
    # trả về 1 vector/mệnh đề) nên dùng đường riêng, nhưng vẫn chạy cùng nhóm.
    want_beit3 = (encoders.beit3 is not None and _branch_on(req, "beit3") and clauses_en)

    encoded: dict[str, np.ndarray] = {}
    b3_vec = None
    if encode_jobs or want_beit3:
        n_jobs = len(encode_jobs) + (1 if want_beit3 else 0)
        with ThreadPoolExecutor(max_workers=n_jobs) as pool:
            futures = {
                pool.submit(encode_cached, branch, texts, enc): name
                for name, (branch, texts, enc) in encode_jobs.items()
            }
            if want_beit3:
                futures[pool.submit(encoders.beit3.encode_one, clauses_en)] = "beit3"
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    result = fut.result()
                    if name == "beit3":
                        b3_vec = result          # có thể là None nếu cầu nối hỏng
                    else:
                        encoded[name] = result
                except Exception as e:
                    # Một nhánh hỏng KHÔNG được làm chết cả truy vấn — các nhánh
                    # còn lại vẫn cho kết quả dùng được.
                    print(f"[search] encode '{name}' lỗi ({type(e).__name__}: {e}) -> bỏ qua nhánh này")

    # ---- metaclip2 (CHÍNH, đa ngữ, không cần dịch) ----
    if "metaclip2" in encoded:
        mc_vecs = encoded["metaclip2"]
        if fb and (fb.positive or fb.negative):
            mc_vecs = np.stack([rocchio(v, "metaclip2", faiss, fb.positive, fb.negative,
                                          fb.beta, fb.gamma) for v in mc_vecs])
        mc_scored, per_clause_scores = maxmean_clauses_detailed(
            mc_vecs, faiss, "metaclip2", allowed_ids=allowed_ids("metaclip2"),
            alpha=alpha, clause_weights=clause_w)
        add_signal("metaclip2", "MetaCLIP-2", mc_scored,
                    _branch_weight(req, "metaclip2", C.METACLIP2_WEIGHT.get(kind, 1.0)),
                    " | ".join(clauses_mc))

    # ---- pecore (chi tiết, tiếng Anh) ----
    if "pecore" in encoded:
        pc_vecs = encoded["pecore"]
        if fb and (fb.positive or fb.negative):
            pc_vecs = np.stack([rocchio(v, "pecore", faiss, fb.positive, fb.negative,
                                          fb.beta, fb.gamma) for v in pc_vecs])
        pc_scored, _ = maxmean_clauses_detailed(
            pc_vecs, faiss, "pecore", allowed_ids=allowed_ids("pecore"), alpha=alpha)
        add_signal("pecore", "PE-Core", pc_scored,
                    _branch_weight(req, "pecore", C.PECORE_WEIGHT.get(kind, 0.3)),
                    " | ".join(clauses_en))

    # ---- beit3 (ensemble, đã max-pool phía server) ----
    if b3_vec is not None:
        if fb and (fb.positive or fb.negative):
            b3_vec = rocchio(b3_vec, "beit3", faiss, fb.positive, fb.negative,
                               fb.beta, fb.gamma)
        add_signal("beit3", "BEiT-3", vector_search("beit3", b3_vec),
                    _branch_weight(req, "beit3", C.BEIT3_WEIGHT.get(kind, 0.2)),
                    " | ".join(clauses_en))

    # ---- capemb (khớp CAPTION, đa ngữ, câu đầy đủ không cắt) ----
    cap_vec = encoded["capemb"][0] if "capemb" in encoded else None
    if cap_vec is not None and _branch_on(req, "capemb"):
        w_cap = _branch_weight(req, "capemb", C.CAPTION_WEIGHT.get(kind, 0.5))
        v = cap_vec
        if fb and (fb.positive or fb.negative):
            v = rocchio(v, "capemb", faiss, fb.positive, fb.negative, fb.beta, fb.gamma)
        add_signal("capemb", "Caption (Qwen3)", vector_search("capemb", v), w_cap, query_vi)

    # ---- asr_emb (khớp Ý NGHĨA lời thoại) ----
    # KHÁC bản cũ: trước đây nhánh này bị khoá sau `if req.asr_query` — tức chỉ chạy
    # khi người dùng ĐÃ BIẾT từ cần tìm, đúng lúc không cần tới nó nữa (nó sinh ra
    # để tìm khi KHÔNG biết chính xác lời thoại). Giờ chạy theo câu ASR nếu có, còn
    # không thì theo chính câu truy vấn — vẫn là chữ NGƯỜI DÙNG gõ, không đoán hộ.
    if _branch_on(req, "asr_emb") and asr_cfg.semantic and encoders.capemb is not None \
            and faiss.has_branch("asr_emb"):
        sem_text = asr_cfg.query.strip() or query_vi
        if sem_text:
            sem_vec = (encode_cached("capemb", [sem_text], encoders.capemb)[0]
                       if sem_text != query_vi or cap_vec is None else cap_vec)
            add_signal("asr_emb", "ASR (khớp ý nghĩa)",
                        _asr_semantic_scored(faiss, media_index, sem_vec,
                                              asr_cfg.window_before, asr_cfg.window_after),
                        _branch_weight(req, "asr_emb", C.ASR_EMB_WEIGHT.get(kind, 0.15)),
                        sem_text)

    # ---- dinov3 (ảnh tham chiếu) ----
    ref_vec, ref_label = None, None
    if req.ref_video and req.ref_n is not None:
        ref_vec = faiss.fetch_vector_by_id("dinov3", f"{req.ref_video}:{req.ref_n:06d}")
        ref_label = f"ảnh mẫu = {req.ref_video}:{req.ref_n:06d}"
    elif req.ref_image_b64:
        if encoders.dinov3_image is not None:
            try:
                b64 = req.ref_image_b64.split(",")[-1]
                ref_vec = encoders.dinov3_image.encode_image(base64.b64decode(b64))
                ref_label = "ảnh mẫu = ảnh tải lên"
            except Exception as e:
                print(f"[search] lỗi encode ảnh tham chiếu ({type(e).__name__}: {e}) -> bỏ qua êm")
        else:
            print("[search] có ảnh tham chiếu nhưng KHÔNG có encoder DINOv3 từ xa -> bỏ qua êm")
    if ref_vec is not None and _branch_on(req, "dinov3") and faiss.has_branch("dinov3"):
        add_signal("dinov3", "DINOv3 (ảnh giống)", vector_search("dinov3", ref_vec),
                    _branch_weight(req, "dinov3", C.DINOV3_WEIGHT.get(kind, 0.5)), ref_label)

    # ---- object + màu + vị trí lưới ----
    if req.objects:
        conds = [o.model_dump() for o in req.objects]
        label = " · ".join(
            f"{o.cls}{'/' + o.color if o.color else ''}{'/ô' + str(o.grid) if o.grid else ''}"
            for o in req.objects)
        scored = meili.search_objects_conds(conds, WIDE_TOPK, videos=scope_videos)
        add_signal("object", "Vật thể + màu + vị trí",
                    sorted(scored.items(), key=lambda kv: -kv[1]),
                    _branch_weight(req, "object", C.COLOR_WEIGHT), label)
    elif req.object_query:
        ids = meili.search_objects(req.object_query, WIDE_TOPK, videos=scope_videos)
        add_signal("object", "Vật thể (gõ tay)",
                    [(i, 1.0 - r / max(len(ids), 1)) for r, i in enumerate(ids)],
                    _branch_weight(req, "object", C.COLOR_WEIGHT), req.object_query)
    elif C.USE_OBJECT_COLOR and query_vi and re.search(C.COLOR_CUES, query_vi, re.IGNORECASE):
        color_query = " ".join(translate.vi2en(clauses_mc))
        ids = meili.search_objects(color_query, WIDE_TOPK, videos=scope_videos)
        add_signal("object", "Vật thể (tự nhận từ câu)",
                    [(i, 1.0 - r / max(len(ids), 1)) for r, i in enumerate(ids)],
                    _branch_weight(req, "object", C.COLOR_WEIGHT), color_query)

    # ============ 2. GỘP ĐIỂM (giữ phân rã cho bảng "Vì sao") ============
    fused, detail = fuse_with_explain(signal_data, k=fusion_k, method=fusion_method)

    # ---- mệnh đề LOẠI TRỪ: trừ điểm / loại hẳn ----
    penalties: dict[str, dict[str, float]] = {}
    neg = req.negative
    if neg and neg.text.strip() and encoders.metaclip2 is not None:
        neg_vecs = encode_cached("metaclip2", [neg.text.strip()], encoders.metaclip2)
        neg_scored = vector_search("metaclip2", neg_vecs[0])
        if neg_scored:
            raws = [s for _, s in neg_scored]
            lo, hi = min(raws), max(raws)
            span = (hi - lo) if (hi - lo) > 1e-9 else 1.0
            for rank0, (doc_id, raw) in enumerate(neg_scored):
                if doc_id not in fused:
                    continue
                if neg.hard_threshold is not None and raw >= neg.hard_threshold:
                    del fused[doc_id]
                    continue
                pen = neg.weight * ((raw - lo) / span) / (fusion_k + rank0 + 1) * fusion_k
                fused[doc_id] -= pen
                penalties.setdefault(doc_id, {})["loại trừ"] = -float(pen)
            signals_info.append(SignalInfo(name="Loại trừ", weight=-neg.weight,
                                            query_text=neg.text, n_hits=len(neg_scored)))

    total_candidates = len(fused)
    top_ids = [i for i, _ in sorted(fused.items(), key=lambda kv: -kv[1])[:CANDIDATE_POOL]]
    meta = faiss.fetch_by_ids("metaclip2", top_ids)

    hits_raw = [Hit(id=i, video=meta[i][0], n=meta[i][1], frame_idx=meta[i][2], score=fused[i])
                for i in top_ids if i in meta]

    if req.dedup_seconds:
        hits_raw = dedup_by_time(hits_raw, media_index.pts_time, req.dedup_seconds)
    cap = req.per_video_cap if req.per_video_cap is not None else C.DEDUP_DEFAULT
    hits_raw = dedup_by_video(hits_raw, cap)[:req.topk]

    # ============ 3. Dựng kết quả (kèm phân rã khi req.explain) ============
    content_map: dict[str, dict] = {}
    if req.explain and hits_raw:
        content_map = meili.get_frame_docs([h.id for h in hits_raw])

    hits: list[SearchHit] = []
    for rank, h in enumerate(hits_raw, 1):
        explain = None
        content = None
        if req.explain:
            branches = [BranchContribution(**b) for b in detail.get(h.id, [])]
            clause_list: list[ClauseScore] = []
            arr = per_clause_scores.get(h.id)
            if arr:
                for ci, val in enumerate(arr):
                    if ci < len(clauses_mc):
                        clause_list.append(ClauseScore(
                            text=clauses_mc[ci],
                            score=0.0 if val != val else float(val)))   # NaN -> 0
            explain = HitExplain(branches=branches, clauses=clause_list,
                                  penalties=penalties.get(h.id, {}))
            doc = content_map.get(h.id, {})
            pts = media_index.pts_time(h.video, h.n)
            asr_window = []
            if pts is not None:
                asr_window = meili.asr_segments_for_video(
                    h.video, pts - asr_cfg.window_before, pts + asr_cfg.window_after, size=5)
            content = FrameContent(caption=doc.get("caption"), ocr=doc.get("ocr"),
                                    objects=doc.get("objects"), asr_window=asr_window)
        hits.append(SearchHit(
            id=h.id, video=h.video, n=h.n, frame_idx=h.frame_idx, score=h.score,
            thumb_url=f"/media/thumb/{h.video}/{h.n}",
            pts_time=media_index.pts_time(h.video, h.n),
            rank=rank, explain=explain, content=content))

    # ============ 4. Bảng xếp hạng RIÊNG từng nhánh (tab nhánh) ============
    branch_rankings: list[BranchRanking] = []
    if req.branch_lists:
        for name, scored, _w in signal_data:
            ids = [i for i, _ in scored[:BRANCH_LIST_TOPK]]
            bmeta = faiss.fetch_by_ids("metaclip2", ids)
            branch_rankings.append(BranchRanking(branch=name, hits=[
                SearchHit(id=i, video=bmeta[i][0], n=bmeta[i][1], frame_idx=bmeta[i][2],
                           score=s, thumb_url=f"/media/thumb/{bmeta[i][0]}/{bmeta[i][1]}",
                           pts_time=media_index.pts_time(bmeta[i][0], bmeta[i][1]), rank=r)
                for r, (i, s) in enumerate(scored[:BRANCH_LIST_TOPK], 1) if i in bmeta
            ]))

    return SearchResponse(
        hits=hits,
        clauses_metaclip2=clauses_mc,
        clauses_en=clauses_en,
        ocr_keywords=[],
        signals_used=signals_info,
        strict_filter_applied=candidate_ids is not None,
        strict_filter_pool_size=len(candidate_ids) if candidate_ids is not None else None,
        total_candidates=total_candidates,
        took_ms=int((time.time() - t0) * 1000),
        branch_rankings=branch_rankings,
        cache_stats={"vector": vec_cache.stats(), "branch": branch_cache.stats()},
    )


def _asr_semantic_scored(faiss: FaissRepo, media_index: MediaIndex, query_vec,
                          window_before: float, window_after: float) -> list[tuple[str, float]]:
    """Khớp Ý NGHĨA lời thoại (nhánh FAISS asr_emb) rồi align sang khung hình, GIỮ
    điểm. Trả [] êm nếu chưa build nhánh."""
    if not faiss.has_branch("asr_emb"):
        return []
    hits = faiss.search_scored("asr_emb", query_vec, WIDE_TOPK)
    segments = []
    for doc_id, score in hits:
        extra = faiss.get_meta_extra("asr_emb", doc_id, "video", "start", "end")
        if extra is None:
            continue
        video, start, end = extra
        segments.append((video, float(start), float(end), score))
    return _align_scored(segments, media_index, window_before, window_after)
