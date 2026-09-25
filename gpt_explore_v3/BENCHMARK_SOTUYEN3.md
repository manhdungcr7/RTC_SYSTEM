# Thử GPT Explore trên bộ Sơ tuyển 3

Ngày chạy: 25/09/2026. Nguồn câu hỏi: `queries/SOTUYEN3-bo-de-thi.zip` (36 câu). Theo yêu cầu người dùng, **không xét câu 5, 6, 9**; mẫu chấm gồm 33 câu còn lại đối chiếu `submission/`. V1/V2/V3 được gọi riêng từng câu bằng OpenAI Responses API, cùng model `gpt-5-mini-2025-08-07`, mức reasoning `low`, với Instructions và Knowledge của từng bản. V3 không dùng Knowledge. Đây là **mô phỏng cấu hình GPT từ file trong repo**, không phải log tương tác trực tiếp với hai GPT trên ChatGPT web; model và cách ChatGPT chọn Knowledge có thể khác.

Mỗi JSON được gửi qua `POST /query/plan/validate`, rồi nhập vào `POST /search` hoặc `POST /temporal` theo mode mà validator chuẩn hóa. Các preset/tín hiệu giống frontend mặc định và không khoanh vùng trước bằng video đáp án. `submission/` chỉ được đọc ở bước chấm sau khi kế hoạch và kết quả retrieval đã được lưu. Kết quả gốc/JSON/kết quả retrieval/CSV điểm nằm ở `artifacts/gpt_explore_eval/` (thư mục này không commit vì chứa dữ liệu benchmark lớn). Script lặp lại: `scripts/benchmark_gpt_explore.py`.

## Kết quả

- V1: 36/36 kế hoạch dùng được; video đúng hạng 1 ở **17/33**, top 10 ở **27/33**, top 50 ở **32/33**. Trong 25 câu KIS được xét, 16 câu có ít nhất một hit cùng video lệch không quá 50 frame so với một dòng submission. Video đúng của cả **6/6 QA** nằm trong top 10.
- V2: 36/36 kế hoạch dùng được (câu 35 cần gọi lại một lần vì đầu ra đầu tiên không qua validator); video đúng hạng 1 **17/33**, top 10 **26/33**, top 50 **32/33**. KIS lệch không quá 50 frame **18/25**; QA video top 10 **4/6**.
- V3: 36/36 kế hoạch dùng được; video đúng hạng 1 **18/33**, top 10 **24/33**, top 50 **31/33**. KIS lệch không quá 50 frame **17/25**; QA video top 10 **4/6**.
- Câu **5, 6 và 9** đều đã chạy nhưng **không chấm**. Câu 9 không có CSV đáp án tham chiếu.

Top 10 tính theo video duy nhất xuất hiện trong danh sách kết quả (với Search có thể có nhiều frame cùng video). Chỉ số frame là độ lệch nhỏ nhất trong các hit đã trả về, **không** khẳng định clip hoặc câu trả lời QA đã được xác minh. Các câu QA cần xem/đọc/nghe đúng đoạn rồi mới điền đáp án.

Hai câu TRAKE cho thấy giới hạn quan trọng: câu 21 đưa video đúng lên hạng 1 ở cả ba bản nhưng ba trong bốn mốc frame vẫn lệch khoảng 500–1.500 frame; câu 34 chỉ có V2 đưa video đúng lên hạng 2, nhưng cả bốn mốc lệch khoảng 8.000 frame. Không nên dùng các frame tự động này làm submission TRAKE khi chưa xem lại video.

## Nhận xét

- V1 hiện có recall video top 10 và QA tốt nhất trên bộ này. V2 tăng số câu KIS có frame gần nhưng làm tụt một số video đúng, như câu 11 và 24. V3 có **top 1 cao hơn V1 một câu** và giúp câu 7, 27 lên hạng 1, song giảm recall top 10, nhất là câu 11, 16, 24 và 34.
- V1/V2 Knowledge chứa ví dụ lấy từ đề Sơ tuyển 3 (V2 có ví dụ gần nguyên câu 24). Điều này làm tập đánh giá **không độc lập** với prompt cũ, dù các ví dụ không chứa đáp án. V3 cố ý không dùng ví dụ của bộ đề hoặc câu trả lời trong `submission/`; vì thế kết quả thấp hơn không đủ chứng minh V3 kém trên câu hỏi chung kết chưa từng thấy.
- V3 xử lý ít cảnh và khoảnh khắc ngắn theo nguyên tắc tổng quát, nhưng cách chọn Search/Temporal và số event chưa đem lại lợi ích nhất quán. Với hệ thống hiện tại, chia quá nhiều event có thể làm mất video đúng; chọn một event quá sớm có thể bỏ mất thứ tự hữu ích.

## Khuyến nghị

Dùng **V1 làm cấu hình chính** theo dữ liệu hiện có. Giữ V3 làm bản thử nghiệm tổng quát và đánh giá tiếp trên một bộ câu hỏi mới chưa dùng để viết instruction. Với QA, kiểm tra nội dung từ video; với TRAKE, tìm video trước rồi xác minh từng mốc frame thủ công. Không coi kết quả retrieval là submission hoàn chỉnh.
