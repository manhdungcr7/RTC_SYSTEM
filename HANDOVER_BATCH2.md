# Bàn giao RTC System — cập nhật Batch 2

Tài liệu này dành cho máy **đã chạy được RTC System với Batch 1** (đã có
`docker/volumes/faiss/` và `docker/volumes/meili/` của Batch 1). Mục tiêu: nâng
lên bản có Batch 2 mà không phải tải video/keyframe về máy.

## 1. Tóm tắt thay đổi

| Thành phần | Batch 1 | Batch 2 | Việc cần làm trên máy bạn |
|---|---|---|---|
| Video | CloudFront | CloudFront | Không — chỉ cần cấu hình `.env` |
| Keyframe + maps CSV | CloudFront | CloudFront | Không — chỉ cần cấu hình `.env` |
| FAISS `metaclip2` | có | **có (mới)** | **Thay cả thư mục `faiss/`** (mục 3) |
| FAISS `pecore`, `beit3`, `dinov3`, `capemb` | có | chưa có | Nằm trong thư mục `faiss/` mới (bản fp16) |
| Meili `aic_frames` (OCR/caption/object) | có | chưa có | Giữ nguyên bản đang có |
| Meili `aic_asr` (lời thoại) | có | chưa có | Giữ nguyên bản đang có |

Batch 2 gồm 614 video: `M01_V001` … `M10_V0xx`, `N001-V001` … `N100-V003`,
`S01-V001` … `S01-V012`. Lưu ý nhóm `N` và `S` dùng **dấu gạch ngang** giữa
mã nhóm và mã video (`N001-V001`), khác Batch 1 (`L21_V001`).

## 2. Lấy code mới

```bash
git pull origin main
```

Code mới có thêm: chọn nguồn keyframe (`AIC_KEYFRAME_SOURCE`), phát video/keyframe
qua CloudFront, nộp bài DRES, bảng chia sẻ bài nộp.

## 3. Thay toàn bộ thư mục FAISS

Nhận thư mục `faiss/` (khoảng 3,0 GB) từ người bàn giao. Thư mục gồm 5 nhánh
`beit3`, `capemb`, `dinov3`, `metaclip2`, `pecore`, đã chuyển sang **fp16**
(`IndexScalarQuantizer`), nên chỉ tốn một nửa RAM so với bản float32 cũ.
Nhánh `metaclip2` đã gộp Batch 1 + Batch 2 (635.181 keyframe).

```powershell
docker compose -f docker/docker-compose.yml stop backend
# Giữ bản cũ để quay lại nếu cần
Rename-Item docker/volumes/faiss faiss_batch1_backup
# Chép thư mục faiss nhận được vào docker/volumes/faiss
```

Không đụng tới `docker/volumes/meili/`.

Vì sao fp16: bản float32 (6,6 GB) không vừa RAM của Docker Desktop (~7,6 GB),
tiến trình backend bị đẩy ra swap và lượt tìm đầu tiên mất 10–60 giây. Bản
fp16 (~3,3 GB RAM) cho lượt tìm lạnh khoảng 1 giây. Top-100 trùng 99,6–99,9%
với bản float32. Nếu sau này build lại index float32 (ví dụ gộp batch mới), chạy
`indexing/convert_faiss_fp16.py` rồi thay thư mục như trên.

## 4. Cấu hình `docker/.env`

Mở `docker/.env.example` để xem đủ danh sách biến. Thêm hoặc sửa các dòng sau:

```env
AIC_VIDEO_CDN_BASE_URL=https://d14le8uni46xsj.cloudfront.net
AIC_KEYFRAME_CDN_BASE_URL=https://d14le8uni46xsj.cloudfront.net
AIC_KEYFRAME_SOURCE=s3
```

`AIC_KEYFRAME_SOURCE`:
- `s3`: chỉ lấy keyframe/maps từ CloudFront. Nên dùng khi máy không có `data/raw_*`.
- `auto`: có file trong `data/raw_*` thì dùng, thiếu thì lấy CloudFront.
- `local`: chỉ dùng đĩa. Batch 2 sẽ không có ảnh.

Các biến còn lại (`AIC_REMOTE_ENCODER_URL`, `AIC_REMOTE_ENCODER_KEY`, API key
LLM, thông tin DRES) nhận riêng từ người bàn giao, **không** commit lên git.
URL encoder dạng `*.trycloudflare.com` thay đổi mỗi lần chạy lại notebook
`indexing/kaggle/11_encode_service.py`, cần cập nhật khi encoder khởi động lại.

## 5. Sửa đường dẫn video trong `docker-compose.yml`

File `docker/docker-compose.yml` có dòng mount thư mục video của máy người bàn giao:

```yaml
      - C:/Users/huypro37/Videos/AIC_videos:/videos-extra:ro
```

Xóa dòng này (video đã phát qua CloudFront), hoặc đổi sang thư mục video trên
máy bạn nếu muốn phát video từ đĩa. Giữ nguyên dòng này sẽ làm Docker báo lỗi
đường dẫn không tồn tại.

## 6. Build lại và khởi động

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --build
```

Log backend phải có dòng `[media_index] nguồn keyframe=s3, ...`:

```bash
docker logs aic-backend 2>&1 | grep media_index
```

## 7. Kiểm tra

```bash
curl http://localhost:8080/health
```

Kết quả đúng:
- `faiss.branches.metaclip2` = **635181**
- `beit3`, `capemb`, `dinov3`, `pecore` = **167850**
- `meili.docs.frames` = **167850**, `meili.docs.asr` = **111411**
- `encoder.ok` = `true`

Kiểm tra ảnh và video Batch 2 (mã `307` là đúng, nghĩa là được chuyển sang CloudFront):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/media/frame/M01_V001/1
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/media/frame/N001-V001/1
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/media/video/M01_V001
```

Cuối cùng mở giao diện, tìm thử một mô tả hình ảnh và xác nhận có kết quả
video `M..`/`N..`/`S..`.

## 8. Giới hạn hiện tại của Batch 2

Batch 2 hiện chỉ tìm được qua nhánh hình ảnh **MetaCLIP2**. Chưa có:
- OCR, caption, object (Meili `aic_frames`): tìm theo chữ trên màn hình chưa ra Batch 2.
- ASR (Meili `aic_asr`): tìm theo lời thoại chưa ra Batch 2. Transcript đã có
  trên Kaggle (`dngomnh/aic2026-batch2-asr-all`), chưa nạp vào Meili.
- PE-Core, BEiT-3, DINOv3, CapEmb.

Khi bổ sung các phần này sẽ có bản bàn giao tiếp theo.

**Không chạy `indexing/build_meili.py`**: script này xóa rồi tạo lại
`aic_frames` và `aic_asr` từ các file trong `artifacts/`. Các file nguồn ASR
Batch 1 hiện không còn, chạy script sẽ làm mất ASR Batch 1.

## 9. Quay lại bản cũ

```powershell
docker compose -f docker/docker-compose.yml stop backend
Rename-Item docker/volumes/faiss faiss_batch2
Rename-Item docker/volumes/faiss_batch1_backup faiss
docker compose -f docker/docker-compose.yml up -d backend
```
