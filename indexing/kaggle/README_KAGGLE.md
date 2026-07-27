# HƯỚNG DẪN CHẠY OFFLINE TRÊN KAGGLE + CHIẾN LƯỢC LƯU TRỮ

> Trả lời câu hỏi: *"trích keyframe xong lưu chỗ nào để lần sau làm cái khác không phải trích lại?"*
> → **Lưu thành KAGGLE DATASET.** Đọc kỹ mục 2-3 bên dưới.

---

## 0. Ý TƯỞNG TỔNG THỂ — vì sao chia notebook

Video NẶNG (tải + giải nén tốn thời gian nhất). Nên **chỉ tải video 1 LẦN** (notebook 01),
trích ra keyframe + audio (nhẹ), rồi **lưu lại**. Các bước sau (embed, OCR, caption, ASR)
chỉ cần keyframe/audio đã lưu → KHÔNG tải/trích video lại → nhanh hơn nhiều lần.

```
        VIDEO (nặng, ~500GB)                 dùng 1 lần rồi XOÁ
              │  notebook 01 (tải + TransNetV2)
              ▼
   ┌──────────────────────────────┐
   │  KAGGLE DATASET: aic-kf-<shard>  │  ← LƯU Ở ĐÂY (keyframe + audio + map)
   │   keyframes/  maps/  audio/      │     nhẹ (~vài trăm MB/shard), giữ mãi
   └──────────────────────────────┘
              │ (Add làm Input cho các notebook sau — KHÔNG cần video nữa)
      ┌───────┼───────┬───────────┐
      ▼       ▼       ▼           ▼
  02_embed  03_caption_ocr  04_asr  ... (mỗi cái ra 1 dataset output nhỏ)
  MetaCLIP2  Qwen2.5-VL    ChunkFormer
```

---

## 1. CHUẨN BỊ 1 LẦN (làm 1 lần duy nhất, dùng cho mọi shard)

### 1a. Upload weights TransNetV2 lên Kaggle Dataset
Weights nằm sẵn ở máy: `reference_repos/kf_transnetv2/inference/transnetv2-weights/`
(gồm `saved_model.pb` + thư mục `variables/`, tổng ~35MB).
- Vào kaggle.com → **Datasets → New Dataset** → kéo cả thư mục `transnetv2-weights` vào →
  đặt tên **`transnetv2-weights`** → Create.
- (Lần sau mọi notebook chỉ cần **Add Input** dataset này.)

### 1b. Lấy Kaggle API token (để tải output về máy)
- kaggle.com → avatar → **Settings → API → Create New Token** → tải `kaggle.json`.
- Đặt vào máy: `C:\Users\LENOVO\.kaggle\kaggle.json`.
- Cài: `pip install kaggle`.

### 1c. Token HuggingFace cho model "gated" (bắt buộc cho DINOv3 — notebook 04)
DINOv3 cần Meta duyệt quyền truy cập (đã xin ở `huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m`
→ bấm "Agree and access repository") **VÀ** cần gửi kèm token khi tải, không thì vẫn lỗi 403 dù đã được duyệt.
1. Lấy token: `huggingface.co/settings/tokens` → **New token** (quyền Read là đủ) → copy.
2. Trong Kaggle Notebook (notebook 04) → menu trái **Add-ons → Secrets** → **Add a new secret**:
   - Label: `HF_TOKEN`
   - Value: dán token vừa copy
   - Bật **Attach** cho notebook đang mở.
3. Notebook 04 tự đọc secret này (`UserSecretsClient().get_secret("HF_TOKEN")`) — không cần sửa code.
   Nếu quên bật Secret, log sẽ in cảnh báo rõ ràng trước khi lỗi 403 xảy ra.

---

## 2. CHẠY NOTEBOOK 01 (trích keyframe) — 5 ACCOUNT, MỖI ACCOUNT CHỈ ĐỔI 1 SỐ

`L21_a` đã chạy xong riêng. **15 shard batch-1 còn lại** chia sẵn thành 5 nhóm (biến `ACCOUNT_GROUPS`
trong code) — mỗi account Kaggle chỉ cần đổi **1 số 0-4**, notebook tự chạy tuần tự cả nhóm 3 shard:

| ACCOUNT | Shard chạy |
|---|---|
| `0` | L22_a, L23_a, L24_a |
| `1` | L25_a, L25_a1, L25_b |
| `2` | L26_a, L26_b, L26_c |
| `3` | L26_d, L26_e, L27_a |
| `4` | L28_a, L29_a, L30_a |

(Batch 2 — K01..K20 — làm sau, lúc đó đặt `ACCOUNT = "K01"` v.v. để chạy đúng 1 shard cụ thể.)

**Các bước trên mỗi account Kaggle:**
1. **New Notebook** → Settings: **GPU T4 x2** + **Internet ON**.
2. **Add Input** → search **`transnetv2-weights`** (dataset public của account đã tạo, account khác add được luôn, không cần upload lại).
3. Copy toàn bộ `01_extract_keyframes.py` vào 1 cell.
4. Sửa dòng `ACCOUNT = os.environ.get("ACCOUNT", os.environ.get("SHARD", "0"))` — chỉ cần đổi số `"0"` cuối cùng thành số của account đó (VD account thứ 2 → `"1"`).
5. Bấm **"Save Version" → "Save & Run All (Commit)"** ngay (không cần Run All trước) — chạy nền server-side, đóng tab vẫn tiếp tục, tự chạy hết cả 3 shard trong nhóm.
6. Khi xong → log in "XONG..." + có `account_<n>_summary.json` tổng kết cả nhóm.

### → 3. LƯU THÀNH KAGGLE DATASET (mấu chốt câu hỏi của bạn)

**Cách A — nhanh nhất (Save Version rồi tạo Dataset từ output):**
1. Bấm **Save Version** (góc trên phải) → **Save & Run All (Commit)** → chờ commit xong (chạy hết cả nhóm 3 shard).
2. Vào trang notebook → tab **Output** → nút **"New Dataset"** (tạo dataset từ output).
   Đặt tên **`aic-kf-account<N>`** (VD `aic-kf-account0`) — 1 dataset chứa cả 3 shard của account đó
   (output đã tự nhóm theo `out/<shard>/...`).
3. Lặp cho 5 account → có `aic-kf-account0` .. `aic-kf-account4`, mỗi cái gồm 3 shard.

**Cách B — gộp tất cả shard vào 1 Dataset (gọn hơn để notebook sau add 1 lần):**
1. Tạo 1 Dataset rỗng tên **`aic-keyframes`** (New Dataset → tải lên `shard_L21a_info.json` tạm).
2. Sau mỗi notebook 01, dùng Kaggle API trong 1 cell cuối để **push output vào dataset đó**:
   ```python
   # cell cuối notebook 01 (tùy chọn) — cần bật Internet + có kaggle token secret
   import shutil; shutil.make_archive('/kaggle/working/kf_' + SHARD, 'zip', '/kaggle/working/out')
   # rồi tải file zip này về / thêm vào dataset aic-keyframes qua giao diện
   ```
   (Đơn giản hơn: cứ mỗi shard 1 dataset riêng `aic-kf-<shard>`, notebook sau add nhiều dataset.)

> **Khuyến nghị**: mỗi shard = 1 dataset `aic-kf-<shard>` (đơn giản, không lỗi). Notebook embed/OCR
> add đúng shard đang xử lý. Khi index toàn bộ thì add hết (Kaggle cho add nhiều dataset/notebook).

---

## 4. TẢI OUTPUT VỀ MÁY (khi cần index/thi trên laptop)

Sau khi keyframe đã thành dataset, tải về máy bằng **Kaggle API** (nhanh, ổn định):
```bash
# tải 1 dataset keyframe về F:
kaggle datasets download -d <username>/aic-kf-L21a -p "F:/AI_Challenge_Video_Image_Retrieval/aic-system/data" --unzip

# hoặc tải output của notebook (nếu chưa tạo dataset):
kaggle kernels output <username>/<notebook-slug> -p "F:/.../aic-system/data"
```
> Keyframe toàn bộ ~15-20GB (thumbnail webp) → F: (389GB trống) thừa sức. Feature .npy + index
> để riêng (notebook 02). Video KHÔNG tải về (xem lúc thi stream YouTube qua `watch_url`).

---

## 5. THỨ TỰ CÁC NOTEBOOK (lộ trình offline)

| # | Notebook | Input | Output | Ghi chú |
|---|---|---|---|---|
| 01 | `01_extract_keyframes.py` | video BTC (tải) + weights TransNetV2 | keyframe webp + map CSV + audio opus | ⭐ NỀN TẢNG, chạy trước |
| 02 | `02_embed.py` | dataset keyframe | `feat_metaclip2.npy` fp16 | nhánh CHÍNH (đa ngữ, không dịch) |
| 03 | `03_embed_pecore.py` | dataset keyframe | `feat_pecore.npy` fp16 | nhánh CHI TIẾT (PE-Core-G14-448, ~9.7GB checkpoint lần đầu) |
| 04 | `04_embed_dinov3.py` | dataset keyframe | `feat_dinov3.npy` fp16 | công cụ "tìm ảnh giống" (không vào ensemble text→image) |
| 05 | `05_embed_beit3.py` | dataset keyframe | `feat_beit3.npy` fp16 | dự phòng ensemble (offline, không dùng online) |
| 06 | `06_asr.py` | dataset audio (trong keyframe dataset) | `asr_<video>.json` + `asr_all.jsonl` | ChunkFormer, tự xử lý audio dài, không cần VAD riêng |
| 07 | `07_caption_qwen3vl.py` | dataset keyframe | `captions_<ACCOUNT>.jsonl` | ⚠️ NẶNG NHẤT — chia 5 account (ACCOUNT="1".."5"), resumable |
| 08 | `08_object_detect.py` | dataset keyframe | `objects_all.jsonl` (YOLO26x object+màu+grid) | ~36 phút, 1 account đủ |
| 09b | `09b_test_ocr_qwen_length.py` | dataset keyframe (mẫu) | in ra màn hình | ⭐ CHẠY TRƯỚC — đo số token thật/ảnh (chạy đo được 09 chỉ ~0.6-0.8 img/s, nghi batch đợi hàng chậm nhất) |
| 09 | `09_ocr_qwen3vl.py` | dataset keyframe | `ocr_<ACCOUNT>.jsonl` (chuỗi text đọc được) | Qwen3-VL-4B, chia 5 account, BATCH=32, bỏ L25_a1/L25_b (trùng L25_a) |
| 09c | `09c_fix_truncated_ocr.py` | dataset keyframe | `ocr_fixed.jsonl` | sửa 168/167,850 (0.1%) dòng bị cắt cụt do MAX_TOK=64 (ảnh chữ dày kiểu certificate) — MAX_TOK=200, key đã nhúng sẵn, 1 account đủ, vài phút |
| 10 | `10_cap_embed.py` | dataset captions_*.jsonl (upload thư mục `artifacts/caption/`, ~30MB) | `feat_capemb.npy` + `feat_index.parquet` | vector hoá caption bằng text-tower MetaCLIP-2 (cùng không gian với emb ảnh chính) — dedup L25_a1/L25_b inline, nhẹ (chỉ text), 1 account đủ |
| ~~09b~~ | ~~`09b_test_ocr_compare.py`~~ | — | — | **BỎ** — PaddleOCR+VietOCR bị chặn bởi bug cộng đồng chưa fix (`set_optimization_level`, GitHub issue #15846) — xem `09_ocr_paddleocr.py`/`09_ocr_paddle_vietocr.py` (không xoá, chỉ không dùng) |

**02/03/04 độc lập nhau** — chạy trên 3 notebook/account riêng cùng lúc cho nhanh (mỗi cái chỉ cần Add dataset
keyframe từ 01, không phụ thuộc nhau). Cùng 1 shard, kết quả 3 notebook join qua `feat_index.parquet`
(cột `video,n,frame_idx` — thứ tự các dòng khớp thứ tự vector trong `.npy` tương ứng, đã đảm bảo giống nhau
vì cùng logic gom keyframe từ `maps/*.csv` theo thứ tự sorted).

**Lưu ý "gộp 1 session cho nhanh"**: notebook 01 đã gộp keyframe + tách audio (đều cần video, làm 1 lần).
Embed/OCR/ASR tách riêng vì: (a) model khác nhau, VRAM khác, dễ debug; (b) chúng KHÔNG cần video nữa
(chỉ cần keyframe/audio đã lưu) nên chạy nhanh & song song trên nhiều account được.

---

## 6. KIỂM TRA SAU KHI CHẠY 01 (đảm bảo đúng trước khi làm tiếp)
- Mở vài ảnh `<shard>/keyframes/<video>/000001.webp` xem có đúng nội dung không.
- Mở `<shard>/maps/<video>.csv`: cột `frame_idx` phải là số nguyên tăng dần, hợp lý (< tổng frame video).
- **Đối chiếu frame_idx** (quan trọng): lấy 1 video có trong `data/extracted/map-keyframes/<video>.csv` của
  BTC (đã giữ lại), so `frame_idx` của mình với của BTC ở vài keyframe gần nhau → phải CÙNG THANG (cùng
  đánh số frame gốc). Nếu lệch hệ thống → sai fps/cách tính, phải sửa trước khi chạy toàn bộ.
