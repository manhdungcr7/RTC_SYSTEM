"""TRAKE: tìm chuỗi sự kiện E1..En THEO ĐÚNG THỨ TỰ trong CÙNG một video. Port từ
`system/aic/engine.py:search_temporal` (boundary-anchor + DANTE DP) — DP loop giữ
NGUYÊN VẸN (toán cục bộ trong 1 video), chỉ thay nguồn dữ liệu: hệ cũ slice từ ma
trận toàn cục trong RAM, ở đây gọi `milvus_repo.fetch_video_vectors()` lấy vector
của TỪNG video ứng viên (nhẹ, ~100-300 keyframe/video) rồi nhân cục bộ.

THÊM (phát hiện qua test thật — xem hội thoại): chỉ dùng thị giác (metaclip2) KHÔNG
đủ phân biệt các cảnh nhìn GIỐNG NHAU (vd "cắt nấm" vs "cắt cà rốt" — đều là cận
cảnh tay+dao+thớt, khác nguyên liệu vẫn ra cùng 1 kiểu ảnh). `/search` (KIS/QA) đã
có OCR/ASR nhưng `/temporal` thì chưa — giờ thêm OCR/ASR làm ĐIỂM CỘNG THÊM (không
thay thế) vào từng ô của ma trận DP, theo ĐÚNG câu chữ của từng sự kiện.

SỬA THÊM (đã đo lỗi thật trên 3 câu TRAKE mẫu — cả 3 đều chọn SAI VIDEO): điểm
cộng OCR/ASR ở trên chỉ có tác dụng SAU KHI đã có tập video ứng viên (boundary-
anchor). Nhưng boundary-anchor TRƯỚC ĐÓ chỉ search THỊ GIÁC (metaclip2) cho E1/En
— nếu video ĐÚNG không lọt top-per_event theo thị giác thuần (vì "cắt gì đó trên
thớt" giống hệt ở hàng chục video khác), nó KHÔNG BAO GIỜ vào được tập ứng viên,
dù OCR có ghi rõ tên nguyên liệu trên banner. Giờ boundary-anchor cũng tự search
OCR/ASR cho từng sự kiện (`_text_candidate_videos`), ưu tiên video có tín hiệu
CHỮ/LỜI rõ ràng vào tập ứng viên — sửa đúng khâu bị nghẽn, không chỉ tinh chỉnh
thứ tự bên trong tập ứng viên như trước.

SỬA THÊM #2 (theo góp ý người dùng, ví dụ thật): boundary-anchor mặc định LUÔN
neo vào E1+En (`videos_from_topk` cho event ĐẦU và event CUỐI). Nhưng không phải
câu nào E1/En cũng là cặp DỄ NHẬN DIỆN nhất — vd query múa lân 4 sự kiện, cặp
E2+E3 ("4 chân chạm đất" + "2 người cúi chào") đặc trưng/dễ tìm hơn nhiều so với
E1 ("lân xoay vòng trên cột") hay E4 ("rồng cử động đầu", chủ thể phụ). Ép cứng
E1/En bỏ lỡ tín hiệu mạnh ở giữa. Giờ `anchor_indices` cho phép người dùng tự
chọn cặp chỉ số sự kiện dùng làm neo (mặc định None -> vẫn (0, n_ev-1) như cũ,
không phá hành vi hiện có).
"""
from __future__ import annotations

import numpy as np

from core import config as C
from core.fusion import Hit
from core.media_index import MediaIndex
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo

ASR_ALIGN_WINDOW_S = 2.0


def _normalize01(scores: dict) -> dict:
    """Min-max về [0,1] — điểm BM25 KHÔNG cùng thang với cosine similarity (có thể
    là số bất kỳ >0 tuỳ tần suất từ), phải chuẩn hoá trước khi CỘNG vào ma trận DP
    (nếu không, 1 khớp OCR mạnh có thể áp đảo toàn bộ tín hiệu thị giác)."""
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return dict.fromkeys(scores, 1.0)
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _text_bonus_matrix(es_repo: MeiliRepo, media_index: MediaIndex, video: str,
                        ids: list[str], ns: list[int],
                        ocr_texts: list[str], asr_texts: list[str],
                        per_video_size: int = 200) -> np.ndarray:
    """(n_ev, n_kf) điểm cộng OCR+ASR đã chuẩn hoá, CÙNG THỨ TỰ với `ids`/`ns` (đã
    sort theo n tăng dần — xem milvus_repo.fetch_video_vectors). `ocr_texts`/
    `asr_texts`: 1 câu/sự kiện — mặc định là câu event (đã strip khung mẫu), NHƯNG
    người vận hành có thể ghi đè tay riêng cho OCR và riêng cho ASR (khác câu event
    gốc) nếu biết chính xác chữ/lời cần tìm — xem api/routers/temporal.py. Video
    không tồn tại trong index / câu rỗng -> hàng 0 (không cộng, không trừ)."""
    n_ev, n_kf = len(ocr_texts), len(ids)
    bonus = np.zeros((n_ev, n_kf), dtype=np.float64)
    n_to_idx = {n: i for i, n in enumerate(ns)}
    ns_pts = media_index.video_ns_pts(video)   # [(n, pts_time), ...] sort theo n

    for j in range(n_ev):
        ocr_text, asr_text = ocr_texts[j], asr_texts[j]
        if ocr_text.strip():
            # strict=True: BẮT BUỘC khớp TẤT CẢ từ trong câu (Meilisearch mặc định
            # chỉ cần khớp 1 phần) — ĐÃ ĐO THẬT: câu "cắt nấm" cộng điểm cho video
            # KHÔNG liên quan chỉ vì có từ "cắt" (xuất hiện ở MỌI banner "X CẮT Y"
            # của MỌI nguyên liệu), dù không hề có "nấm" — xem module docstring.
            ocr_hits = _normalize01(es_repo.search_frames_scored("ocr_text", ocr_text, video, per_video_size, strict=True))
            for doc_id, score in ocr_hits.items():
                n = int(doc_id.rsplit(":", 1)[-1])
                if n in n_to_idx:
                    bonus[j, n_to_idx[n]] += C.OCR_WEIGHT.get("trake", 0.25) * score

        if not asr_text.strip():
            continue
        asr_segs = es_repo.search_asr_in_video(video, asr_text, per_video_size, strict=True)
        if asr_segs:
            raw = {i: s for i, (_, _, s) in enumerate(asr_segs)}
            norm = _normalize01(raw)
            for n, pts in ns_pts:
                if n not in n_to_idx:
                    continue
                best = 0.0
                for i, (start, end, _) in enumerate(asr_segs):
                    if start - ASR_ALIGN_WINDOW_S <= pts <= end + ASR_ALIGN_WINDOW_S:
                        best = max(best, norm[i])
                if best > 0:
                    bonus[j, n_to_idx[n]] += C.ASR_WEIGHT.get("trake", 0.15) * best
    return bonus


def _text_candidate_videos(es_repo: MeiliRepo, ocr_texts: list[str], asr_texts: list[str],
                            size: int = 150, max_videos: int = 80) -> list[str]:
    """Lọc video ứng viên bằng OCR/ASR (KHÔNG chỉ thị giác) — đã đo thật: cảnh
    "cắt X" nhìn giống hệt nhau qua mọi nguyên liệu (tay+dao+thớt), nên video ĐÚNG
    có thể không lọt top-per_event của boundary-anchor thị giác thuần dù OCR có
    ghi rõ tên nguyên liệu trên banner (vd "CÀ RỐT CẮT HÌNH THOI"). Trả rank-list
    video (giữ thứ tự khớp trước), giới hạn `max_videos` để không lấn át hẳn tập
    ứng viên thị giác nếu 1 event dùng từ quá phổ biến."""
    videos: list[str] = []
    seen: set[str] = set()

    def _add(video: str):
        if video not in seen:
            seen.add(video)
            videos.append(video)

    for text in ocr_texts:
        if not text.strip() or len(videos) >= max_videos:
            break
        for doc_id in es_repo.search_frames("ocr_text", text, size):
            _add(doc_id.split(":", 1)[0])
    for text in asr_texts:
        if not text.strip() or len(videos) >= max_videos:
            break
        for video, *_ in es_repo.search_asr(text, size):
            _add(video)
    return videos[:max_videos]


def search_temporal(event_vecs: np.ndarray, milvus_repo: FaissRepo, collection: str,
                     per_event: int = 1500, topk: int = 100,
                     ocr_texts: list[str] | None = None,
                     asr_texts: list[str] | None = None,
                     es_repo: MeiliRepo | None = None,
                     media_index: MediaIndex | None = None,
                     lam: float | None = None,
                     anchor_indices: tuple[int, int] | None = None) -> list[tuple[float, list[Hit]]]:
    """event_vecs: (n_ev, D) đã encode sẵn (1 vector/sự kiện, thường metaclip2).
    `ocr_texts`/`asr_texts`+`es_repo`+`media_index`: TÙY CHỌN — truyền đủ thì (a)
    boundary-anchor tự search thêm OCR/ASR để mở rộng tập video ứng viên (không
    chỉ thị giác), (b) cộng thêm tín hiệu OCR/ASR vào DP. Thiếu -> chỉ chạy thị
    giác thuần (giữ tương thích ngược, không lỗi).
    `lam`: hệ số phạt khoảng cách DANTE — None dùng mặc định `C.TRAKE_LAMBDA`.
    Đặt 0 khi các sự kiện KHÔNG cần gần nhau về thời gian (vd "vượt lên" rồi rất
    lâu sau mới "về đích" — ép gần nhau như mặc định sẽ sai giả định).
    `anchor_indices`: (i, j) chỉ số 2 sự kiện dùng làm NEO thị giác cho boundary-
    anchor — None dùng mặc định (0, n_ev-1) tức E1/En. Đặt tay khi biết cặp sự
    kiện KHÁC dễ nhận diện thị giác hơn (vd sự kiện ở giữa đặc trưng hơn đầu/cuối).
    Trả list (total_score, hits) — hits = list n_ev Hit (1 hit/sự kiện, đúng thứ
    tự E1..En), sort theo total_score giảm dần."""
    n_ev = event_vecs.shape[0]
    if n_ev == 0:
        return []
    use_text = ocr_texts is not None and asr_texts is not None and es_repo is not None and media_index is not None

    # --- Neo boundary: video có cả 2 sự kiện neo trong top-per_event (MADTempo) ---
    # videos_from_topk() GIỮ THỨ TỰ rank -> cắt về MAX_TRAKE_CANDIDATES vẫn ưu tiên
    # đúng video liên quan nhất, không cắt ngẫu nhiên (xem lý do trong core.config).
    a, b = anchor_indices if anchor_indices is not None else (0, n_ev - 1)
    v_first = milvus_repo.videos_from_topk(collection, event_vecs[a], per_event)
    v_last = milvus_repo.videos_from_topk(collection, event_vecs[b], per_event) if n_ev >= 2 and b != a else []
    set_first, set_last = set(v_first), set(v_last)
    inter = set_first & set_last
    if len(inter) >= 20:
        cand_videos = [v for v in v_first if v in inter]
    else:
        cand_videos = list(dict.fromkeys(v_first + v_last))

    if use_text:
        # Video có tín hiệu chữ/lời RÕ được ưu tiên ĐẦU danh sách — text hiếm/chính
        # xác hơn thị giác chung chung, xứng đáng thắng khi bị cắt bớt bởi MAX_TRAKE_CANDIDATES.
        text_videos = _text_candidate_videos(es_repo, ocr_texts, asr_texts)
        cand_videos = list(dict.fromkeys(text_videos + cand_videos))
    cand_videos = cand_videos[:C.MAX_TRAKE_CANDIDATES]

    lam = C.TRAKE_LAMBDA if lam is None else lam
    results = []
    for video in cand_videos:
        ids, ns, frame_idxs, vecs = milvus_repo.fetch_video_vectors(collection, video)
        n_kf = len(ids)
        if n_kf < n_ev:
            continue
        sub = event_vecs @ vecs.T                          # (n_ev, n_kf)
        if use_text:
            sub = sub + _text_bonus_matrix(es_repo, media_index, video, ids, ns, ocr_texts, asr_texts)

        # DP: best[j][t] = điểm tốt nhất khi sự kiện j khớp keyframe t, chuỗi tăng
        # dần theo thời gian. DANTE: phạt khoảng cách λ(t-τ). Port nguyên engine.py:355-380.
        best = np.full((n_ev, n_kf), -np.inf, dtype=np.float64)
        back = np.zeros((n_ev, n_kf), dtype=np.int32)
        best[0] = sub[0]
        for j in range(1, n_ev):
            run_val, run_arg = -np.inf, -1
            for t in range(n_kf):
                if t > 0:
                    cand = best[j - 1, t - 1] + lam * (t - 1)
                    if cand > run_val:
                        run_val, run_arg = cand, t - 1
                if run_arg >= 0:
                    best[j, t] = sub[j, t] + run_val - lam * t
                    back[j, t] = run_arg

        t_end = int(np.argmax(best[-1]))
        if not np.isfinite(best[-1, t_end]):
            continue

        path = [t_end]
        for j in range(n_ev - 1, 0, -1):
            path.append(int(back[j, path[-1]]))
        path.reverse()

        total = float(best[-1, t_end]) / n_ev
        hits = [Hit(id=ids[t], video=video, n=ns[t], frame_idx=frame_idxs[t], score=float(sub[j, t]))
                for j, t in enumerate(path)]
        results.append((total, hits))

    results.sort(key=lambda x: -x[0])
    return results[:topk]
