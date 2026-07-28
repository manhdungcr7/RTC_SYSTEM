# AIC Retrieval System

Hệ thống tìm kiếm khung hình video cho cuộc thi AIC 2026 (kiểu LSC/VBS): tìm
khung hình đúng theo mô tả tiếng Việt, kết hợp nhiều tín hiệu (hình ảnh, OCR,
ASR, vật thể+màu) — **thiết kế "truyền thống có tương tác"**: người vận hành
gõ câu mô tả + có thể ghi đè tay OCR/ASR/Object khi biết chính xác cần tìm gì,
không phải hộp đen tự động hoàn toàn.

Kiến trúc: FastAPI (backend) + React/Vite (frontend) + Milvus (5 collection
vector: metaclip2/pecore/beit3/capemb/dinov3) + Elasticsearch (OCR/ASR/objects)
+ 1 notebook Kaggle chạy encoder (GPU free, vì máy dev không đủ VRAM/RAM nạp
4 model cùng lúc).

---

## 1. Yêu cầu máy

- **Docker Desktop** (Windows/Mac) hoặc Docker Engine + Compose (Linux) — bật
  WSL2 backend nếu Windows.
- **≥ 8GB RAM trống** dành cho Docker sau khi trừ các app khác đang mở (Milvus
  cần load vector vào RAM của chính nó, không phải VRAM). Máy càng nhiều RAM
  càng ổn — hệ đã từng crash khi RAM trống < 1.5GB lúc Milvus reload collection.
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

### 3a. Database đã build sẵn (Milvus + Elasticsearch) — BẮT BUỘC

Repo: **[manhdungcr7/aic2026-milvus-es-db](https://huggingface.co/datasets/manhdungcr7/aic2026-milvus-es-db)**
— kết quả pipeline offline đã chạy xong (167,850 keyframe đã embed +
OCR/caption/objects + 111,411 đoạn ASR, ~13GB) — **không cần chạy lại pipeline
indexing**, chỉ cần tải đúng vào thư mục Docker dùng.

```bash
hf download manhdungcr7/aic2026-milvus-es-db \
  --repo-type dataset --local-dir aic-system/docker/volumes
```

Kết quả phải có đúng cấu trúc con `docker/volumes/{etcd,minio,milvus,es}/`.
(Lần đầu setup thì chưa có Docker nào chạy nên cứ tải bình thường. Chỉ cần
lưu ý nếu SAU NÀY tải lại/cập nhật bộ dữ liệu mới: phải `docker compose stop`
trước — không tải đè lên volume đang có container ghi vào, dễ hỏng dữ liệu.)

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
    etcd/  minio/  milvus/  es/
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

Lần đầu sẽ build image backend/frontend (vài phút) + tải image Milvus/ES/etcd/
minio. Theo dõi log:

```bash
docker compose logs -f backend
```

Khi thấy `Application startup complete` là backend sẵn sàng. Mở trình duyệt:

- **Frontend (giao diện dùng)**: http://localhost:5173
- Backend API (debug trực tiếp nếu cần): http://localhost:8080
- Milvus UI (Attu, xem collection/dữ liệu): http://localhost:8000
- Elasticsearch: http://localhost:9200

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

- **Container `milvus` tự thoát (exit 137 = OOM-kill, hoặc exit 1 kèm log
  "disconnected from etcd")**: RAM máy không đủ lúc Milvus tải collection vào
  RAM của chính nó (không phải RAM Docker Desktop cấp, mà RAM host thật —
  kiểm tra RAM trống trước khi `docker compose up`). Đóng bớt ứng dụng nặng
  (trình duyệt nhiều tab, IDE...) rồi `docker compose up -d milvus` lại.
- **Backend log lỗi `UnicodeEncodeError`**: đã set `PYTHONIOENCODING=utf-8`
  trong Dockerfile, không cần sửa gì nếu chạy qua Docker (chỉ gặp nếu chạy
  `python -m uvicorn` trực tiếp trên Windows console không phải qua Docker).
- **`/search` trả 0 kết quả hoặc lỗi 500**: kiểm tra `docker compose logs
  backend` — thường do `AIC_REMOTE_ENCODER_URL` sai/hết hạn (notebook Kaggle
  đã tắt) hoặc Milvus/ES chưa healthy (`docker compose ps`, đợi cột STATUS
  thành `healthy`).
- **Không có API key LLM**: các trường "Mệnh đề tiếng Anh", "Từ khoá OCR
  (LLM trích)" sẽ rỗng — hệ thống vẫn tìm được bằng hình ảnh (metaclip2/
  pecore/beit3/capemb) + OCR/ASR nguyên văn câu tiếng Việt, chỉ mất các bước
  xử lý câu qua LLM.

---

## 8. Dùng giao diện (tóm tắt)

- **Search**: gõ câu mô tả tiếng Việt → chọn loại (KIS/QA/TRAKE) → Top K →
  bấm Tìm kiếm. Mở "Bộ lọc nâng cao" để tự nhập tay OCR/ASR/Object khi biết
  chính xác chữ/lời/vật thể cần tìm (bỏ qua đoán tự động — khuyến nghị dùng
  khi câu mô tả có tên riêng/chữ cụ thể mà bạn tự đọc thấy).
  - **Object**: chỉ nên dùng khi vật thể + màu ĐẶC TRƯNG (vd "áo đỏ, duy
    nhất"), tránh gõ 1 danh từ chung chung (vd "person") — dễ làm loãng do
    vật thể phổ biến xuất hiện khắp nơi.
- Panel "Chi tiết truy vấn đã dùng" cho xem đúng những gì hệ thống thực sự
  tra (mệnh đề dịch, từ khoá OCR trích, trọng số từng nguồn) — hữu ích để
  hiểu VÌ SAO ra kết quả đó.
- Click 1 kết quả → modal chi tiết: xem frame lớn/video, filmstrip lân cận,
  nút "🔍 Tìm ảnh giống" (dùng dinov3), nút thêm vào file nộp bài.
- **Temporal**: tìm chuỗi sự kiện theo đúng thứ tự thời gian trong 1 video
  (bài TRAKE).
- **Submit**: gom các frame đã chọn thành file CSV đúng chuẩn BTC, đóng gói
  nộp bài.
