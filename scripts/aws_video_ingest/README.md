# Chuyển ZIP video qua EC2 vào S3 Singapore

Bộ này chạy **trong AWS CloudShell và EC2**. Máy Windows của bạn chỉ giữ các file script nhỏ; không tải ZIP hoặc MP4 về máy.

## Đích và trạng thái hiện tại

- Bucket đích: `video-data-735792832986-ap-southeast-1-an` ở `ap-southeast-1` (Singapore).
- Link phát: `https://d14le8uni46xsj.cloudfront.net/TEN_VIDEO.mp4`.
- `sources.tsv` chứa đúng 14 ZIP **Videos_L21–L30**; không có Keyframes.
- `next-sources.tsv` chứa 21 ZIP mới **Video_S01, Video_N001–N100, Videos_M01–M10**. Kích thước ZIP đã được kiểm tra từ HTTP `Content-Length`: tổng **266.923.243.587 byte**, lớn nhất `Video_S01.zip` **53.896.100.459 byte**. Đây là manifest để chạy batch hiện tại.
- `Video_S01.zip` đã hoàn thành 12 MP4 trên S3. Các ZIP nhóm N chứa MOV, nhóm M chứa MP4; `remaining-sources.tsv` chỉ gồm 20 ZIP N/M để tiếp tục sau khi bổ sung hỗ trợ MOV. Không khởi chạy hai EC2 cùng lúc trên manifest này.
- Ngày 24/09/2026, cả 14 ZIP đầu tiên đã được xử lý: bucket Singapore và bucket nguồn đều có **873 MP4 / 82.984.040.674 byte**. File cuối `L30_V096.mp4` phát qua CloudFront với HTTP 206. EC2 cũ đã kết thúc. **Không chạy lại `sources.tsv`**; script khởi chạy chặn manifest này. Dùng một manifest mới chỉ chứa ZIP bổ sung hoặc ZIP thật sự còn thiếu nếu cần khôi phục.

## Cách chạy trong AWS CloudShell

1. Mở AWS Console bằng tài khoản `735792832986`, chọn biểu tượng **CloudShell**. CloudShell có thể mở ở vùng bất kỳ; script chỉ định Singapore rõ ràng.
2. Trong CloudShell, chọn **Actions → Upload file** và tải lên `aic-video-ingest-scripts.zip` đi kèm. ZIP này chỉ chứa mã nguồn và danh sách URL, không chứa dữ liệu video.
3. Chạy:

   ```bash
   mkdir -p ~/aic-video-ingest
   unzip -o ~/aic-video-ingest-scripts.zip -d ~/aic-video-ingest
   cd ~/aic-video-ingest
   python3 -m py_compile ingest_videos.py
   bash -n launch_cloudshell.sh
   ```

4. Với **batch N/M còn lại**, dùng `remaining-sources.tsv` đi kèm, không cần gõ lại 20 URL. Với batch bổ sung sau này, tạo manifest mới bằng `nano ten-batch.tsv` và dán các URL ZIP video, mỗi dòng một URL. Nếu biết kích thước ZIP, thêm dấu Tab thật và số byte để kiểm tra tải đủ; nếu chưa biết, chỉ cần URL. Không thêm ZIP Keyframes. Ví dụ:

   ```text
   https://aic-data.ledo.io.vn/Videos_L31_a.zip<TAB>1234567890
   ```

   `<TAB>` nghĩa là phím Tab thật, không gõ nguyên văn `<TAB>`. Lưu trong `nano` bằng `Ctrl+O`, Enter, rồi `Ctrl+X`. Dùng tên manifest mới cho mỗi batch; `sources.tsv` dành cho 14 ZIP đầu tiên.

5. Chạy một EC2 mới tại Singapore:

   ```bash
   bash launch_cloudshell.sh remaining-sources.tsv
   ```

   Mặc định script dùng ổ EC2 tạm **100 GB**, phù hợp với ZIP lớn nhất khoảng **55 GB**. Dù giải nén ZIP đó thành khoảng **75 GB** video, phần đã giải nén đi thẳng lên S3 và không chiếm thêm 75 GB trên ổ EC2. Nếu một ZIP sau này vượt khoảng 85 GB, tăng ổ tạm. Ổ cần lớn hơn ZIP lớn nhất và vẫn còn chỗ cho hệ điều hành:

   ```bash
   VOLUME_GB=140 bash launch_cloudshell.sh next-sources.tsv
   ```

   Script tạo IAM role chỉ đọc/ghi bucket video Singapore, security group không mở cổng vào, EC2 `t3.small` với ổ `gp3` mã hóa và hồ sơ IAM. Không tạo access key. Khi hoàn tất, EC2 tự hủy cùng ổ EBS.

6. Xem mã EC2 và log:

   ```bash
   INSTANCE_ID="$(cat ~/aic-video-ingest-run/instance-id.txt)"
   aws ec2 describe-instances --region ap-southeast-1 --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].State.Name' --output text
   aws ec2 get-console-output --region ap-southeast-1 --instance-id "$INSTANCE_ID" --latest --query Output --output text | tail -n 40
   ```

   Log lần lượt có `SOURCE_START`, `ZIP_OK`, `UPLOADED`, `ZIP_REMOVED_FROM_EC2`, `SOURCE_DONE`, cuối cùng `ALL_DONE` và `AIC_INGEST_DONE`. Nếu có `AIC_INGEST_FAILED`, kiểm tra các dòng lỗi trước đó. EC2 vẫn tự dọn ổ và hủy để tránh tiếp tục tính phí máy.

7. Kiểm tra S3 và CDN:

   ```bash
   aws s3api get-bucket-location --bucket video-data-735792832986-ap-southeast-1-an --region ap-southeast-1 --query LocationConstraint --output text
   aws s3 ls s3://video-data-735792832986-ap-southeast-1-an/ --recursive --summarize | tail -n 2
   curl -sS -D - -o /dev/null -r 0-1023 https://d14le8uni46xsj.cloudfront.net/L21_V001.mp4 | grep -Ei 'HTTP/|content-type:|content-range:'
   ```

   Lệnh `curl` chỉ lấy 1 KiB để thử chức năng phát/tua, không tải cả video. Kết quả mong đợi là HTTP `206`, `video/mp4`, và `content-range`.

## Dọn dung lượng EC2

- EC2 tải **một ZIP vào** `/var/lib/aic-video-ingest/current.zip`. Nếu mạng đứt, file `.zip.part` được tải tiếp bằng HTTP Range khi nguồn hỗ trợ.
- Python kiểm tra đường dẫn, tên MP4/MOV và CRC của từng video. Video giải nén được đưa qua pipe vào `aws s3 cp -`; **không có thư mục video giải nén trên EC2**. MOV được giữ nguyên đuôi `.mov` với `Content-Type: video/quicktime`.
- Sau khi xử lý từng ZIP, khối `finally` xóa `current.zip`, kể cả khi ZIP đó gặp lỗi.
- Khi cả batch kết thúc hoặc thất bại, user data xóa `/var/lib/aic-video-ingest`, rồi shutdown. Thiết lập `instance-initiated-shutdown-behavior=terminate` và `DeleteOnTermination=true` xóa luôn EC2/ổ EBS. Video trên S3 vẫn giữ nguyên.
- Nếu EC2 gặp sự cố phần cứng và không tự shutdown, kiểm tra trạng thái EC2 và dừng/hủy máy sau khi đọc log để tránh chi phí chạy tiếp.

## Lưu ý khi dùng lại

- S3 tự mở rộng, không cần cấp trước “350 GB”. `VOLUME_GB` là ổ **tạm của EC2**, chỉ cần đủ cho ZIP lớn nhất.
- Các MP4 nằm ngay ở gốc bucket. Nếu hai ZIP chứa cùng tên MP4, script báo lỗi thay vì ghi đè.
- Khi chạy lại cùng một ZIP, MP4 đã có cùng `source-zip` và cùng kích thước được bỏ qua. Đừng chạy hai EC2 trên cùng một danh sách đồng thời.
- Nếu manifest mới không ghi kích thước ZIP, script vẫn kiểm tra cấu trúc và CRC của từng MP4, nhưng không thể kiểm tra chính xác tổng byte ZIP trước khi mở.
- Không đặt API key, URL có chữ ký bí mật hoặc mật khẩu trong manifest hay script.
- Dùng CloudFront để phát video; không đưa link S3 trực tiếp cho người xem.
