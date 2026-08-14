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

**Lưu ý quan trọng:** thư mục `RTC_SYSTEM/` sau khi clone CHÍNH LÀ root của dự
án (tương đương thư mục `aic-system/` trên máy dev gốc) — bên trong đã có sẵn
`api/`, `core/`, `config/`, `docker/`, `frontend/`, `indexing/` ngay cấp 1,
KHÔNG có thêm 1 lớp `aic-system/` bọc ngoài nữa. Mọi lệnh/đường dẫn trong
README này (`docker/...`, `data/...`, `indexing/...`) đều tính từ ngay trong
`RTC_SYSTEM/` — đừng thêm `aic-system/` vào trước, sẽ tạo nhầm thư mục và
Docker/backend sẽ không tìm thấy dữ liệu.

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
  --repo-type dataset --local-dir docker/volumes
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
  --repo-type dataset --local-dir data
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
cd indexing
bash download_all_videos.sh
```

Script tự resume nếu bị ngắt giữa chừng (chạy lại bao nhiêu lần cũng được),
tự bỏ qua shard đã tải đủ. Tải xong, giải nén các file `Videos_*.zip` vào
`data/videos_full/videos/` (mỗi video 1 file `.mp4`, tên khớp với tên trong
CSV map ở mục 3b).

Chỉ cần bước này nếu muốn xem/phát lại video gốc trong modal chi tiết — tìm
kiếm/xem thumbnail không phụ thuộc vào nó.

Sau khi giải nén xong, cấu trúc phải giống (tính từ `RTC_SYSTEM/`, KHÔNG có
lớp `aic-system/` bọc ngoài — xem lưu ý ở mục 2):

```
RTC_SYSTEM/
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

(File `.env` phải nằm trong `RTC_SYSTEM/docker/`, cạnh `docker-compose.yml`
— đó là nơi Docker Compose tự đọc, KHÔNG phải thư mục gốc `RTC_SYSTEM/`.)

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

2 trang: **Search** (`/`, dùng cho KIS/QA) và **Temporal** (`/temporal`, dùng
cho TRAKE). "Nộp bài" KHÔNG phải trang riêng — là 1 tab trong cột phải, dùng
chung cho cả 2 trang (frame thêm từ Search hay Temporal đều gom vào cùng chỗ).
Nguyên tắc xuyên suốt: **mọi bước tự động đều có thể ghi đè tay** — máy đoán
là mặc định tốt, nhưng khi bạn tự đọc/nghe thấy chính xác cần tìm gì thì luôn
có ô để nhập thẳng, bỏ qua đoán tự động. Phím `[` / `]` thu gọn cột trái/phải
khi cần xem kết quả rộng hơn.

### 8.1. Trang Search — cột trái (mọi đòn bẩy điều khiển)

**a) Ô truy vấn**

- Gõ mô tả tiếng Việt (Enter để tìm, Shift+Enter xuống dòng).
- **"Tách mệnh đề"**: gọi LLM tách câu dài thành các mệnh đề thị giác ngắn,
  hiện ra từng thẻ có thể **sửa chữ / tắt riêng / chỉnh trọng số 0–3** từng
  mệnh đề — đây chỉ là ĐỀ XUẤT, sửa/xoá/thêm tay thoải mái (nút "+ Thêm tay").
  Thanh **"Gộp mệnh đề: max + α·mean"** chỉnh mức đóng góp của điểm trung bình
  bên cạnh điểm cao nhất khi gộp nhiều mệnh đề lại (mặc định đã đo sẵn).
- Khi có mệnh đề, hộp **bản dịch tiếng Anh** hiện ra riêng cho PE-Core/BEiT-3
  (2 nhánh này chỉ hiểu tiếng Anh) — sửa được trực tiếp nếu thấy dịch sai nghĩa.

**b) Bàn trộn tín hiệu** — giống bàn trộn âm thanh thật, control chính của
toàn hệ thống:

- Mỗi nhánh có: chấm tròn bật/tắt (bấm để tắt hẳn khỏi tính toán — nhanh hơn;
  **Alt+bấm = SOLO**, chỉ chạy riêng nhánh đó, hữu ích khi gỡ câu khó), thanh
  trượt trọng số 0–2, ô số gõ tay.
- Nhánh THỊ GIÁC: metaclip2 (chính, đa ngữ, luôn nên bật), pecore, beit3,
  capemb (so khớp với caption đã sinh sẵn cho từng khung hình), asr_emb (khớp
  Ý NGHĨA lời thoại), dinov3 (cần ảnh mẫu — xem mục d).
- Nhánh CHỮ: ocr, asr, object — chỉ thật sự chạy khi bạn tự gõ nội dung ở các
  panel bên dưới (gõ vào là tự bật, không cần nhớ bật thêm công tắc).
- Nút **"Bật hết"** / **"Trọng số mặc định"** ở đầu bàn trộn.

**c) Chữ trên hình (OCR)** — 1 CƠ CHẾ DUY NHẤT (đã bỏ các lựa chọn match-mode
gây rối trước đây): gõ vài chữ bạn NHỚ được, không cần đủ, không cần đúng thứ
tự, **tự động chấp nhận sai chính tả nhẹ cho từng từ** (dung sai theo độ dài
từ — xem mục 9 "Cơ chế sai chính tả" nếu cần hiểu sâu). Chọn **Cộng điểm**
(mặc định, kết hợp mềm với tín hiệu khác) hoặc **Lọc cứng** (các nhánh khác
CHỈ tìm trong khung đã khớp chữ — tự động quay lại Cộng điểm nếu ra 0 kết quả).

**d) Lời thoại (ASR)** — tách 2 kiểu độc lập, tick riêng từng kiểu:
**"Khớp đúng từ"** (cùng cơ chế dung-sai-chính-tả như OCR) và **"Khớp ý
nghĩa"** (nhánh vector riêng, hiểu được đồng nghĩa — vd hỏi "giá xăng tăng"
vẫn ra đoạn nói "giá nhiên liệu leo thang"). Cửa sổ thời gian **trước/sau**
quanh đoạn thoại chỉnh riêng được (mặc định lệch, vì lời dẫn tin tức thường
nói TRƯỚC rồi hình minh hoạ mới lên). Cũng có Cộng điểm / Lọc cứng.

**e) Vật thể + màu** — gõ tên vật thể (có gợi ý danh sách tiếng Anh phổ biến,
vd person/car/dog) + chọn màu tuỳ chọn, bấm "Thêm điều kiện". (Đã bỏ lựa chọn
vị trí theo lưới 3×3 của bản trước — đo thấy ít tác dụng mà làm giao diện
rườm rà.)

**f) Ảnh tham chiếu** — kéo-thả ảnh vào khung, dán bằng Ctrl+V, hoặc bấm biểu
tượng 🔍 trên 1 khung hình kết quả để lấy luôn ảnh đó làm mẫu. Có nút **"Cắt
vùng"** (khoanh 1 vùng nhỏ trong ảnh — logo, mũ, biển số — trước khi tìm, độ
chính xác cao hơn hẳn so với để nguyên cả khung vì nền không còn lấn át).

**g) Loại trừ** — mô tả cảnh KHÔNG muốn thấy (vd "cảnh trong phòng họp"),
chỉnh mức trừ điểm, hoặc bật "Loại hẳn khung vượt ngưỡng giống" để loại cứng
thay vì chỉ trừ điểm mềm.

**h) Thu hẹp video** — gõ nội dung (tìm theo ASR + caption + tiêu đề gộp cả
video) và/hoặc chọn thể loại, bấm "Tìm video" → hiện lưới video để tick chọn
→ "Áp dụng N video làm phạm vi". Có tuỳ chọn **đảo ngược (loại trừ)** các video
đã chọn thay vì giới hạn trong đó. Banner xanh hiện khi đang có phạm vi giới
hạn, có nút bỏ nhanh.

**i) Gộp điểm & chống trùng** — 3 thanh trượt: tối đa khung hình giữ lại mỗi
video (1 khi đang quét rộng tìm đúng video, tăng lên khi đã biết video và cần
soi kỹ), gộp các khung quá gần nhau về thời gian, và tổng số kết quả trả về.

### 8.2. Kết quả & modal chi tiết

- Sau khi tìm, có tab lọc theo TỪNG NHÁNH riêng (vd chỉ xem bảng OCR đã xếp
  hạng thế nào, tách khỏi kết quả đã gộp) nếu bạn bật `branch_lists`.
- Click 1 khung hình bất kỳ (không chỉ khung hạng cao nhất) → modal **"Giải
  thích"** mở ra, LUÔN đầy đủ: ảnh lớn, video tua tới đúng giây, caption đã
  sinh, chữ OCR đọc được, vật thể nhận diện, đoạn lời thoại quanh đó, và (nếu
  bật `explain`) bảng đóng góp điểm từng nhánh + từng mệnh đề — công cụ chẩn
  đoán chính: mệnh đề nào yếu thì biết ngay nên viết lại hay hạ trọng số.
- Phím tắt khi đang xem kết quả: mũi tên di chuyển, `p` ghim, `a`/`d` đánh dấu
  đúng/sai (phản hồi để tìm lại), `r` dùng làm ảnh tham chiếu, `s` thêm vào
  file nộp bài đang soạn, `w` mở workbench cả video, `c` so sánh.

### 8.3. Trang Temporal (TRAKE — chuỗi sự kiện theo thứ tự thời gian)

- **Bối cảnh chung** (tuỳ chọn): 1 câu mô tả chung cho CẢ chuỗi (vd "đoạn video
  múa lân, một con lân màu vàng đen trắng") — được chèn vào TRƯỚC mỗi sự kiện
  lúc mã hoá, giúp các nhánh thị giác "thấy" màu sắc/chủ thể chung mà từng câu
  sự kiện ngắn không nhắc lại. Không ảnh hưởng thuật toán dò chuỗi phía sau.
- Nhập từng sự kiện **E1, E2, ...** đúng thứ tự thời gian (nút "+ Thêm sự
  kiện", tối thiểu 2). Nút **⚓** cạnh mỗi sự kiện: chọn ĐÚNG 2 sự kiện làm neo
  thị giác cho bước lọc video ứng viên ban đầu — mặc định đầu+cuối, nhưng nếu
  1 cặp sự kiện Ở GIỮA đặc trưng hơn (vd "4 chân chạm đất" dễ nhận hơn "lân
  xoay trên cột") thì tự chọn cặp đó thay vào.
- **"Chữ/lời riêng"** (mở rộng): mỗi sự kiện tự nhập riêng chữ trên hình / lời
  thoại cần khớp CHO ĐÚNG sự kiện đó — khác câu mô tả chung, bỏ trống thì tự
  đoán theo câu sự kiện như bình thường. Có thêm ô 🔒 khoá frame_idx nếu bạn
  đã TỰ TÌM RA chắc chắn 1 sự kiện — DP sẽ ép đi qua đúng khung đó, không gian
  tìm các sự kiện còn lại co lại đáng kể (đòn bẩy mạnh nhất cho chuỗi dài).
- **Bàn trộn tín hiệu** — giống hệt Search về giao diện, CHỈ đổi cách CHẤM
  ĐIỂM từng khung hình, KHÔNG đụng thuật toán DP/boundary-anchor phía sau:
  - Nhánh thị giác phụ (pecore/beit3/capemb): tắt mặc định, bật khi câu mô tả
    chi tiết mà metaclip2 thuần chưa phân biệt được.
  - Nhánh **ocr**/**asr**: bật mặc định (khớp với câu chữ/lời đã nhập ở trên,
    trọng số mặc định 0.25/0.15) — tự tắt hoặc chỉnh nếu thấy nó kéo lệch kết
    quả sang video sai (đây là trọng số DÙNG CHUNG cho mọi sự kiện, không phải
    riêng từng sự kiện — câu chữ/lời đã nhập riêng theo sự kiện ở trên rồi).
  - Sự kiện DÀI/nhiều chi tiết cũng được tự tách mệnh đề như Search (mỗi mệnh
    đề encode riêng rồi gộp max+mean) — sự kiện ngắn 1 vế thì không đổi gì.
- **Không còn phạt khoảng cách thời gian** giữa các sự kiện (đã bỏ hẳn theo
  yêu cầu — trước đây có tuỳ chọn "Tắt phạt khoảng cách", giờ LUÔN tắt mặc
  định, không có ô để bật lại) — hệ thống không giả định các sự kiện phải xảy
  ra gần nhau, dựa hoàn toàn vào tín hiệu thị giác/chữ/lời thật.
- **Thu hẹp video**: y hệt Search, thu hẹp trước khi dò chuỗi.
- **Nâng cao**: chỉnh số video ứng viên/neo (per_event) — tăng nếu nghi ngờ
  video đúng bị lọt khỏi tập ứng viên ban đầu.
- Kết quả: mỗi ứng viên là 1 video + đúng số khung hình theo thứ tự E1..En,
  có nút **"đổi khung"** xem khung thay thế cho từng vị trí (không phải chạy
  lại cả chuỗi), click từng khung mở modal "Giải thích" đầy đủ như Search.

### 8.4. Tab "Nộp bài" (cột phải, dùng chung Search + Temporal)

- **Tạo file kết quả**: đặt tên TRÙNG tên câu truy vấn BTC giao (vd
  `query-p1-1-kis`, không kèm `.csv`), chọn loại KIS/QA/TRAKE.
- **Đổi tên file đã tạo**: ô tên ngay đầu bảng của file đang mở — sửa xong bấm
  ra ngoài hoặc Enter để lưu (báo lỗi nếu trùng tên file khác).
- TRAKE: ô **"số sự kiện"** chỉnh được số cột frame (E1..En) — gõ số rồi bấm
  ra ngoài/Enter để áp dụng.
- Thêm frame bằng phím `s` khi đang xem kết quả ở Search/Temporal, hoặc nút
  "Đưa vào bản nháp" ở mỗi chuỗi TRAKE. Kéo thả để đổi thứ tự dòng (CÓ Ý
  NGHĨA — dòng trên cùng là đáp án tin nhất).
- Tự báo lỗi/cảnh báo tại chỗ: thiếu cột, sai số dòng TRAKE, answer quá 100
  ký tự, trùng dòng, 2 dòng cùng video cách nhau <10 khung (nghi cùng cảnh).
- **Xem trước CSV** (nút "Cập nhật") — đúng thứ SẼ NỘP, kể cả quy tắc bọc
  ngoặc kép, do backend dựng (không phải preview giả ở frontend).
- Tải riêng từng file `.csv`, hoặc **"Đóng gói ZIP"** toàn bộ file đang có
  thành đúng cấu trúc nộp Codabench. Ô đếm "Đã nộp lên Codabench: x/3" tự bấm
  +1 sau mỗi lần nộp thật (tối đa 3 lần/gói theo luật BTC).

---

## 9. Cơ chế sai chính tả OCR/ASR — hoạt động thế nào

OCR và "Khớp đúng từ" của ASR dùng CHUNG 1 cơ chế: Meilisearch tự động dung
sai theo TỪNG TỪ ở cấp INDEX (không chỉnh được per-query) — mặc định: từ 1-4
ký tự không dung sai (phải gõ đúng), từ 5-8 ký tự dung sai 1 lỗi, từ ≥9 ký tự
dung sai 2 lỗi (đếm theo Levenshtein distance — thêm/xoá/đổi 1 ký tự). Index
cũng tự động bỏ dấu tiếng Việt khi so khớp. Chế độ "Cộng điểm"/mặc định yêu
cầu MỌI từ bạn gõ phải xuất hiện đâu đó trong field (không cần liền nhau,
không cần đúng thứ tự).

---

## 10. Frame đầu tiên của video đánh số 0 hay 1?

Tuỳ đại lượng:
- **`frame_idx`** (số NỘP CHO BTC, cũng là số hiển thị trên UI, vd "f123") —
  **0-indexed**: khung đầu tiên của video gốc là `frame_idx = 0` (trích bằng
  `decord.VideoReader`, cùng quy ước 0-based với OpenCV — khớp đúng cách BTC
  đánh số, xem `indexing/kaggle/01_extract_keyframes.py`).
- **`n`** (chỉ số keyframe NỘI BỘ, dùng đặt tên file `.webp`) — **1-indexed**:
  keyframe đầu tiên là `n=1`, file `000001.webp`.
