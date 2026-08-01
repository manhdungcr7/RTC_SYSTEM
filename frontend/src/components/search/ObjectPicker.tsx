import { useMemo, useState } from "react";

import { GRID_COLS, GRID_ROWS, OBJECT_CLASSES, OBJECT_COLORS } from "../../data/objectVocab";

interface Props {
  onChange: (objectQuery: string) => void;
}

// Thay input tự gõ tự do bằng danh sách nhấp chọn (tiếng Việt) — người dùng
// không cần nhớ/gõ đúng tên lớp vật thể tiếng Anh. Chọn xong tự ghép thành
// chuỗi token tiếng Anh (class/color/grid) đúng định dạng đã lưu trong
// Meilisearch field "objects" (xem core/repositories/meili_repo.py).
export function ObjectPicker({ onChange }: Props) {
  const [classFilter, setClassFilter] = useState("");
  const [selectedClasses, setSelectedClasses] = useState<Set<string>>(new Set());
  const [selectedColors, setSelectedColors] = useState<Set<string>>(new Set());
  const [selectedGrid, setSelectedGrid] = useState<Set<string>>(new Set());
  const [showClassList, setShowClassList] = useState(false);

  const filteredClasses = useMemo(() => {
    const q = classFilter.trim().toLowerCase();
    if (!q) return OBJECT_CLASSES;
    return OBJECT_CLASSES.filter((c) => c.vi.toLowerCase().includes(q) || c.en.includes(q));
  }, [classFilter]);

  const emit = (classes: Set<string>, colors: Set<string>, grid: Set<string>) => {
    const tokens = [...classes, ...colors, ...grid];
    onChange(tokens.join(" "));
  };

  const toggleClass = (en: string) => {
    const next = new Set(selectedClasses);
    if (next.has(en)) next.delete(en);
    else next.add(en);
    setSelectedClasses(next);
    emit(next, selectedColors, selectedGrid);
  };
  const toggleColor = (en: string) => {
    const next = new Set(selectedColors);
    if (next.has(en)) next.delete(en);
    else next.add(en);
    setSelectedColors(next);
    emit(selectedClasses, next, selectedGrid);
  };
  const toggleGrid = (cell: string) => {
    const next = new Set(selectedGrid);
    if (next.has(cell)) next.delete(cell);
    else next.add(cell);
    setSelectedGrid(next);
    emit(selectedClasses, selectedColors, next);
  };

  const classLabel = (en: string) => OBJECT_CLASSES.find((c) => c.en === en)?.vi ?? en;

  return (
    <div className="object-picker">
      <div className="object-picker-section">
        <div className="object-picker-label">Vật thể</div>
        {selectedClasses.size > 0 && (
          <div className="object-picker-chips">
            {[...selectedClasses].map((en) => (
              <button key={en} type="button" className="object-chip" onClick={() => toggleClass(en)}>
                {classLabel(en)} ×
              </button>
            ))}
          </div>
        )}
        <input
          value={classFilter}
          onChange={(e) => setClassFilter(e.target.value)}
          onFocus={() => setShowClassList(true)}
          placeholder="Gõ để lọc (vd: xe, người, chó...)"
        />
        {showClassList && (
          <div className="object-picker-list">
            {filteredClasses.map((c) => (
              <label key={c.en} className="object-picker-item">
                <input type="checkbox" checked={selectedClasses.has(c.en)} onChange={() => toggleClass(c.en)} />
                {c.vi}
              </label>
            ))}
            {filteredClasses.length === 0 && <div className="object-picker-empty">Không tìm thấy</div>}
            <button type="button" className="object-picker-close" onClick={() => setShowClassList(false)}>
              Đóng danh sách
            </button>
          </div>
        )}
      </div>

      <div className="object-picker-section">
        <div className="object-picker-label">Màu</div>
        <div className="object-picker-chips">
          {OBJECT_COLORS.map((c) => (
            <button
              key={c.en}
              type="button"
              className={`object-chip${selectedColors.has(c.en) ? " active" : ""}`}
              onClick={() => toggleColor(c.en)}
            >
              {c.vi}
            </button>
          ))}
        </div>
      </div>

      <div className="object-picker-section">
        <div className="object-picker-label">Vị trí trong khung hình (tuỳ chọn)</div>
        <div className="object-picker-grid">
          {GRID_ROWS.map((row) => (
            <div className="object-picker-grid-row" key={row}>
              {GRID_COLS.map((col) => {
                const cell = `${row}${col}`;
                return (
                  <button
                    key={cell}
                    type="button"
                    className={`object-picker-cell${selectedGrid.has(cell) ? " active" : ""}`}
                    onClick={() => toggleGrid(cell)}
                    title={cell}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
