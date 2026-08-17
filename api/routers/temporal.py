"""POST /temporal — TRAKE (chuỗi sự kiện theo thứ tự trong cùng video).

BÀN TRỘN TÍN HIỆU (mục "Temporal cũng có cơ chế chỉnh trọng số như Search"):
CHỈ đổi CÁCH CHẤM ĐIỂM từng khung hình (cộng thêm cosine similarity theo từng
nhánh, có trọng số) — thuật toán DP/boundary-anchor/DANTE giữ NGUYÊN VẸN, xem
core.temporal.search_temporal. metaclip2 luôn là nhánh chính (mặc định weight=1,
dùng để neo biên); pecore/beit3/capemb là nhánh PHỤ, tắt theo mặc định, người
dùng tự bật khi câu mô tả chi tiết mà thị giác thuần chưa phân biệt được.
OCR/ASR CŨNG là 2 kênh trên bàn trộn (mặc định BẬT, weight=C.OCR_WEIGHT/
C.ASR_WEIGHT["trake"]) — câu chữ/lời vẫn nhập RIÊNG từng sự kiện như cũ
(req.ocr_queries[i]/asr_queries[i]), signals["ocr"]/["asr"] chỉ điều khiển có
tính điểm đó vào DP hay không và tính bao nhiêu, giống hệt semantics của các
nhánh thị giác — xem _signal().

KHÔNG PHẠT KHOẢNG CÁCH THỜI GIAN (theo yêu cầu): luôn gọi search_temporal với
lam=0.0, không còn nhận lambda_penalty từ client.

TÁCH MỆNH ĐỀ TỪNG SỰ KIỆN (giống Search): mỗi câu event được tách thành nhiều
mệnh đề thị giác trước khi encode (core.query_service.clauses_metaclip2), sự
kiện 1 vế ngắn thì tách ra vẫn còn 1 phần tử — không đổi gì. Chỉ sự kiện dài,
nhiều chi tiết mới thật sự đổi cách chấm điểm (max+mean qua mệnh đề thay vì
1 vector nguyên khối) — xem core.temporal.search_temporal. Mệnh đề THỰC SỰ đã
dùng được trả kèm trong response (`event_clauses`) để người dùng xem được máy
đang hiểu câu thế nào — trước đây chỉ chạy ngầm, không có gì để kiểm tra.

PHẢN HỒI LIÊN QUAN (Rocchio, giống Search): `req.feedback[j]` dịch vector CỦA
ĐÚNG sự kiện j theo khung ✓/✗ người dùng đánh dấu cho sự kiện đó — xem
core.fusion.rocchio. Chỉ đổi vector đầu vào, không đụng DP/boundary-anchor.
"""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends

from api.deps import get_encoders, get_faiss, get_media_index, get_meili
from api.schemas.search import FrameContent, SearchHit
from api.schemas.temporal import (TemporalCandidate, TemporalEventHit, TemporalRequest,
                                   TemporalResponse)
from core import config as C
from core import translate
from core.media_index import MediaIndex
from core.query_encoders import QueryEncoders
from core.fusion import rocchio
from core.query_service import clauses_metaclip2, strip_temporal_framing
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo
from core.temporal import search_temporal

router = APIRouter()

# Nhánh THỊ GIÁC phụ có thể bật cho Temporal — asr_emb/dinov3/object/ocr/asr
# KHÔNG nằm ở đây vì đã có đường riêng (ocr_queries/asr_queries mỗi sự kiện,
# hoặc không có tương đương hợp lý cho 1 mô tả sự kiện — vd dinov3 cần 1 ảnh mẫu).
AUX_BRANCHES = ("pecore", "beit3", "capemb")


def _signal(req: TemporalRequest, name: str, default_enabled: bool, default_weight: float
            ) -> tuple[bool, float]:
    if req.signals and name in req.signals:
        cfg = req.signals[name]
        return cfg.enabled, (cfg.weight if cfg.weight is not None else default_weight)
    return default_enabled, default_weight


def _encode_branch_events(encoders: QueryEncoders, branch: str, texts: list[str]) -> np.ndarray | None:
    """Encode N câu -> N vector RIÊNG (không pool) cho 1 nhánh — dùng .encode()
    nếu có (mọi encoder từ xa đều có, kể cả beit3 — xem RemoteBranchEncoder);
    rơi về gọi encode_one() từng câu một nếu chỉ có bản local (Beit3BridgeEncoder
    chỉ hỗ trợ pool, phải gọi riêng từng câu mới ra N vector tách biệt)."""
    enc = getattr(encoders, branch, None)
    if enc is None:
        return None
    if hasattr(enc, "encode"):
        try:
            return enc.encode(texts)
        except Exception as e:
            print(f"[temporal] encode '{branch}' lỗi ({type(e).__name__}: {e}) -> bỏ qua nhánh")
            return None
    if hasattr(enc, "encode_one"):
        rows = []
        for t in texts:
            v = enc.encode_one([t])
            if v is None:
                return None
            rows.append(v)
        return np.stack(rows)
    return None


@router.post("/temporal", response_model=TemporalResponse)
def temporal(req: TemporalRequest,
             faiss: FaissRepo = Depends(get_faiss),
             meili: MeiliRepo = Depends(get_meili),
             encoders: QueryEncoders = Depends(get_encoders),
             media_index: MediaIndex = Depends(get_media_index)) -> TemporalResponse:
    # Cắt khung mẫu "Khoảnh khắc đầu tiên/cuối cùng thấy..." TRƯỚC khi dùng cho cả
    # encode thị giác lẫn OCR/ASR — ĐO THẬT: giữ nguyên khung mẫu làm OCR khớp NHẦM
    # theo từ chung ("khoảnh khắc","cắt"...) thay vì từ phân biệt thật (xem
    # core.query_service.strip_temporal_framing).
    cleaned = [strip_temporal_framing(e) for e in req.events]
    # `context` (mô tả chung đầu câu, vd "múa lân con lân vàng đen trắng") được
    # CHÈN VÀO MỌI sự kiện trước khi encode — giúp các nhánh vector "thấy" được
    # bối cảnh chung mà 1 câu sự kiện ngắn không nói lại (màu sắc, chủ thể chung),
    # KHÔNG đụng gì tới thuật toán DP/boundary-anchor phía sau, chỉ làm vector
    # từng sự kiện "đặc" hơn trước khi so khớp.
    texts = [f"{req.context} {e}".strip() if req.context else e for e in cleaned]

    # Tách mệnh đề TỪNG sự kiện — giống Search (đã đo: câu dài encode nguyên khối
    # loãng tín hiệu, tách mệnh đề riêng thì GT xếp hạng tốt hơn). Sự kiện ngắn 1
    # vế (đa số case TRAKE) -> clauses_metaclip2 trả về đúng 1 phần tử, kết quả y
    # hệt hành vi cũ (search_temporal tự nhận biết case 1-mệnh-đề, xem core.
    # temporal.py). CHỈ đổi ĐẦU VÀO của bước encode, không đụng DP/boundary-anchor.
    # `clauses_override[i]` (nếu có) THẮNG tách tự động — người dùng tự viết lại
    # mệnh đề cho ĐÚNG sự kiện đó, sự kiện không ghi đè vẫn tách tự động như cũ.
    def _clauses_for(i: int, text: str) -> list[str]:
        override = req.clauses_override.get(i) if req.clauses_override else None
        if override:
            cleaned_override = [c.strip() for c in override if c.strip()]
            if cleaned_override:
                return cleaned_override
        if not req.split_clauses:
            return [text]
        return clauses_metaclip2(text) or [text]

    event_clauses = [_clauses_for(i, t) for i, t in enumerate(texts)]
    flat_texts = [c for clist in event_clauses for c in clist]
    flat_vecs = encoders.metaclip2.encode(flat_texts)
    event_clause_vecs: list[np.ndarray] = []
    _pos = 0
    for clist in event_clauses:
        k = len(clist)
        event_clause_vecs.append(np.asarray(flat_vecs[_pos:_pos + k]))
        _pos += k

    # Phản hồi liên quan (Rocchio) RIÊNG từng sự kiện — đánh dấu ✓/✗ trên khung
    # của sự kiện j chỉ dịch vector CỦA ĐÚNG sự kiện đó (mỗi sự kiện tìm 1
    # khoảnh khắc khác nhau trong cùng video, không nên trộn phản hồi giữa các
    # sự kiện). Áp dụng cho MỌI mệnh đề của sự kiện đó (nếu đã bị tách >1 mệnh
    # đề) — cùng 1 độ dịch chuyển cho tất cả, đơn giản và nhất quán. CHỈ đổi
    # vector đầu vào trước khi đưa vào search_temporal, không đụng DP.
    if req.feedback:
        for j, fb in req.feedback.items():
            if j < 0 or j >= len(event_clause_vecs) or not (fb.positive or fb.negative):
                continue
            event_clause_vecs[j] = np.stack([
                rocchio(v, "metaclip2", faiss, fb.positive, fb.negative, fb.beta, fb.gamma)
                for v in event_clause_vecs[j]
            ])

    # OCR/ASR mặc định dùng câu event đã cắt khung mẫu — NHƯNG người vận hành có
    # thể ghi đè tay RIÊNG từng sự kiện (req.ocr_queries[i]/asr_queries[i]) khi
    # biết chính xác chữ/lời cần tìm, bỏ qua đoán tự động cho đúng sự kiện đó
    # (các sự kiện không ghi đè vẫn dùng tự động — không phải tất-cả-hoặc-không-gì).
    def _override(manual: list[str] | None, i: int, fallback: str) -> str:
        if manual and i < len(manual) and manual[i].strip():
            return manual[i]
        return fallback

    # OCR/ASR CŨNG lên bàn trộn (giống Search) — bật/tắt + chỉnh trọng số đóng góp
    # của điểm khớp chữ/lời vào từng ô DP. Mặc định BẬT (giữ hành vi cũ: OCR/ASR
    # luôn được thử với câu event tự động), người dùng tự tắt hoặc hạ/tăng trọng
    # số khi thấy nó kéo lệch kết quả. TẮT -> gửi câu rỗng cho mọi sự kiện, tận
    # dụng lại logic "câu rỗng = bỏ qua" đã có sẵn trong _text_bonus_matrix.
    ocr_on, ocr_weight = _signal(req, "ocr", True, C.OCR_WEIGHT.get("trake", 0.25))
    asr_on, asr_weight = _signal(req, "asr", True, C.ASR_WEIGHT.get("trake", 0.15))
    ocr_texts = [_override(req.ocr_queries, i, t) for i, t in enumerate(texts)] if ocr_on else ["" for _ in texts]
    asr_texts = [_override(req.asr_queries, i, t) for i, t in enumerate(texts)] if asr_on else ["" for _ in texts]

    # ============ Bàn trộn: mã hoá thêm cho nhánh phụ được bật ============
    mc_enabled, mc_weight = _signal(req, "metaclip2", True, 1.0)
    en_texts: list[str] | None = None
    aux_branches: list[tuple[str, np.ndarray, float]] = []
    for branch in AUX_BRANCHES:
        enabled, weight = _signal(req, branch, False, {"pecore": 0.3, "beit3": 0.2, "capemb": 0.5}[branch])
        if not enabled or weight == 0:
            continue
        if branch == "capemb":
            src_texts = texts               # đa ngữ, không cần dịch
        else:
            if en_texts is None:
                en_texts = translate.vi2en(texts) if translate.available() else texts
            src_texts = en_texts
        vecs = _encode_branch_events(encoders, branch, src_texts)
        if vecs is not None and len(vecs) == len(texts):
            aux_branches.append((branch, vecs, weight))

    anchor = tuple(req.anchor_indices) if req.anchor_indices and len(req.anchor_indices) == 2 else None
    results = search_temporal(
        event_clause_vecs, faiss, "metaclip2", per_event=req.per_event, topk=req.topk,
        ocr_texts=ocr_texts, asr_texts=asr_texts, meili_repo=meili, media_index=media_index,
        lam=0.0,   # LUÔN không phạt khoảng cách thời gian — xem docstring module
        anchor_indices=anchor,
        video_scope=req.video_scope,
        locked_frames=req.locked_frames,
        gap_constraints=[{"from": g.from_, "to": g.to, "min_s": g.min_s, "max_s": g.max_s}
                          for g in (req.gap_constraints or [])],
        alternates_per_event=req.alternates_per_event,
        metaclip2_weight=(mc_weight if mc_enabled else 1.0),
        aux_branches=aux_branches,
        ocr_weight=ocr_weight,
        asr_weight=asr_weight,
    )

    # ============ Nội dung đầy đủ (OCR/caption/object/ASR quanh đây) cho MỌI
    # khung hình được trả về — không chỉ khung hạng cao nhất, xem yêu cầu "Giải
    # thích phải hiển thị đủ thông tin cho bất kỳ frame nào được bấm vào". ============
    all_ids = [h.id for _, hits, alts in results for h in hits] + \
              [a.id for _, hits, alts in results for alt_list in alts for a in alt_list]
    content_map = meili.get_frame_docs(list(dict.fromkeys(all_ids))) if all_ids else {}

    def _content_for(video: str, n: int, doc_id: str) -> FrameContent | None:
        doc = content_map.get(doc_id)
        if doc is None:
            return None
        pts = media_index.pts_time(video, n)
        asr_window = []
        if pts is not None:
            asr_window = meili.asr_segments_for_video(video, pts - 5, pts + 8, size=5)
        return FrameContent(caption=doc.get("caption"), ocr=doc.get("ocr"),
                             objects=doc.get("objects"), asr_window=asr_window)

    def _hit(h, alts=None) -> TemporalEventHit:
        return TemporalEventHit(
            id=h.id, video=h.video, n=h.n, frame_idx=h.frame_idx, score=h.score,
            thumb_url=f"/media/thumb/{h.video}/{h.n}",
            pts_time=media_index.pts_time(h.video, h.n),
            content=_content_for(h.video, h.n, h.id),
            alternates=[SearchHit(id=a.id, video=a.video, n=a.n, frame_idx=a.frame_idx,
                                   score=a.score, thumb_url=f"/media/thumb/{a.video}/{a.n}",
                                   pts_time=media_index.pts_time(a.video, a.n),
                                   content=_content_for(a.video, a.n, a.id))
                        for a in (alts or [])],
        )

    candidates = [
        TemporalCandidate(
            video=hits[0].video,
            total_score=total,
            hits=[_hit(h, alts[j] if j < len(alts) else None) for j, h in enumerate(hits)],
        )
        for total, hits, alts in results
    ]
    return TemporalResponse(candidates=candidates, event_clauses=event_clauses)
