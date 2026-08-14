"""TRAKE: tìm chuỗi sự kiện E1..En THEO ĐÚNG THỨ TỰ trong CÙNG một video. Port từ
`system/aic/engine.py:search_temporal` (boundary-anchor + DANTE DP) — DP loop giữ
NGUYÊN VẸN (toán cục bộ trong 1 video), chỉ thay nguồn dữ liệu: hệ cũ slice từ ma
trận toàn cục trong RAM, ở đây gọi `faiss_repo.fetch_video_vectors()` lấy vector
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
    """KHÔNG còn min-max theo từng video — ĐÃ ĐO LỖI THẬT: min-max riêng trong
    từng video luôn kéo khớp MẠNH NHẤT của video đó lên 1.0, dù khớp đó chỉ là
    rác so với video khác — hàm này vốn dùng để CHỌN ĐÚNG VIDEO (so sánh CHÉO
    giữa các video ứng viên, xem docstring search_temporal), min-max theo từng
    video làm phẳng mất chính khả năng so sánh đó. Meilisearch _rankingScore đã
    tự nhiên nằm trong [0,1] toàn cục (xem core.config, cùng giả định dùng ở
    OCR_FILTER_CONFIDENCE/ASR_FILTER_CONFIDENCE) — dùng thẳng điểm thô, so sánh
    được xuyên suốt mọi video ứng viên."""
    return dict(scores)


def _text_bonus_matrix(meili_repo: MeiliRepo, media_index: MediaIndex, video: str,
                        ids: list[str], ns: list[int],
                        ocr_texts: list[str], asr_texts: list[str],
                        ocr_weight: float | None = None, asr_weight: float | None = None,
                        per_video_size: int = 200) -> np.ndarray:
    """(n_ev, n_kf) điểm cộng OCR+ASR đã chuẩn hoá, CÙNG THỨ TỰ với `ids`/`ns` (đã
    sort theo n tăng dần — xem faiss_repo.fetch_video_vectors). `ocr_texts`/
    `asr_texts`: 1 câu/sự kiện — mặc định là câu event (đã strip khung mẫu), NHƯNG
    người vận hành có thể ghi đè tay riêng cho OCR và riêng cho ASR (khác câu event
    gốc) nếu biết chính xác chữ/lời cần tìm — xem api/routers/temporal.py.
    `ocr_weight`/`asr_weight`: None = dùng hằng số C.OCR_WEIGHT/C.ASR_WEIGHT["trake"]
    (hành vi cũ); truyền số khác để NGƯỜI DÙNG tự chỉnh qua bàn trộn (giống Search)
    — CHỈ đổi trọng số cộng điểm, không đụng cách tính bonus. Video không tồn tại
    trong index / câu rỗng -> hàng 0 (không cộng, không trừ)."""
    ocr_w = C.OCR_WEIGHT.get("trake", 0.25) if ocr_weight is None else ocr_weight
    asr_w = C.ASR_WEIGHT.get("trake", 0.15) if asr_weight is None else asr_weight
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
            ocr_hits = _normalize01(meili_repo.search_frames_scored("ocr_text", ocr_text, video, per_video_size, strict=True))
            for doc_id, score in ocr_hits.items():
                n = int(doc_id.rsplit(":", 1)[-1])
                if n in n_to_idx:
                    bonus[j, n_to_idx[n]] += ocr_w * score

        if not asr_text.strip():
            continue
        asr_segs = meili_repo.search_asr_in_video(video, asr_text, per_video_size, strict=True)
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
                    bonus[j, n_to_idx[n]] += asr_w * best
    return bonus


def _text_candidate_videos(meili_repo: MeiliRepo, ocr_texts: list[str], asr_texts: list[str],
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
        for doc_id in meili_repo.search_frames("ocr_text", text, size):
            _add(doc_id.split(":", 1)[0])
    for text in asr_texts:
        if not text.strip() or len(videos) >= max_videos:
            break
        for video, *_ in meili_repo.search_asr(text, size):
            _add(video)
    return videos[:max_videos]


def _videos_from_topk_clauses(faiss_repo: FaissRepo, collection: str,
                               clause_vecs: np.ndarray, per_event: int) -> list[str]:
    """Như faiss_repo.videos_from_topk() nhưng nhận NHIỀU vector mệnh đề của CÙNG 1
    sự kiện (xem search_temporal::event_clause_vecs) — search RIÊNG từng mệnh đề
    rồi hợp union video (giữ thứ tự rank, mệnh đề nào ra trước ưu tiên trước),
    cùng nguyên tắc với core.query_service.clauses_metaclip2/core.fusion.
    maxmean_clauses: 1 mệnh đề (đa số case TRAKE) -> giống hệt gọi trực tiếp
    videos_from_topk() cũ, không đổi hành vi."""
    if clause_vecs.shape[0] == 1:
        return faiss_repo.videos_from_topk(collection, clause_vecs[0], per_event)
    videos: list[str] = []
    seen: set[str] = set()
    for vec in clause_vecs:
        for v in faiss_repo.videos_from_topk(collection, vec, per_event):
            if v not in seen:
                seen.add(v)
                videos.append(v)
    return videos[:per_event]


def search_temporal(event_clause_vecs: list[np.ndarray], faiss_repo: FaissRepo, collection: str,
                     per_event: int = 1500, topk: int = 100,
                     ocr_texts: list[str] | None = None,
                     asr_texts: list[str] | None = None,
                     meili_repo: MeiliRepo | None = None,
                     media_index: MediaIndex | None = None,
                     lam: float = 0.0,
                     anchor_indices: tuple[int, int] | None = None,
                     video_scope: list[str] | None = None,
                     locked_frames: list[int | None] | None = None,
                     gap_constraints: list[dict] | None = None,
                     alternates_per_event: int = 0,
                     metaclip2_weight: float = 1.0,
                     aux_branches: list[tuple[str, np.ndarray, float]] | None = None,
                     ocr_weight: float | None = None,
                     asr_weight: float | None = None,
                     ) -> list[tuple[float, list[Hit], list[list[Hit]]]]:
    """event_clause_vecs: list N phần tử (1/sự kiện), mỗi phần tử là mảng
    (n_clauses_i, D) đã encode sẵn (thường metaclip2) — sự kiện càng dài/nhiều
    chi tiết thì càng nên tách nhiều mệnh đề trước khi encode (xem core.
    query_service.clauses_metaclip2), TƯƠNG TỰ Search: câu dài encode nguyên
    khối làm loãng tín hiệu — đã đo. Sự kiện 1 mệnh đề (đa số case TRAKE ngắn
    gọn) dùng ĐÚNG 1 vector, giống hệt hành vi cũ (không đổi điểm).
    `ocr_texts`/`asr_texts`+`meili_repo`+`media_index`: TÙY CHỌN — truyền đủ thì (a)
    boundary-anchor tự search thêm OCR/ASR để mở rộng tập video ứng viên (không
    chỉ thị giác), (b) cộng thêm tín hiệu OCR/ASR vào DP. Thiếu -> chỉ chạy thị
    giác thuần (giữ tương thích ngược, không lỗi).
    `lam`: hệ số phạt khoảng cách DANTE — MẶC ĐỊNH 0 (KHÔNG phạt). Trước đây từng
    đo λ=0.001 nhỉnh hơn λ=0 trên một bộ 11 mẫu tự tạo (xem core/config.py::
    TRAKE_LAMBDA, còn giữ nguyên giá trị cho tham khảo), nhưng bộ đo đó nhỏ và tự
    xây (có thể lệch — xem cảnh báo GT-bias trong ghi chú dự án). Theo yêu cầu
    người dùng: KHÔNG giả định các sự kiện phải gần nhau về thời gian — nhiều
    chuỗi thật có khoảng cách rất khác nhau giữa các sự kiện, ép sát bằng phạt
    mặc định dễ sai hơn là để tự do và dựa vào tín hiệu thị giác/chữ/lời thật.

    `metaclip2_weight`: trọng số nhân vào điểm thị giác CHÍNH trước khi cộng các
    nhánh phụ — mặc định 1.0 (giữ nguyên hành vi cũ khi không có nhánh phụ nào).
    Sự kiện nhiều mệnh đề dùng công thức max+alpha*mean giống Search (core.
    fusion.maxmean_clauses, alpha=C.MAXMEAN_ALPHA) — CHỈ khác Search ở chỗ tính
    ĐÚNG (không cần xấp xỉ qua FAISS search) vì trong 1 video ứng viên đã có sẵn
    TOÀN BỘ vector trong RAM (`vecs`), không phải xấp xỉ qua top-K như khi tìm
    trên toàn kho 167,850 khung hình.

    `aux_branches`: các nhánh BỔ TRỢ góp thêm vào điểm mỗi khung hình — list
    (tên_nhánh, vector_sự_kiện (n_ev, D_nhánh), trọng_số). CHỈ thay đổi CÁCH
    CHẤM ĐIỂM từng ô của DP (cộng thêm cosine similarity theo nhánh đó), thuật
    toán DP/boundary-anchor/DANTE giữ NGUYÊN VẸN — đúng yêu cầu "cập nhật chỗ
    chấm điểm, không đụng thuật toán".

    `ocr_weight`/`asr_weight`: trọng số cộng điểm OCR/ASR — None = dùng hằng số
    cũ (C.OCR_WEIGHT/C.ASR_WEIGHT["trake"]), người dùng tự chỉnh qua bàn trộn
    (giống các nhánh thị giác) khi cần OCR/ASR đóng góp nhiều/ít hơn mặc định.
    `anchor_indices`: (i, j) chỉ số 2 sự kiện dùng làm NEO thị giác cho boundary-
    anchor — None dùng mặc định (0, n_ev-1) tức E1/En. Đặt tay khi biết cặp sự
    kiện KHÁC dễ nhận diện thị giác hơn (vd sự kiện ở giữa đặc trưng hơn đầu/cuối).

    `video_scope`: chỉ dò trong tập video này (thu hẹp trước khi tìm chuỗi).

    `locked_frames`: song song với sự kiện — frame_idx mà NGƯỜI DÙNG ĐÃ TỰ TÌM RA
    và chắc chắn đúng. DP bị ép đi qua đúng khung đó, chỉ còn phải tìm các sự
    kiện còn lại quanh điểm neo. Đây là đòn bẩy mạnh nhất cho chuỗi dài: mỗi lần
    khoá được một sự kiện, không gian tìm kiếm co lại đáng kể. Không có nó thì
    người dùng KHÔNG có cách nào góp kiến thức đã biết chắc vào thuật toán.

    `gap_constraints`: [{from, to, min_s, max_s}] — ràng buộc khoảng cách THỜI
    GIAN giữa từng cặp sự kiện. Mạnh hơn hẳn một hệ số phạt λ toàn cục: "E2 phải
    xảy ra trong vòng 30 giây sau E1" là kiến thức con người có mà máy không có.

    `alternates_per_event`: trả kèm K khung hình thay thế tốt nhất cho MỖI vị trí
    sự kiện, để người dùng đổi nhanh một mắt xích yếu mà không phải chạy lại cả DP.

    Trả list (total_score, hits, alternates) — hits = n_ev Hit đúng thứ tự E1..En;
    alternates[j] = danh sách khung thay thế cho sự kiện j (rỗng nếu không yêu cầu)."""
    n_ev = len(event_clause_vecs)
    if n_ev == 0:
        return []
    use_text = ocr_texts is not None and asr_texts is not None and meili_repo is not None and media_index is not None

    # --- Neo boundary: video có cả 2 sự kiện neo trong top-per_event (MADTempo) ---
    # videos_from_topk() GIỮ THỨ TỰ rank -> cắt về MAX_TRAKE_CANDIDATES vẫn ưu tiên
    # đúng video liên quan nhất, không cắt ngẫu nhiên (xem lý do trong core.config).
    # Sự kiện neo nhiều mệnh đề -> search RIÊNG từng mệnh đề rồi hợp union video
    # (_videos_from_topk_clauses), 1 mệnh đề thì y hệt gọi thẳng videos_from_topk().
    a, b = anchor_indices if anchor_indices is not None else (0, n_ev - 1)
    v_first = _videos_from_topk_clauses(faiss_repo, collection, event_clause_vecs[a], per_event)
    v_last = (_videos_from_topk_clauses(faiss_repo, collection, event_clause_vecs[b], per_event)
              if n_ev >= 2 and b != a else [])
    set_first, set_last = set(v_first), set(v_last)
    inter = set_first & set_last
    if len(inter) >= 20:
        cand_videos = [v for v in v_first if v in inter]
    else:
        cand_videos = list(dict.fromkeys(v_first + v_last))

    if use_text:
        # Video có tín hiệu chữ/lời RÕ được ưu tiên ĐẦU danh sách — text hiếm/chính
        # xác hơn thị giác chung chung, xứng đáng thắng khi bị cắt bớt bởi MAX_TRAKE_CANDIDATES.
        text_videos = _text_candidate_videos(meili_repo, ocr_texts, asr_texts)
        cand_videos = list(dict.fromkeys(text_videos + cand_videos))

    if video_scope:
        allowed = set(video_scope)
        cand_videos = [v for v in cand_videos if v in allowed]
    # Khoá khung hình ngụ ý khoá luôn VIDEO — chỉ dò trong video chứa khung đó.
    if locked_frames and any(f is not None for f in locked_frames):
        locked_videos = _videos_containing_frames(faiss_repo, collection, locked_frames)
        if locked_videos:
            cand_videos = [v for v in cand_videos if v in locked_videos] or sorted(locked_videos)

    cand_videos = cand_videos[:C.MAX_TRAKE_CANDIDATES]

    gaps = _parse_gaps(gap_constraints, n_ev)
    results = []

    for video in cand_videos:
        ids, ns, frame_idxs, vecs = faiss_repo.fetch_video_vectors(collection, video)
        n_kf = len(ids)
        if n_kf < n_ev:
            continue
        # Sự kiện 1 mệnh đề: điểm = cosine thẳng, y hệt hành vi cũ. Sự kiện nhiều
        # mệnh đề: max+alpha*mean qua các mệnh đề — TÍNH ĐÚNG (không xấp xỉ) vì
        # `vecs` đã là TOÀN BỘ khung hình của video này, có sẵn trong RAM.
        sub = np.empty((n_ev, vecs.shape[0]), dtype=np.float64)
        for j, cvecs in enumerate(event_clause_vecs):
            if cvecs.shape[0] == 1:
                sub[j] = cvecs[0] @ vecs.T
            else:
                sims = cvecs @ vecs.T                       # (n_clauses_j, n_kf)
                sub[j] = sims.max(axis=0) + C.MAXMEAN_ALPHA * sims.mean(axis=0)
        sub *= metaclip2_weight
        for branch, br_vecs, br_weight in (aux_branches or []):
            if br_weight == 0:
                continue
            contrib = _aligned_branch_scores(faiss_repo, branch, video, ns, br_vecs)
            if contrib is not None:
                sub = sub + br_weight * contrib
        if use_text:
            sub = sub + _text_bonus_matrix(meili_repo, media_index, video, ids, ns, ocr_texts, asr_texts,
                                            ocr_weight=ocr_weight, asr_weight=asr_weight)

        # Khoá khung: ép sự kiện j chỉ được khớp đúng vị trí đã khoá bằng cách
        # đặt -inf cho mọi vị trí khác (thay vì sửa vòng DP — giữ vòng lặp nguyên vẹn).
        if locked_frames:
            sub = sub.copy()
            for j, want in enumerate(locked_frames[:n_ev]):
                if want is None:
                    continue
                pos = next((t for t, fi in enumerate(frame_idxs) if fi == want), None)
                if pos is None:
                    sub[j, :] = -np.inf          # video này không chứa khung đã khoá
                else:
                    masked = np.full(n_kf, -np.inf)
                    masked[pos] = sub[j, pos]
                    sub[j] = masked
            if not np.isfinite(sub).any():
                continue

        pts = [media_index.pts_time(video, n) if media_index else None for n in ns]
        best, back = _run_dp(sub, lam, gaps, pts)

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

        alts: list[list[Hit]] = [[] for _ in range(n_ev)]
        if alternates_per_event > 0:
            for j, t_chosen in enumerate(path):
                lo = path[j - 1] + 1 if j > 0 else 0
                hi = path[j + 1] if j < n_ev - 1 else n_kf
                # Chỉ đề xuất khung VẪN GIỮ ĐÚNG thứ tự thời gian với 2 sự kiện kề,
                # nên đổi sang khung thay thế không bao giờ làm chuỗi thành không hợp lệ.
                window = [t for t in range(max(0, lo), min(n_kf, hi))
                          if t != t_chosen and np.isfinite(sub[j, t])]
                window.sort(key=lambda t: -sub[j, t])
                alts[j] = [Hit(id=ids[t], video=video, n=ns[t], frame_idx=frame_idxs[t],
                                score=float(sub[j, t]))
                           for t in window[:alternates_per_event]]

        results.append((total, hits, alts))

    results.sort(key=lambda x: -x[0])
    return results[:topk]


def _aligned_branch_scores(faiss_repo: FaissRepo, branch: str, video: str,
                            ns: list[int], event_vecs_branch: np.ndarray) -> np.ndarray | None:
    """cosine(event, khung hình) cho MỘT NHÁNH PHỤ (pecore/beit3/capemb...), CĂN
    ĐÚNG theo chỉ số `n` với ma trận `sub` chính (không giả định thứ tự/tập khung
    hình 2 nhánh trùng nhau tuyệt đối — tra qua dict cho chắc). Khung hình nhánh
    phụ KHÔNG có (hiếm, lệch dữ liệu) -> góp 0 cho khung đó, không phạt, không lỗi."""
    ids2, ns2, _, vecs2 = faiss_repo.fetch_video_vectors(branch, video)
    if not ns2:
        return None
    n_to_idx2 = {n: i for i, n in enumerate(ns2)}
    n_kf = len(ns)
    aligned = np.zeros((n_kf, vecs2.shape[1]), dtype=np.float32)
    for i, n in enumerate(ns):
        j = n_to_idx2.get(n)
        if j is not None:
            aligned[i] = vecs2[j]
    return event_vecs_branch @ aligned.T   # (n_ev, n_kf)


def _videos_containing_frames(repo: FaissRepo, collection: str,
                               locked: list[int | None]) -> set[str]:
    """Video nào chứa TẤT CẢ các frame_idx đã khoá — giao các tập lại."""
    wanted = [f for f in locked if f is not None]
    if not wanted:
        return set()
    meta = repo._meta[collection]                      # noqa: SLF001
    out: set[str] | None = None
    for f in wanted:
        vids = set(meta.loc[meta["frame_idx"] == f, "video"].unique())
        out = vids if out is None else (out & vids)
        if not out:
            return set()
    return out or set()


def _parse_gaps(gap_constraints: list[dict] | None, n_ev: int) -> dict[int, tuple[float, float]]:
    """{chỉ số sự kiện sau: (min_s, max_s)} cho các cặp LIỀN KỀ. Cặp không liền kề
    bị bỏ qua — DP chỉ nhìn được bước chuyển giữa hai sự kiện kề nhau, hứa hỗ trợ
    cặp bất kỳ rồi âm thầm không áp dụng sẽ tệ hơn là nói rõ giới hạn này."""
    out: dict[int, tuple[float, float]] = {}
    for g in gap_constraints or []:
        a, b = int(g.get("from", -1)), int(g.get("to", -1))
        if b != a + 1 or b <= 0 or b >= n_ev:
            continue
        lo = float(g["min_s"]) if g.get("min_s") is not None else 0.0
        hi = float(g["max_s"]) if g.get("max_s") is not None else float("inf")
        out[b] = (lo, hi)
    return out


def _run_dp(sub: np.ndarray, lam: float, gaps: dict[int, tuple[float, float]],
             pts: list[float | None]) -> tuple[np.ndarray, np.ndarray]:
    """DP: best[j][t] = điểm tốt nhất khi sự kiện j khớp keyframe t, chuỗi TĂNG DẦN
    theo thời gian, phạt khoảng cách λ (DANTE).

    Không có ràng buộc thời gian -> giữ nguyên thuật toán gốc chạy tuyến tính
    (running max, O(n_ev × n_kf)). Có ràng buộc -> phải xét từng cặp (t, τ) để
    kiểm khoảng cách giây, O(n_ev × n_kf²) — chỉ dùng khi người dùng chủ động đặt,
    và n_kf chỉ vài trăm nên vẫn nhanh."""
    n_ev, n_kf = sub.shape
    best = np.full((n_ev, n_kf), -np.inf, dtype=np.float64)
    back = np.zeros((n_ev, n_kf), dtype=np.int32)
    best[0] = sub[0]

    for j in range(1, n_ev):
        gap = gaps.get(j)
        if gap is None:
            run_val, run_arg = -np.inf, -1
            for t in range(n_kf):
                if t > 0:
                    cand = best[j - 1, t - 1] + lam * (t - 1)
                    if cand > run_val:
                        run_val, run_arg = cand, t - 1
                if run_arg >= 0 and np.isfinite(sub[j, t]):
                    best[j, t] = sub[j, t] + run_val - lam * t
                    back[j, t] = run_arg
            continue

        lo_s, hi_s = gap
        for t in range(1, n_kf):
            if not np.isfinite(sub[j, t]):
                continue
            t_pts = pts[t]
            bv, ba = -np.inf, -1
            for tau in range(t):
                if not np.isfinite(best[j - 1, tau]):
                    continue
                if t_pts is not None and pts[tau] is not None:
                    d = t_pts - pts[tau]
                    if d < lo_s or d > hi_s:
                        continue
                cand = best[j - 1, tau] + lam * tau
                if cand > bv:
                    bv, ba = cand, tau
            if ba >= 0:
                best[j, t] = sub[j, t] + bv - lam * t
                back[j, t] = ba

    return best, back
