/**
 * VIDEO WORKBENCH — trả lời câu: "Tôi khá chắc đáp án nằm trong video này.
 * Cho tôi mọi thứ về video này."
 *
 * Đây là ĐƯỜNG THỦ CÔNG CUỐI CÙNG: khi mọi tín hiệu tự động đều thất bại, người
 * dùng vẫn còn một cách luôn luôn có tác dụng — thu hẹp về một video (bằng thể
 * loại, bằng một câu thoại nhớ mang máng, bằng một dòng chữ trên màn hình), rồi
 * đọc trọn transcript và quét mắt toàn bộ keyframe. Với ~190 keyframe/video,
 * quét hết mất khoảng 30–60 giây. Không có màn hình này thì thao tác đó phải tua
 * video thủ công, chậm hơn cả chục lần.
 */
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import { api, thumbUrl } from "../../api/client";
import { Button, TextInput } from "../../components/ui";
import { useUi } from "../../stores/uiStore";
import { formatTimecode } from "../viewer/useFrameIndex";

export function WorkbenchOverlay() {
  const video = useUi((s) => s.workbenchVideo);
  const close = useUi((s) => s.openWorkbench);
  const openDetail = useUi((s) => s.openDetail);
  const [filter, setFilter] = useState("");

  const enabled = !!video;
  const { data: map } = useQuery({
    queryKey: ["map", video], queryFn: ({ signal }) => api.videoMap(video!, signal),
    enabled, staleTime: Infinity,
  });
  const { data: tr } = useQuery({
    queryKey: ["transcript", video], queryFn: ({ signal }) => api.videoTranscript(video!, signal),
    enabled, staleTime: Infinity,
  });
  const { data: ocr } = useQuery({
    queryKey: ["ocr", video], queryFn: ({ signal }) => api.videoOcr(video!, signal),
    enabled, staleTime: Infinity,
  });

  const q = filter.trim().toLowerCase();
  const ocrByN = useMemo(
    () => new Map((ocr?.rows ?? []).map((r) => [r.n, r.text])), [ocr]);

  // Lọc tại chỗ trên CẢ 3 nguồn — không gọi mạng, gõ tới đâu lọc tới đó.
  const frames = useMemo(() => {
    const rows = map?.rows ?? [];
    if (!q) return rows;
    return rows.filter((r) => (ocrByN.get(r.n) ?? "").toLowerCase().includes(q));
  }, [map, q, ocrByN]);

  const segs = useMemo(() => {
    const list = tr?.segments ?? [];
    if (!q) return list;
    return list.filter((s) => s.text.toLowerCase().includes(q));
  }, [tr, q]);

  const ocrRows = useMemo(() => {
    const list = ocr?.rows ?? [];
    if (!q) return list;
    return list.filter((r) => r.text.toLowerCase().includes(q));
  }, [ocr, q]);

  if (!video) return null;

  const jump = (n: number) => {
    const row = map?.rows.find((r) => r.n === n);
    if (!row) return;
    openDetail({
      id: `${video}:${String(n).padStart(6, "0")}`, video, n,
      frame_idx: row.frame_idx, score: 0, rank: 0,
      thumb_url: thumbUrl(video, n), pts_time: row.pts_time,
    });
    close(null);
  };

  const jumpAtTime = (t: number) => {
    const rows = map?.rows ?? [];
    if (!rows.length) return;
    const near = rows.reduce((a, b) =>
      Math.abs(b.pts_time - t) < Math.abs(a.pts_time - t) ? b : a);
    jump(near.n);
  };

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-[var(--color-bg)]">
      <div className="flex shrink-0 items-center gap-3 border-b border-[var(--color-line)] px-3 py-2">
        <span className="font-mono text-[13px]">{video}</span>
        <span className="font-mono text-[11px] tabular-nums text-[var(--color-fg-mute)]">
          {map ? `${map.rows.length} keyframe · ${formatTimecode(map.duration ?? 0)} · ${map.fps.toFixed(2)} fps` : "…"}
        </span>
        <div className="relative ml-2 w-[280px]">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-fg-mute)]" />
          <TextInput value={filter} onChange={(e) => setFilter(e.target.value)}
                     placeholder="Lọc trong video này (chữ trên hình, lời thoại)…"
                     className="py-1 pl-6 text-[11.5px]" />
        </div>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={() => close(null)}>
          <X size={14} />
        </Button>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto p-3">
          <div className="mb-1.5 text-[11px] text-[var(--color-fg-dim)]">
            {q ? `${frames.length} khung hình có chữ khớp "${filter}"` : `Toàn bộ ${frames.length} keyframe`}
          </div>
          <div className="grid gap-1.5"
               style={{ gridTemplateColumns: "repeat(auto-fill, minmax(132px, 1fr))" }}>
            {frames.map((r) => {
              const text = ocrByN.get(r.n);
              return (
                <button key={r.n} type="button" onClick={() => jump(r.n)}
                        className="overflow-hidden rounded-[var(--radius-sm)] border border-[var(--color-line)] text-left hover:border-[var(--color-focus)]">
                  <img src={thumbUrl(video, r.n)} alt="" loading="lazy"
                       className="aspect-video w-full bg-black object-cover" />
                  <div className="px-1 py-0.5">
                    <div className="font-mono text-[9.5px] tabular-nums text-[var(--color-fg-mute)]">
                      f{r.frame_idx} · {formatTimecode(r.pts_time).slice(0, 5)}
                    </div>
                    {text && (
                      <div className="truncate text-[9.5px] text-[var(--color-sig-ocr)]" title={text}>
                        {text.replace(/\n/g, " ")}
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex w-[420px] shrink-0 flex-col border-l border-[var(--color-line)]">
          <div className="flex min-h-0 flex-1 flex-col border-b border-[var(--color-line)]">
            <div className="label-xs shrink-0 px-3 py-1.5">
              Lời thoại {q && `(${segs.length} đoạn khớp)`}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-2">
              {segs.map((s, i) => (
                <button key={i} type="button" onClick={() => jumpAtTime(s.t)}
                        className="mb-1 block w-full text-left text-[11.5px] leading-snug text-[var(--color-fg-dim)] hover:text-[var(--color-fg)]">
                  <span className="font-mono tabular-nums text-[var(--color-fg-mute)]">
                    {formatTimecode(s.t).slice(0, 5)}
                  </span>{" "}
                  {s.text}
                </button>
              ))}
              {segs.length === 0 && (
                <p className="text-[11px] text-[var(--color-fg-mute)]">Không có đoạn thoại nào khớp.</p>
              )}
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <div className="label-xs shrink-0 px-3 py-1.5">
              Chữ trên hình {q && `(${ocrRows.length} khung khớp)`}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-2">
              {ocrRows.map((r) => {
                const row = map?.rows.find((x) => x.n === r.n);
                return (
                  <button key={r.n} type="button" onClick={() => jump(r.n)}
                          className="mb-1 block w-full text-left text-[11px] leading-snug text-[var(--color-fg-dim)] hover:text-[var(--color-fg)]">
                    <span className="font-mono tabular-nums text-[var(--color-fg-mute)]">
                      {row ? formatTimecode(row.pts_time).slice(0, 5) : `n${r.n}`}
                    </span>{" "}
                    {r.text.replace(/\n/g, " · ")}
                  </button>
                );
              })}
              {ocrRows.length === 0 && (
                <p className="text-[11px] text-[var(--color-fg-mute)]">Không có chữ nào khớp.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
