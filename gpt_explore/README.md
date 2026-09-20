# Dùng AIC Visual Query Expert với RTC

## Thiết lập

1. Tạo hoặc mở một GPT/agent tùy chỉnh mà tài khoản ChatGPT của bạn có quyền chỉnh sửa.
2. Đặt tên `AIC Visual Query Expert`.
3. Dán toàn bộ nội dung [AIC_VISUAL_QUERY_EXPERT_INSTRUCTIONS.md](AIC_VISUAL_QUERY_EXPERT_INSTRUCTIONS.md) vào trường Instructions. File này được giữ dưới giới hạn 8.000 ký tự.
4. Tải [AIC_VISUAL_QUERY_EXAMPLES.md](AIC_VISUAL_QUERY_EXAMPLES.md) lên mục Knowledge.
5. Không bật Action gọi thẳng RTC và không đưa API key, URL encoder hoặc secret vào GPT.
6. Thử trong Preview bằng vài đề thật trước khi dùng trong buổi thi.

Nếu giao diện ChatGPT của bạn không cho tạo GPT mới, vẫn có thể dùng file instructions này làm prompt cố định trong một project/agent hiện có. Thiết kế JSON không phụ thuộc vào một model cụ thể và có thể chuyển thành Skill/Plugin về sau.

## Cách dùng hằng ngày

1. Ở trang **Tìm khung hình** hoặc **Chuỗi sự kiện**, dán nguyên đề vào ô đề bài.
2. Bấm **Nhập kế hoạch GPT** rồi bấm **Chép câu gốc cho GPT**.
3. Gửi nội dung đó cho `AIC Visual Query Expert`.
4. Sao chép nguyên JSON GPT trả về, dán vào hộp nhập của RTC và bấm **Kiểm tra và áp dụng**.
5. Kiểm tra lại mệnh đề, bản dịch, OCR/ASR và hai neo trước khi tìm.

RTC sẽ chuẩn hóa JSON, không gọi lại model mini để phân tách kế hoạch đã nhập. Kế hoạch một sự kiện dùng ở Search; kế hoạch nhiều sự kiện có thứ tự dùng ở Temporal.

## Tại sao vẫn giữ bộ tách cũ

Bộ tách `gpt-4o-mini` hiện tại vẫn là lựa chọn nhanh khi không mở GPT ngoài. Nó phù hợp với câu đơn giản, nhưng không còn là nguồn lập kế hoạch chính cho các mô tả dài, nhiều trạng thái hoặc nhiều danh từ mơ hồ. Cách mới kế thừa toàn bộ encoder, OCR, ASR, bộ trộn điểm, phạm vi video và thuật toán Temporal của RTC; chỉ thay lớp hiểu đề và cách đưa tín hiệu vào các thành phần đó.

## Kiểm tra nhanh JSON

Endpoint nội bộ:

```text
POST /api/query/plan/validate
{"plan": { ...JSON từ GPT... }}
```

Kết quả trả về gồm `plan` đã chuẩn hóa và `warnings`. Server không lưu nội dung kế hoạch này.
