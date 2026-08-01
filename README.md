# AIC Retrieval System

Hệ thống tìm kiếm khung hình video cho cuộc thi AIC 2026 (kiểu LSC/VBS): tìm
khung hình đúng theo mô tả tiếng Việt, kết hợp nhiều tín hiệu (hình ảnh, OCR,
ASR, vật thể+màu) — **thiết kế "truyền thống có tương tác"**: người vận hành
gõ câu mô tả + có thể ghi đè tay OCR/ASR/Object khi biết chính xác cần tìm gì,
không phải hộp đen tự động hoàn toàn.

Kiến trúc: FastAPI (backend) + React/Vite (frontend) + FAISS (5 index vector
in-process: metaclip2/pecore/beit3/capemb/dinov3, không cần server riêng) +
Meilisearch (OCR/ASR/objects) + 1 notebook Kaggle chạy encoder (GPU free, vì
máy dev không đủ VRAM/RAM nạp 4 model cùng lúc).

*(Trước dùng Milvus+Elasticsearch — đã đổi sang FAISS+Meilisearch vì máy dev
RAM hạn chế: Milvus (kèm etcd+MinIO) nhiều lần "healthy" giả — báo sống nhưng
nội bộ đã hết RAM, treo mọi truy vấn. FAISS/Meilisearch nhẹ hơn nhiều, không
cần server/cluster phụ trợ, đủ nhanh ở quy mô 167,850 vector — xem PIPELINE.md.)*

📊 Xem **[PIPELINE.md](PIPELINE.md)** — sơ đồ chi tiết toàn bộ thuật toán, từ
video thô (offline) tới xử lý 1 câu truy vấn (online), có giải thích lý do
thiết kế từng bước.

---

## 1. Yêu cầu máy

- **Docker Desktop** (Windows/Mac) hoặc Docker Engine + Compose (Linux) — bật
  WSL2 backend nếu Windows.
- **≥ 4GB RAM trống** dành cho Docker sau khi trừ các app khác đang mở (FAISS
  nạp thẳng vector vào RAM tiến trình backend, không phải VRAM — nhẹ hơn nhiều
  so với Milvus trước đây vì không có etcd/MinIO/query-coordinator phụ trợ).
- Tài khoản **Kaggle** (free) — dùng GPU T4x2 free để chạy encoder, xem mục 4.
- 1 API key LLM (**Anthropic/OpenAI/Gemini**, chọn 1) — dùng để dịch câu, mở
  rộng câu truy vấn, trích OCR-keyword, sinh biến thể ASR. Không có key nào
  thì hệ vẫn chạy nhưng mất các bước này (chỉ còn tìm bằng hình ảnh thuần).
- Ổ đĩa trống đủ chứa dữ liệu (xem mục 3 — có thể tới hàng chục-trăm GB tuỳ
  bạn tải đủ video gốc hay không).

Backend/frontend chạy **trong Docker**, không cần cài Node/GPU driver riêng.
Chỉ cần **Python 3 + pip** trên máy host cho bước tải dữ liệu (mục 3, dùng
`huggingface_hub`) — không dùng để chạy hệ thống, chỉ để tải file.

---

## 2. Lấy code

```bash
git clone https://github.com/manhdungcr7/RTC_SYSTEM.git
cd RTC_SYSTEM
```

(Nếu repo chỉ chứa đúng thư mục `aic-system/` làm root thì bỏ qua bước `cd`
thêm; nếu repo là cả project lớn hơn thì `cd aic-system` trước khi làm tiếp.)

---

## 3. Lấy dữ liệu (KHÔNG có trong Git — quá lớn)

2 gói dữ liệu đã up sẵn lên **Hugging Face Hub** (public, không cần đăng nhập/
token để tải) — cài `huggingface_hub` rồi tải thẳng bằng lệnh dưới, không cần
chờ Google Drive:

```bash
pip install -U huggingface_hub
```

**Cả 2 lệnh tải bên dưới đều RESUME được** nếu bị ngắt mạng/tắt máy giữa
chừng — chạy lại y nguyên lệnh, nó tự tiếp tục từ chỗ dở dang, không tải lại
từ đầu. Tổng dữ liệu ~18GB (13GB DB + 5.3GB keyframe) nên tuỳ tốc độ mạng có
thể mất từ vài chục phút tới vài giờ — cứ để chạy nền, không cần canh chừng.

### 3a. Database đã build sẵn (FAISS + Meilisearch) — BẮT BUỘC

Repo: **[manhdungcr7/aic2026-faiss-meili-db](https://huggingface.co/datasets/manhdungcr7/aic2026-faiss-meili-db)**
— kết quả pipeline offline đã chạy xong (167,850 keyframe đã embed +
OCR/caption/objects + 111,411 đoạn ASR) — **không cần chạy lại pipeline
indexing**, chỉ cần tải đúng vào thư mục Docker dùng.

```bash
hf download manhdungcr7/aic2026-faiss-meili-db \
  --repo-type dataset --local-dir aic-system/docker/volumes
```

Kết quả phải có đúng cấu trúc con `docker/volumes/{faiss,meili}/`. (Lần đầu
setup thì chưa có Docker nào chạy nên cứ tải bình thường. Chỉ cần lưu ý nếu
SAU NÀY tải lại/cập nhật bộ dữ liệu mới: phải `docker compose stop` trước —
không tải đè lên volume đang có container Meilisearch ghi vào.)

### 3b. Keyframe + CSV map — BẮT BUỘC

Repo: **[manhdungcr7/aic2026-keyframes](https://huggingface.co/datasets/manhdungcr7/aic2026-keyframes)**
— sản phẩm riêng của pipeline xử lý (TransNetV2 keyframe + OCR/caption,
~5.3GB), không tải được từ đâu khác:

```bash
hf download manhdungcr7/aic2026-keyframes \
  --repo-type dataset --local-dir aic-system/data
```

Kết quả phải có các thư mục `data/raw_L21_a/`, `data/raw_account0/`...,
mỗi thư mục có `keyframes/<video>/*.webp` + `maps/<video>.csv`.

Không cần `videos_full/videos/*.mp4` để TÌM KIẾM (chỉ cần keyframe cho
thumbnail) — xem mục 3c để lấy video gốc nhanh hơn nếu cần phát lại.

### 3c. Video gốc (`.mp4`) — TẢI TRỰC TIẾP từ nguồn BTC, NHANH HƠN Google Drive

Video gốc (78GB+) là dữ liệu **CÔNG KHAI của BTC**, không cần qua Google Drive
(Drive sẽ chậm hơn nhiều vì phải giới hạn theo tốc độ UPLOAD của người gửi
trước, rồi mới tải xuống lại) — tải THẲNG từ server gốc bằng script có sẵn,
đa luồng (aria2c), tốc độ full:

```bash
# Cài aria2 nếu chưa có (Windows: winget install aria2.aria2, hoặc choco/scoop)
cd aic-system/indexing
bash download_all_videos.sh
```

Script tự resume nếu bị ngắt giữa chừng (chạy lại bao nhiêu lần cũng được),
tự bỏ qua shard đã tải đủ. Tải xong, giải nén các file `Videos_*.zip` vào
`aic-system/data/videos_full/videos/` (mỗi video 1 file `.mp4`, tên khớp với
tên trong CSV map ở mục 3b).

Chỉ cần bước này nếu muốn xem/phát lại video gốc trong modal chi tiết — tìm
kiếm/xem thumbnail không phụ thuộc vào nó.

Sau khi giải nén xong, cấu trúc phải giống:

```
aic-system/
  data/
    raw_L21_a/out/keyframes/<video>/<n>.webp, .../maps/<video>.csv
    raw_account0/out/<sub_batch>/keyframes/..., maps/...
    ... (các shard raw_* khác)
    videos_full/videos/<video>.mp4
  docker/volumes/
    faiss/  meili/
```

---

## 4. Chạy encoder trên Kaggle (GPU free)

Máy dev thường không đủ VRAM/RAM nạp cùng lúc 4 model text-encoder
(MetaCLIP-2/PE-Core/BEiT-3/capemb) — thay vào đó chạy chúng trên Kaggle
(GPU T4x2 free) qua 1 API nhỏ, backend gọi sang lấy vector.

1. Vào [kaggle.com](https://kaggle.com) → **New Notebook**.
2. Cài đặt notebook: **Settings → Accelerator → GPU T4 x2**, **Internet: ON**.
3. **Add-ons → Secrets** → thêm secret tên `NGROK_AUTHTOKEN` (lấy token free
   tại [ngrok.com](https://dashboard.ngrok.com/get-started/your-authtoken)) →
   bật **Attach** cho notebook này.
4. Copy toàn bộ nội dung file [`indexing/kaggle/11_encode_service.py`](indexing/kaggle/11_encode_service.py)
   vào 1 cell, bấm **Save & Run All (Commit)** (khuyên dùng chế độ này thay vì
   "Run" thường — đảm bảo server tiếp tục chạy dù đóng trình duyệt/tab Kaggle).
5. Đợi log in ra:
   ```
   URL PUBLIC: NgrokTunnel: "https://xxxx.ngrok-free.app" -> "http://localhost:8000"
   API_KEY   : xxxxxxxxxxxx
   ```
6. Copy 2 giá trị này vào file `.env` ở bước 5 dưới đây.

**Lưu ý:** phiên Kaggle free tối đa ~9-12 tiếng hoặc tự ngắt nếu rảnh lâu —
đủ cho 1 buổi luyện tập/test, **KHÔNG có SLA nên không nên dựa vào lúc thi
thật**. Mỗi lần khởi động lại notebook, URL/API_KEY sẽ đổi — phải cập nhật
lại `.env` và restart container `backend`.

---

## 5. Cấu hình `.env`

```bash
cd docker
cp .env.example .env
```

(File `.env` phải nằm trong `aic-system/docker/`, cạnh `docker-compose.yml`
— đó là nơi Docker Compose tự đọc, KHÔNG phải thư mục `aic-system/`.)

Mở `.env`, điền:
- `AIC_REMOTE_ENCODER_URL` / `AIC_REMOTE_ENCODER_KEY` — lấy từ bước 4.
- Ít nhất 1 trong `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY`.

---

## 6. Chạy hệ thống

```bash
cd docker
docker compose up -d --build
```

Lần đầu sẽ build image backend/frontend (vài phút) + tải image Meilisearch.
Theo dõi log:

```bash
docker compose logs -f backend
```

Khi thấy `Application startup complete` là backend sẵn sàng. Mở trình duyệt:

- **Frontend (giao diện dùng)**: http://localhost:5173
- Backend API (debug trực tiếp nếu cần): http://localhost:8080
- Meilisearch (xem index/thử search thô): http://localhost:7700

### Dừng hệ thống

```bash
docker compose down          # dừng, giữ dữ liệu (volumes)
```

### Đổi lại encoder Kaggle (URL/KEY mới sau khi restart notebook)

Sửa `.env` rồi:

```bash
docker compose up -d --force-recreate backend
```

---

## 7. Xử lý sự cố (đã gặp thật khi phát triển)

- **Backend log không hiện gì dù container "Up"**: bình thường — Python
  buffer stdout khi không gắn TTY, đã set `PYTHONUNBUFFERED=1` trong Dockerfile
  để giảm độ trễ log, nhưng vẫn có thể trễ vài giây. Kiểm tra bằng
  `curl http://localhost:8080/health` thay vì chỉ nhìn log nếu nghi ngờ treo.
- **Backend log lỗi `UnicodeEncodeError`**: đã set `PYTHONIOENCODING=utf-8`
  trong Dockerfile, không cần sửa gì nếu chạy qua Docker (chỉ gặp nếu chạy
  `python -m uvicorn` trực tiếp trên Windows console không phải qua Docker).
- **`/search` trả 0 kết quả hoặc lỗi 500**: kiểm tra `docker compose logs
  backend` — thường do `AIC_REMOTE_ENCODER_URL` sai/hết hạn (notebook Kaggle
  đã tắt) hoặc Meilisearch chưa healthy (`docker compose ps`, đợi cột STATUS
  thành `healthy`).
- **Meilisearch trả lỗi 403 `invalid_api_key`**: đã gặp thật — set biến môi
  trường `MEILI_MASTER_KEY` (dù để GIÁ TRỊ RỖNG) cũng đủ khiến Meilisearch bật
  yêu cầu xác thực, khác hẳn KHÔNG set biến đó. `docker-compose.yml` mặc định
  KHÔNG set biến này (chạy không khoá) — chỉ thêm nếu chủ động muốn bật khoá
  thật, và phải build lại index từ đầu nếu đổi qua lại giữa 2 chế độ (đã đo
  thật: đổi chế độ khoá làm Meilisearch coi là instance khác, mất dữ liệu cũ).
- **Không có API key LLM**: các trường "Mệnh đề tiếng Anh", "Từ khoá OCR
  (LLM trích)" sẽ rỗng — hệ thống vẫn tìm được bằng hình ảnh (metaclip2/
  pecore/beit3/capemb) + OCR/ASR nguyên văn câu tiếng Việt, chỉ mất các bước
  xử lý câu qua LLM.

---

## 8. Dùng giao diện (chi tiết)

3 trang: **Search** (KIS/QA + lọc video trước), **Temporal** (TRAKE), **Submit**
(đóng gói nộp bài). Nguyên tắc xuyên suốt: **mọi bước tự động đều có thể ghi đè
tay** — máy đoán là mặc định tốt, nhưng khi bạn tự đọc/nghe thấy chính xác cần
tìm gì thì luôn có ô để nhập thẳng, bỏ qua đoán tự động.

### 8.1. Trang Search

**a) Lọc video trước (tuỳ chọn, thu gọn mặc định — bấm "▸ Lọc video trước" để mở)**

Bước NÀY ĐỘC LẬP với tìm khung hình bên dưới — không bắt buộc phải làm trước.
Dùng khi bạn muốn thu hẹp phạm vi tìm về 1 nhóm video trước (vd biết chắc đáp
án nằm trong video nấu ăn, hoặc muốn duyệt nhanh 1 thể loại):

1. Gõ nội dung (tìm theo ASR + caption + tiêu đề gộp của cả video) và/hoặc
   chọn **thể loại** (Tin tức / Thể thao / Nấu ăn / Giải trí — suy từ kênh
   YouTube gốc, xem PIPELINE.md) — để trống ô gõ nếu chỉ muốn lọc theo thể loại.
2. Bấm **"Tìm video"** → hiện NGAY lưới video (ảnh đại diện, tiêu đề, thể loại) —
   xem kết quả ở bước này mà **không** bị ép làm tiếp gì cả.
3. Muốn dùng cho bước tìm khung hình: tick chọn video (hoặc "Chọn tất cả"),
   bấm **"Dùng N video đã chọn làm phạm vi tìm khung hình"**. Phạm vi hiện
   thành banner trên ô tìm kiếm chính, có nút ✕ để bỏ (quay về tìm toàn kho).

**b) Ô tìm kiếm chính**

- Gõ mô tả (tiếng Việt hoặc Anh) → chọn loại **KIS / QA / TRAKE** (TRAKE nên
  dùng trang Temporal thay vì đây) → chỉnh **Top K** → tick **"Mở rộng câu
  (LLM)"** nếu muốn LLM diễn giải thêm câu trước khi tìm.
- Hàng **"Model"**: tick chọn nhánh embedding nào tham gia — mặc định CHỈ
  MetaCLIP-2 (nhánh chính, đủ dùng phần lớn trường hợp và nhanh nhất). Tick
  thêm BEiT-3 / PE-Core / Qwen3-Embedding (caption) / Qwen3-Embedding (ASR ngữ
  nghĩa) / DINOv3 nếu muốn — mỗi nhánh thêm là 1 lượt gọi model từ xa (Kaggle),
  chậm hơn nhưng có thể ra kết quả tốt hơn cho câu khó.

**c) "Bộ lọc nâng cao"** (bấm mở rộng)

- **OCR / ASR ghi đè tay**: biết chính xác chữ trên màn hình hoặc câu ai đó
  nói thì gõ thẳng vào đây — bỏ qua bước LLM/heuristic tự đoán.
- **"Lọc chắc chắn theo OCR/ASR"** (checkbox): khi bật, nếu OCR/ASR khớp với
  độ tin cậy cao, các nhánh còn lại (hình ảnh...) sẽ CHỈ tìm trong đúng những
  khung hình đã khớp (có nới thêm sai số — OCR vài khung lân cận, ASR ±8 giây,
  vì lời nói có thể trước/sau cảnh minh hoạ) thay vì chỉ cộng điểm mềm như
  bình thường. Có banner xanh báo khi cơ chế này thật sự kích hoạt; nếu OCR/ASR
  không đủ tin cậy, hệ thống tự quay về kiểu tìm mềm như cũ (không lỗi).
- **Object/màu/vị trí**: nhấp chọn từ danh sách tiếng Việt (không cần gõ tay,
  không cần nhớ tên tiếng Anh) — chọn vật thể (có ô gõ để lọc nhanh trong danh
  sách), chọn màu, và tuỳ chọn bấm ô trên lưới 4×4 để chỉ định vùng trong khung
  hình (vd góc trên-trái).
- **Ảnh tham chiếu (DINOv3)**: upload 1 ảnh (vd ảnh mẫu BTC đưa, hoặc ảnh bạn
  tìm được) — hệ thống tìm khung hình GIỐNG ảnh này, **kết hợp cùng** mô tả
  chữ và mọi tín hiệu khác trong RRF chung (không phải công cụ tách riêng).
- **Trọng số từng tín hiệu**: mỗi tín hiệu (metaclip2, pecore, beit3, capemb,
  dinov3, asr ngữ nghĩa, ocr, ocr từ khoá, asr, object, entity) có checkbox
  "ghi đè" + thanh trượt 0–3. KHÔNG tích = dùng số mặc định đã đo sẵn theo loại
  câu (KIS/QA/TRAKE); tích rồi kéo thanh trượt để tự tăng/giảm mức độ ảnh
  hưởng của tín hiệu đó cho đúng lần tìm này. Dùng khi thấy 1 tín hiệu bị lấn
  át (vd câu chỉ dựa vào lời thoại → tăng "asr" lên, giảm "metaclip2" xuống).

**d) Kết quả**

- Panel **"Chi tiết truy vấn đã dùng"**: xem đúng những gì hệ thống THỰC SỰ đã
  tra (mệnh đề đã dịch/tách, từ khoá OCR đã trích, trọng số + số kết quả từng
  nguồn) — để hiểu VÌ SAO ra kết quả đó, và biết chỗ nào nên ghi đè tay.
- Click 1 kết quả → modal chi tiết: ảnh lớn + video (tua tới đúng giây), dải
  khung hình lân cận (filmstrip, bấm để đổi khung đang chọn), nút **"🔍 Tìm ảnh
  giống"** (tìm nhanh ảnh giống chính khung này), nút **"+ Thêm frame này"**
  vào file nộp bài đang soạn.
- **"Tìm theo ảnh"** (cuối trang): công cụ RIÊNG, đơn giản — upload 1 ảnh, tìm
  khung hình giống ảnh đó, KHÔNG kèm mô tả chữ (khác ô "Ảnh tham chiếu" ở bộ
  lọc nâng cao, vốn kết hợp CẢ chữ lẫn ảnh trong cùng 1 lượt tìm).

### 8.2. Trang Temporal (TRAKE — chuỗi sự kiện theo thứ tự thời gian)

- Nhập từng sự kiện **E1, E2, ...** theo đúng thứ tự thời gian xảy ra trong
  video (bấm "+ Thêm sự kiện" / "− Bớt sự kiện" để đổi số lượng, tối thiểu 2).
- Nút **⚓** cạnh mỗi sự kiện: chọn ĐÚNG 2 sự kiện làm "neo" cho bước lọc video
  ứng viên ban đầu — mặc định dùng sự kiện đầu + cuối, nhưng nếu 1 cặp sự kiện
  Ở GIỮA đặc trưng/dễ nhận diện hơn (vd "4 chân chạm đất" dễ nhận hơn "lân xoay
  vòng trên cột") thì tự chọn cặp đó thay vào.
- **"▸ Ghi đè OCR/ASR theo từng sự kiện"**: mỗi sự kiện có thể tự nhập riêng
  chữ/lời cần khớp CHO ĐÚNG sự kiện đó (khác câu mô tả chung) — bỏ trống thì
  tự đoán theo câu sự kiện như bình thường.
- **"Tắt phạt khoảng cách"**: mặc định các sự kiện được ưu tiên xảy ra GẦN
  nhau về thời gian trong video (DANTE DP). Tick tắt khi các sự kiện có thể
  cách xa nhau (vd "vượt lên" rồi rất lâu sau mới "về đích").
- Kết quả: mỗi ứng viên là 1 video + đúng số khung hình theo thứ tự E1..En,
  click từng khung để xem chi tiết như trang Search.

### 8.3. Trang Submit

- Gom các frame đã "+ Thêm" từ trang Search/Temporal thành từng file CSV theo
  đúng tên truy vấn BTC yêu cầu (vd `query-p1-1-kis.csv`) — xem/sửa bảng trước
  khi chốt, hệ thống tự báo lỗi format (thiếu cột, sai số dòng, answer quá dài...).
- Bấm đóng gói để tải file `.zip` chứa thư mục `submission/` đúng chuẩn nộp
  Codabench (không nén trực tiếp `.csv`, xem `core/submit.py`).
