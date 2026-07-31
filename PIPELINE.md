# Pipeline hệ thống — từ video thô đến kết quả tìm kiếm

Toàn bộ luồng xử lý của hệ thống, chia làm 2 giai đoạn tách biệt: **offline**
(index hoá dữ liệu — chạy 1 lần, trên GPU Kaggle) và **online** (xử lý mỗi câu
truy vấn — chạy real-time khi dùng). Input/output từng bước ghi rõ để biết chỗ
nào có thể đo lại, thay model, hay chỉnh trọng số.

Chú thích màu: 🟢 module offline (index hoá) · 🟠 module online (truy vấn) ·
🔵 lưu trữ/hạ tầng · ⬜ dữ liệu input/output.

---

## 0 · Toàn cảnh

```mermaid
flowchart LR
  classDef offline fill:#123a35,stroke:#52d1bd,color:#d8fff6,font-weight:600;
  classDef online fill:#3a2c12,stroke:#ffb454,color:#ffefd8,font-weight:600;
  classDef aux fill:#1c2340,stroke:#8aa2ff,color:#e6ebff,font-weight:600;
  classDef root fill:#161b26,stroke:#8992a8,color:#ffffff,font-weight:700;

  ROOT["Hệ thống<br/>AIC Retrieval"]:::root

  ROOT --- OFF["① Offline<br/>index hoá 1 lần"]:::offline
  OFF --- OFF1["Trích keyframe + audio"]:::offline
  OFF --- OFF2["4 nhánh embedding ảnh"]:::offline
  OFF --- OFF3["Caption + vector hoá caption"]:::offline
  OFF --- OFF4["OCR chữ trên khung hình"]:::offline
  OFF --- OFF5["ASR lời thoại"]:::offline
  OFF --- OFF6["Object + màu"]:::offline
  OFF --- OFF7["Nạp FAISS / Meilisearch"]:::offline

  ROOT --- ON["② Online<br/>mỗi câu truy vấn"]:::online
  ON --- ON1["Xử lý câu bằng LLM"]:::online
  ON --- ON2["Vector hoá qua GPU Kaggle"]:::online
  ON --- ON3["Tìm kiếm đa nguồn song song"]:::online
  ON --- ON4["Hợp nhất RRF theo trọng số"]:::online
  ON --- ON5["Trả kết quả + giải thích"]:::online

  ROOT --- AUX["③ Tính năng phụ"]:::aux
  AUX --- AUX1["Temporal/TRAKE — chuỗi sự kiện"]:::aux
  AUX --- AUX2["Tìm ảnh giống — DINOv3"]:::aux
  AUX --- AUX3["Submit — đóng gói nộp bài"]:::aux
```

---

## 1 · Offline — Index hoá dữ liệu

Chạy 1 lần trên GPU Kaggle free (notebook `01`–`10`, xem
[`indexing/kaggle/`](indexing/kaggle/)), output là các file/vector nạp thẳng
vào FAISS + Meilisearch — máy dev không cần GPU cho bước này.

```mermaid
flowchart TD
  classDef offline fill:#123a35,stroke:#52d1bd,color:#d8fff6,font-weight:600;
  classDef infra fill:#1c2340,stroke:#8aa2ff,color:#e6ebff,font-weight:600;
  classDef io fill:#161b26,stroke:#3a4256,color:#c7cede,stroke-dasharray: 4 3;

  V["🎬 Video gốc BTC<br/>.mp4 · ~78GB · 873 video"]:::io
  V --> TN["Notebook 01 — TransNetV2<br/>tách keyframe + audio"]:::offline
  TN --> KF["Keyframe .webp + CSV map<br/>(n, frame_idx, pts_time, fps)<br/>167,850 khung hình"]:::io
  TN --> AU["Audio .opus<br/>tách riêng theo video"]:::io

  subgraph EMB["4 nhánh embedding ẢNH (song song, độc lập nhau)"]
    direction TB
    MC["Notebook 02<br/>MetaCLIP-2<br/>đa ngữ — nhánh CHÍNH"]:::offline
    PC["Notebook 03<br/>PE-Core-L14-336<br/>nhánh chi tiết"]:::offline
    B3["Notebook 05<br/>BEiT-3<br/>dự phòng ensemble"]:::offline
    DV["Notebook 04<br/>DINOv3<br/>chỉ dùng tìm-ảnh-giống"]:::offline
  end
  KF --> EMB

  KF --> CAP["Notebook 07<br/>Qwen3-VL-4B<br/>sinh caption tiếng Anh"]:::offline
  CAP --> CE["Notebook 10<br/>Qwen3-Embedding-4B<br/>vector hoá caption"]:::offline

  KF --> OCR["Notebook 09<br/>Qwen3-VL-4B (prompt khác)<br/>đọc chữ trên khung hình"]:::offline
  KF --> OBJ["Notebook 08<br/>YOLO 80 lớp COCO<br/>+ màu chủ đạo + ô lưới 4x4"]:::offline
  AU --> ASR["Notebook 06<br/>ChunkFormer<br/>ASR tiếng Việt · WER 8.31%"]:::offline

  MC --> MV1[("FAISS<br/>metaclip2")]:::infra
  PC --> MV2[("FAISS<br/>pecore")]:::infra
  B3 --> MV3[("FAISS<br/>beit3")]:::infra
  DV --> MV4[("FAISS<br/>dinov3")]:::infra
  CE --> MV5[("FAISS<br/>capemb")]:::infra

  OCR --> MS1[("Meilisearch<br/>aic_frames<br/>ocr_text · caption · objects")]:::infra
  OBJ --> MS1
  CAP --> MS1
  ASR --> MS2[("Meilisearch<br/>aic_asr<br/>text theo đoạn (start,end)")]:::infra
```

### Chi tiết từng module

| Module | Input | Model | Output |
|---|---|---|---|
| Keyframe + audio | video `.mp4` | TransNetV2 (phát hiện chuyển cảnh) | `.webp` + CSV map + `.opus` — 167,850 khung (dedup từ 182,422) |
| 4 nhánh embedding ảnh | keyframe `.webp` | MetaCLIP-2 / PE-Core-L14-336 / BEiT-3 / DINOv3 | vector 1024 chiều/nhánh → FAISS index riêng |
| Caption + Cap-Embedding | keyframe `.webp` | Qwen3-VL-4B → Qwen3-Embedding-4B | câu tiếng Anh + vector 2560 chiều → FAISS `capemb` + Meilisearch `caption` |
| OCR | keyframe `.webp` | Qwen3-VL-4B (prompt "chỉ liệt kê chữ nhìn thấy") | Meilisearch `ocr_text` (ngram 2-5) |
| ASR | audio `.opus` | ChunkFormer (WER 8.31%) | Meilisearch `aic_asr` — 111,411 đoạn theo (start, end) |
| Object + màu | keyframe `.webp` | YOLO (80 lớp COCO) + màu chủ đạo (11 màu cơ bản) + ô lưới 4×4 | Meilisearch `objects` (cls/grid/color là TỪ RIÊNG, vd "bicycle 2a red") |

**Vì sao tách nhiều nhánh embedding?** Mỗi model "nhìn" ảnh khác nhau (đa ngữ
vs. chi tiết vs. ensemble) — giai đoạn online sẽ hợp nhất kết quả của tất cả
bằng RRF thay vì chọn 1 model duy nhất, bù trừ điểm yếu cho nhau.

---

## 2 · Online — Xử lý 1 câu truy vấn

Chạy real-time mỗi lần bấm Tìm kiếm — encode qua GPU Kaggle (không cần GPU
máy dev), search FAISS/Meilisearch song song rồi hợp nhất.

```mermaid
flowchart TD
  classDef online fill:#3a2c12,stroke:#ffb454,color:#ffefd8,font-weight:600;
  classDef infra fill:#1c2340,stroke:#8aa2ff,color:#e6ebff,font-weight:600;
  classDef io fill:#161b26,stroke:#3a4256,color:#c7cede,stroke-dasharray: 4 3;

  Q["Câu mô tả tiếng Việt<br/>+ loại KIS / QA / TRAKE<br/>+ ghi đè tay OCR/ASR/Object (tuỳ chọn)"]:::io

  Q --> QS["query_service — 4 việc LLM làm song song"]:::online
  QS --> CMC["Mệnh đề đa ngữ<br/>(giữ tiếng Việt)"]:::io
  QS --> CEN["Mệnh đề dịch tiếng Anh"]:::io
  QS --> OKW["Từ khoá OCR<br/>(chỉ tên riêng/số liệu RÕ)"]:::io
  QS --> APA["3-5 biến thể ASR<br/>(diễn giải giọng bản tin)"]:::io

  CMC & CEN --> ENC["query_encoders<br/>gọi GPU Kaggle qua ngrok"]:::online

  ENC --> SM["FAISS: metaclip2<br/>maxmean đa mệnh đề"]:::online
  ENC --> SP["FAISS: pecore<br/>maxmean đa mệnh đề"]:::online
  ENC --> SB["FAISS: beit3"]:::online
  ENC --> SC["FAISS: capemb<br/>(câu đầy đủ, không tách)"]:::online

  OKW --> MSO["Meili: OCR — MỖI từ khoá<br/>tra riêng, tránh loãng tín hiệu"]:::online
  Q --> MSOF["Meili: OCR nguyên văn câu<br/>(trọng số thích ứng theo cue)"]:::online
  APA --> MSA["Meili: ASR đa biến thể<br/>→ RRF nội bộ → căn ±2s theo pts_time"]:::online
  Q -.->|nếu câu nêu rõ vật+màu| MSOB["Meili: Object + màu<br/>(cls/grid/color là từ riêng)"]:::online
  Q --> ENT["LLM: suy TÊN RIÊNG ẨN<br/>(khác OCR-keyword — cái này SUY LUẬN)"]:::online
  ENT -.->|chỉ khi confidence=high| MSE["Meili: OCR/ASR theo tên suy ra"]:::online

  SM & SP & SB & SC & MSO & MSOF & MSA & MSE --> RRF["core.fusion.rrf<br/>Reciprocal Rank Fusion<br/>trọng số riêng theo KIS/QA/TRAKE"]:::online
  MSOB -.-> RRF

  RRF --> DEDUP["Dedup theo video<br/>tối đa 8 khung/video"]:::online
  DEDUP --> HYD["Lấy metadata thật<br/>(video, n, frame_idx, pts_time)"]:::online
  HYD --> UI["Kết quả hiển thị<br/>+ panel minh bạch: nguồn nào,<br/>trọng số bao nhiêu, khớp gì"]:::io
```

### Chi tiết từng bước

| Bước | Vì sao thiết kế vậy |
|---|---|
| Trích mệnh đề / dịch | Câu dài bị cắt/mờ tín hiệu ở model CLIP-family (giới hạn ~77 token) — LLM tách thành nhiều câu ngắn, mỗi câu tra riêng rồi gộp. |
| maxmean đa mệnh đề | Mỗi mệnh đề search FAISS riêng (topk rộng) → hợp candidate → điểm = `max + 0.3×mean` qua các mệnh đề khớp — thắng RRF/MAX/MEAN thuần khi đo thật. |
| OCR-keyword riêng lẻ | Đã đo thật: tên riêng hiếm (2/167,850 khung) bị từ phổ biến áp đảo nếu tra chung 1 câu — tách riêng từng từ khoá sửa đúng vấn đề. |
| ASR theo ý nghĩa | Transcript thật hiếm dùng đúng từ câu hỏi — LLM đóng vai phóng viên diễn đạt lại 3-5 cách, rồi mới tra BM25, fuse nội bộ thành 1 tín hiệu. |
| Object + màu | CHỈ bật khi câu nêu rõ vật+màu đặc trưng (regex chặt) — vật thể chung chung 1 mình dễ làm loãng vì xuất hiện khắp nơi. |
| RRF hợp nhất | `score = Σ weight / (60 + rank + 1)` — miễn nhiễm với thang điểm khác nhau giữa cosine similarity và BM25. |

**Điểm cốt lõi:** mọi trọng số (OCR/ASR/object/entity so với hình ảnh) đều đo
được bằng số trong [`core/config.py`](core/config.py), khác nhau theo
KIS/QA/TRAKE — không phải đoán, chỉnh ở đúng 1 chỗ.

---

## 3 · Tính năng phụ — Temporal, tìm ảnh giống, nộp bài

3 luồng riêng, dùng lại module đã có ở trên nhưng ghép khác nhau cho từng mục
đích.

### Temporal / TRAKE — tìm chuỗi sự kiện đúng thứ tự

```mermaid
flowchart LR
  classDef online fill:#3a2c12,stroke:#ffb454,color:#ffefd8,font-weight:600;
  EV["Sự kiện E1..En<br/>theo thứ tự"]:::online --> STRIP["Bỏ khung mẫu câu<br/>'Khoảnh khắc đầu tiên...'"]:::online
  STRIP --> ENCE["Encode từng event<br/>metaclip2"]:::online
  ENCE --> ANCHOR["Boundary-anchor<br/>search riêng E1 & En<br/>→ giao tập video"]:::online
  ANCHOR --> CAP150["Cắt còn ≤150 video<br/>giữ thứ tự rank"]:::online
  CAP150 --> FETCH["Lấy TOÀN BỘ vector<br/>của từng video"]:::online
  FETCH --> BONUS["+ điểm thưởng OCR/ASR<br/>nếu event nhắc chữ/lời"]:::online
  BONUS --> DP["DANTE DP<br/>chuỗi khung tăng dần thời gian,<br/>tối ưu cosine − phạt khoảng cách"]:::online
  DP --> SEQ["Chuỗi khung kết quả<br/>đúng thứ tự sự kiện"]:::online
```

### Tìm ảnh giống (image-to-image)

```mermaid
flowchart LR
  classDef online fill:#3a2c12,stroke:#ffb454,color:#ffefd8,font-weight:600;
  IMG["Khung mẫu<br/>đã chọn từ kết quả"]:::online --> DINO["Encode DINOv3"]:::online --> SIM["FAISS search<br/>index dinov3"]:::online --> RES["Ảnh tương tự nhất"]:::online
```

### Submit — đóng gói nộp bài

```mermaid
flowchart LR
  classDef online fill:#3a2c12,stroke:#ffb454,color:#ffefd8,font-weight:600;
  PICK["Chọn khung từ<br/>search/temporal"]:::online --> ROW["Thêm dòng<br/>video, frame_idx"]:::online --> VALID["Validate<br/>đúng chuẩn BTC"]:::online --> PACK["Đóng gói CSV/ZIP<br/>nộp Codabench"]:::online
```

---

Sơ đồ phản ánh code thật trong `aic-system/` tại thời điểm viết — khi đổi
model/trọng số, cập nhật lại file này để nhóm luôn nhìn đúng trạng thái hệ
thống.
