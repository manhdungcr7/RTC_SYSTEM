import { useState } from "react";

import { SIGNAL_WEIGHT_KEYS } from "../../types/search";

interface Props {
  onChange: (weights: Record<string, number> | undefined) => void;
}

// Trọng số ĐỘNG (mục 2) — mỗi tín hiệu có checkbox "ghi đè" + thanh trượt. KHÔNG
// tích checkbox = dùng mặc định đã đo trong core/config.py (theo kind KIS/QA/
// TRAKE riêng, UI không biết/không cần biết số đó) — chỉ khi tích mới GỬI key đó
// lên backend để ghi đè tại chỗ (xem api/schemas/search.py::SearchRequest.weights).
export function WeightPanel({ onChange }: Props) {
  const [overrides, setOverrides] = useState<Record<string, number>>({});

  const emit = (next: Record<string, number>) => {
    onChange(Object.keys(next).length > 0 ? next : undefined);
  };

  const toggle = (key: string, typical: number) => {
    setOverrides((prev) => {
      const next = { ...prev };
      if (key in next) delete next[key];
      else next[key] = typical;
      emit(next);
      return next;
    });
  };

  const setValue = (key: string, value: number) => {
    setOverrides((prev) => {
      const next = { ...prev, [key]: value };
      emit(next);
      return next;
    });
  };

  return (
    <div className="weight-panel">
      {SIGNAL_WEIGHT_KEYS.map((s) => {
        const active = s.key in overrides;
        return (
          <div className={`weight-row${active ? " active" : ""}`} key={s.key}>
            <label className="weight-row-checkbox">
              <input type="checkbox" checked={active} onChange={() => toggle(s.key, s.typical)} />
              {s.label}
            </label>
            <input
              type="range" min={0} max={3} step={0.05}
              value={overrides[s.key] ?? s.typical}
              disabled={!active}
              onChange={(e) => setValue(s.key, Number(e.target.value))}
            />
            <span className="weight-row-value">{(overrides[s.key] ?? s.typical).toFixed(2)}</span>
          </div>
        );
      })}
    </div>
  );
}
