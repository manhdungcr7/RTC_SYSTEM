# AIC Visual Query Expert V2

Bản thử nghiệm riêng, không sửa `gpt_explore/` và không thay đổi backend/frontend hay cấu hình tìm kiếm hiện tại. V2 vẫn xuất đúng hợp đồng JSON mà hộp **Nhập kế hoạch GPT** của RTC đang nhận.

## Thiết lập GPT riêng

1. Tạo một GPT mới, đặt tên `AIC Visual Query Expert V2`; không ghi đè GPT đang dùng.
2. Dán toàn bộ [AIC_VISUAL_QUERY_EXPERT_INSTRUCTIONS.md](AIC_VISUAL_QUERY_EXPERT_INSTRUCTIONS.md) vào Instructions. File được giữ dưới 8.000 ký tự.
3. Đính kèm [AIC_VISUAL_QUERY_EXAMPLES.md](AIC_VISUAL_QUERY_EXAMPLES.md) vào Knowledge của GPT mới.
4. Gửi nguyên đề ban tổ chức. Chép JSON trả về vào **Nhập kế hoạch GPT → Kiểm tra và áp dụng** trên RTC.

Không cần Action, API key hay kết nối trực tiếp tới RTC để dùng bộ prompt này. Đây là các file cấu hình để bạn tự tạo GPT, chưa phải một GPT đã được tạo trên tài khoản ChatGPT.

## Dùng trong chat ChatGPT/Gemini thông thường

Mở [ONE_SHOT_VISUAL_QUERY_PROMPT.md](ONE_SHOT_VISUAL_QUERY_PROMPT.md), thay nội dung trong `<de_bai>` ở cuối bằng đề thật rồi gửi toàn bộ file trong một tin nhắn. Bản này tự chứa quy tắc và ví dụ, không cần Knowledge. Chép JSON kết quả vào web như trên.

## V2 thay đổi gì?

- Bối cảnh ngắn; thường chọn 2–3 cảnh đặc trưng thay vì đưa mọi thao tác phổ biến vào chuỗi Temporal. Vẫn giữ đủ từng mốc nếu đề yêu cầu E1–E4 hoặc khoảnh khắc cụ thể.
- Dấu hiệu mạnh nằm trong câu thực sự được encode, không chỉ trong ghi chú `visual_keywords`/`distinctive_features`.
- Dịch sát vật liệu, thao tác và quan hệ: không mặc định bột là bột nhào, người con là trẻ nhỏ, hay tách ruột là bóc bỏ vỏ.
- Câu hỏi cuối hướng dẫn xác minh, không tạo sự kiện giả hoặc đưa đáp án chưa biết vào truy vấn.
- OCR/ASR chỉ gắn đúng sự kiện. Danh sách tổng hợp của mỗi kênh chọn một cụm mạnh để tránh ghép các chữ ở nhiều cảnh thành truy vấn khó khớp.
- Giữ nguyên `original_query` để xem sâu lại ứng viên và kiểm tra các chi tiết đã lược khỏi chuỗi tìm kiếm.

`distinctive_features` và `possible_confusions` là ghi chú đối chiếu, không phải trọng số mới của hệ thống. V2 không thêm trường JSON, không chỉnh encoder, nhánh CapEmb, fusion hoặc thuật toán Temporal.

## Đánh giá trung thực

Các JSON trong Knowledge là ví dụ biên soạn thủ công, không phải đầu ra đã chạy từ GPT V2. Kiểm tra JSON/giới hạn Instructions chỉ chứng minh khả năng import, không chứng minh chất lượng truy vấn.

Kiểm tra khi tạo bản này:

- Instructions: 6.956 ký tự, dưới giới hạn 8.000.
- 7 khối JSON (5 ví dụ Knowledge, 1 mẫu hợp đồng, 1 ví dụ one-shot) được validator của web đang chạy chấp nhận, không cảnh báo hoặc sửa nội dung mẫu.
- SHA-256 của cả 5 file trong `gpt_explore/` giữ nguyên trước/sau khi tạo V2.
- Chưa chạy GPT V2 để tạo kế hoạch và chưa benchmark thứ hạng tìm kiếm của đầu ra V2.

Để so V1/V2: dùng cùng đề, cùng phạm vi toàn bộ video và cùng preset; lưu JSON thực tế từ hai GPT; kiểm tra thứ hạng video đúng và frame đúng với đáp án `submission/`. Chạy cả nhóm khó `unnormal/` lẫn một nhóm đang tốt để tránh tối ưu riêng câu khó rồi làm giảm các câu còn lại. Không thu hẹp range bằng video đáp án trước khi đo. Tăng thứ hạng video chưa đồng nghĩa tìm đúng frame.

Khi xem kết quả: quét nhanh ứng viên, thấy có khả năng khớp thì xem sâu lại một lần theo đề gốc; sai thì bỏ và kiểm tra tiếp. Nếu chỉ kiểm tra keyframe, nói rõ giới hạn đó. Chưa thấy bằng chứng thì báo **chưa tìm thấy kết quả phù hợp trong phạm vi đã kiểm tra**, không đoán và không kết luận video không tồn tại trong toàn bộ kho.

Bộ prompt áp dụng cách tách quy tắc, hợp đồng đầu ra và ví dụ đa dạng theo [OpenAI Docs về prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering). Các quy tắc chọn cảnh/OCR/ASR được thiết kế theo cách RTC hiện tại nhận kế hoạch, không phải cam kết hiệu quả từ tài liệu OpenAI.
