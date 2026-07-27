# THIẾT KẾ HỆ THỐNG RETRIEVAL — Frontend / Backend / Database / Deploy

> Dựa trên: 16 paper hệ thống VBS2025 thật (toàn bộ Part V, MMM2025 LNCS 15524), 12 paper AIC2025,
> 3 paper nền tảng (FRED SOICT'25, "Stubborn Strawberries" SOICT'24, LongCLIP/arbitrary-length),
> `reference_repos/INDEX.md`, và tìm kiếm bổ sung 2026. Mọi quyết định dưới đây đều có trích dẫn
> nguồn cụ thể — không phải suy đoán. Xem thảo luận đầy đủ trong hội thoại; đây là bản tổng hợp
> để code theo.
>
> **Tiền đề đã chốt**: hệ thống TRUYỀN THỐNG (fusion + rule/heuristic), KHÔNG Agent/LLM-loop tự trị.
> Offline pipeline (batch1, 182,422 keyframe / 873 video) đã xong: TransNetV2 keyframe, 4 nhánh
> embedding ảnh (MetaCLIP-2/BEiT-3/DINOv3/PE-Core), OCR (Qwen3-VL), ASR (ChunkFormer), object
> detection (YOLO26x), caption (Qwen3-VL) + cap_emb (Qwen3-Embedding-4B, đang chạy).

---

## 0. Sơ đồ tổng thể

```
                         ┌─────────────────────────────────────────┐
                         │            REACT FRONTEND (Vite+TS)       │
                         │  Search panel · Grid · Frame detail ·     │
                         │  Temporal panel · Filmstrip · Submit UI   │
                         └───────────────────┬───────────────────────┘
                                              │ REST (JSON)
                         ┌───────────────────▼───────────────────────┐
                         │          FASTAPI BACKEND (modular monolith)│
                         │  routers/ → services/ → repositories/      │
                         └──────┬────────────────────────┬────────────┘
                                │                          │
                    ┌───────────▼──────────┐   ┌───────────▼───────────┐
                    │   MILVUS (vector)     │   │ ELASTICSEARCH (text)  │
                    │  5 collection: siglip/ │   │ aic_frames (OCR/cap/  │
                    │  metaclip2/beit3/      │   │   objects, ngram BM25)│
                    │  dinov3/pecore/capemb  │   │ aic_asr (ASR segment) │
                    └────────────────────────┘   └────────────────────────┘
```

**Nguyên tắc kiến trúc** (theo `sys_xlinh_aic2024` — template FastAPI+FAISS+ES "sạch nhất" trong
`reference_repos/INDEX.md`, và HORUS/VERGE/PraK/Fusionista/NII-UIT thực chiến): **modular monolith**,
KHÔNG microservice (VERGE 4-layer và PraK 3-tier đều dùng 1 backend service duy nhất, tách theo
module code chứ không tách theo process — tránh overhead network/deploy không cần thiết cho quy mô
1 máy thi).

---

## 1. FRONTEND — React + Vite + TypeScript + Tailwind

### 1.1 Stack

Theo `sys_FRED_aic2025` (đã dùng làm template UI trước đây) + xác nhận thêm qua research 2026:
- **React 19 + Vite + TypeScript + Tailwind 4** (giữ nguyên lựa chọn cũ, không có bằng chứng cần đổi).
- State: **Context API** cho state toàn cục (query, filter, session) — đủ cho quy mô 1 trang, không
  cần Redux/Zustand (search 2026 xác nhận Context API vẫn là 1 trong 2 pattern chính 2026, cùng Signals).
- **CSS Grid cho layout tổng, Flexbox cho từng component** — chuẩn 2026 cho layout 2 chiều (grid ảnh).
- **Lazy loading ảnh theo viewport** (IMSearch2.0 dùng, đo được cải thiện tốc độ tải) — dùng
  `IntersectionObserver` hoặc `react-lazy-load-image-component`.
- **Client-side fuzzy filter** cho metadata đã tải về (SnapSeek 2.0 dùng `Fuse.js`, giảm tải backend,
  phản hồi tức thì) — áp dụng cho filter object/color sau khi có kết quả, không cần gọi lại backend.

### 1.2 Nguyên tắc thiết kế cấp cao nhất — Progressive Disclosure

**Bằng chứng: 2 đội độc lập** hội tụ cùng 1 giải pháp:
- **NII-UIT (#1 VBS2025)**: "Advanced Mode" toggle — ẩn slider trọng số model, tùy chọn paraphrase,
  chỉ hiện khi user bật. Mặc định TẮT cho novice.
- **VERGE**: tự thú nhận UI cũ "designed mainly for experienced users... confusing for novice users"
  sau nhiều năm chồng tính năng → redesign thành 2 mode Novice/Advanced.

→ **Quyết định**: mọi control nâng cao (trọng số fusion, ngưỡng object filter, chọn nhánh embedding cụ
thể) nằm trong 1 panel "Advanced" ẩn mặc định. Giao diện mặc định (novice/nhanh) chỉ có: 1 ô query
chính + nút Search + grid kết quả.

**Bằng chứng hành vi thật (Exquisitor, quan sát tại IVR4B/LSC 2024)**: *"novice users still tend to
favor textual search, despite half the interface being allocated to URF [relevance feedback]... users
only resort to URF after spending significant time with textual search and failing."*
→ Text search phải là **entry point chính, chiếm không gian lớn nhất**; relevance feedback/filter/sketch
là tính năng PHỤ, không tranh chỗ ngang hàng ngay từ đầu màn hình.

**Bằng chứng phủ định (đừng làm)**: `vitrivr-VR` đo được nhập liệu text trong VR chậm hơn desktop
**≥24%** qua nhiều kỳ thi liên tiếp, hệ thống thường thua vì chưa trả kết quả đầu khi đội khác đã nộp
xong → **không đầu tư input modality lạ (VR/gesture)**, tập trung làm tốt text input + shortcut bàn phím
trên desktop.

### 1.3 Bố cục màn hình chính

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Query box lớn ...........................] [Search] [Advanced ▾]     │  ← 1 dòng, nổi bật nhất
│ Temporal: [+ thêm sự kiện]  Filter: [object] [color] [OCR] [ASR]      │  ← phụ, thu gọn được
├──────────────────────────────────────────────────────────────────────┤
│  GRID KẾT QUẢ (chiếm ≥80% màn hình — theo SnapSeek 2.0 đo cụ thể)     │
│  [img][img][img][img][img]     mỗi ảnh: video_id dưới, hover →       │
│  [img][img][img][img][img]     "Similar" + "Play from here"          │
│  ...                                                                  │
└──────────────────────────────────────────────────────────────────────┘
```

- **≥80% màn hình cho grid ảnh** (SnapSeek 2.0 đo cụ thể "over 80%") — control panel gọn, không chiếm
  chỗ hiển thị.
- Grid 5 cột (IMSearch2.0, cân bằng số ảnh hiển thị/độ rõ) — có thể chỉnh số cột trong Advanced.
- Mỗi ảnh kết quả: hiện `video_id` bên dưới (VideoEase), hover/click hiện 2 nút:
  - **"Similar"** (image-to-image search bằng vector nhánh embedding hiện tại) — xuất hiện độc lập ở
    **5 hệ thống** (ViFi, VideoEase, Fusionista, SnapSeek, IMSearch2.0) → gần như bắt buộc.
  - **"Play from here"** → mở Frame Detail (mục 1.4).

### 1.4 Frame Detail / "Filmstrip lân cận" — giải quyết bài toán frame lệch

Đây là tính năng đã thiết kế trong hội thoại trước, giờ có **bằng chứng hội tụ từ nhiều hệ thống
thật** xác nhận hướng đi đúng:
- **Fusionista**: "preview 40 images around the selected one" — đúng ý tưởng filmstrip lân cận.
- **diveXplore**: video scrubbing bằng kéo chuột dọc trục keyframe, context-preview window
  (video summary + similar videos).
- **Exquisitor**: tự báo cáo lỗi THẬT — nộp bài lệch timestamp tới 0.5s vì browser cũ không đủ chính
  xác → phải redesign lại toàn bộ video-summary browser để sửa. → xác nhận nỗi lo "frame lệch lúc nộp"
  là có thật, từng xảy ra ở hệ thống thi đấu thật.

**Thiết kế cụ thể**:
1. Click "Play from here" → mở modal/panel: video player bắt đầu tại timestamp của keyframe, VÀ
2. Một filmstrip ngang bên dưới: `ffmpeg` trích on-demand ~40 frame lân cận (theo Fusionista), mỗi
   frame gắn `frame_idx` thật (không phải index keyframe đã lưu).
3. Kéo chuột ngang filmstrip = scrub nhanh qua các frame lân cận (theo diveXplore).
4. Nút "Chọn frame này" ngay dưới mỗi frame trong filmstrip → set làm candidate nộp — **hiện rõ
   `frame_idx` số nguyên đang chọn** để tránh đúng lỗi 0.5s của Exquisitor.

### 1.5 Temporal Search Panel (cho TRAKE + KIS có gợi ý thời gian)

Theo pattern lặp lại ở **7 hệ thống** (NII-UIT #1, ViewsInsight2.0, VideoEase, ViFi, VERGE, MERVIN,
Vortex) — tất cả theo cùng khung: (1) nhiều ô nhập độc lập cho từng sự kiện theo thứ tự thời gian,
(2) ràng buộc cùng `video_id` + cửa sổ thời gian, (3) cộng/max điểm nhiều giai đoạn.

- UI: nút "+ thêm sự kiện" bên cạnh ô query chính → mở thêm ô nhập (Event 2, Event 3...).
- **VERGE pattern** (giảm thao tác): tự nhận diện — 1 ô nhập = search thường, ≥2 ô = tự động chạy
  temporal search, không cần nút riêng.
- Kết quả temporal hiển thị dạng chuỗi ảnh nối tiếp theo đúng thứ tự (không phải grid rời rạc) — riêng
  cho TRAKE, có nút xem lại toàn bộ chuỗi trên 1 timeline video (giống "Timeline" tab của SnapSeek 2.0).

### 1.6 Relevance Feedback (nút Like/Dislike)

**3 hệ thống độc lập** (SnapSeek 2.0, Fusionista, IMSearch2.0) đều làm relevance feedback bằng nút
đơn giản (+/-) trên từng ảnh kết quả, feed vào công thức Rocchio/Ide Regular đã có sẵn trong kế hoạch
gốc (Vortex cũng dùng công thức Rocchio `qm = α·q0 + β·mean(Cr) − γ·mean(Cnr)`).

- UI: nút xanh (+) / đỏ (-) góc mỗi ảnh kết quả.
- Ảnh đã feedback gom vào 1 sidebar nhỏ (IMSearch2.0) để user xem lại/điều chỉnh.
- **KHÔNG dùng eye-tracking** (VEAGLE) — cần phần cứng chuyên dụng, không khả thi cho máy thi thông
  thường; nút Like/Dislike đạt hiệu quả tương tự với chi phí triển khai thấp hơn nhiều.

### 1.7 Tính năng cộng tác (nếu thi theo đội ≥2 người)

Theo `diveXplore` (tính năng đã đo hiệu quả tại VBS2024/IVR4B2024):
- Ảnh đã nộp bởi đồng đội → phủ overlay xám + chữ đỏ, có toggle ẩn hẳn.
- Nút "Chia sẻ" trên mỗi ảnh → popup hiện cho đồng đội, có nút mở nhanh tới đúng shotlist video đó.
- Cần xác nhận với BTC AIC 2026 xem thể thức có phải 1 hay nhiều người/đội trước khi build phần này.

### 1.8 Trợ giúp viết query (dựa trên phát hiện diveXplore, đo trên log thi thật)

- Đặt placeholder/tooltip gợi ý: "Viết câu đầy đủ, có ngữ pháp, nêu góc quay nếu biết (VD: 'cảnh quay
  từ trên cao...')" — vì đo được câu đầy đủ + có góc máy thắng rõ rệt so với từ khoá rời rạc.
- (Tùy chọn nâng cao, không bắt buộc P5): highlight từ đệm ("some", "a bit"...) trong ô nhập — ý tưởng
  diveXplore ĐANG DỰ ĐỊNH làm (chưa build ở bên họ), có thể làm bằng 1 danh sách từ đệm tiếng Anh/Việt
  cố định, không cần LLM.

### 1.9 CSV Submission Creator

Giữ nguyên thiết kế cũ (tái dùng `system/aic/submit.py`), thêm: xác nhận rõ `frame_idx` (số nguyên,
không phải timestamp giây) trước khi thêm vào danh sách nộp — tránh lỗi Exquisitor đã gặp.

---

## 2. BACKEND — FastAPI (modular monolith)

### 2.1 Cấu trúc thư mục (layered, theo best-practice FastAPI 2026 đã kiểm chứng)

```
aic-system/api/
  main.py                      # khởi tạo app, mount routers, CORS, lifespan (connect Milvus/ES)
  routers/
    search.py                  # POST /search           — multi-signal search 1 sự kiện
    temporal.py                # POST /temporal          — TRAKE / multi-event
    similar.py                 # POST /similar            — image-to-image (DINOv3 chủ yếu)
    media.py                   # GET  /media/frame/{id}   — serve keyframe/filmstrip on-demand
    submit.py                  # POST /submit             — build CSV nộp bài
    feedback.py                # POST /feedback           — relevance feedback (Rocchio state)
  services/
    fusion_service.py          # RRF + cascaded rerank (mục 3)
    temporal_service.py        # DANTE DP (mục 4)
    query_service.py           # dịch, expand, FQS, entity resolution (mục 5)
    media_service.py           # ffmpeg on-demand filmstrip extraction (mục 1.4)
  repositories/
    milvus_repo.py             # wrapper truy vấn 5 collection Milvus
    es_repo.py                 # wrapper truy vấn aic_frames / aic_asr
  schemas/                     # Pydantic request/response models
  config.py                    # bảng trọng số kis/qa/trake (đã bake sẵn, xem plan gốc)
```

Pattern: **Router → Service → Repository → DB**, đúng chuẩn FastAPI 2026 đã xác nhận qua search
("clean pattern... improves maintainability, testability, and scalability"). KHÔNG để logic fusion/DP
trong router — chỉ orchestration.

### 2.2 API endpoints cụ thể (tham khảo shape API thật từ FRED + NII-UIT + VERGE)

| Endpoint | Method | Mô tả |
|---|---|---|
| `/search` | POST | 1 câu query → RRF đa nhánh embedding + BM25 OCR/ASR + object filter → cascaded rerank top-100 → trả top-K |
| `/temporal` | POST | N câu query theo thứ tự → DANTE DP → trả N-tuple frame theo video, xếp hạng theo video |
| `/similar` | POST | 1 `frame_id` → tìm ảnh tương tự (mặc định DINOv3, cho phép chọn nhánh khác trong Advanced) |
| `/media/frame/{video}/{frame_idx}` | GET | serve keyframe đã lưu (webp) |
| `/media/filmstrip/{video}?center=<frame_idx>&window=40` | GET | on-demand ffmpeg extract 40 frame lân cận (mục 1.4), cache theo `(video, center)` |
| `/submit` | POST | nhận danh sách frame đã chọn theo task KIS/QA/TRAKE → build CSV đúng format Codabench (tái dùng `submit.py`) |
| `/feedback` | POST | nhận list ảnh (+/-) → cập nhật vector query theo Rocchio, trả kết quả rerank mới |
| `/translate` | POST | dịch VI→EN cho câu query (giữ từ kế hoạch gốc, envit5 hoặc API nếu BTC cho phép) |

### 2.3 Xử lý query (query_service.py)

Theo tổng hợp GQE + RAPID + Vortex đã bàn trước:
1. Dịch VI→EN nếu cần.
2. Query expansion: sinh thêm 1-2 biến thể (LLM hoặc rule), rồi áp **Farthest Query Sampling (FQS,
   k=2)** — GQE đo được R@1 52.1% (tốt hơn dùng cả 10 expansion: 49.6%) mà rẻ hơn. KHÔNG concat/average
   embedding các query mở rộng (GQE đo: concat làm HẠI, giảm còn 45.4% so với baseline 46.7%).
3. Entity resolution (giữ từ kế hoạch gốc, gate confidence=high).
4. Negative query (`S(v) = sim(qpos,v) − λ·sim(qneg,v)`, từ FRED — giữ nguyên).
5. **Vortex nguyên tắc quan trọng**: LLM chỉ **gợi ý**, KHÔNG tự động rewrite/thay query của user —
   giữ người dùng kiểm soát cuối cùng, khớp đúng quyết định "không Agent tự trị".

---

## 3. FUSION LOGIC (core/fusion.py)

### 3.1 Tầng 1 — RRF đa nhánh (đã đo, giữ nguyên)

```
RRF_Score(d) = Σ_{i=1}^{N} 1/(k + rank_i(d)),   k = 60  (chuẩn Cormack et al. 2009)
```
N = số nhánh tham gia (embedding ảnh + OCR/ASR BM25 + cap_emb nếu bật). Dùng bởi VISIONE 5.0 (vô địch
VBS2024), Vortex (ablation: 20.6→27.8/88 khi thêm RRF), Enhanced-Multimodal-QueryExpansion.

**Cảnh báo cần nhớ khi tune** (VideoEase, bảng thực nghiệm thật): single-best-model đôi khi thắng cả
RRF lẫn weighted-sum trên cùng bộ query. → Luôn giữ 1 chế độ "chỉ nhánh chính" để so sánh, không mặc
định tin fusion luôn thắng.

### 3.2 Tầng 2 — Cascaded rerank (MỚI, thêm vào kế hoạch gốc)

Lấy top-100 từ RRF → rerank bằng cross-encoder rẻ hơn BLIP-2 đầy đủ nhưng cùng ý tưởng — **do hệ
thống không có ngân sách chạy BLIP-2 trên từng cặp real-time**, dùng phương án nhẹ hơn:
- Dùng **caption text đã có sẵn** (Qwen3-VL) + `cap_emb` (Qwen3-Embedding-4B) làm tín hiệu rerank thay
  cho cross-encoder ảnh nặng — vì đã tính sẵn offline, không tốn thêm compute lúc query.
- Bằng chứng: SMU/PolyU paper đo trên TRECVID 6 năm — late-fusion t2v+t2c cho **median rank 4.75**
  (so với 9.92 chỉ t2v, 2487 chỉ t2c), trọng số 0.8/0.2. **Đo lại với cap_emb THẬT** (Qwen3-Embedding-4B,
  tốt hơn hẳn embedding cũ dùng để đo `+0.031` trước đây) trước khi chốt trọng số cuối.

### 3.3 Tầng 3 — Fusion đa mệnh đề (giữ nguyên, đã đo thắng)

`maxmean` cho query nhiều mệnh đề trong 1 câu — đã đo thắng trung bình cộng thường, khớp với phát
hiện GQE (naive-average hại kết quả).

---

## 4. TEMPORAL / TRAKE (core/temporal.py)

Giữ nguyên **DANTE** (đã có, đã đo "Outstanding" tại AIC'25 thật qua paper AIO_Owlgorithms):

```
DP[i,t] = S[i,t] + max_{τ∈[sv,t-1]}(DP[i-1,τ] − λ(t-τ))     # tối ưu bằng running-max: O(N·T)
DANTE[v] = max_t DP[N,t]
```
λ=0.001 khi gap keyframe 3-15 frame; λ=0.01 khi gap 1-3 frame (tuning thực nghiệm từ paper gốc).

**Ràng buộc bắt buộc** (bài học từ Vortex — team cố tình BỎ DP vì lý do scalability): DP chỉ chạy
trên **candidate pool đã lọc trước** (theo video, hoặc top-M boundary candidate kiểu MADTempo), KHÔNG
brute-force trên toàn bộ 167,850+ keyframe — nếu không sẽ chậm không dùng được trong thi tương tác.

---

## 5. DATABASE

### 5.1 Milvus — 6 collection vector

| Collection | Model | Dim | Nguồn |
|---|---|---|---|
| `metaclip2` | facebook/metaclip-2-worldwide-huge-378 | 1024 | đã nạp (`load_to_milvus.py`) |
| `beit3` | BEiT-3 COCO-retrieval | 1024 | đã nạp |
| `dinov3` | facebook/dinov3-vitl16 | 1024 | đã nạp |
| `pecore` | PE-Core-L14-336 | 1024 | đã nạp |
| `capemb` | Qwen3-Embedding-4B (caption text) | tùy model | chờ Kaggle chạy xong, nạp thêm |

Mỗi collection: `id` (VARCHAR PK, `video:NNNNNN`), `video`, `n`, `frame_idx`, `vector` — index HNSW
COSINE (đã cấu hình trong `load_to_milvus.py`). `capemb` không có `frame_idx` gốc trong file riêng —
join qua `(video,n)` với collection `metaclip2` lúc nạp.

### 5.2 Elasticsearch — 2 index

- `aic_frames`: 1 doc/keyframe — `ocr_text` (ngram 2-5 fuzzy), `caption` (text thường, dùng cho BM25
  t2c bổ sung cascaded rerank), `objects` (token VISIONE-style, whitespace analyzer).
- `aic_asr`: 1 doc/đoạn ASR — `video`, `start`, `end`, `text` (ngram fuzzy) — frame-align ±2s làm ở
  tầng query (`query_service.py`), không bake cứng lúc index (đã quyết định trước, giữ nguyên).

Cả 2 đã có script nạp (`load_to_es.py`), dedup L25_a1/L25_b inline.

---

## 6. DEPLOYMENT

### 6.1 Docker Compose (đã dựng, formalize thêm 2 service)

Đã có: `etcd`, `minio`, `milvus`, `attu`, `elasticsearch` (`aic-system/docker/docker-compose.yml`,
data bind-mount vào `./volumes` trên ổ F:). Thêm khi backend/frontend code xong:

```yaml
  backend:
    build: ../api
    ports: ["8000:8000"]
    environment:
      MILVUS_URI: http://milvus:19530
      ES_URL: http://elasticsearch:9200
    depends_on: [milvus, elasticsearch]

  frontend:
    build: ../frontend
    ports: ["5173:5173"]   # dev; production build serve qua nginx hoặc backend static
```

### 6.2 Production checklist (theo best-practice FastAPI 2026 đã xác nhận)

- KHÔNG chạy `uvicorn --reload` khi thi — dùng `uvicorn` thường hoặc `gunicorn -k uvicorn.workers.UvicornWorker`.
- Pin version `fastapi`/`pymilvus`/`elasticsearch` trong `requirements.txt` (tránh lệch bản như đã gặp
  với `elasticsearch` client 9.x vs server 8.x trước đây).
- Reverse proxy (nginx) trước backend nếu deploy nhiều máy; nếu chạy 1 máy thi thì có thể bỏ qua.

---

## 7. LỘ TRÌNH THỰC THI (cập nhật P3-P6 so với kế hoạch gốc)

- **P3a** (đang làm): dựng Milvus+ES, nạp dữ liệu, xác nhận số liệu đúng 167,850/182,422.
- **P3b**: code `core/fusion.py` (RRF + cascaded rerank t2v+t2c), `core/temporal.py` (DANTE với
  candidate-pool lọc trước), `core/query_service.py` (FQS + maxmean).
- **P4**: FastAPI routers theo mục 2.2, test bằng `curl` từng endpoint.
- **P5**: React frontend theo mục 1 — làm THEO THỨ TỰ ưu tiên: (1) search box + grid cơ bản, (2) frame
  detail + filmstrip lân cận, (3) temporal panel, (4) relevance feedback, (5) advanced mode/collab —
  vì bằng chứng VBS2025 cho thấy UI/UX cơ bản làm tốt quan trọng hơn tính năng nâng cao.
- **P6**: E2E test bằng query mẫu BTC thật, nộp thử Codabench sớm.
