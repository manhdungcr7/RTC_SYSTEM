/**
 * PHIÊN LÀM VIỆC — mỗi CÂU HỎI của gói đề là một phiên độc lập.
 *
 * Vì sao cần: trong lúc thi, người dùng nhảy qua lại giữa nhiều câu hỏi. Nếu
 * trạng thái truy vấn là toàn cục thì chuyển câu là mất sạch (câu chữ, trọng số
 * đã tinh chỉnh, danh sách ghim, ghi chú "đã thử gì rồi"). Mỗi phiên giữ TOÀN BỘ
 * ngữ cảnh của một câu hỏi để quay lại là tiếp tục được ngay.
 *
 * Lưu bền xuống localStorage: mất trạng thái giữa vòng thi là thảm hoạ, và F5
 * hay treo trình duyệt là chuyện có thật.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

import { DEFAULT_WEIGHTS } from "../types/api";
import type {
  AsrConfig, ClauseConfig, FrameRef, ObjectCond, OcrConfig, QueryKind,
} from "../types/api";

export interface PinnedFrame {
  id: string;
  video: string;
  n: number;
  frame_idx: number;
  pts_time: number | null;
  note: string;
}

export interface SessionState {
  id: string;
  label: string;
  kind: QueryKind;
  liveQuestionId?: string;

  query: string;
  autoSplit: boolean;         // false = KHÔNG tự tách mệnh đề/mở rộng câu, dùng nguyên câu gốc
  clauses: ClauseConfig[];
  clausesDirty: boolean;      // true = người dùng đã sửa tay, không ghi đè bằng LLM nữa
  alpha: number;

  translations: Record<number, string>;
  translationsDirty: boolean;

  weights: Record<string, number>;
  enabled: Record<string, boolean>;

  ocr: OcrConfig;
  asr: AsrConfig;
  objects: ObjectCond[];
  negative: { text: string; weight: number; hardThreshold: number | null };

  scopeVideos: string[];
  scopeInvert: boolean;

  refImageB64: string | null;
  refVideo: string | null;
  refN: number | null;

  feedbackPos: FrameRef[];
  feedbackNeg: FrameRef[];
  feedbackBeta: number;
  feedbackGamma: number;

  perVideoCap: number;
  dedupSeconds: number;
  topk: number;
  rrfK: number;

  pins: PinnedFrame[];
  notes: string;
}

const DEFAULT_ENABLED: Record<string, boolean> = {
  // Mặc định bật các nhánh thị giác đã có sẵn tín hiệu từ câu chữ. OCR/ASR/object
  // TẮT vì chúng chỉ có nghĩa khi người dùng tự gõ vào (nguyên tắc: không đoán hộ).
  metaclip2: true, pecore: true, beit3: true, capemb: true,
  asr_emb: false, dinov3: false, ocr: false, asr: false, object: false,
};

export function makeSession(id: string, label?: string): SessionState {
  return {
    id,
    label: label ?? id,
    kind: "kis",
    query: "",
    autoSplit: true,
    clauses: [],
    clausesDirty: false,
    alpha: 0.3,
    translations: {},
    translationsDirty: false,
    weights: { ...DEFAULT_WEIGHTS },
    enabled: { ...DEFAULT_ENABLED },
    ocr: { query: "", mode: "score" },
    asr: { query: "", lexical: true, semantic: true, mode: "score",
           window_before: 3, window_after: 5 },
    objects: [],
    negative: { text: "", weight: 0.45, hardThreshold: null },
    scopeVideos: [],
    scopeInvert: false,
    refImageB64: null,
    refVideo: null,
    refN: null,
    feedbackPos: [],
    feedbackNeg: [],
    feedbackBeta: 0.6,
    feedbackGamma: 0.3,
    perVideoCap: 5,
    dedupSeconds: 0,
    topk: 200,
    rrfK: 60,
    pins: [],
    notes: "",
  };
}

interface Store {
  sessions: Record<string, SessionState>;
  order: string[];
  activeId: string;

  addSession: (label?: string) => string;
  removeSession: (id: string) => void;
  setActive: (id: string) => void;
  renameSession: (id: string, label: string) => void;
  patch: (patch: Partial<SessionState>) => void;
  patchOf: (id: string, patch: Partial<SessionState>) => void;
  resetToDefault: () => void;

  togglePin: (f: Omit<PinnedFrame, "note">) => void;
  setPinNote: (id: string, note: string) => void;
  reorderPins: (from: number, to: number) => void;
  clearPins: () => void;

  markGood: (f: FrameRef) => void;
  markBad: (f: FrameRef) => void;
  clearFeedback: () => void;
}

const sameRef = (a: FrameRef, b: FrameRef) => a.video === b.video && a.n === b.n;

export const useSession = create<Store>()(
  persist(
    (set, get) => {
      const first = makeSession("q01");
      return {
        sessions: { q01: first },
        order: ["q01"],
        activeId: "q01",

        addSession: (label) => {
          const n = get().order.length + 1;
          let id = `q${String(n).padStart(2, "0")}`;
          while (get().sessions[id]) id = `${id}_`;
          set((s) => ({
            sessions: { ...s.sessions, [id]: makeSession(id, label) },
            order: [...s.order, id],
            activeId: id,
          }));
          return id;
        },

        removeSession: (id) =>
          set((s) => {
            if (s.order.length <= 1) return s;            // luôn còn ít nhất 1 phiên
            const { [id]: _drop, ...rest } = s.sessions;
            const order = s.order.filter((x) => x !== id);
            return {
              sessions: rest,
              order,
              activeId: s.activeId === id ? order[0] : s.activeId,
            };
          }),

        setActive: (id) => set({ activeId: id }),

        renameSession: (id, label) =>
          set((s) => ({ sessions: { ...s.sessions, [id]: { ...s.sessions[id], label } } })),

        patch: (patch) =>
          set((s) => ({
            sessions: {
              ...s.sessions,
              [s.activeId]: { ...s.sessions[s.activeId], ...patch },
            },
          })),

        patchOf: (id, patch) =>
          set((s) => ({ sessions: { ...s.sessions, [id]: { ...s.sessions[id], ...patch } } })),

        // "Mặc định" — không CHỈ đưa trọng số về số đã đo sẵn, mà đưa cả bàn
        // trộn về đúng trạng thái BAN ĐẦU: OCR/ASR tắt hẳn + xoá chữ đã gõ
        // (2 nhánh này vốn chỉ nên chạy khi người dùng CHỦ Ý gõ, để sót lại
        // chữ cũ mà tưởng đã "mặc định" dễ gây nhầm), và bỏ giới hạn "Thu hẹp
        // video" (về lại tìm trên TOÀN BỘ kho, không phải phạm vi lần trước).
        resetToDefault: () =>
          set((s) => {
            const cur = s.sessions[s.activeId];
            return {
              sessions: {
                ...s.sessions,
                [s.activeId]: {
                  ...cur,
                  weights: { ...DEFAULT_WEIGHTS },
                  enabled: { ...DEFAULT_ENABLED },
                  ocr: { query: "", mode: "score" },
                  asr: { query: "", lexical: true, semantic: true, mode: "score",
                         window_before: 3, window_after: 5 },
                  scopeVideos: [],
                  scopeInvert: false,
                },
              },
            };
          }),

        togglePin: (f) =>
          set((s) => {
            const cur = s.sessions[s.activeId];
            const exists = cur.pins.some((p) => p.id === f.id);
            const pins = exists
              ? cur.pins.filter((p) => p.id !== f.id)
              : [...cur.pins, { ...f, note: "" }];
            return { sessions: { ...s.sessions, [s.activeId]: { ...cur, pins } } };
          }),

        setPinNote: (id, note) =>
          set((s) => {
            const cur = s.sessions[s.activeId];
            return {
              sessions: {
                ...s.sessions,
                [s.activeId]: {
                  ...cur,
                  pins: cur.pins.map((p) => (p.id === id ? { ...p, note } : p)),
                },
              },
            };
          }),

        reorderPins: (from, to) =>
          set((s) => {
            const cur = s.sessions[s.activeId];
            const pins = [...cur.pins];
            const [m] = pins.splice(from, 1);
            pins.splice(to, 0, m);
            return { sessions: { ...s.sessions, [s.activeId]: { ...cur, pins } } };
          }),

        clearPins: () =>
          set((s) => ({
            sessions: { ...s.sessions, [s.activeId]: { ...s.sessions[s.activeId], pins: [] } },
          })),

        // Phản hồi liên quan: đánh dấu ✓ tự gỡ khỏi ✗ và ngược lại; bấm lại = bỏ đánh dấu.
        markGood: (f) =>
          set((s) => {
            const cur = s.sessions[s.activeId];
            const has = cur.feedbackPos.some((x) => sameRef(x, f));
            return {
              sessions: {
                ...s.sessions,
                [s.activeId]: {
                  ...cur,
                  feedbackPos: has
                    ? cur.feedbackPos.filter((x) => !sameRef(x, f))
                    : [...cur.feedbackPos, f],
                  feedbackNeg: cur.feedbackNeg.filter((x) => !sameRef(x, f)),
                },
              },
            };
          }),

        markBad: (f) =>
          set((s) => {
            const cur = s.sessions[s.activeId];
            const has = cur.feedbackNeg.some((x) => sameRef(x, f));
            return {
              sessions: {
                ...s.sessions,
                [s.activeId]: {
                  ...cur,
                  feedbackNeg: has
                    ? cur.feedbackNeg.filter((x) => !sameRef(x, f))
                    : [...cur.feedbackNeg, f],
                  feedbackPos: cur.feedbackPos.filter((x) => !sameRef(x, f)),
                },
              },
            };
          }),

        clearFeedback: () =>
          set((s) => ({
            sessions: {
              ...s.sessions,
              [s.activeId]: { ...s.sessions[s.activeId], feedbackPos: [], feedbackNeg: [] },
            },
          })),
      };
    },
    { name: "aic-sessions", version: 1 },
  ),
);

/** Phiên đang mở. Dùng selector nguyên tử ở component để tránh render thừa. */
export const useActiveSession = () => useSession((s) => s.sessions[s.activeId]);
export const useSessionPatch = () => useSession((s) => s.patch);
