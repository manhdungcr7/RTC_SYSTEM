/** Ảnh tham chiếu (kèm cắt vùng) + thu hẹp phạm vi video. */
import { useMutation } from "@tanstack/react-query";
import { Crop, ImageUp, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { Button, Modal, Select, TextInput, cx } from "../../components/ui";
import { useSession } from "../../stores/sessionStore";

/* ------------------------------ Ảnh tham chiếu ------------------------------ */

/** Cắt vùng quan tâm TRƯỚC khi gửi đi encode.
 *  Khi chỉ quan tâm một chi tiết nhỏ (logo, mũ, biển số), embedding của cả khung
 *  hình bị nền lấn át — cắt riêng vùng đó làm độ chính xác tăng rõ rệt. */
function CropDialog({ src, open, onOpenChange, onDone }: {
  src: string; open: boolean; onOpenChange: (b: boolean) => void;
  onDone: (dataUrl: string) => void;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);

  const onDown = (e: React.MouseEvent) => {
    const b = boxRef.current!.getBoundingClientRect();
    drag.current = { x: e.clientX - b.left, y: e.clientY - b.top };
    setRect({ x: drag.current.x, y: drag.current.y, w: 0, h: 0 });
  };
  const onMove = (e: React.MouseEvent) => {
    if (!drag.current) return;
    const b = boxRef.current!.getBoundingClientRect();
    const cx2 = e.clientX - b.left, cy = e.clientY - b.top;
    setRect({
      x: Math.min(drag.current.x, cx2), y: Math.min(drag.current.y, cy),
      w: Math.abs(cx2 - drag.current.x), h: Math.abs(cy - drag.current.y),
    });
  };
  const onUp = () => { drag.current = null; };

  const apply = () => {
    const img = imgRef.current, box = boxRef.current;
    if (!img || !box || !rect || rect.w < 5 || rect.h < 5) return;
    const scale = img.naturalWidth / box.clientWidth;
    const c = document.createElement("canvas");
    c.width = Math.round(rect.w * scale);
    c.height = Math.round(rect.h * scale);
    c.getContext("2d")!.drawImage(
      img, rect.x * scale, rect.y * scale, rect.w * scale, rect.h * scale,
      0, 0, c.width, c.height);
    onDone(c.toDataURL("image/jpeg", 0.92));
    onOpenChange(false);
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Cắt vùng quan tâm" wide>
      <p className="mb-2 text-[11.5px] text-[var(--color-fg-dim)]">
        Kéo chuột để khoanh vùng. Chỉ phần khoanh được đem đi so khớp, phần nền bị bỏ qua.
      </p>
      <div
        ref={boxRef} onMouseDown={onDown} onMouseMove={onMove}
        onMouseUp={onUp} onMouseLeave={onUp}
        className="relative inline-block max-w-full cursor-crosshair select-none"
      >
        <img ref={imgRef} src={src} alt="Ảnh cần cắt" className="max-h-[60vh] max-w-full" draggable={false} />
        {rect && rect.w > 2 && (
          <div className="pointer-events-none absolute border-2 border-[var(--color-focus)] bg-[color-mix(in_srgb,var(--color-focus)_18%,transparent)]"
               style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h }} />
        )}
      </div>
      <div className="mt-3 flex gap-2">
        <Button variant="primary" onClick={apply} disabled={!rect || rect.w < 5}>Dùng vùng đã cắt</Button>
        <Button variant="ghost" onClick={() => setRect(null)}>Bỏ khoanh</Button>
      </div>
    </Modal>
  );
}

export function RefImagePanel() {
  const s = useSession((st) => st.sessions[st.activeId]);
  const patch = useSession((st) => st.patch);
  const [cropOpen, setCropOpen] = useState(false);

  const load = (file: File) => {
    const r = new FileReader();
    r.onload = () => {
      patch({
        refImageB64: r.result as string, refVideo: null, refN: null,
        enabled: { ...s.enabled, dinov3: true },
      });
    };
    r.readAsDataURL(file);
  };

  // Dán ảnh thẳng từ clipboard — nhanh hơn nhiều so với lưu file rồi chọn.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = Array.from(e.clipboardData?.items ?? [])
        .find((i) => i.type.startsWith("image/"));
      const f = item?.getAsFile();
      if (f) load(f);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  });

  const preview = s.refImageB64
    ?? (s.refVideo && s.refN != null ? `/media/frame/${s.refVideo}/${s.refN}` : null);

  return (
    <div className="flex flex-col gap-2">
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const f = e.dataTransfer.files?.[0];
          if (f?.type.startsWith("image/")) load(f);
        }}
        className="flex flex-col items-center gap-1.5 rounded-[var(--radius-sm)] border border-dashed border-[var(--color-line)] p-3 text-center"
      >
        {preview ? (
          <>
            <img src={preview} alt="Ảnh mẫu" className="max-h-[110px] rounded-[var(--radius-sm)]" />
            <div className="flex gap-1">
              {s.refImageB64 && (
                <Button size="sm" variant="ghost" onClick={() => setCropOpen(true)}>
                  <Crop size={11} /> Cắt vùng
                </Button>
              )}
              <Button size="sm" variant="ghost"
                      onClick={() => patch({ refImageB64: null, refVideo: null, refN: null })}>
                <X size={11} /> Bỏ ảnh
              </Button>
            </div>
          </>
        ) : (
          <>
            <ImageUp size={18} className="text-[var(--color-fg-mute)]" />
            <p className="text-[11px] leading-snug text-[var(--color-fg-mute)]">
              Kéo ảnh vào đây, dán bằng Ctrl+V, hoặc bấm 🔍 trên một khung hình kết quả
            </p>
            <label className="cursor-pointer text-[11px] text-[var(--color-focus)] hover:underline">
              chọn tệp…
              <input type="file" accept="image/*" className="hidden"
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) load(f); }} />
            </label>
          </>
        )}
      </div>

      {s.refImageB64 && (
        <CropDialog
          src={s.refImageB64} open={cropOpen} onOpenChange={setCropOpen}
          onDone={(d) => patch({ refImageB64: d })}
        />
      )}
    </div>
  );
}

/* ------------------------------ Thu hẹp phạm vi video ------------------------------ */

export interface VideoScopeValue { videos: string[]; invert: boolean }

/** Component THUẦN (không đụng sessionStore) — dùng lại được cho cả Search
 *  (bọc bởi SessionVideoScopePanel bên dưới) lẫn Temporal (state cục bộ, vì
 *  Temporal không dùng sessionStore). */
export function VideoScopePanel({ value, onChange }: {
  value: VideoScopeValue; onChange: (v: VideoScopeValue) => void;
}) {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [field, setField] = useState<"all" | "asr" | "caption">("all");
  const [cats, setCats] = useState<string[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set(value.videos));

  const search = useMutation({
    mutationFn: () => api.searchVideos(q, cat || null, 100, field),
    onSuccess: (d) => setCats(d.categories),
  });

  useEffect(() => {
    api.searchVideos("", null, 1).then((d) => setCats(d.categories)).catch(() => {});
  }, []);

  const hits = search.data?.hits ?? [];
  const toggle = (v: string) =>
    setPicked((p) => {
      const n = new Set(p);
      n.has(v) ? n.delete(v) : n.add(v);
      return n;
    });

  return (
    <div className="flex flex-col gap-2">
      {value.videos.length > 0 && (
        <div className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-focus)] bg-[color-mix(in_srgb,var(--color-focus)_12%,transparent)] px-2 py-1.5">
          <span className="flex-1 text-[11.5px] text-[var(--color-focus)]">
            Đang giới hạn trong <b className="font-mono">{value.videos.length}</b> video
            {value.invert && " (đảo ngược: LOẠI TRỪ)"}
          </span>
          <Button size="sm" variant="ghost"
                  onClick={() => { onChange({ videos: [], invert: false }); setPicked(new Set()); }}>
            Bỏ giới hạn
          </Button>
        </div>
      )}

      <TextInput value={q} onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && search.mutate()}
                 placeholder="Nội dung video… (để trống nếu chỉ lọc theo thể loại)" />
      <div className="flex gap-1">
        <Select value={cat} onChange={(e) => setCat(e.target.value)} className="flex-1 py-1 text-[12px]">
          <option value="">Mọi thể loại</option>
          {cats.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <Select value={field} onChange={(e) => setField(e.target.value as typeof field)}
                className="w-[104px] py-1 text-[12px]">
          <option value="all">Cả hai</option>
          <option value="asr">Lời thoại</option>
          <option value="caption">Hình ảnh</option>
        </Select>
      </div>

      <Button size="sm" onClick={() => search.mutate()} disabled={search.isPending || (!q.trim() && !cat)}>
        <Search size={11} /> {search.isPending ? "Đang tìm…" : "Tìm video"}
      </Button>

      {hits.length > 0 && (
        <>
          <div className="flex items-center gap-1">
            <span className="flex-1 text-[11px] text-[var(--color-fg-dim)]">
              {hits.length} video · chọn {picked.size}
            </span>
            <Button size="sm" variant="ghost" onClick={() => setPicked(new Set(hits.map((h) => h.video)))}>
              Chọn hết
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Bỏ chọn</Button>
          </div>

          <div className="grid max-h-[280px] grid-cols-2 gap-1 overflow-y-auto pr-1">
            {hits.map((h) => (
              <button
                key={h.video} type="button" onClick={() => toggle(h.video)}
                aria-pressed={picked.has(h.video)}
                className={cx(
                  "overflow-hidden rounded-[var(--radius-sm)] border text-left transition-colors",
                  picked.has(h.video)
                    ? "border-[var(--color-focus)]"
                    : "border-[var(--color-line)] hover:border-[var(--color-line-hi)]",
                )}
              >
                <img src={h.thumb_url} alt="" loading="lazy" className="aspect-video w-full object-cover" />
                <div className="px-1.5 py-1">
                  <div className="truncate font-mono text-[10px] text-[var(--color-fg-dim)]">{h.video}</div>
                  <div className="truncate text-[10px] text-[var(--color-fg-mute)]">{h.category}</div>
                </div>
              </button>
            ))}
          </div>

          <label className="flex items-center gap-1.5 text-[11px] text-[var(--color-fg-dim)]">
            <input type="checkbox" checked={value.invert}
                   onChange={(e) => onChange({ ...value, invert: e.target.checked })}
                   className="h-3 w-3 accent-[var(--color-focus)]" />
            Đảo ngược — LOẠI TRỪ các video đã chọn
          </label>

          <Button size="sm" variant="primary" disabled={picked.size === 0}
                  onClick={() => onChange({ videos: [...picked], invert: value.invert })}>
            Áp dụng {picked.size} video làm phạm vi
          </Button>
        </>
      )}
    </div>
  );
}

/** Bọc VideoScopePanel gắn với phiên làm việc của Search (lưu bền vào
 *  sessionStore) — giữ nguyên hành vi trước khi tách component thuần ở trên. */
export function SessionVideoScopePanel() {
  const s = useSession((st) => st.sessions[st.activeId]);
  const patch = useSession((st) => st.patch);
  return (
    <VideoScopePanel
      value={{ videos: s.scopeVideos, invert: s.scopeInvert }}
      onChange={(v) => patch({ scopeVideos: v.videos, scopeInvert: v.invert })}
    />
  );
}
