/** TRAKE — tìm CHUỖI N khung hình đúng thứ tự thời gian trong cùng một video.
 *
 *  Đòn bẩy thủ công đặc thù của màn hình này:
 *   - Neo thị giác chọn tay: mặc định lấy sự kiện đầu + cuối, nhưng cặp Ở GIỮA
 *     thường đặc trưng hơn (vd "4 chân chạm đất" dễ nhận hơn "lân xoay trên cột").
 *   - Ghi đè chữ/lời riêng cho TỪNG sự kiện — khi cả chuỗi nhìn giống nhau,
 *     chữ trên banner mới là thứ phân biệt được.
 *   - KHÔNG phạt mềm khoảng cách thời gian; có thể đặt giới hạn cứng để tránh
 *     ghép các phóng sự khác nhau trong cùng video dài.
 *   - Bàn trộn trọng số 4 nhánh thị giác (metaclip2/pecore/beit3/capemb) — CHỈ
 *     đổi cách CHẤM ĐIỂM từng khung hình, không đụng thuật toán DP/boundary-
 *     anchor phía sau (xem core/temporal.py).
 */
import { useMutation } from "@tanstack/react-query";
import {
  Anchor, CheckSquare, ChevronDown, FileJson, Loader2, Lock, Plus, Search, ThumbsDown, ThumbsUp, Trash2, X,
} from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { api, thumbUrl } from "../api/client";
import { Button, EmptyState, Label, ResizeHandle, Section, TextArea, TextInput, cx } from "../components/ui";
import { Inspector } from "../features/inspector/Inspector";
import { TemporalMixerStrip } from "../features/search/SignalMixer";
import { VideoScopePanel } from "../features/search/ScopePanels";
import type { VideoScopeValue } from "../features/search/ScopePanels";
import { QueryPlanImportModal } from "../features/search/QueryPlanImportModal";
import { temporalEventsFromPlan } from "../features/search/temporalQueryPlan";
import { VideoListDownload } from "../features/results/VideoListDownload";
import { SubmitPanel } from "../features/submission/SubmitPanel";
import { formatTimecode } from "../features/viewer/useFrameIndex";
import { framesPerRow, useSubmission } from "../stores/submissionStore";
import { useUi } from "../stores/uiStore";
import { DEFAULT_WEIGHTS, TEMPORAL_BRANCHES } from "../types/api";
import type { FeedbackConfig, FrameRef, SearchHit, TemporalCandidate, VisualQueryPlan } from "../types/api";

interface EventRow {
  text: string;
  translation: string;
  ocr: string;
  asr: string;
  anchor: boolean;
  /** frame_idx người dùng đã tự tìm ra và chắc chắn đúng — ép thuật toán đi qua
   *  đúng khung này, chỉ còn phải tìm các sự kiện còn lại quanh nó. */
  locked: string;
  /** Mệnh đề TỰ VIẾT, thay cho tách tự động — rỗng = vẫn tách tự động (mặc định). */
  clausesOverride: string[];
}

const newEvent = (): EventRow => ({ text: "", translation: "", ocr: "", asr: "", anchor: false, locked: "", clausesOverride: [] });

type WeightState = Record<string, { enabled: boolean; weight: number }>;
// Nhánh THỊ GIÁC — trộn vào vector sự kiện trước khi so khớp.
const VISUAL_BRANCHES = TEMPORAL_BRANCHES;
// Nhánh CHỮ/LỜI — cộng điểm OCR/ASR (câu nhập riêng từng sự kiện ở trên) vào DP.
// Mặc định TẮT — cùng nguyên tắc với Tìm khung hình (xem DEFAULT_ENABLED ở
// sessionStore.ts): chỉ nên chạy khi người dùng CHỦ Ý gõ chữ/lời riêng cho sự
// kiện, không đoán hộ khi ô đó còn trống.
const TEXT_BRANCHES = ["ocr", "asr"] as const;
const initialWeights: WeightState = {
  metaclip2: { enabled: true, weight: 1.0 },
  pecore: { enabled: true, weight: DEFAULT_WEIGHTS.pecore },
  beit3: { enabled: true, weight: DEFAULT_WEIGHTS.beit3 },
  capemb: { enabled: true, weight: DEFAULT_WEIGHTS.capemb },
  ocr: { enabled: false, weight: DEFAULT_WEIGHTS.ocr },
  asr: { enabled: false, weight: DEFAULT_WEIGHTS.asr },
  object: { enabled: false, weight: DEFAULT_WEIGHTS.object },
  
};

export function TemporalPage() {
  const [sourceQuery, setSourceQuery] = useState("");
  const [planOpen, setPlanOpen] = useState(false);
  const [context, setContext] = useState("");
  const [events, setEvents] = useState<EventRow[]>([
    { ...newEvent(), anchor: true }, { ...newEvent(), anchor: true },
  ]);
  const [autoSplit, setAutoSplit] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [perEvent, setPerEvent] = useState(1500);
  const [maxGapS, setMaxGapS] = useState(120);
  const [weights, setWeights] = useState<WeightState>(initialWeights);
  const [scope, setScope] = useState<VideoScopeValue>({ videos: [], invert: false });
  // Khung người dùng đã tự đổi, theo khoá "chỉ-số-ứng-viên-chỉ-số-sự-kiện".
  const [swaps, setSwaps] = useState<Record<string, SearchHit>>({});
  const [selectMode, setSelectMode] = useState(false);
  const [selectedFrames, setSelectedFrames] = useState<string[]>([]);
  const [selectionAnswer, setSelectionAnswer] = useState("");
  const [dragBox, setDragBox] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const selectionAreaRef = useRef<HTMLDivElement>(null);
  const candidateRangeStartRef = useRef<number | null>(null);
  // Phản hồi liên quan (✓/✗) RIÊNG từng sự kiện — key = chỉ số sự kiện. KHÔNG
  // reset khi tìm lại (khác `swaps`) vì đây chính là thứ người dùng muốn giữ
  // qua nhiều lượt tìm để dịch dần vector về đúng hướng.
  const [feedback, setFeedback] = useState<Record<number, { positive: FrameRef[]; negative: FrameRef[] }>>({});
  const openDetail = useUi((s) => s.openDetail);
  const openWorkbench = useUi((s) => s.openWorkbench);
  const detail = useUi((s) => s.detail);
  const leftWidth = useUi((s) => s.leftWidth);
  const rightOpen = useUi((s) => s.rightOpen);
  const rightWidth = useUi((s) => s.rightWidth);
  const setLeftWidth = useUi((s) => s.setLeftWidth);
  const setRightWidth = useUi((s) => s.setRightWidth);

  const markFeedback = (eventIdx: number, ref: FrameRef, kind: "positive" | "negative") =>
    setFeedback((p) => {
      const cur = p[eventIdx] ?? { positive: [], negative: [] };
      const same = (r: FrameRef) => r.video === ref.video && r.n === ref.n;
      const already = cur[kind].some(same);
      const next = {
        positive: kind === "positive" && !already ? [...cur.positive, ref] : cur.positive.filter((r) => !same(r)),
        negative: kind === "negative" && !already ? [...cur.negative, ref] : cur.negative.filter((r) => !same(r)),
      };
      return { ...p, [eventIdx]: next };
    });

  const feedbackCount = Object.values(feedback)
    .reduce((n, f) => n + f.positive.length + f.negative.length, 0);

  const files = useSubmission((s) => s.files);
  const activeName = useSubmission((s) => s.activeName);
  const addRow = useSubmission((s) => s.addRow);
  const activeFile = activeName ? files[activeName] : null;

  const setEv = (i: number, u: Partial<EventRow>) =>
    setEvents((p) => p.map((e, k) => (k === i ? { ...e, ...u } : e)));

  const pasteEventChain = (text: string) => {
    const markers = [...text.matchAll(/(?:^|\r?\n)\s*E\d+\s*:\s*/gi)];
    if (markers.length < 2) return false;
    const parsed = markers.map((marker, i) =>
      text.slice((marker.index ?? 0) + marker[0].length, markers[i + 1]?.index ?? text.length).trim());
    setEvents(parsed.map((event, i) => ({
      ...newEvent(), text: event, anchor: i === 0 || i === parsed.length - 1,
    })));
    return true;
  };

  const applyPlan = (plan: VisualQueryPlan) => {
    if (plan.events.length < 2) {
      toast.error("Kế hoạch chỉ có một sự kiện; hãy dùng nó ở trang Tìm khung hình.");
      return;
    }
    const planned = temporalEventsFromPlan(plan).map((event) => ({
      ...newEvent(),
      ...event,
    }));
    const hasOcr = planned.some((event) => event.ocr.trim());
    const hasAsr = planned.some((event) => event.asr.trim());
    setSourceQuery(plan.original_query || sourceQuery);
    setContext(plan.context.vi || plan.context.en);
    setEvents(planned);
    setAutoSplit(false);
    setMaxGapS(plan.max_gap_s ?? 120);
    setShowAdvanced(hasOcr || hasAsr || planned.some((event) => event.translation));
    setWeights((previous) => ({
      ...previous,
      ocr: { ...previous.ocr, enabled: hasOcr },
      asr: { ...previous.asr, enabled: hasAsr },
    }));
    setFeedback({});
    setSwaps({});
  };

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
      // Chỉ số sự kiện đổi khi có sự kiện rỗng bị lọc (valid.map) — remap phản
      // hồi theo chỉ số MỚI (khớp đúng thứ tự events gửi lên backend).
      const feedbackPayload: Record<number, FeedbackConfig> = {};
      valid.forEach(({ i }, newIdx) => {
        const f = feedback[i];
        if (f && (f.positive.length || f.negative.length))
          feedbackPayload[newIdx] = { positive: f.positive, negative: f.negative, beta: 0.6, gamma: 0.3 };
      });
      const clausesOverridePayload: Record<number, string[]> = {};
      valid.forEach(({ e }, newIdx) => {
        if (e.clausesOverride.length) clausesOverridePayload[newIdx] = e.clausesOverride;
      });
      return api.temporal({
        events: valid.map(({ e }) => e.text),
        context: context.trim() || undefined,
        split_clauses: autoSplit,
        ocr_queries: valid.map(({ e }) => e.ocr),
        asr_queries: valid.map(({ e }) => e.asr),
        event_translations: valid.map(({ e }) => e.translation),
        anchor_indices: anchors.length === 2 ? anchors : null,
        per_event: perEvent,
        max_gap_s: maxGapS > 0 ? maxGapS : null,
        topk: 50,
        locked_frames: valid.map(({ e }) => (e.locked.trim() ? Number(e.locked) : null)),
        alternates_per_event: 5,
        signals,
        video_scope: scope.videos.length ? scope.videos : null,
        feedback: Object.keys(feedbackPayload).length ? feedbackPayload : undefined,
        clauses_override: Object.keys(clausesOverridePayload).length ? clausesOverridePayload : undefined,
      });
    },
    onSuccess: () => setSwaps({}),
    onError: (e: Error) => toast.error(e.message),
  });

  const nEvents = events.filter((e) => e.text.trim()).length;
  // event_clauses trả về đánh số theo danh sách ĐÃ LỌC bỏ ô rỗng gửi lên backend
  // (xem `valid` trong search.mutate ở trên) — map lại về đúng chỉ số ô đang
  // hiển thị. Nếu bạn đổi ô nào rỗng/không-rỗng sau lần tìm gần nhất thì mapping
  // này có thể lệch — chấp nhận được vì chỉ ảnh hưởng hiển thị tham khảo, không
  // ảnh hưởng lần tìm tiếp theo (backend luôn tính lại đúng theo ô hiện tại).
  const filledIdxs = events.map((e, i) => (e.text.trim() ? i : -1)).filter((i) => i >= 0);
  const clausesFor = (i: number) => {
    const pos = filledIdxs.indexOf(i);
    return pos >= 0 ? search.data?.event_clauses?.[pos] : undefined;
  };

  // k = chỉ số trong c.hits (đã lọc bỏ ô rỗng, khớp thứ tự request vừa gửi) ->
  // đổi về chỉ số Ô GỐC trên UI để feedback gắn đúng với event input tương ứng
  // (xem `filledIdxs` — cùng phép map dùng để hiển thị mệnh đề đã tách).
  const markFromResult = (k: number, ref: FrameRef, kind: "positive" | "negative") => {
    const origIdx = filledIdxs[k];
    if (origIdx == null) return;
    markFeedback(origIdx, ref, kind);
  };

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

  const addSelectedFrames = () => {
    const f = activeFile;
    if (!f) { toast.error("Chưa chọn file nộp bài — mở tab Nộp bài để tạo/chọn."); return; }
    const chosen = selectedFrames.flatMap((key) => {
      const [ci, k] = key.split("-").map(Number);
      const candidate = search.data?.candidates[ci];
      const hit = candidate ? (swaps[key] ?? candidate.hits[k]) : null;
      return hit ? [hit] : [];
    });
    if (f.kind === "trake") {
      const byVideo = new Map<string, SearchHit[]>();
      chosen.forEach((h) => byVideo.set(h.video, [...(byVideo.get(h.video) ?? []), h]));
      for (const [video, hits] of byVideo) {
        for (let i = 0; i < hits.length; i += f.nEvents) {
          const frames = hits.slice(i, i + f.nEvents).map((h) => String(h.frame_idx));
          while (frames.length < f.nEvents) frames.push("");
          addRow(f.name, { video, frames });
        }
      }
    } else {
      chosen.forEach((h) => addRow(f.name, {
        video: h.video,
        frames: [String(h.frame_idx)],
        answer: f.kind === "qa" ? selectionAnswer : "",
      }));
    }
    toast.success(`Đã thêm ${chosen.length} khung vào ${f.name}.csv`);
    setSelectedFrames([]);
    candidateRangeStartRef.current = null;
    if (f.kind === "qa") setSelectionAnswer("");
  };

  const selectCandidate = (candidateIdx: number, shiftKey: boolean) => {
    const candidates = search.data?.candidates ?? [];
    const keysFor = (ci: number) => candidates[ci]?.hits.map((_, k) => `${ci}-${k}`) ?? [];
    if (shiftKey) {
      if (candidateRangeStartRef.current != null) {
        const [lo, hi] = candidateRangeStartRef.current <= candidateIdx
          ? [candidateRangeStartRef.current, candidateIdx]
          : [candidateIdx, candidateRangeStartRef.current];
        const rangeKeys = candidates.slice(lo, hi + 1)
          .flatMap((c, offset) => c.hits.map((_, k) => `${lo + offset}-${k}`));
        setSelectedFrames((p) => [...p, ...rangeKeys.filter((key) => !p.includes(key))]);
        candidateRangeStartRef.current = null;
        return;
      }
      setSelectedFrames((p) => [...p, ...keysFor(candidateIdx).filter((key) => !p.includes(key))]);
      candidateRangeStartRef.current = candidateIdx;
      return;
    }
    const keys = keysFor(candidateIdx);
    setSelectedFrames((p) => keys.every((key) => p.includes(key))
      ? p.filter((key) => !keys.includes(key))
      : [...p, ...keys.filter((key) => !p.includes(key))]);
    candidateRangeStartRef.current = null;
  };

  const startSelectDrag = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!selectMode || e.target !== e.currentTarget) return;
    e.preventDefault();
    const start = { x0: e.clientX, y0: e.clientY, x1: e.clientX, y1: e.clientY };
    setDragBox(start);
    const onMove = (ev: MouseEvent) => setDragBox((p) => p ? { ...p, x1: ev.clientX, y1: ev.clientY } : p);
    const onUp = (ev: MouseEvent) => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      const left = Math.min(start.x0, ev.clientX), right = Math.max(start.x0, ev.clientX);
      const top = Math.min(start.y0, ev.clientY), bottom = Math.max(start.y0, ev.clientY);
      const ids = new Set<string>();
      selectionAreaRef.current?.querySelectorAll<HTMLElement>("[data-temporal-select]").forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.left < right && r.right > left && r.top < bottom && r.bottom > top)
          ids.add(el.dataset.temporalSelect!);
      });
      const ordered = search.data?.candidates.flatMap((c, ci) => c.hits.map((_, k) => `${ci}-${k}`)) ?? [];
      setSelectedFrames((p) => [...p, ...ordered.filter((id) => ids.has(id) && !p.includes(id))]);
      setDragBox(null);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  // Mở khung xem chi tiết THẬT (video tua được, đồng hồ frame_idx) — giống hệt
  // bấm vào 1 kết quả bình thường — CỘNG THÊM bộ chọn sự kiện: tua tới đâu,
  // bấm gán tới đó, đổi tab sự kiện, tua tiếp, KHÔNG phải thoát ra mở lại cho
  // từng sự kiện (thay cho "đổi khung"/"xem video chọn khung" cũ). Khởi động ở
  // đúng sự kiện người dùng vừa bấm vào để sửa, khung gợi ý hiện tại làm điểm
  // xuất phát cho video (mở đúng ngay tại đó).
  const openTrakePicker = (ci: number, c: TemporalCandidate, startEvent: number) => {
    const chosenHits = c.hits.map((h, k) => swaps[`${ci}-${k}`] ?? h);
    const initialPicks = chosenHits.map((h) => h.frame_idx);
    openDetail(chosenHits[startEvent], [chosenHits[startEvent]], {
      nEvents: c.hits.length,
      initialPicks,
      activeEvent: startEvent,
      onSubmit: (frames) => {
        const f = activeName ? files[activeName] : null;
        if (!f) { toast.error("Chưa chọn file nộp bài — mở tab Nộp bài ở trang Tìm khung hình."); return; }
        if (f.kind !== "trake") { toast.error(`File ${f.name} không phải loại TRAKE.`); return; }
        const want = framesPerRow(f);
        const rowFrames = frames.map(String).slice(0, want);
        while (rowFrames.length < want) rowFrames.push("");
        addRow(f.name, { video: c.video, frames: rowFrames });
        toast.success(`Đã thêm chuỗi ${c.video} vào ${f.name}.csv`);
      },
    });
  };

  return (
    <div className="flex min-h-0 flex-1">
      <aside style={{ width: leftWidth }}
             className="flex shrink-0 flex-col overflow-y-auto border-r border-[var(--color-line)] bg-[var(--color-panel)]">
        <div className="border-b border-[var(--color-line)] p-3">
          <Label>Đề bài gốc</Label>
          <TextArea
            value={sourceQuery}
            onChange={(e) => setSourceQuery(e.target.value)}
            rows={3}
            placeholder="Dán nguyên mô tả của BTC, sau đó gửi cho GPT Explore để tạo kế hoạch…"
            className="mb-2 text-[12px]"
          />
          <Button size="sm" variant="primary" className="mb-3" onClick={() => setPlanOpen(true)}>
            <FileJson size={11} /> Nhập kế hoạch GPT
          </Button>

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

          <label className="mb-2 flex items-center gap-1.5 text-[11px] text-[var(--color-fg-dim)]">
            <input type="checkbox" checked={autoSplit}
                   onChange={(e) => setAutoSplit(e.target.checked)}
                   className="h-3 w-3 accent-[var(--color-focus)]" />
            Tự động tách mệnh đề (LLM) cho sự kiện chưa tự sửa
          </label>
          {!autoSplit && (
            <p className="-mt-1 mb-2 text-[10px] leading-snug text-[var(--color-warn)]">
              Đang TẮT — mỗi sự kiện chưa bấm "✎ Tự sửa" sẽ encode NGUYÊN câu,
              không gọi LLM tách mệnh đề. Sự kiện đã tự sửa mệnh đề vẫn giữ
              nguyên bản tự viết, không bị ảnh hưởng bởi cờ này.
            </p>
          )}

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
                <div className="flex items-start gap-1">
                  <span className="mt-1 flex h-5 w-6 shrink-0 items-center justify-center rounded-[2px] bg-[var(--color-panel-3)] font-mono text-[10px] text-[var(--color-focus)]">
                    E{i + 1}
                  </span>
                  <TextArea rows={1} value={ev.text} onChange={(e) => setEv(i, { text: e.target.value })}
                            onPaste={(e) => {
                              if (pasteEventChain(e.clipboardData.getData("text"))) e.preventDefault();
                            }}
                            placeholder={`Sự kiện ${i + 1}…`} className="flex-1 py-1 text-[12px] leading-snug" />
                  <button type="button" onClick={() => toggleAnchor(i)}
                          title="Dùng sự kiện này làm neo thị giác"
                          aria-pressed={ev.anchor}
                          className={cx("mt-1 shrink-0 rounded-[2px] border p-1 transition-colors",
                            ev.anchor
                              ? "border-[var(--color-focus)] text-[var(--color-focus)]"
                              : "border-[var(--color-line)] text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]")}>
                    <Anchor size={11} />
                  </button>
                  {events.length > 2 && (
                    <button type="button" onClick={() => setEvents((p) => p.filter((_, k) => k !== i))}
                            aria-label="Xoá sự kiện"
                            className="mt-1 shrink-0 p-1 text-[var(--color-fg-mute)] hover:text-[var(--color-err)]">
                      <Trash2 size={11} />
                    </button>
                  )}
                </div>
                {showAdvanced && (
                  <div className="ml-7 flex flex-col gap-1">
                    <div className="flex gap-1">
                      <TextInput value={ev.translation}
                                 onChange={(e) => setEv(i, { translation: e.target.value })}
                                 placeholder="English cho PE-Core/BEiT-3"
                                 className="flex-1 py-0.5 text-[11px]" />
                    </div>
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
                {/* Mệnh đề dùng để mã hoá sự kiện này — mặc định tự tách (LLM),
                    xem được sau lần tìm gần nhất, và SỬA/THÊM/XOÁ tay được: bấm
                    "Tự sửa" để bắt đầu ghi đè, ghi đè thắng tách tự động cho
                    ĐÚNG sự kiện này ở lần tìm tiếp theo. */}
                {ev.clausesOverride.length > 0 ? (
                  <div className="ml-7 flex flex-col gap-1">
                    {ev.clausesOverride.map((c, ci) => (
                      <div key={ci} className="flex items-center gap-1">
                        <TextArea rows={1} value={c}
                                  onChange={(e) => setEv(i, {
                                    clausesOverride: ev.clausesOverride.map((x, k) => (k === ci ? e.target.value : x)),
                                  })}
                                  placeholder={`Mệnh đề ${ci + 1}`}
                                  className="flex-1 py-0.5 text-[11px] leading-snug" />
                        <button type="button"
                                onClick={() => setEv(i, { clausesOverride: ev.clausesOverride.filter((_, k) => k !== ci) })}
                                aria-label="Xoá mệnh đề"
                                className="shrink-0 p-0.5 text-[var(--color-fg-mute)] hover:text-[var(--color-err)]">
                          <X size={11} />
                        </button>
                      </div>
                    ))}
                    <div className="flex items-center gap-1">
                      <Button size="sm" variant="ghost"
                              onClick={() => setEv(i, { clausesOverride: [...ev.clausesOverride, ""] })}>
                        <Plus size={10} /> Thêm mệnh đề
                      </Button>
                      <Button size="sm" variant="ghost"
                              onClick={() => setEv(i, { clausesOverride: [] })}>
                        Khôi phục tự động
                      </Button>
                    </div>
                  </div>
                ) : (clausesFor(i)?.length ?? 0) > 0 && (
                  <div className="ml-7 flex flex-wrap items-center gap-1">
                    {clausesFor(i)!.map((c, ci) => (
                      <span key={ci}
                            className="rounded-full border border-[var(--color-line)] px-1.5 py-0.5 text-[9.5px] text-[var(--color-fg-mute)]">
                        {c}
                      </span>
                    ))}
                    <button type="button"
                            onClick={() => setEv(i, { clausesOverride: clausesFor(i)! })}
                            title="Tự sửa mệnh đề đã tách"
                            className="text-[9.5px] text-[var(--color-focus)] hover:underline">
                      ✎ Tự sửa
                    </button>
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

          {feedbackCount > 0 && (
            <div className="mt-1.5 flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-2 py-1">
              <span className="flex-1 text-[10.5px] text-[var(--color-fg-dim)]">
                <ThumbsUp size={10} className="mr-0.5 inline text-[var(--color-ok)]" />
                Đã đánh dấu {feedbackCount} khung — bấm "Tìm chuỗi sự kiện" để áp dụng
              </span>
              <button type="button" onClick={() => setFeedback({})}
                      title="Xoá hết phản hồi"
                      className="shrink-0 text-[var(--color-fg-mute)] hover:text-[var(--color-err)]">
                <X size={11} />
              </button>
            </div>
          )}
        </div>

        <Section title="Bàn trộn tín hiệu">
          <p className="mb-2 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
            Chỉ đổi cách CHẤM ĐIỂM từng khung hình — thuật toán dò chuỗi (DP,
            neo biên) giữ nguyên. metaclip2 luôn là nhánh chính; bật thêm nhánh
            phụ khi câu mô tả chi tiết mà thị giác thuần chưa phân biệt được.
          </p>
          <Button size="sm" variant="ghost" className="mb-1.5" onClick={() => setWeights(initialWeights)}
                  title="Trọng số về mặc định (MC2, PE, B3, CAP bật; các nhánh còn lại tắt)">
            Mặc định
          </Button>
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
            Hệ thống không phạt mềm khoảng cách; có thể đặt giới hạn cứng giữa
            hai sự kiện liền kề để tránh ghép nhầm các phóng sự khác nhau.
          </p>
          <div className="flex items-center gap-2">
            <span className="w-[110px] text-[11px] text-[var(--color-fg-dim)]">Top frame/sự kiện</span>
            <input type="range" min={300} max={3000} step={100} value={perEvent}
                   onChange={(e) => setPerEvent(Number(e.target.value))}
                   className="h-1 flex-1 accent-[var(--color-focus)]" />
            <span className="w-[36px] text-right font-mono text-[11px] tabular-nums">{perEvent}</span>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="w-[110px] text-[11px] text-[var(--color-fg-dim)]">Cách nhau tối đa</span>
            <input type="number" min={0} step={10} value={maxGapS}
                   onChange={(e) => setMaxGapS(Math.max(0, Number(e.target.value) || 0))}
                   className="min-w-0 flex-1 rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-2 py-1 text-[11px]" />
            <span className="w-[36px] text-right text-[11px] text-[var(--color-fg-mute)]">giây</span>
          </div>
          <p className="mt-1 text-[10px] leading-snug text-[var(--color-fg-mute)]">
            Đặt 0 để không giới hạn. Mặc định 120 giây giúp tránh ghép các phóng sự khác nhau trong cùng video dài.
          </p>
        </Section>
      </aside>
      <QueryPlanImportModal
        open={planOpen}
        onOpenChange={setPlanOpen}
        sourceQuery={sourceQuery}
        onApply={applyPlan}
      />
      <ResizeHandle side="left" width={leftWidth} onResize={setLeftWidth} />

      <main className="min-w-0 flex-1 overflow-y-auto">
        {search.isPending ? (
          <EmptyState title="Đang dò chuỗi sự kiện…"
                      hint="Đang gom video theo độ phủ của mọi sự kiện rồi dò thứ tự thời gian trong từng video." />
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
          <div ref={selectionAreaRef} className="flex flex-col gap-2 p-3">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <VideoListDownload videoIds={search.data.candidates.map((candidate) => candidate.video)} />
              <Button size="sm" variant="ghost"
                      onClick={() => {
                        setSelectMode((v) => !v);
                        candidateRangeStartRef.current = null;
                        if (selectMode) setSelectedFrames([]);
                      }}
                      className={selectMode ? "bg-[var(--color-focus)] text-[#0B1220]" : undefined}>
                {selectMode ? <X size={12} /> : <CheckSquare size={12} />}
                {selectMode ? "Hủy" : "Chọn"}
              </Button>
            </div>
            {search.data.candidates.map((c, i) => {
              const weakest = Math.min(...c.hits.map((h) => h.score));
              const candidateSelected = c.hits.every((_, k) => selectedFrames.includes(`${i}-${k}`));
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
                      {selectMode && (
                        <button type="button" onClick={(e) => selectCandidate(i, e.shiftKey)}
                                title={`Chọn cả ${c.hits.length} khung; giữ Shift và click hai cụm để chọn cả khoảng`}
                                className="flex items-center gap-1 rounded-[2px] px-1.5 py-1 text-[10.5px] text-[var(--color-fg-dim)] hover:bg-[var(--color-panel-2)]">
                          <input type="checkbox" checked={candidateSelected} readOnly
                                 className="pointer-events-none h-3 w-3 accent-[var(--color-focus)]" />
                          Chọn {c.hits.length}
                        </button>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => openWorkbench(c.video)}>
                        Mở cả video
                      </Button>
                      <Button size="sm" onClick={() => addChain(c, i)}>Đưa vào bản nháp</Button>
                    </div>
                  </div>
                  <div className="flex gap-1.5 overflow-x-auto pb-1" onMouseDown={startSelectDrag}>
                    {c.hits.map((h, k) => {
                      const selectKey = `${i}-${k}`;
                      const selectedOrder = selectedFrames.indexOf(selectKey);
                      const weak = h.score <= weakest + 1e-9 && c.hits.length > 1;
                      const chosen = swaps[`${i}-${k}`] ?? h;
                      const origIdx = filledIdxs[k];
                      const fb = origIdx != null ? feedback[origIdx] : undefined;
                      const isPos = fb?.positive.some((r) => r.video === chosen.video && r.n === chosen.n);
                      const isNeg = fb?.negative.some((r) => r.video === chosen.video && r.n === chosen.n);
                      return (
                        <div key={k} className="shrink-0" data-temporal-select={selectMode ? selectKey : undefined}>
                          <div className="relative">
                            <button type="button" onClick={() => selectMode
                                      ? setSelectedFrames((p) => p.includes(selectKey)
                                        ? p.filter((x) => x !== selectKey) : [...p, selectKey])
                                      : openTrakePicker(i, c, k)}
                                    title="Xem trọn video, tự chọn/tinh chỉnh khung cho sự kiện này rồi nộp"
                                    className={cx("block rounded-[var(--radius-sm)] border transition-colors",
                                      selectedOrder >= 0 ? "border-[var(--color-focus)] ring-1 ring-[var(--color-focus)]"
                                           : weak ? "border-[var(--color-warn)]"
                                           : "border-[var(--color-line)] hover:border-[var(--color-focus)]")}> 
                              <img src={thumbUrl(chosen.video, chosen.n)} alt="" loading="lazy"
                                   className="h-[80px] w-[142px] bg-black object-cover" />
                            </button>
                            {selectMode && selectedOrder >= 0 && (
                              <span className="absolute left-1 top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--color-focus)] px-1 font-mono text-[10px] font-semibold text-[#0B1220]">
                                {selectedOrder + 1}
                              </span>
                            )}
                            {!selectMode && <div className="absolute right-0.5 top-0.5 flex gap-0.5">
                              <button type="button"
                                      onClick={() => markFromResult(k, { video: chosen.video, n: chosen.n }, "positive")}
                                      title="Đúng sự kiện này — dịch vector tìm về hướng khung này"
                                      className={cx("rounded-[2px] border p-0.5 backdrop-blur-sm",
                                        isPos ? "border-[var(--color-ok)] bg-[var(--color-ok)] text-black"
                                              : "border-[var(--color-line)] bg-[color-mix(in_srgb,black_60%,transparent)] text-[var(--color-fg-mute)] hover:text-[var(--color-ok)]")}>
                                <ThumbsUp size={9} />
                              </button>
                              <button type="button"
                                      onClick={() => markFromResult(k, { video: chosen.video, n: chosen.n }, "negative")}
                                      title="Sai — dịch vector tìm ra xa khung này"
                                      className={cx("rounded-[2px] border p-0.5 backdrop-blur-sm",
                                        isNeg ? "border-[var(--color-err)] bg-[var(--color-err)] text-black"
                                              : "border-[var(--color-line)] bg-[color-mix(in_srgb,black_60%,transparent)] text-[var(--color-fg-mute)] hover:text-[var(--color-err)]")}>
                                <ThumbsDown size={9} />
                              </button>
                            </div>}
                          </div>
                          <button type="button" onClick={() => openTrakePicker(i, c, k)}
                                  className="block w-full text-left">
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
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
            {selectMode && selectedFrames.length > 0 && (
              <div className="fixed bottom-3 left-1/2 z-30 flex -translate-x-1/2 items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-3 py-2 shadow-2xl">
                <span className="font-mono text-[11.5px]">Đã chọn {selectedFrames.length} khung</span>
                {activeFile?.kind === "qa" && (
                  <TextInput value={selectionAnswer} onChange={(e) => setSelectionAnswer(e.target.value)}
                             placeholder="Nhập đáp án QA" className="w-[180px] py-1 text-[11px]" />
                )}
                <Button size="sm" variant="primary" onClick={addSelectedFrames}>Thêm vào bản nháp</Button>
                <Button size="sm" variant="ghost" onClick={() => {
                  setSelectedFrames([]);
                  candidateRangeStartRef.current = null;
                }}>Bỏ chọn hết</Button>
              </div>
            )}
            {dragBox && (
              <div className="pointer-events-none fixed z-40 border-2 border-[var(--color-focus)] bg-[color-mix(in_srgb,var(--color-focus)_15%,transparent)]"
                   style={{
                     left: Math.min(dragBox.x0, dragBox.x1), top: Math.min(dragBox.y0, dragBox.y1),
                     width: Math.abs(dragBox.x1 - dragBox.x0), height: Math.abs(dragBox.y1 - dragBox.y0),
                   }} />
            )}
          </div>
        )}
      </main>

      {/* Cột phải: tra cứu — DÙNG CHUNG với Search (cùng Inspector, cùng bản
          nháp nộp bài toàn cục) thay vì chỉ có ở Tìm khung hình như trước. */}
      {rightOpen && (
        <>
        <ResizeHandle side="right" width={rightWidth} onResize={setRightWidth} />
        <aside style={{ width: rightWidth }}
               className="shrink-0 border-l border-[var(--color-line)] bg-[var(--color-panel)]">
          <Inspector current={detail} submitPanel={<SubmitPanel />} />
        </aside>
        </>
      )}
    </div>
  );
}
