/** TRAKE — tìm CHUỖI N khung hình đúng thứ tự thời gian trong cùng một video.
 *
 *  Đòn bẩy thủ công đặc thù của màn hình này:
 *   - Neo thị giác chọn tay: mặc định lấy sự kiện đầu + cuối, nhưng cặp Ở GIỮA
 *     thường đặc trưng hơn (vd "4 chân chạm đất" dễ nhận hơn "lân xoay trên cột").
 *   - Ghi đè chữ/lời riêng cho TỪNG sự kiện — khi cả chuỗi nhìn giống nhau,
 *     chữ trên banner mới là thứ phân biệt được.
 *   - KHÔNG phạt khoảng cách thời gian giữa các sự kiện (luôn tắt — không giả
 *     định các sự kiện phải gần nhau, xem api/routers/temporal.py).
 *   - Bàn trộn trọng số 4 nhánh thị giác (metaclip2/pecore/beit3/capemb) — CHỈ
 *     đổi cách CHẤM ĐIỂM từng khung hình, không đụng thuật toán DP/boundary-
 *     anchor phía sau (xem core/temporal.py).
 */
import { useMutation } from "@tanstack/react-query";
import {
  Anchor, ArrowLeftRight, ChevronDown, Loader2, Lock, Plus, Search, Trash2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api, thumbUrl } from "../api/client";
import { Button, EmptyState, Label, Pop, Section, TextArea, TextInput, cx } from "../components/ui";
import { TemporalMixerStrip } from "../features/search/SignalMixer";
import { VideoScopePanel } from "../features/search/ScopePanels";
import type { VideoScopeValue } from "../features/search/ScopePanels";
import { formatTimecode } from "../features/viewer/useFrameIndex";
import { framesPerRow, useSubmission } from "../stores/submissionStore";
import { useUi } from "../stores/uiStore";
import { DEFAULT_WEIGHTS, TEMPORAL_BRANCHES } from "../types/api";
import type { SearchHit, TemporalCandidate } from "../types/api";

interface EventRow {
  text: string;
  ocr: string;
  asr: string;
  anchor: boolean;
  /** frame_idx người dùng đã tự tìm ra và chắc chắn đúng — ép thuật toán đi qua
   *  đúng khung này, chỉ còn phải tìm các sự kiện còn lại quanh nó. */
  locked: string;
}

const newEvent = (): EventRow => ({ text: "", ocr: "", asr: "", anchor: false, locked: "" });

type WeightState = Record<string, { enabled: boolean; weight: number }>;
// Nhánh THỊ GIÁC — trộn vào vector sự kiện trước khi so khớp.
const VISUAL_BRANCHES = TEMPORAL_BRANCHES;
// Nhánh CHỮ/LỜI — cộng điểm OCR/ASR (câu nhập riêng từng sự kiện ở trên) vào DP.
// Mặc định BẬT vì OCR/ASR trước giờ vẫn luôn được thử ngầm — giờ chỉ lộ ra để
// tự tắt/chỉnh khi thấy nó kéo lệch kết quả (xem api/routers/temporal.py).
const TEXT_BRANCHES = ["ocr", "asr"] as const;
const initialWeights: WeightState = {
  metaclip2: { enabled: true, weight: 1.0 },
  pecore: { enabled: false, weight: DEFAULT_WEIGHTS.pecore },
  beit3: { enabled: false, weight: DEFAULT_WEIGHTS.beit3 },
  capemb: { enabled: false, weight: DEFAULT_WEIGHTS.capemb },
  ocr: { enabled: true, weight: DEFAULT_WEIGHTS.ocr },
  asr: { enabled: true, weight: DEFAULT_WEIGHTS.asr },
};

export function TemporalPage() {
  const [context, setContext] = useState("");
  const [events, setEvents] = useState<EventRow[]>([
    { ...newEvent(), anchor: true }, { ...newEvent(), anchor: true },
  ]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [perEvent, setPerEvent] = useState(1500);
  const [weights, setWeights] = useState<WeightState>(initialWeights);
  const [scope, setScope] = useState<VideoScopeValue>({ videos: [], invert: false });
  // Khung người dùng đã tự đổi, theo khoá "chỉ-số-ứng-viên-chỉ-số-sự-kiện".
  const [swaps, setSwaps] = useState<Record<string, SearchHit>>({});
  const openDetail = useUi((s) => s.openDetail);
  const openWorkbench = useUi((s) => s.openWorkbench);

  const files = useSubmission((s) => s.files);
  const activeName = useSubmission((s) => s.activeName);
  const addRow = useSubmission((s) => s.addRow);

  const setEv = (i: number, u: Partial<EventRow>) =>
    setEvents((p) => p.map((e, k) => (k === i ? { ...e, ...u } : e)));

  const toggleAnchor = (i: number) =>
    setEvents((p) => {
      const cur = p[i].anchor;
      const count = p.filter((e) => e.anchor).length;
      if (!cur && count >= 2) {
        // Giữ tối đa 2 neo — bỏ neo cũ nhất rồi thêm neo mới.
        const firstAnchor = p.findIndex((e) => e.anchor);
        return p.map((e, k) =>
          k === firstAnchor ? { ...e, anchor: false } : k === i ? { ...e, anchor: true } : e);
      }
      return p.map((e, k) => (k === i ? { ...e, anchor: !cur } : e));
    });

  const search = useMutation({
    mutationFn: async () => {
      const valid = events.map((e, i) => ({ e, i })).filter(({ e }) => e.text.trim());
      if (valid.length < 2) throw new Error("Cần ít nhất 2 sự kiện.");
      const anchors = valid.map(({ e }, k) => (e.anchor ? k : -1)).filter((k) => k >= 0);
      const signals = Object.fromEntries(
        [...VISUAL_BRANCHES, ...TEXT_BRANCHES].map(
          (b) => [b, { enabled: weights[b].enabled, weight: weights[b].weight }]));
      return api.temporal({
        events: valid.map(({ e }) => e.text),
        context: context.trim() || undefined,
        ocr_queries: valid.map(({ e }) => e.ocr),
        asr_queries: valid.map(({ e }) => e.asr),
        anchor_indices: anchors.length === 2 ? anchors : null,
        per_event: perEvent,
        topk: 50,
        locked_frames: valid.map(({ e }) => (e.locked.trim() ? Number(e.locked) : null)),
        alternates_per_event: 5,
        signals,
        video_scope: scope.videos.length ? scope.videos : null,
      });
    },
    onSuccess: () => setSwaps({}),
    onError: (e: Error) => toast.error(e.message),
  });

  const nEvents = events.filter((e) => e.text.trim()).length;

  const addChain = (c: TemporalCandidate, ci: number) => {
    const f = activeName ? files[activeName] : null;
    if (!f) { toast.error("Chưa chọn file nộp bài — mở tab Nộp bài ở trang Tìm khung hình."); return; }
    if (f.kind !== "trake") { toast.error(`File ${f.name} không phải loại TRAKE.`); return; }
    const want = framesPerRow(f);
    // Lấy khung ĐANG HIỂN THỊ (đã tính cả những khung người dùng tự đổi tay).
    const frames = c.hits
      .map((h, k) => String((swaps[`${ci}-${k}`] ?? h).frame_idx))
      .slice(0, want);
    while (frames.length < want) frames.push("");
    addRow(f.name, { video: c.video, frames });
    toast.success(`Đã thêm chuỗi ${c.video} vào ${f.name}.csv`);
  };

  return (
    <div className="flex min-h-0 flex-1">
      <aside className="flex w-[368px] shrink-0 flex-col overflow-y-auto border-r border-[var(--color-line)] bg-[var(--color-panel)]">
        <div className="border-b border-[var(--color-line)] p-3">
          <Label>Bối cảnh chung (tuỳ chọn)</Label>
          <TextArea
            value={context} onChange={(e) => setContext(e.target.value)}
            placeholder="vd: đoạn video múa lân, một con lân màu vàng đen trắng…"
            rows={2} className="mb-2 text-[12px]"
          />
          <p className="mb-3 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
            Được chèn vào TRƯỚC mỗi sự kiện khi mã hoá — giúp các nhánh thị giác
            "thấy" bối cảnh chung (màu sắc, chủ thể) mà một câu sự kiện ngắn
            không nhắc lại. Không ảnh hưởng thuật toán dò chuỗi phía sau.
          </p>

          <div className="mb-2 flex items-center justify-between">
            <Label className="mb-0">Chuỗi sự kiện theo thứ tự thời gian</Label>
            <span className="font-mono text-[10.5px] tabular-nums text-[var(--color-fg-mute)]">
              N = {nEvents}
            </span>
          </div>

          <p className="mb-2 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
            <Anchor size={9} className="inline" /> = neo thị giác. Chọn đúng 2 sự kiện
            DỄ NHẬN DIỆN nhất — không nhất thiết là đầu và cuối.
          </p>

          <div className="flex flex-col gap-2">
            {events.map((ev, i) => (
              <div key={i} className="flex flex-col gap-1">
                <div className="flex items-center gap-1">
                  <span className="flex h-5 w-6 shrink-0 items-center justify-center rounded-[2px] bg-[var(--color-panel-3)] font-mono text-[10px] text-[var(--color-focus)]">
                    E{i + 1}
                  </span>
                  <TextInput value={ev.text} onChange={(e) => setEv(i, { text: e.target.value })}
                             placeholder={`Sự kiện ${i + 1}…`} className="flex-1 py-1 text-[12px]" />
                  <button type="button" onClick={() => toggleAnchor(i)}
                          title="Dùng sự kiện này làm neo thị giác"
                          aria-pressed={ev.anchor}
                          className={cx("shrink-0 rounded-[2px] border p-1 transition-colors",
                            ev.anchor
                              ? "border-[var(--color-focus)] text-[var(--color-focus)]"
                              : "border-[var(--color-line)] text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]")}>
                    <Anchor size={11} />
                  </button>
                  {events.length > 2 && (
                    <button type="button" onClick={() => setEvents((p) => p.filter((_, k) => k !== i))}
                            aria-label="Xoá sự kiện"
                            className="shrink-0 p-1 text-[var(--color-fg-mute)] hover:text-[var(--color-err)]">
                      <Trash2 size={11} />
                    </button>
                  )}
                </div>
                {showAdvanced && (
                  <div className="ml-7 flex flex-col gap-1">
                    <div className="flex gap-1">
                      <TextInput value={ev.ocr} onChange={(e) => setEv(i, { ocr: e.target.value })}
                                 placeholder="chữ riêng cho sự kiện này"
                                 className="flex-1 py-0.5 text-[11px]" />
                      <TextInput value={ev.asr} onChange={(e) => setEv(i, { asr: e.target.value })}
                                 placeholder="lời riêng"
                                 className="flex-1 py-0.5 text-[11px]" />
                    </div>
                    <div className="flex items-center gap-1">
                      <Lock size={10} className={cx("shrink-0",
                        ev.locked.trim() ? "text-[var(--color-pin)]" : "text-[var(--color-fg-mute)]")} />
                      <TextInput value={ev.locked} inputMode="numeric"
                                 onChange={(e) => setEv(i, { locked: e.target.value.replace(/\D/g, "") })}
                                 placeholder="đã biết chắc frame_idx? khoá lại"
                                 className="flex-1 py-0.5 font-mono text-[11px]" />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="mt-2 flex items-center gap-1">
            <Button size="sm" variant="ghost" onClick={() => setEvents((p) => [...p, newEvent()])}>
              <Plus size={11} /> Thêm sự kiện
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowAdvanced((v) => !v)}>
              <ChevronDown size={11} className={cx(!showAdvanced && "-rotate-90")} />
              Chữ/lời riêng
            </Button>
          </div>

          <Button variant="primary" className="mt-2 w-full"
                  onClick={() => search.mutate()} disabled={search.isPending || nEvents < 2}>
            {search.isPending ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
            {search.isPending ? "Đang tìm chuỗi…" : "Tìm chuỗi sự kiện"}
          </Button>
        </div>

        <Section title="Bàn trộn tín hiệu">
          <p className="mb-2 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
            Chỉ đổi cách CHẤM ĐIỂM từng khung hình — thuật toán dò chuỗi (DP,
            neo biên) giữ nguyên. metaclip2 luôn là nhánh chính; bật thêm nhánh
            phụ khi câu mô tả chi tiết mà thị giác thuần chưa phân biệt được.
          </p>
          <div className="flex flex-col gap-0.5">
            {VISUAL_BRANCHES.map((b) => (
              <TemporalMixerStrip key={b} branchKey={b}
                value={weights[b]}
                onChange={(v) => setWeights((p) => ({ ...p, [b]: v }))} />
            ))}
          </div>

          <div className="my-1.5 border-t border-dashed border-[var(--color-line)]" />
          <div className="mb-0.5 label-xs">Chữ/lời — chấm điểm theo ô "chữ riêng"/"lời riêng" của từng sự kiện</div>
          <div className="flex flex-col gap-0.5">
            {TEXT_BRANCHES.map((b) => (
              <TemporalMixerStrip key={b} branchKey={b}
                value={weights[b]}
                onChange={(v) => setWeights((p) => ({ ...p, [b]: v }))} />
            ))}
          </div>
        </Section>

        <Section title="Thu hẹp video" defaultOpen={false}>
          <VideoScopePanel value={scope} onChange={setScope} />
        </Section>

        <Section title="Nâng cao" defaultOpen={false}>
          <p className="mb-2 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
            Các sự kiện KHÔNG bị ép phải gần nhau về thời gian — hệ thống không
            còn phạt khoảng cách giữa các sự kiện (luôn tắt).
          </p>
          <div className="flex items-center gap-2">
            <span className="w-[110px] text-[11px] text-[var(--color-fg-dim)]">Video ứng viên/neo</span>
            <input type="range" min={300} max={3000} step={100} value={perEvent}
                   onChange={(e) => setPerEvent(Number(e.target.value))}
                   className="h-1 flex-1 accent-[var(--color-focus)]" />
            <span className="w-[36px] text-right font-mono text-[11px] tabular-nums">{perEvent}</span>
          </div>
        </Section>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        {search.isPending ? (
          <EmptyState title="Đang dò chuỗi sự kiện…"
                      hint="Đang lọc video ứng viên theo neo thị giác rồi dò thứ tự thời gian trong từng video." />
        ) : !search.data ? (
          <EmptyState
            title="Nhập ít nhất 2 sự kiện rồi bấm Tìm"
            hint="Mô tả từng khoảnh khắc theo đúng thứ tự xảy ra. Nếu các cảnh nhìn giống nhau, mở phần Chữ/lời riêng để phân biệt bằng chữ trên màn hình."
          />
        ) : search.data.candidates.length === 0 ? (
          <EmptyState
            title="Không tìm được chuỗi nào"
            hint="Thử đổi cặp neo thị giác sang hai sự kiện dễ nhận diện hơn, tăng số video ứng viên, hoặc bỏ giới hạn phạm vi video."
          />
        ) : (
          <div className="flex flex-col gap-2 p-3">
            {search.data.candidates.map((c, i) => {
              const weakest = Math.min(...c.hits.map((h) => h.score));
              // Danh sách cho ←/→ khi mở khung chi tiết — toàn bộ khung của
              // CHUỖI này theo đúng thứ tự E1..En (đã tính khung đã đổi tay).
              const navList = c.hits.map((h, k) => swaps[`${i}-${k}`] ?? h);
              return (
                <div key={`${c.video}-${i}`}
                     className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-panel)] p-2">
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="font-mono text-[11px] tabular-nums text-[var(--color-fg-mute)]">#{i + 1}</span>
                    <span className="font-mono text-[12px]">{c.video}</span>
                    <span className="font-mono text-[11px] tabular-nums text-[var(--color-fg-dim)]">
                      tổng {c.total_score.toFixed(3)}
                    </span>
                    <div className="ml-auto flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => openWorkbench(c.video)}>
                        Mở cả video
                      </Button>
                      <Button size="sm" onClick={() => addChain(c, i)}>Đưa vào bản nháp</Button>
                    </div>
                  </div>
                  <div className="flex gap-1.5 overflow-x-auto pb-1">
                    {c.hits.map((h, k) => {
                      const weak = h.score <= weakest + 1e-9 && c.hits.length > 1;
                      const chosen = swaps[`${i}-${k}`] ?? h;
                      const alts = h.alternates ?? [];
                      return (
                        <div key={k} className="shrink-0">
                          <button type="button" onClick={() => openDetail(chosen, navList)}
                                  className={cx("block rounded-[var(--radius-sm)] border transition-colors",
                                    weak ? "border-[var(--color-warn)]"
                                         : "border-[var(--color-line)] hover:border-[var(--color-focus)]")}>
                            <img src={thumbUrl(chosen.video, chosen.n)} alt="" loading="lazy"
                                 className="h-[80px] w-[142px] bg-black object-cover" />
                            <div className="px-1 py-0.5 text-left">
                              <div className="font-mono text-[9.5px] text-[var(--color-focus)]">E{k + 1}</div>
                              <div className="font-mono text-[9.5px] tabular-nums text-[var(--color-fg-mute)]">
                                f{chosen.frame_idx} · {formatTimecode(chosen.pts_time ?? 0).slice(0, 5)}
                              </div>
                              <div className={cx("font-mono text-[9.5px] tabular-nums",
                                weak ? "text-[var(--color-warn)]" : "text-[var(--color-fg-mute)]")}>
                                {chosen.score.toFixed(3)}{weak && " ← yếu nhất"}
                              </div>
                            </div>
                          </button>
                          {alts.length > 0 && (
                            <Pop width={230} trigger={
                              <button type="button"
                                      className="mt-0.5 w-full rounded-[2px] border border-[var(--color-line)] py-0.5 text-[9.5px] text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]">
                                <ArrowLeftRight size={9} className="inline" /> đổi khung ({alts.length})
                              </button>
                            }>
                              <div className="mb-1 text-[10.5px] text-[var(--color-fg-dim)]">
                                Khung thay thế cho E{k + 1} — vẫn giữ đúng thứ tự thời gian
                              </div>
                              <div className="grid grid-cols-2 gap-1">
                                {[h, ...alts].map((alt) => (
                                  <button key={alt.id} type="button"
                                          onClick={() => setSwaps((p) => ({ ...p, [`${i}-${k}`]: alt }))}
                                          className={cx("rounded-[2px] border",
                                            chosen.id === alt.id
                                              ? "border-[var(--color-focus)]"
                                              : "border-[var(--color-line)] hover:border-[var(--color-line-hi)]")}>
                                    <img src={thumbUrl(alt.video, alt.n)} alt="" loading="lazy"
                                         className="h-[48px] w-full bg-black object-cover" />
                                    <div className="font-mono text-[9px] tabular-nums text-[var(--color-fg-mute)]">
                                      f{alt.frame_idx} · {alt.score.toFixed(2)}
                                    </div>
                                  </button>
                                ))}
                              </div>
                            </Pop>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
