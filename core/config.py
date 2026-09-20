"""Kiến thức đo được: trọng số fusion, tham số thuật toán. Port từ
`system/aic/config.py` (hệ FAISS-flat cũ, đã đo bằng số trên GT/benchmark thật)
— GIỮ NGUYÊN GIÁ TRỊ, chỉ bỏ phần liên quan tới FAISS/đường dẫn cục bộ (đã
chuyển sang config/settings.py + core/repositories/).

QUY ƯỚC: mọi trọng số trong file này PHẢI ghi rõ "ĐÃ ĐO" (port nguyên, có bằng
chứng số trong comment) hay "PLACEHOLDER — CHƯA ĐO" (nhánh mới, cần A/B ở P7).
Không được lẫn hai loại để tránh tưởng nhầm placeholder là đã validate.
"""

# ==================== ĐÃ ĐO (port nguyên từ system/aic/config.py) ====================

# OCR THÍCH ỨNG THEO LOẠI QUERY: KIS mạnh gây hại (0.25 trung tính, 2.0 -> tụt);
# QA mạnh CỨU (2.0 -> AIC gấp ~12 lần so với 0.25). Xem system/aic/config.py gốc.
OCR_WEIGHT = {"kis": 0.25, "qa": 2.0, "trake": 0.25}
# trake: ĐÃ THỬ tăng 0.25->2.0 để "cứu" video đúng khi nó đã vào được candidate
# pool nhưng vẫn thua video sai -> KẾT QUẢ NGƯỢC (video sai được cộng điểm còn
# NHIỀU hơn vì nó cũng khớp OCR/ASR giả — do Meilisearch mặc định chỉ cần khớp
# 1 PHẦN từ trong câu, ví dụ "cắt nấm" khớp bất kỳ video nào có chữ "cắt" dù
# không có "nấm"). Gốc rễ thật là ở TẦNG KHỚP TỪ chứ không phải trọng số — đã
# sửa bằng strict=True (matchingStrategy="all") trong core/temporal.py, nên trả
# về baseline 0.25 (KIS/QA benchmark). Tăng lại weight chỉ nên thử SAU KHI đã đo
# strict-matching qua nhiều query, không tăng mù theo trọng số nữa.
OCR_TEXT_WEIGHT = 0.25


# ASR (frame-level nhờ có timestamp thật): KIS w=0.15 -> AIC 0.5895->0.6211;
# QA w=1.0 -> AIC 0.4444->0.4778.
ASR_WEIGHT = {"kis": 0.15, "qa": 1.0, "trake": 0.15}  # trake: về baseline, xem comment OCR_WEIGHT

# PLACEHOLDER — CHƯA ĐO: ASR NGỮ NGHĨA (nhánh FAISS "asr_emb", Qwen3-Embedding-4B
# — xem core/asr_align.py::search_asr_semantic_as_frames, indexing/kaggle/
# 12_asr_embed.py). Khác ASR_WEIGHT ở trên (khớp TỪ, Meilisearch) — nhánh này
# khớp Ý NGHĨA, bổ sung cho nhau chứ không thay thế (2 tín hiệu ASR cùng tồn tại
# trong /search). Đặt tạm BẰNG ASR_WEIGHT làm điểm khởi đầu hợp lý (cùng loại tín
# hiệu ASR) — CẦN A/B qua pipeline thật, KHÔNG dùng số này để kết luận gì trước
# khi đo.
ASR_EMB_WEIGHT = {"kis": 0.15, "qa": 1.0, "trake": 0.15}

# BEiT-3 ensemble: KIS w=0.2 -> +0.013 AIC; QA w=1.5 -> +0.138 AIC (+27%!, COCO-ft
# bắt chi tiết nhỏ/chữ tốt hơn KIS thị giác thuần).
BEIT3_WEIGHT = {"kis": 0.2, "qa": 1.5, "trake": 0.2}

# ĐÃ BỎ USE_OBJECT_COLOR/COLOR_CUES (tự nhận diện màu trong câu rồi tự lọc vật
# thể) — vi phạm P4 (tự động phải do người dùng bật) và màu trong câu tự nhiên
# quá mơ hồ để trích thành 1 điều kiện lọc cứng đáng tin (xem api/routers/
# search.py). Người dùng tự thêm điều kiện Vật thể + màu khi muốn lọc cứng.
#
# ĐÃ HẠ (trước 2.0): đo thật thấy object đơn (vd "bicycle" không kèm màu/vị trí
# đặc trưng) là vật thể QUÁ PHỔ BIẾN trong dữ liệu -> weight 2.0 (cao hơn cả
# metaclip2=1.0) áp đảo tín hiệu hình ảnh ĐÚNG, kéo kết quả sang video không liên
# quan. Hạ xuống dưới metaclip2 để object CHỈ cộng điểm bổ trợ, không lấn át.
COLOR_WEIGHT = 0.6


# Caption t2c (giờ là nhánh Milvus `capemb`, Qwen3-Embedding-4B thay SmolVLM2+ST cũ
# — trọng số port nguyên từ đo lần 2 qua FULL production stack): KIS +0.031 AIC,
# +7pp hit@1 -> giữ BẬT; QA -0.021 AIC, -5pp hit@1 (nhoè tín hiệu ASR/BEiT-3/Entity
# đã sắc sẵn) -> TẮT hẳn (w=0.0). trake: CHƯA wire vào core/temporal.py (P7 nếu cần).
CAPTION_WEIGHT = {"kis": 0.5, "qa": 0.0, "trake": 0.5}

# Dedup: max 3/video cắt oan ở rank sâu (AIC 0.5938); max 8 -> +0.025 AIC (hit@1
# không đổi); max 15 thêm +0.006 (lợi ích giảm dần) -> 8 là điểm cân bằng.
DEDUP_DEFAULT = 8

# TRAKE DANTE DP: phạt khoảng cách thời gian λ(t-τ). λ=0 (DP thuần thứ tự) = 0.821;
# λ=0.001 (DANTE) = 0.949 trên GT 11 mẫu (exact match 0.615->0.769).
TRAKE_LAMBDA = 0.001

# Trần số video ứng viên sau boundary-anchor — ĐÃ GẶP THẬT: khi giao tập E1∩En
# yếu, code nới sang HỢP (v_first | v_last, có thể lên tới ~2×per_event video) ->
# mỗi video cần 1 lượt Milvus fetch_video_vectors() + (nếu bật OCR/ASR bonus) 2
# lượt ES/sự kiện -> hàng nghìn lượt gọi mạng, timeout thật (2/3 câu TRAKE test
# thật bị ReadTimeout 120s). Cắt về top-N theo rank (không cắt ngẫu nhiên, xem
# milvus_repo.videos_from_topk giữ thứ tự) — 150 đủ rộng cho @top5-10 kết quả.
MAX_TRAKE_CANDIDATES = 150

# Candidate generation for multi-event retrieval. These fractions reserve recall
# budget for videos covering many events, strong hits from any single event, and
# OCR/ASR hits. Final ranking is still computed by temporal DP on every keyframe
# of each shortlisted video.
TRAKE_COVERAGE_CANDIDATE_FRACTION = 0.50
TRAKE_STRONG_EVENT_CANDIDATE_FRACTION = 0.25
TRAKE_TEXT_CANDIDATE_FRACTION = 0.25


# Submit (theo quy chế BTC — xem core/submit.py)
MAX_SUBMIT_ROWS = 100
MAX_ANSWER_LEN = 100
TOPK_THRESHOLDS = (1, 5, 20, 50, 100)

# maxmean đa mệnh đề (nhánh metaclip2 CHÍNH): score = max_c cos(c,kf) + alpha*mean_c.
# Đo trên benchmark manual (8 query): MAX+0.3*MEAN thắng RRF/MAX/MEAN thuần.
MAXMEAN_ALPHA = 0.3
MAXMEAN_TOPK_PER_CLAUSE = 800   # Milvus search topk/clause — đủ rộng để union candidate pool

# RRF đa modality (giữa các nhánh Milvus + ES độc lập)
RRF_K = 60

# ==================== MỚI — CHO NHÁNH MILVUS/ES (chưa có ở hệ cũ) ====================

# Max token (an toàn) của từng model CLIP-family trước khi phải cắt-giữ-đầu-câu.
# MetaCLIP-2/PE-Core kế thừa CLIP gốc = 77 cứng; BEiT-3 (sentencepiece, maxlen server
# hiện tại) = 64. Xem nghiên cứu "Xử lý query vượt max-token" trong plan.
MAX_TOKENS = {"metaclip2": 77, "beit3": 64, "pecore": 77}

# MetaCLIP-2 "worldwide" ĐÃ ĐƯỢC CHỌN vì đa ngữ (xem comment trong
# indexing/kaggle/02_embed.py: "đa ngữ → KHỎI dịch tiếng Việt") — feed câu tiếng
# Việt (đã tách mệnh đề) trực tiếp, KHÔNG dịch. BEiT-3/PE-Core chỉ tiếng Anh -> BẮT
# BUỘC dịch trước. capemb (Qwen3-Embedding) đa ngữ -> feed câu gốc, không dịch.
TRANSLATE_FOR = {"metaclip2": False, "beit3": True, "pecore": True, "capemb": False}

# PLACEHOLDER — CHƯA ĐO: PE-Core là nhánh mới (thay BEiT-3 làm nhánh "chi tiết" ở
# offline pipeline, nhưng BEiT-3 vẫn được trích + có ensemble weight đã đo ở trên).
# Đặt trọng số khởi đầu thận trọng (cùng độ lớn BEiT-3 KIS) — CẦN A/B qua pipeline
# thật ở P7 trước khi tin số này.
PECORE_WEIGHT = {"kis": 0.3, "qa": 0.3, "trake": 0.3}

# TRỌNG SỐ metaclip2 — TRƯỚC ĐÂY hardcode 1.0 thẳng trong api/routers/search.py
# (nhánh CHÍNH, luôn coi là mốc 1.0 để so trọng số khác). Đưa vào config để có
# thể GHI ĐÈ ĐỘNG (req.weights, xem mục "TRỌNG SỐ ĐỘNG" cuối file) giống mọi
# nhánh khác — giá trị mặc định GIỮ NGUYÊN 1.0 (không đổi hành vi cũ).
METACLIP2_WEIGHT = {"kis": 1.0, "qa": 1.0, "trake": 1.0}

# PLACEHOLDER — CHƯA ĐO: DINOv3 giờ THÊM vào RRF fusion chung của /search (mục
# "tích hợp DINOv3 vào chung" — trước đây CHỈ dùng cho /similar độc lập) khi
# request có ảnh tham chiếu (req.ref_video/ref_n HOẶC req.ref_image_b64, xem
# api/routers/search.py). Đặt tạm thấp hơn metaclip2 vì đây là tín hiệu THỊ GIÁC
# THUẦN theo 1 ảnh mẫu cụ thể — CẦN A/B trước khi tin số này.
DINOV3_WEIGHT = {"kis": 0.5, "qa": 0.5, "trake": 0.5}


# ==================== GIỚI HẠN TÀI NGUYÊN MÁY DEV (KHÔNG phải quyết định kiến trúc) ====================
# ĐÃ ĐỔI SANG FAISS+MEILISEARCH (thay Milvus+Elasticsearch) — xem
# core/repositories/faiss_repo.py + PIPELINE.md. FAISS chỉ lưu vector thô trong
# RAM (không HNSW graph, không etcd/MinIO/query-coordinator overhead của Milvus)
# nên nhẹ hơn đáng kể — bật lại đủ cả 5 nhánh, theo dõi RAM nếu máy vẫn hạn chế
# thì tắt bớt CHỈ CẦN đổi dict này, không cần sửa code khác.
ENABLED_BRANCHES = {
    "metaclip2": True,   # nhánh CHÍNH — bắt buộc, quyết định phần lớn chất lượng
    "pecore": True,      # PLACEHOLDER weight chưa đo
    "beit3": True,       # đã đo có lợi (đặc biệt QA)
    "capemb": True,      # đã đo có lợi cho KIS
    "dinov3": True,      # dùng cho /similar (image-to-image)
    "asr_emb": True,     # semantic ASR (TÙY CHỌN) — an toàn để True dù CHƯA build
                          # xong index: FaissRepo._load_branch() tự bỏ qua êm nếu
                          # thiếu file, core.asr_align.search_asr_semantic_as_frames()
                          # tự trả [] nếu branch chưa nạp. Xem indexing/kaggle/12_asr_embed.py.
}
# "metaclip2" LUÔN phải True — đây là nhánh bắt buộc, tắt sẽ làm /search mất hết tín hiệu vector.
#
# Việc nạp encoder (local vs remote Kaggle, settings.REMOTE_ENCODER_URL) và việc
# nạp FAISS index là 2 chi phí RAM ĐỘC LẬP — tắt nhánh ở đây tiết kiệm RAM phía
# FaissRepo (core/repositories/faiss_repo.py chỉ đọc index.faiss của nhánh BẬT),
# không liên quan tới việc encoder nạp ở đâu.

# ==================== LỌC VIDEO TRƯỚC (mục 3) ====================
# BTC KHÔNG cung cấp trường "thể loại" (category) tường minh trong metadata —
# đã kiểm tra thật 873/873 file media-info: chỉ có author/title/description/
# keywords/publish_date, KHÔNG có category_id/categories. Ban đầu thử suy từ
# "author" (kênh YouTube, chỉ 7 kênh) nhưng KHÔNG đủ chi tiết (vd 1 kênh có thể
# gộp nhiều nội dung khác nhau theo shard). THAY BẰNG bảng do người dùng TỰ XEM
# THẬT nội dung từng shard rồi xác nhận — chính xác hơn nhiều, dùng trực tiếp
# tiền tố video ("L21_V001" -> shard "L21") làm khoá tra, không qua metadata nữa.
SHARD_CATEGORY_MAP = {
    "L21": "Thời sự 60 giây",
    "L22": "Thời sự 60 giây",
    "L23": "Đua xe đạp",
    "L24": "Múa lân",
    "L25": "Dạy học",
    "L26": "Nấu ăn",
    "L27": "Du lịch trải nghiệm",
    "L28": "Chương trình Tản mạn Mê Kông",
    "L29": "Chương trình Đôi mắt Mê Kông",
    "L30": "Cuộc thi lan tỏa năng lượng tích cực năm 2024",
}
VIDEO_CATEGORIES = sorted(set(SHARD_CATEGORY_MAP.values()))

# ==================== STRICT OCR/ASR FILTER (mục 4) ====================
# Khi OCR/ASR khớp với điểm >= ngưỡng này, coi là "CHẮC CHẮN" -> thay vì chỉ
# CỘNG trọng số vào RRF (soft fusion như trước), giới hạn hẳn các nhánh thị giác
# CHỈ search trong tập khung hình đã khớp (± sai số) — xem
# api/routers/search.py (req.strict_text_filter). PLACEHOLDER — ngưỡng đặt theo
# trực giác (Meilisearch _rankingScore đã tự nhiên nằm [0,1], strict=True matching
# càng chặt điểm càng gần 1 khi khớp thật) — CẦN A/B trước khi tin số này.
OCR_FILTER_CONFIDENCE = 0.85
ASR_FILTER_CONFIDENCE = 0.85
# OCR gắn CHẶT vào đúng khung hình khớp (chữ hiện đúng lúc đó) -> sai số nhỏ, chỉ
# nới thêm vài khung lân cận (chống trường hợp OCR miss 1 khung do mờ/chuyển cảnh).
OCR_FILTER_MARGIN_FRAMES = 2
# ASR thì LỜI NÓI có thể ĐI TRƯỚC hoặc SAU khung hình minh hoạ nội dung đó khá xa
# (người dẫn nói xong mới cắt cảnh, hoặc cảnh lên trước rồi mới thuyết minh) -> nới
# sai số RỘNG HƠN hẳn mức ±2s mặc định của core.asr_align (đó là cho fusion mềm,
# đây là filter CỨNG nên cần dư ra để không lỡ mất khung đúng).
ASR_FILTER_MARGIN_S = 8.0
