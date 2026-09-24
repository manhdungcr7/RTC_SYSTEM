# Sao lưu keyframe AIC lên S3 Singapore

Chạy `launch_cloudshell.sh` trong AWS CloudShell của tài khoản `735792832986` sau khi đặt ba file trong thư mục này cạnh nhau. Script dùng IAM role EC2 hiện có, tạo một EC2 tạm 100 GB tại Singapore, tải lần lượt 7 Kaggle datasets trong `datasets.txt`, rồi ghi vào bucket `video-data-735792832986-ap-southeast-1-an`:

- `keyframes/<video>/<n:06d>.webp`
- `maps/<video>.csv`
- `audio/<video>.opus`

EC2 xóa bộ tải tạm sau mỗi dataset và tự hủy khi xong hoặc khi lỗi; ổ đĩa cũng bị xóa. Chạy lại an toàn: object trùng tên và kích thước được bỏ qua. Video `.mp4`/`.mov` ở gốc bucket không bị đụng tới. Không có dataset nào tải về PC.

```bash
bash ~/aic-keyframe-ingest/launch_cloudshell.sh
```

Xem trạng thái một lần (không cần giữ CloudShell mở):

```bash
ID="$(cat ~/aic-keyframe-ingest-run/instance-id.txt)"
aws ec2 describe-instances --region ap-southeast-1 --instance-ids "$ID" --query 'Reservations[0].Instances[0].State.Name' --output text
aws ec2 get-console-output --region ap-southeast-1 --instance-id "$ID" --latest --query Output --output text | grep -E 'SOURCE_START|KAGGLE_OK|UPLOADED|SOURCE_DONE|ALL_DONE|AIC_KEYFRAME_INGEST_(DONE|FAILED)' | tail -n 30
```

Máy RTC hiện đã đặt `AIC_KEYFRAME_CDN_BASE_URL=https://d14le8uni46xsj.cloudfront.net` trong `docker/.env` và đã dựng lại backend. Backend ưu tiên ảnh/map local, thiếu thì dùng CloudFront; ảnh Batch 2 sẽ hiện khi EC2 upload xong. Nếu cần dựng lại sau này: `docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --build backend`.
