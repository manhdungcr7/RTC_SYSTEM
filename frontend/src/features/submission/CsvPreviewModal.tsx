/**
 * XEM TRƯỚC FILE CSV BẰNG ẢNH — trước khi thực sự đem 1 file .csv đi nộp
 * Codabench, gửi lại chính file đó vào đây để xem THEO ĐÚNG THỨ TỰ hệ thống sẽ
 * chấm: dòng nào ứng với khung nào, có bị lệch video/frame không, đáp án QA có
 * đúng ý không — kiểm chứng bằng mắt, không chỉ tin vào số đã gõ.
 *
 * Cùng cơ chế với "Tra khung" (GET /media/lookup) — vì frame_idx không phải
 * lúc nào cũng đúng ngay 1 keyframe đã lập chỉ mục, mỗi ô số được tra ra khung
 * GẦN NHẤT, giống hệt cách hệ thống sẽ hiểu file này lúc nộp.
 */
import { AlertTriangle, FileUp, Loader2 } from "lucide-react";
import { useRef, useState } from "react";

import { api } from "../../api/client";
import { Modal, Select } from "../../components/ui";
import { useUi } from "../../stores/uiStore";
import type { QueryKind, SearchHit } from "../../types/api";

/** Parse 1 dòng CSV — có xử lý ô bọc ngoặc kép (đáp án QA có thể chứa dấu
 *  phẩy) theo đúng quy tắc chuẩn CSV mà backend dùng lúc dựng file. */
function parseCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "", inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; } else inQuotes = false;
      } else cur += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ",") { out.push(cur); cur = ""; }
    else cur += c;
  }
  out.push(cur);
  return out;
}

function parseCsv(text: string): string[][] {
  return text.split(/\r?\n/).filter((l) => l.trim().length > 0).map(parseCsvLine);
}

interface PreviewFrame {
  askedFrameIdx: number;
  hit: SearchHit | null;
  error: string | null;
}
interface PreviewRow {
  video: string;
  frames: PreviewFrame[];
  answer: string | null;
}

/** Chạy tối đa `limit` lookup cùng lúc — 1 file TRAKE 100 dòng x nhiều sự
 *  kiện có thể ra hàng trăm khung, bắn hết 1 lượt dễ nghẽn máy encode/BE. */
async function mapLimit<T, R>(items: T[], limit: number, fn: (x: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let i = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (i < items.length) {
      const idx = i++;
      out[idx] = await fn(items[idx]);
    }
  });
  await Promise.all(workers);
  return out;
}

export function CsvPreviewModal({ open, onOpenChange }: { open: boolean; onOpenChange: (b: boolean) => void }) {
  const openDetail = useUi((s) => s.openDetail);
  const setDetailReturnToCsv = useUi((s) => s.setDetailReturnToCsv);
  const [kind, setKind] = useState<QueryKind>("kis");
  const [fileName, setFileName] = useState("");
  const [rows, setRows] = useState<PreviewRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const onFile = async (file: File) => {
    setFileName(file.name);
    setRows(null);
    setParseError(null);
    const text = await file.text();
    const lines = parseCsv(text);
    if (lines.length === 0) { setParseError("File rỗng hoặc không đọc được dòng nào."); return; }

    const minCols = kind === "trake" ? 3 : 2;
    const bad = lines.findIndex((l) => l.length < minCols);
    if (bad >= 0) {
      setParseError(`Dòng ${bad + 1} chỉ có ${lines[bad].length} cột, cần ít nhất ${minCols} cho loại ${kind.toUpperCase()}.`);
      return;
    }

    setLoading(true);
    try {
      const parsed = lines.map((cols) => {
        const video = cols[0].trim();
        if (kind === "qa") {
          return { video, frameStrs: [cols[1]], answer: cols[2] ?? "" };
        }
        if (kind === "trake") {
          return { video, frameStrs: cols.slice(1), answer: null as string | null };
        }
        return { video, frameStrs: [cols[1]], answer: null as string | null };
      });

      const flatLookups: { video: string; frameIdx: number }[] = [];
      for (const p of parsed) for (const fs of p.frameStrs)
        flatLookups.push({ video: p.video, frameIdx: Number(fs.trim()) || 0 });

      const results = await mapLimit(flatLookups, 6, async ({ video, frameIdx }) => {
        try {
          const hit = await api.lookupFrame(video, frameIdx);
          return { askedFrameIdx: frameIdx, hit, error: null } as PreviewFrame;
        } catch (e) {
          return { askedFrameIdx: frameIdx, hit: null, error: (e as Error).message || "lỗi tra khung" } as PreviewFrame;
        }
      });

      let cursor = 0;
      const out: PreviewRow[] = parsed.map((p) => {
        const frames = p.frameStrs.map(() => results[cursor++]);
        return { video: p.video, frames, answer: p.answer };
      });
      setRows(out);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Xem trước file CSV bằng ảnh" wide>
      <div className="flex flex-col gap-3">
        <p className="text-[11px] leading-snug text-[var(--color-fg-mute)]">
          Gửi lại đúng file .csv sắp nộp — mỗi dòng hiện ra thành ảnh THEO ĐÚNG
          THỨ TỰ trong file, để soát bằng mắt trước khi nộp thật lên Codabench.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={kind} onChange={(e) => setKind(e.target.value as QueryKind)}
                  className="w-[100px] px-1.5 py-1 text-[12px]">
            <option value="kis">KIS</option>
            <option value="qa">Q&amp;A</option>
            <option value="trake">TRAKE</option>
          </Select>
          <button type="button" onClick={() => inputRef.current?.click()}
                  className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-2.5 py-1.5 text-[12px] hover:border-[var(--color-line-hi)]">
            <FileUp size={12} /> Chọn file .csv
          </button>
          <input ref={inputRef} type="file" accept=".csv" className="hidden"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
          {fileName && <span className="font-mono text-[11px] text-[var(--color-fg-dim)]">{fileName}</span>}
          {loading && <Loader2 size={13} className="animate-spin text-[var(--color-fg-mute)]" />}
        </div>

        {parseError && (
          <div className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-err)] bg-[color-mix(in_srgb,var(--color-err)_10%,transparent)] px-2 py-1.5 text-[11.5px] text-[var(--color-err)]">
            <AlertTriangle size={12} /> {parseError}
          </div>
        )}

        {rows && (
          <div className="flex max-h-[60vh] flex-col gap-2 overflow-y-auto">
            {rows.map((r, i) => (
              <div key={i} className="rounded-[var(--radius-sm)] border border-[var(--color-line)] p-2">
                <div className="mb-1 flex items-center gap-2">
                  <span className="font-mono text-[11px] tabular-nums text-[var(--color-fg-mute)]">
                    dòng {i + 1}{i === 0 && " (tin cậy nhất)"}
                  </span>
                  <span className="font-mono text-[12px]">{r.video}</span>
                  {r.answer != null && (
                    <span className="ml-auto text-[11px] text-[var(--color-fg-dim)]">
                      đáp án: <b>{r.answer || "(trống)"}</b>
                    </span>
                  )}
                </div>
                <div className="flex gap-1.5 overflow-x-auto pb-1">
                  {r.frames.map((f, k) => (
                    <div key={k} className="shrink-0">
                      {f.hit ? (
                        <>
                          <button type="button"
                                  onClick={() => {
                                    setDetailReturnToCsv(true);
                                    onOpenChange(false);
                                    openDetail(f.hit!, [f.hit!]);
                                  }}
                                  title="Mở video, tua tới đúng khung này — giống hệt bấm vào 1 kết quả tìm kiếm">
                            <img src={f.hit.thumb_url} alt="" loading="lazy"
                                 className="h-[74px] w-[132px] rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-black object-cover hover:border-[var(--color-focus)]" />
                          </button>
                          <div className="mt-0.5 font-mono text-[9.5px] tabular-nums text-[var(--color-fg-mute)]">
                            {r.frames.length > 1 && `E${k + 1} · `}
                            hỏi f{f.askedFrameIdx} → khung gần nhất f{f.hit.frame_idx}
                          </div>
                        </>
                      ) : (
                        <div className="flex h-[74px] w-[132px] flex-col items-center justify-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-err)] bg-[color-mix(in_srgb,var(--color-err)_10%,transparent)] px-1 text-center text-[9.5px] text-[var(--color-err)]">
                          <AlertTriangle size={12} />
                          {f.error ?? "không tra được"}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}
