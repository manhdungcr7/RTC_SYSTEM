/**
 * Khung xem chi tiết — nơi CHỐT đáp án.
 *
 * Điểm nhấn: ĐỒNG HỒ FRAME_IDX kiểu thiết bị dựng phim. Tua tới đâu, con số sẽ
 * nộp hiện tới đó. Ba thông tin luôn tách bạch, không gộp:
 *   1. frame_idx tại vị trí đang tua — số sẽ nộp nếu chốt ngay bây giờ
 *   2. Nguồn của con số: đo trực tiếp / đúng keyframe / nội suy (khi nghi VFR)
 *   3. Keyframe gần nhất và độ lệch — để tự quyết nộp số đo tay hay số keyframe
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ChevronLeft, ChevronRight, Copy, Layers, Pin, Plus, Search, SkipBack, SkipForward, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { api, frameAtUrl, frameUrl, thumbUrl, videoUrl } from "../../api/client";
import { Button, Label, Pop, TextInput, copyToClipboard, cx } from "../../components/ui";
import { useSession } from "../../stores/sessionStore";
import { useSubmission } from "../../stores/submissionStore";
import { useUi } from "../../stores/uiStore";
import { formatTimecode, useFrameIndex } from "./useFrameIndex";

type StripMode = "keyframe" | "1s" | "5s";

/** Gắn MỘT LẦN ở App.tsx (không đặt trong SearchPage nữa) — dùng chung cho mọi
 *  trang (Search/Temporal đều gọi openDetail(hit, hits) trước khi mở). Trước
 *  đây modal chỉ được mount trong SearchPage nên bấm vào khung hình ở Temporal
 *  không hiện gì cả — đây là lý do sửa. */
export function DetailOverlay() {
  const hit = useUi((s) => s.detail);
  const hits = useUi((s) => s.detailHits);
  const trake = useUi((s) => s.detailTrake);
  const setTrakeActiveEvent = useUi((s) => s.setDetailTrakeActiveEvent);
  const pickTrakeFrame = useUi((s) => s.pickDetailTrakeFrame);
  const openDetail = useUi((s) => s.openDetail);
  const openWorkbench = useUi((s) => s.openWorkbench);
  const detailReturnToCsv = useUi((s) => s.detailReturnToCsv);
  const setDetailReturnToCsv = useUi((s) => s.setDetailReturnToCsv);
  const setCsvPreviewOpen = useUi((s) => s.setCsvPreviewOpen);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stripMode, setStripMode] = useState<StripMode>("keyframe");
  const [lookupFrameIdx, setLookupFrameIdx] = useState("");
  const [otherVideo, setOtherVideo] = useState("");
  const [otherFrameIdx, setOtherFrameIdx] = useState("");

  const session = useSession((s) => s.sessions[s.activeId]);
  const patch = useSession((s) => s.patch);
  const togglePin = useSession((s) => s.togglePin);
  const files = useSubmission((s) => s.files);
  const activeName = useSubmission((s) => s.activeName);
  const addRow = useSubmission((s) => s.addRow);

  const { data: map } = useQuery({
    queryKey: ["map", hit?.video],
    queryFn: ({ signal }) => api.videoMap(hit!.video, signal),
    enabled: !!hit,
    staleTime: Infinity,
  });

  const { data: nearbyAsr } = useQuery({
    queryKey: ["asr-window", hit?.video, hit?.pts_time,
               session.asr.window_before, session.asr.window_after],
    queryFn: ({ signal }) => api.asrWindow(
      hit!.video, hit!.pts_time!, session.asr.window_before, session.asr.window_after, signal),
    enabled: !!hit && hit.pts_time != null && !hit.content?.asr_window?.length,
    staleTime: Infinity,
    retry: 0,
  });
  const asrWindow = hit?.content?.asr_window?.length
    ? hit.content.asr_window : nearbyAsr?.segments ?? [];

  const { reading, stepFrames, seekTo } = useFrameIndex(videoRef, map);

  const lookup = useMutation({
    mutationFn: () => api.lookupFrame(hit!.video, Number(lookupFrameIdx)),
    onSuccess: (found) => openDetail(found, [found]),
    onError: (error: Error) => toast.error(error.message || "Không tra được khung hình này"),
  });
  const otherLookup = useMutation({
    mutationFn: () => api.lookupFrame(otherVideo.trim(), otherFrameIdx.trim() ? Number(otherFrameIdx) : 1),
    onSuccess: (found) => openDetail(found, [found]),
    onError: (error: Error) => toast.error(error.message || "Không tra được khung hình này"),
  });

  const idx = useMemo(() => hits.findIndex((h) => h.id === hit?.id), [hits, hit]);
  const go = (d: number) => {
    const n = idx + d;
    if (n >= 0 && n < hits.length) openDetail(hits[n]);
  };
  const closeDetail = (returnToCsv = false) => {
    openDetail(null);
    if (returnToCsv && detailReturnToCsv) setCsvPreviewOpen(true);
    setDetailReturnToCsv(false);
  };

  // Nhảy tới đúng mốc thời gian của khung hình khi mở / đổi khung.
  useEffect(() => {
    const el = videoRef.current;
    if (el && hit?.pts_time != null) el.currentTime = hit.pts_time;
  }, [hit?.id, hit?.pts_time]);

  useEffect(() => {
    if (!hit) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "Escape") closeDetail(true);
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
      else if (e.key === ",") { e.preventDefault(); stepFrames(-1); }
      else if (e.key === ".") { e.preventDefault(); stepFrames(1); }
      else if (e.key === "j") { e.preventDefault(); seekTo((videoRef.current?.currentTime ?? 0) - 1); }
      else if (e.key === "l") { e.preventDefault(); seekTo((videoRef.current?.currentTime ?? 0) + 1); }
      else if (e.key === " ") {
        e.preventDefault();
        const el = videoRef.current;
        if (el) el.paused ? el.play() : el.pause();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hit, idx, hits, openDetail, stepFrames, seekTo, detailReturnToCsv]);

  const strip = useMemo(() => {
    if (!hit || !map) return [];
    if (stripMode === "keyframe") {
      const center = map.rows.findIndex((r) => r.n === hit.n);
      const from = Math.max(0, center - 8);
      return map.rows.slice(from, from + 17).map((r) => ({
        key: `k${r.n}`, t: r.pts_time, url: thumbUrl(hit.video, r.n),
        label: `f${r.frame_idx}`, isKeyframe: true,
      }));
    }
    const step = stripMode === "1s" ? 1 : 5;
    const base = reading.mediaTime;
    return Array.from({ length: 13 }, (_, i) => {
      const t = Math.max(0, base + (i - 6) * step);
      return { key: `t${t.toFixed(2)}`, t, url: frameAtUrl(hit.video, t),
               label: formatTimecode(t).slice(0, 5), isKeyframe: false };
    });
  }, [hit, map, stripMode, reading.mediaTime]);

  if (!hit) return null;

  const activeFile = activeName ? files[activeName] : null;
  const copyFrame = async () => {
    const ok = await copyToClipboard(String(reading.frameIdx));
    if (ok) toast.success(`Đã chép ${reading.frameIdx}`);
    else toast.error("Trình duyệt chặn chép tự động ở kết nối không an toàn (http qua IP) — tự bôi đen số rồi Ctrl+C.");
  };
  const addToDraft = () => {
    if (!activeFile) { toast.error("Chưa chọn file nộp bài — mở tab Nộp bài để tạo."); return; }
    addRow(activeFile.name, {
      video: hit.video,
      frames: [String(reading.frameIdx),
               ...Array(Math.max(0, (activeFile.kind === "trake" ? activeFile.nEvents : 1) - 1)).fill("")],
    });
    toast.success(`Đã thêm ${hit.video} · ${reading.frameIdx} vào ${activeFile.name}.csv`);
  };

  const srcLabel = { measured: "ĐANG TUA", keyframe: "KEYFRAME", interpolated: "NỘI SUY" }[reading.source];

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-[var(--color-bg)]">
      <div className="flex shrink-0 items-center gap-3 border-b border-[var(--color-line)] px-3 py-2">
        <span className="font-mono text-[13px]">{hit.video}</span>
        <span className="font-mono text-[11px] tabular-nums text-[var(--color-fg-mute)]">
          {map ? `${map.fps.toFixed(2)} fps · ${formatTimecode(map.duration ?? 0)}` : "…"}
        </span>
        <span className="text-[11px] text-[var(--color-fg-mute)]">
          {idx + 1}/{hits.length} · ←→ đổi khung · , . lùi/tiến 1 khung · Space phát
        </span>
        <div className="ml-auto flex items-center gap-1">
          <Button size="sm" variant="ghost" onClick={() => go(-1)} disabled={idx <= 0}>
            <ChevronLeft size={13} />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => go(1)} disabled={idx >= hits.length - 1}>
            <ChevronRight size={13} />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => { openWorkbench(hit.video); closeDetail(); }}>
            <Layers size={12} /> Mở cả video
          </Button>
          <Pop width={250} align="end" trigger={
            <Button size="sm" variant="default" title="Tra khung của video bất kỳ">
              <Search size={12} /> Tra khung
            </Button>
          }>
            <Label className="mb-1.5">Tra khung video khác</Label>
            <div className="flex flex-col gap-1.5">
              <TextInput value={otherVideo} onChange={(e) => setOtherVideo(e.target.value.trim())}
                         placeholder="L21_V001" className="font-mono text-[12px]"
                         onKeyDown={(e) => e.key === "Enter" && otherVideo && otherLookup.mutate()} />
              <TextInput value={otherFrameIdx} inputMode="numeric"
                         onChange={(e) => setOtherFrameIdx(e.target.value.replace(/\D/g, ""))}
                         placeholder="frame_idx (bỏ trống = 1)" className="font-mono text-[12px]"
                         onKeyDown={(e) => e.key === "Enter" && otherVideo && otherLookup.mutate()} />
              <Button size="sm" variant="primary" onClick={() => otherLookup.mutate()}
                      disabled={!otherVideo || otherLookup.isPending}>
                <Search size={11} /> {otherLookup.isPending ? "Đang tra…" : "Mở khung"}
              </Button>
            </div>
          </Pop>
          <Button size="sm" variant="ghost" onClick={() => closeDetail(true)} aria-label="Đóng">
            <X size={14} />
          </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1 items-center justify-center bg-black p-2">
            <video ref={videoRef} src={videoUrl(hit.video)} controls preload="metadata"
                   className="max-h-full max-w-full" />
          </div>

          <div className="shrink-0 border-t border-[var(--color-line)] px-3 py-2">
            <div className="mb-1.5 flex items-center gap-2">
              <span className="label-xs">Dải khung hình</span>
              {(["keyframe", "1s", "5s"] as StripMode[]).map((m) => (
                <button key={m} type="button" onClick={() => setStripMode(m)}
                        className={cx("rounded-[2px] px-1.5 py-0.5 text-[10.5px]",
                          stripMode === m ? "bg-[var(--color-panel-3)] text-[var(--color-fg)]"
                                          : "text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]")}>
                  {m === "keyframe" ? "Theo keyframe" : `Mỗi ${m}`}
                </button>
              ))}
              {stripMode !== "keyframe" && (
                <span className="text-[10.5px] text-[var(--color-fg-mute)]">
                  Trích trực tiếp từ video — thấy được cả khoảnh khắc nằm giữa hai keyframe
                </span>
              )}
            </div>
            <div className="flex gap-1 overflow-x-auto pb-1">
              {strip.map((f) => {
                const on = Math.abs(f.t - reading.mediaTime) < 0.35;
                return (
                  <button key={f.key} type="button" onClick={() => seekTo(f.t)}
                          className={cx("shrink-0 rounded-[2px] border transition-all",
                            on ? "border-[var(--color-focus)] opacity-100"
                               : "border-transparent opacity-55 hover:opacity-90")}>
                    <img src={f.url} alt="" loading="lazy" className="h-[54px] w-[96px] bg-black object-cover" />
                    <div className="font-mono text-[9px] tabular-nums text-[var(--color-fg-mute)]">{f.label}</div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Rail phải: đồng hồ frame_idx + nội dung khung hình */}
        <div className="flex w-[330px] shrink-0 flex-col gap-3 overflow-y-auto border-l border-[var(--color-line)] p-3">
          <div className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-panel-2)] p-3">
            <div className="label-xs mb-1">frame_idx — số sẽ nộp</div>
            <div className="font-mono text-[30px] font-semibold leading-none tabular-nums tracking-wider">
              {reading.frameIdx}
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <span className="font-mono text-[11px] tabular-nums text-[var(--color-fg-dim)]">
                {formatTimecode(reading.mediaTime)}
              </span>
              <span className={cx("rounded-[2px] px-1 py-[1px] text-[9.5px] font-semibold",
                reading.source === "keyframe"
                  ? "bg-[color-mix(in_srgb,var(--color-ok)_20%,transparent)] text-[var(--color-ok)]"
                  : reading.source === "interpolated"
                    ? "bg-[color-mix(in_srgb,var(--color-warn)_20%,transparent)] text-[var(--color-warn)]"
                    : "bg-[var(--color-panel-3)] text-[var(--color-fg-dim)]")}>
                {srcLabel}
              </span>
            </div>

            {reading.nearestKeyframe && (
              <div className="mt-1 font-mono text-[10.5px] tabular-nums text-[var(--color-fg-mute)]">
                Keyframe gần nhất: n={reading.nearestKeyframe.n} → {reading.nearestKeyframe.frame_idx}
                {reading.deltaToNearest !== 0 &&
                  ` (${reading.deltaToNearest > 0 ? "+" : ""}${reading.deltaToNearest})`}
              </div>
            )}
            {reading.vfrWarning && (
              <div className="mt-1.5 rounded-[2px] bg-[color-mix(in_srgb,var(--color-warn)_14%,transparent)] px-1.5 py-1 text-[10px] leading-snug text-[var(--color-warn)]">
                Video này có vẻ không đều tốc độ khung. Đang nội suy từ hai keyframe
                đo thật thay vì nhân theo fps. Nếu nghi ngờ, nộp số của keyframe.
              </div>
            )}

            <div className="mt-2 flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => stepFrames(-10)} title="Lùi 10 khung">
                <SkipBack size={11} />10
              </Button>
              <Button size="sm" variant="ghost" onClick={() => stepFrames(-1)} title="Lùi 1 khung (,)">−1</Button>
              <Button size="sm" variant="ghost" onClick={() => stepFrames(1)} title="Tiến 1 khung (.)">+1</Button>
              <Button size="sm" variant="ghost" onClick={() => stepFrames(10)} title="Tiến 10 khung">
                10<SkipForward size={11} />
              </Button>
            </div>

            <div className="mt-2 border-t border-[var(--color-line)] pt-2">
              <div className="mb-1 text-[10.5px] font-medium text-[var(--color-focus)]">
                Tra khung trong video này
              </div>
              <div className="flex gap-1">
                <TextInput value={lookupFrameIdx} inputMode="numeric" placeholder="frame_idx"
                           onChange={(e) => setLookupFrameIdx(e.target.value.replace(/\D/g, ""))}
                           onKeyDown={(e) => e.key === "Enter" && lookupFrameIdx && lookup.mutate()}
                           className="min-w-0 flex-1 px-2 py-1 font-mono text-[11px]" />
                <Button size="sm" variant="primary" onClick={() => lookup.mutate()}
                        disabled={!lookupFrameIdx || lookup.isPending}>
                  <Search size={11} /> Tra
                </Button>
              </div>
            </div>

            {trake ? (
              <div className="mt-2 flex flex-col gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-focus)] bg-[color-mix(in_srgb,var(--color-focus)_8%,transparent)] p-2">
                <div className="text-[10.5px] leading-snug text-[var(--color-fg-dim)]">
                  Tua tới đúng khung rồi bấm gán — chuyển sự kiện, tua tiếp, gán
                  tiếp, KHÔNG cần thoát ra mở lại.
                </div>
                <div className="flex flex-wrap gap-1">
                  {Array.from({ length: trake.nEvents }, (_, i) => (
                    <button key={i} type="button" onClick={() => setTrakeActiveEvent(i)}
                            className={cx("rounded-[2px] border px-1.5 py-0.5 font-mono text-[10.5px] tabular-nums",
                              trake.activeEvent === i
                                ? "border-[var(--color-focus)] bg-[color-mix(in_srgb,var(--color-focus)_18%,transparent)] text-[var(--color-focus)]"
                                : trake.picks[i] != null
                                  ? "border-[var(--color-ok)] text-[var(--color-ok)]"
                                  : "border-[var(--color-line)] text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]")}>
                      E{i + 1} {trake.picks[i] != null ? `· f${trake.picks[i]}` : "· chưa chọn"}
                    </button>
                  ))}
                </div>
                <Button size="sm" variant="primary" onClick={() => pickTrakeFrame(reading.frameIdx)}>
                  <Plus size={11} /> Gán khung này (f{reading.frameIdx}) cho E{trake.activeEvent + 1}
                </Button>
                <Button size="sm" variant="ghost" disabled={trake.picks.some((p) => p == null)}
                        onClick={() => { trake.onSubmit(trake.picks as number[]); openDetail(null); }}>
                  Nộp {trake.nEvents} khung vào bản nháp
                </Button>
              </div>
            ) : (
              <div className="mt-2 flex flex-col gap-1">
                <Button size="sm" onClick={copyFrame}><Copy size={11} /> Chép frame_idx</Button>
                <Button size="sm" variant="primary" onClick={addToDraft}>
                  <Plus size={11} /> Điền vào {activeFile ? `${activeFile.name}.csv` : "bản nháp"}
                </Button>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" className="flex-1"
                          onClick={() => togglePin({ id: hit.id, video: hit.video, n: hit.n,
                                                     frame_idx: hit.frame_idx, pts_time: hit.pts_time })}>
                    <Pin size={11} /> Ghim
                  </Button>
                  <Button size="sm" variant="ghost" className="flex-1"
                          onClick={() => {
                            patch({ refVideo: hit.video, refN: hit.n, refImageB64: null,
                                    enabled: { ...session.enabled, dinov3: true } });
                            toast.success("Đã đặt làm ảnh mẫu");
                          }}>
                    <Search size={11} /> Ảnh mẫu
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <div>
              <div className="label-xs mb-0.5">Ảnh keyframe gốc</div>
              <img src={frameUrl(hit.video, hit.n)} alt=""
                   className="w-full rounded-[var(--radius-sm)] border border-[var(--color-line)]" />
            </div>

            {hit.content?.ocr && (
              <div>
                <div className="label-xs mb-0.5" style={{ color: "var(--color-sig-ocr)" }}>Chữ trên hình</div>
                <p className="whitespace-pre-wrap text-[11.5px] leading-snug text-[var(--color-fg-dim)]">
                  {hit.content.ocr}
                </p>
              </div>
            )}
            {hit.content?.caption && (
              <div>
                <div className="label-xs mb-0.5" style={{ color: "var(--color-sig-capemb)" }}>Mô tả cảnh</div>
                <p className="text-[11.5px] leading-snug text-[var(--color-fg-dim)]">{hit.content.caption}</p>
              </div>
            )}
            {hit.content?.objects && (
              <div>
                <div className="label-xs mb-0.5" style={{ color: "var(--color-sig-object)" }}>Vật thể nhận diện</div>
                <p className="font-mono text-[11px] leading-snug text-[var(--color-fg-dim)]">{hit.content.objects}</p>
              </div>
            )}
            {!!asrWindow.length && (
              <div>
                <div className="label-xs mb-0.5" style={{ color: "var(--color-sig-asr)" }}>Lời thoại quanh đây</div>
                <div className="flex flex-col gap-0.5">
                  {asrWindow.map((s, i) => (
                    <button key={i} type="button" onClick={() => seekTo(s.t)}
                            className="text-left text-[11px] leading-snug text-[var(--color-fg-dim)] hover:text-[var(--color-fg)]">
                      <span className="font-mono tabular-nums text-[var(--color-fg-mute)]">
                        {formatTimecode(s.t).slice(0, 5)}
                      </span>{" "}
                      {s.text}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
