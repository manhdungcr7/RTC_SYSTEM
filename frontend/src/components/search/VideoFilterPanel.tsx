import { useState } from "react";

import { useVideoFilter } from "../../hooks/useVideoFilter";

interface Props {
  onUseAsScope: (videos: string[]) => void;
}

// Lọc video trước (mục 3) — ĐỘC LẬP với tìm khung hình bên dưới: bấm "Tìm video"
// hiện kết quả NGAY (không bắt buộc phải làm tiếp gì cả). Muốn dùng làm phạm vi
// cho tìm khung hình thì TỰ chọn video rồi bấm nút riêng — không tự động chuyển
// bước, đúng yêu cầu "người dùng được quyền thấy kết quả lọc video" trước.
export function VideoFilterPanel({ onUseAsScope }: Props) {
  const { hits, categories, loading, error, runVideoSearch } = useVideoFilter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    runVideoSearch(query, category || null, 100);
    setSelected(new Set());
  };

  const toggleVideo = (video: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(video)) next.delete(video);
      else next.add(video);
      return next;
    });

  const selectAll = () => setSelected(new Set(hits.map((h) => h.video)));
  const clearSelection = () => setSelected(new Set());

  return (
    <div className="video-filter-panel">
      <button type="button" className="query-box-toggle-filters" onClick={() => setOpen((s) => !s)}>
        {open ? "▾" : "▸"} Lọc video trước (tuỳ chọn — thu hẹp phạm vi trước khi tìm khung hình)
      </button>

      {open && (
        <div className="video-filter-body">
          <form className="video-filter-row" onSubmit={submit}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Nội dung video (ASR + caption + tiêu đề)... để trống nếu chỉ lọc theo thể loại"
            />
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Mọi thể loại</option>
              {(categories.length > 0 ? categories : ["Tin tức", "Thể thao", "Nấu ăn", "Giải trí"]).map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <button type="submit" disabled={loading || (!query.trim() && !category)}>
              {loading ? "Đang tìm..." : "Tìm video"}
            </button>
          </form>
          {error && <div className="search-error">Lỗi: {error}</div>}

          {hits.length > 0 && (
            <>
              <div className="video-filter-actions">
                <span>{hits.length} video — đã chọn {selected.size}</span>
                <button type="button" onClick={selectAll}>Chọn tất cả</button>
                <button type="button" onClick={clearSelection}>Bỏ chọn</button>
                <button
                  type="button"
                  disabled={selected.size === 0}
                  onClick={() => onUseAsScope([...selected])}
                >
                  Dùng {selected.size} video đã chọn làm phạm vi tìm khung hình
                </button>
              </div>
              <div className="video-filter-grid">
                {hits.map((h) => (
                  <label key={h.video} className={`video-filter-card${selected.has(h.video) ? " selected" : ""}`}>
                    <input type="checkbox" checked={selected.has(h.video)} onChange={() => toggleVideo(h.video)} />
                    <img src={h.thumb_url} alt={h.video} />
                    <div className="video-filter-card-info">
                      <span className="video-filter-card-category">{h.category}</span>
                      <span className="video-filter-card-title" title={h.title}>{h.title}</span>
                      <span className="video-filter-card-video">{h.video}</span>
                    </div>
                  </label>
                ))}
              </div>
            </>
          )}
          {!loading && hits.length === 0 && <div className="result-grid-empty">Chưa có kết quả — nhập nội dung hoặc chọn thể loại rồi tìm.</div>}
        </div>
      )}
    </div>
  );
}
