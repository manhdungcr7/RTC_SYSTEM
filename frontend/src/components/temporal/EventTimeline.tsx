import { useState } from "react";

interface Props {
  onSearch: (
    events: string[],
    context: string,
    ocrQueries: string[],
    asrQueries: string[],
    lambdaPenalty: number | undefined,
    anchorIndices: number[] | undefined,
  ) => void;
  loading: boolean;
}

export function EventTimeline({ onSearch, loading }: Props) {
  const [context, setContext] = useState("");
  const [events, setEvents] = useState<string[]>(["", ""]);
  const [ocrOverrides, setOcrOverrides] = useState<string[]>(["", ""]);
  const [asrOverrides, setAsrOverrides] = useState<string[]>(["", ""]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [noDistancePenalty, setNoDistancePenalty] = useState(false);
  // Chỉ số (trong mảng `events` GỐC, chưa lọc rỗng) của TỐI ĐA 2 sự kiện được
  // chọn làm neo thị giác cho boundary-anchor. Rỗng = mặc định (E1 + cuối) —
  // xem core/temporal.py. Chọn tay khi 1 cặp Ở GIỮA dễ nhận diện hơn đầu/cuối.
  const [anchorIdxs, setAnchorIdxs] = useState<number[]>([]);

  const setEvent = (i: number, v: string) =>
    setEvents((prev) => prev.map((e, idx) => (idx === i ? v : e)));
  const setOcrOverride = (i: number, v: string) =>
    setOcrOverrides((prev) => prev.map((e, idx) => (idx === i ? v : e)));
  const setAsrOverride = (i: number, v: string) =>
    setAsrOverrides((prev) => prev.map((e, idx) => (idx === i ? v : e)));

  const toggleAnchor = (i: number) =>
    setAnchorIdxs((prev) => {
      if (prev.includes(i)) return prev.filter((x) => x !== i);
      const next = [...prev, i];
      return next.length > 2 ? next.slice(next.length - 2) : next; // giữ tối đa 2, mới nhất thắng
    });

  const addEvent = () => {
    setEvents((p) => [...p, ""]);
    setOcrOverrides((p) => [...p, ""]);
    setAsrOverrides((p) => [...p, ""]);
  };
  const removeEvent = () => {
    setEvents((p) => p.slice(0, -1));
    setOcrOverrides((p) => p.slice(0, -1));
    setAsrOverrides((p) => p.slice(0, -1));
    setAnchorIdxs((p) => p.filter((i) => i < events.length - 1));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const idxs = events.map((_, i) => i).filter((i) => events[i].trim());
    const anchorMapped = anchorIdxs
      .filter((i) => idxs.includes(i))
      .map((i) => idxs.indexOf(i))
      .sort((a, b) => a - b);
    onSearch(
      idxs.map((i) => events[i]),
      context,
      idxs.map((i) => ocrOverrides[i]),
      idxs.map((i) => asrOverrides[i]),
      noDistancePenalty ? 0 : undefined,
      anchorMapped.length === 2 ? anchorMapped : undefined,
    );
  };

  return (
    <form className="event-timeline" onSubmit={submit}>
      <input
        placeholder="Bối cảnh chung (tuỳ chọn)"
        value={context}
        onChange={(e) => setContext(e.target.value)}
      />
      <p className="event-timeline-hint">
        ⚓ = chọn NEO thị giác (2 sự kiện dễ nhận diện nhất) cho bước lọc video ứng viên — mặc định dùng sự kiện đầu + cuối,
        nhưng cặp Ở GIỮA có thể đặc trưng hơn (vd "4 chân chạm đất" dễ nhận hơn "lân xoay vòng trên cột").
      </p>
      {events.map((ev, i) => (
        <div className="event-block" key={i}>
          <div className="event-row">
            <span className="event-label">E{i + 1}</span>
            <input value={ev} onChange={(e) => setEvent(i, e.target.value)} placeholder={`Sự kiện ${i + 1}...`} />
            <button
              type="button"
              className={`event-anchor-btn${anchorIdxs.includes(i) ? " active" : ""}`}
              title="Dùng sự kiện này làm neo thị giác (chọn đúng 2)"
              onClick={() => toggleAnchor(i)}
            >
              ⚓
            </button>
          </div>
          {showAdvanced && (
            <div className="event-row event-row-advanced">
              <span className="event-label event-label-ghost" />
              <input
                value={ocrOverrides[i] ?? ""}
                onChange={(e) => setOcrOverride(i, e.target.value)}
                placeholder="OCR ghi đè riêng cho sự kiện này (bỏ trống = tự đoán theo câu trên)"
              />
              <input
                value={asrOverrides[i] ?? ""}
                onChange={(e) => setAsrOverride(i, e.target.value)}
                placeholder="ASR ghi đè riêng cho sự kiện này (bỏ trống = tự đoán theo câu trên)"
              />
            </div>
          )}
        </div>
      ))}

      <button type="button" className="query-box-toggle-filters" onClick={() => setShowAdvanced((s) => !s)}>
        {showAdvanced ? "▾" : "▸"} Ghi đè OCR/ASR theo từng sự kiện (tuỳ chọn nâng cao — dùng khi biết chính xác chữ/lời cần tìm)
      </button>

      <div className="event-timeline-actions">
        <button type="button" onClick={addEvent}>+ Thêm sự kiện</button>
        {events.length > 2 && (
          <button type="button" onClick={removeEvent}>− Bớt sự kiện</button>
        )}
        <label className="query-box-checkbox">
          <input type="checkbox" checked={noDistancePenalty} onChange={(e) => setNoDistancePenalty(e.target.checked)} />
          Tắt phạt khoảng cách (sự kiện không cần gần nhau về thời gian)
        </label>
        <button type="submit" disabled={loading || events.filter((e) => e.trim()).length < 2}>
          {loading ? "Đang tìm..." : "Tìm chuỗi sự kiện"}
        </button>
      </div>
    </form>
  );
}
