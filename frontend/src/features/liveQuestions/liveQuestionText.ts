import type { LiveQuestion } from "../../types/api";

/** One source text per reveal avoids counting the same bilingual clue twice. */
export function liveSearchText(question: LiveQuestion): string {
  return question.reveals
    .map((reveal) => reveal.text_vi.trim() || reveal.text_en.trim())
    .filter(Boolean)
    .join("\n");
}

export function liveGptPrompt(question: LiveQuestion): string {
  const lines = [
    "Đây là MỘT đề tìm video được BTC công bố dần. Hãy phân tích toàn bộ phần đã lộ như một đề hiện tại và trả JSON theo Instructions bạn đang dùng.",
    "Thứ tự công bố hint KHÔNG phải thứ tự các cảnh trong video. Chỉ dùng thứ tự sự kiện nếu nội dung đề thực sự mô tả thứ tự đó.",
    "Hai ngôn ngữ trong cùng một mốc là cùng một thông tin, không phải hai sự kiện. Không đoán các hint chưa được công bố.",
    "Các hint chỉ nêu từ khóa rời KHÔNG chứng minh chúng xuất hiện cùng khung hình, có quan hệ hay theo thứ tự trong video. Giữ dấu hiệu độc lập trong search_clauses khi chưa có bằng chứng để ghép thành một cảnh.",
    "Trong original_query, chỉ giữ nguyên văn đề; bỏ nhãn mốc, thời gian và các dòng hướng dẫn này.",
    `Câu ${question.label} · ${question.kind.toUpperCase()}`,
    "<de_bai>",
  ];
  if (question.kind === "qa" && question.qa_question.trim()) {
    lines.push(`Câu hỏi cần trả lời (chỉ để xác minh, không đưa đáp án chưa biết vào truy vấn): ${question.qa_question.trim()}`);
  }
  question.reveals.forEach((reveal, index) => {
    lines.push(`${index === 0 ? "Mô tả mở đầu" : `Hint ${index}`}:`);
    if (reveal.text_vi.trim()) lines.push(`VI: ${reveal.text_vi.trim()}`);
    if (reveal.text_en.trim()) lines.push(`EN: ${reveal.text_en.trim()}`);
  });
  lines.push("</de_bai>");
  return lines.join("\n\n");
}
