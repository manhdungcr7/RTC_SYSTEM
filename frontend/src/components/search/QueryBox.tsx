import { useState } from "react";

import type { QueryKind, SearchRequest } from "../../types/search";

interface Props {
  onSearch: (req: SearchRequest) => void;
  loading: boolean;
}

export function QueryBox({ onSearch, loading }: Props) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<QueryKind>("kis");
  const [topk, setTopk] = useState(100);
  const [useExpansion, setUseExpansion] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [ocrQuery, setOcrQuery] = useState("");
  const [asrQuery, setAsrQuery] = useState("");
  const [objectQuery, setObjectQuery] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch({
      query,
      kind,
      topk,
      use_expansion: useExpansion,
      ocr_query: ocrQuery.trim() || undefined,
      asr_query: asrQuery.trim() || undefined,
      object_query: objectQuery.trim() || undefined,
    });
  };

  return (
    <form className="query-box" onSubmit={submit}>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Mô tả cảnh cần tìm (tiếng Việt hoặc Anh)..."
        rows={3}
      />

      <button type="button" className="query-box-toggle-filters" onClick={() => setShowFilters((s) => !s)}>
        {showFilters ? "▾" : "▸"} Bộ lọc nâng cao (OCR / ASR / Object — nhập tay, bỏ qua tự động đoán)
      </button>

      {showFilters && (
        <div className="query-box-filters">
          <label>
            OCR — chữ trên màn hình (banner, slide, phụ đề...)
            <input value={ocrQuery} onChange={(e) => setOcrQuery(e.target.value)} placeholder="vd: FANA, Khánh Hòa" />
          </label>
          <label>
            ASR — lời thuyết minh/nói
            <input value={asrQuery} onChange={(e) => setAsrQuery(e.target.value)} placeholder="vd: tên riêng được nhắc tới" />
          </label>
          <label>
            Object/màu — vật thể + màu cụ thể
            <input value={objectQuery} onChange={(e) => setObjectQuery(e.target.value)} placeholder="vd: red car, helmet" />
          </label>
        </div>
      )}

      <div className="query-box-row">
        <select value={kind} onChange={(e) => setKind(e.target.value as QueryKind)}>
          <option value="kis">KIS</option>
          <option value="qa">QA</option>
          <option value="trake">TRAKE (dùng trang Temporal)</option>
        </select>
        <label className="query-box-topk">
          Top K
          <input type="number" min={1} max={100} value={topk} onChange={(e) => setTopk(Number(e.target.value))} />
        </label>
        <label className="query-box-checkbox">
          <input type="checkbox" checked={useExpansion} onChange={(e) => setUseExpansion(e.target.checked)} />
          Mở rộng câu (LLM)
        </label>
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? "Đang tìm..." : "Tìm kiếm"}
        </button>
      </div>
    </form>
  );
}
