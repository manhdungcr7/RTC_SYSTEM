import { useState } from "react";

interface Props {
  onSearch: (events: string[], context: string) => void;
  loading: boolean;
}

export function EventTimeline({ onSearch, loading }: Props) {
  const [context, setContext] = useState("");
  const [events, setEvents] = useState<string[]>(["", ""]);

  const setEvent = (i: number, v: string) =>
    setEvents((prev) => prev.map((e, idx) => (idx === i ? v : e)));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(events.filter((e) => e.trim()), context);
  };

  return (
    <form className="event-timeline" onSubmit={submit}>
      <input
        placeholder="Bối cảnh chung (tuỳ chọn)"
        value={context}
        onChange={(e) => setContext(e.target.value)}
      />
      {events.map((ev, i) => (
        <div className="event-row" key={i}>
          <span className="event-label">E{i + 1}</span>
          <input value={ev} onChange={(e) => setEvent(i, e.target.value)} placeholder={`Sự kiện ${i + 1}...`} />
        </div>
      ))}
      <div className="event-timeline-actions">
        <button type="button" onClick={() => setEvents((p) => [...p, ""])}>+ Thêm sự kiện</button>
        {events.length > 2 && (
          <button type="button" onClick={() => setEvents((p) => p.slice(0, -1))}>− Bớt sự kiện</button>
        )}
        <button type="submit" disabled={loading || events.filter((e) => e.trim()).length < 2}>
          {loading ? "Đang tìm..." : "Tìm chuỗi sự kiện"}
        </button>
      </div>
    </form>
  );
}
