import { useRef, useState } from "react";

import { MODEL_OPTIONS, type QueryKind, type SearchRequest } from "../../types/search";
import { ObjectPicker } from "./ObjectPicker";
import { WeightPanel } from "./WeightPanel";

interface Props {
  onSearch: (req: SearchRequest) => void;
  loading: boolean;
  videoScope: string[] | null;
  onClearScope: () => void;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function QueryBox({ onSearch, loading, videoScope, onClearScope }: Props) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<QueryKind>("kis");
  const [topk, setTopk] = useState(100);
  const [useExpansion, setUseExpansion] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [ocrQuery, setOcrQuery] = useState("");
  const [asrQuery, setAsrQuery] = useState("");
  const [objectQuery, setObjectQuery] = useState("");
  const [weights, setWeights] = useState<Record<string, number> | undefined>(undefined);
  const [strictTextFilter, setStrictTextFilter] = useState(false);
  const [refImagePreview, setRefImagePreview] = useState<string | null>(null);
  const refImageB64 = useRef<string | null>(null);
  // Mặc định chỉ tích metaclip2 (nhánh CHÍNH) — các nhánh khác gọi thêm model từ
  // xa (Kaggle), để người dùng tự bật khi cần thay vì chạy hết mỗi lần tìm.
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set(["metaclip2"]));

  const toggleModel = (key: string) =>
    setSelectedModels((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const onPickRefImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const dataUri = await fileToBase64(file);
    refImageB64.current = dataUri;
    setRefImagePreview(dataUri);
  };
  const clearRefImage = () => {
    refImageB64.current = null;
    setRefImagePreview(null);
  };

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
      models: [...selectedModels],
      weights,
      ref_image_b64: refImageB64.current ?? undefined,
      video_scope: videoScope ?? undefined,
      strict_text_filter: strictTextFilter,
    });
  };

  return (
    <form className="query-box" onSubmit={submit}>
      {videoScope && videoScope.length > 0 && (
        <div className="query-box-scope">
          Phạm vi: <strong>{videoScope.length} video</strong> đã chọn từ bước lọc video
          <button type="button" onClick={onClearScope}>✕ Bỏ phạm vi (tìm toàn kho)</button>
        </div>
      )}

      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Mô tả cảnh cần tìm (tiếng Việt hoặc Anh)..."
        rows={3}
      />

      <div className="query-box-models">
        <span className="query-box-models-label">Model:</span>
        {MODEL_OPTIONS.map((m) => (
          <label key={m.key} className="query-box-checkbox">
            <input type="checkbox" checked={selectedModels.has(m.key)} onChange={() => toggleModel(m.key)} />
            {m.label}
          </label>
        ))}
      </div>

      <button type="button" className="query-box-toggle-filters" onClick={() => setShowFilters((s) => !s)}>
        {showFilters ? "▾" : "▸"} Bộ lọc nâng cao (OCR / ASR / Object / ảnh tham chiếu / trọng số — tuỳ chỉnh tay)
      </button>

      {showFilters && (
        <>
          <div className="query-box-filters">
            <label>
              OCR — chữ trên màn hình (banner, slide, phụ đề...)
              <input value={ocrQuery} onChange={(e) => setOcrQuery(e.target.value)} placeholder="vd: FANA, Khánh Hòa" />
            </label>
            <label>
              ASR — lời thuyết minh/nói
              <input value={asrQuery} onChange={(e) => setAsrQuery(e.target.value)} placeholder="vd: tên riêng được nhắc tới" />
            </label>
          </div>

          <label className="query-box-checkbox">
            <input type="checkbox" checked={strictTextFilter} onChange={(e) => setStrictTextFilter(e.target.checked)} />
            Lọc chắc chắn theo OCR/ASR (khi khớp độ tin cậy cao, các nhánh khác CHỈ tìm trong tập đã khớp ± sai số)
          </label>

          <div className="query-box-object">
            <span className="query-box-object-title">Object/màu/vị trí — nhấp chọn (không cần gõ tay)</span>
            <ObjectPicker onChange={setObjectQuery} />
          </div>

          <div className="query-box-refimage">
            <span className="query-box-object-title">Ảnh tham chiếu (DINOv3 — tìm khung hình giống ảnh này, kết hợp cùng mô tả chữ ở trên)</span>
            <div className="image-search-row">
              <input type="file" accept="image/*" onChange={onPickRefImage} />
              {refImagePreview && (
                <>
                  <img src={refImagePreview} className="image-search-preview" alt="ref preview" />
                  <button type="button" onClick={clearRefImage}>✕ Bỏ ảnh</button>
                </>
              )}
            </div>
          </div>

          <div className="query-box-object">
            <span className="query-box-object-title">Trọng số từng tín hiệu (tuỳ chỉnh tay — không tích = dùng mặc định đã đo)</span>
            <WeightPanel onChange={setWeights} />
          </div>
        </>
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
