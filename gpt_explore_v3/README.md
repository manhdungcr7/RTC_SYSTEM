# AIC Visual Query Expert V3 — bản thử nghiệm

Dán nội dung `AIC_VISUAL_QUERY_EXPERT_INSTRUCTIONS.md` vào Instructions của một GPT riêng. Bản này không dùng Knowledge ví dụ để tránh đưa các câu của một vòng thi cụ thể vào ngữ cảnh. GPT chỉ tạo kế hoạch JSON; nhập JSON vào **Nhập kế hoạch GPT** của RTC rồi kiểm tra video và frame bằng mắt trước khi nộp.

V3 được thử cùng model, cùng backend, cùng 36 câu với V1/V2 bằng `scripts/benchmark_gpt_explore.py`. Kết quả đối chiếu `submission/` nằm trong `artifacts/gpt_explore_eval/`; theo yêu cầu người dùng, câu 5, 6 và 9 không tính vào điểm.

Trên bộ này V3 **chưa vượt V1** về recall video top 10; xem `BENCHMARK_SOTUYEN3.md` trước khi dùng làm GPT chính.
