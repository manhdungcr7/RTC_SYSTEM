/** Trạng thái GIAO DIỆN thuần — không lưu bền (mở lại là về mặc định sạch).
 *  Tách khỏi sessionStore có chủ đích: cái gì thuộc về NỘI DUNG câu hỏi thì lưu
 *  bền, cái gì chỉ là "đang mở panel nào" thì không. */
import { create } from "zustand";

import type { SearchHit } from "../types/api";

export type InspectorTab = "explain" | "pins" | "submit" | "notes";
export type ResultView = "grid" | "byVideo" | "compare";

interface UiState {
  leftOpen: boolean;
  rightOpen: boolean;
  /** Bề rộng 2 cột 2 bên (px) — kéo được bằng thanh chia, DÙNG CHUNG cho cả
   *  Search lẫn Temporal (2 trang cùng bố cục 3 cột) nên đặt ở đây thay vì
   *  từng trang tự nhớ riêng. */
  leftWidth: number;
  rightWidth: number;
  inspectorTab: InspectorTab;

  /** Nhánh đang xem riêng ("" = xem kết quả đã gộp). */
  branchTab: string;
  resultView: ResultView;
  /** Cỡ ô trong lưới kết quả (px) — soi ảnh cần to, quét rộng cần nhỏ. */
  tileSize: number;

  /** Khung hình đang chọn bằng bàn phím (chỉ số trong danh sách kết quả). */
  cursor: number;
  /** Khung hình đang mở ở khung xem chi tiết. */
  detail: SearchHit | null;
  /** Danh sách khung hình dùng cho ←/→ khi khung chi tiết đang mở — mỗi trang
   *  (Search/Temporal) tự set trước khi gọi openDetail, để DetailOverlay dùng
   *  chung 1 chỗ mount ở App.tsx thay vì mỗi trang tự vẽ modal riêng (đây là lý
   *  do trước đây Temporal bấm vào khung hình không hiện gì — modal chỉ được
   *  mount trong SearchPage). */
  detailHits: SearchHit[];
  /** Khi khác null: khung xem chi tiết đang ở CHẾ ĐỘ GÁN CHUỖI TRAKE — cùng 1
   *  khung xem (video thật, tua được, đồng hồ frame_idx) như bấm vào 1 kết quả
   *  bình thường, CỘNG THÊM 1 bộ chọn sự kiện (E1..En): tua tới đâu, bấm "gán
   *  cho E{k}" tới đó, không phải thoát ra rồi mở lại cho từng sự kiện. Đủ N
   *  sự kiện thì `onSubmit` được gọi để đưa cả chuỗi vào bản nháp. */
  detailTrake: {
    nEvents: number;
    picks: (number | null)[];   // frame_idx đã gán cho mỗi sự kiện, null = chưa chọn
    activeEvent: number;        // chỉ số (0-based) sự kiện đang chờ gán
    onSubmit: (frames: number[]) => void;
  } | null;
  /** Video đang mở ở Workbench (xem toàn bộ keyframe/transcript/OCR 1 video). */
  workbenchVideo: string | null;
  /** Danh sách khung hình đang so sánh cạnh nhau (tối đa 4). */
  compare: SearchHit[];

  /** Chế độ CHỌN HÀNG LOẠT ở lưới kết quả — nộp nhiều ứng viên cùng lúc khi
   *  không chắc đáp án nào đúng (mỗi khung 1 dòng, thứ tự = độ tin cậy). Tick
   *  từng ô: thứ tự = thứ tự bấm. Kéo bôi đen 1 vùng: thứ tự = thứ tự hệ thống
   *  đã xếp hạng (không phải thứ tự chuột quét qua). */
  bulkMode: boolean;
  bulkSelection: string[];   // id khung hình, theo đúng thứ tự sẽ ghi ra dòng CSV

  connectionOpen: boolean;
  shortcutsOpen: boolean;
  paletteOpen: boolean;
  csvPreviewOpen: boolean;

  toggleLeft: () => void;
  toggleRight: () => void;
  setLeftWidth: (n: number) => void;
  setRightWidth: (n: number) => void;
  setInspectorTab: (t: InspectorTab) => void;
  setBranchTab: (b: string) => void;
  setResultView: (v: ResultView) => void;
  setTileSize: (n: number) => void;
  setCursor: (n: number) => void;
  moveCursor: (delta: number, max: number) => void;
  openDetail: (h: SearchHit | null, hits?: SearchHit[], trake?: {
    nEvents: number; initialPicks?: (number | null)[]; activeEvent?: number;
    onSubmit: (frames: number[]) => void;
  }) => void;
  openWorkbench: (v: string | null) => void;
  setDetailTrakeActiveEvent: (i: number) => void;
  pickDetailTrakeFrame: (frameIdx: number) => void;
  toggleCompare: (h: SearchHit) => void;
  clearCompare: () => void;
  setBulkMode: (b: boolean) => void;
  toggleBulkId: (id: string) => void;
  addBulkIds: (ids: string[]) => void;
  clearBulk: () => void;
  setConnectionOpen: (b: boolean) => void;
  setShortcutsOpen: (b: boolean) => void;
  setPaletteOpen: (b: boolean) => void;
  setCsvPreviewOpen: (b: boolean) => void;
}

export const useUi = create<UiState>((set) => ({
  leftOpen: true,
  rightOpen: true,
  leftWidth: 336,
  rightWidth: 366,
  inspectorTab: "explain",
  branchTab: "",
  resultView: "grid",
  tileSize: 190,
  cursor: -1,
  detail: null,
  detailHits: [],
  detailTrake: null,
  workbenchVideo: null,
  compare: [],
  bulkMode: false,
  bulkSelection: [],
  connectionOpen: false,
  shortcutsOpen: false,
  paletteOpen: false,
  csvPreviewOpen: false,

  toggleLeft: () => set((s) => ({ leftOpen: !s.leftOpen })),
  toggleRight: () => set((s) => ({ rightOpen: !s.rightOpen })),
  setLeftWidth: (n) => set({ leftWidth: Math.min(640, Math.max(260, n)) }),
  setRightWidth: (n) => set({ rightWidth: Math.min(640, Math.max(260, n)) }),
  setInspectorTab: (t) => set({ inspectorTab: t }),
  setBranchTab: (b) => set({ branchTab: b }),
  setResultView: (v) => set({ resultView: v }),
  setTileSize: (n) => set({ tileSize: Math.min(420, Math.max(110, n)) }),
  setCursor: (n) => set({ cursor: n }),
  moveCursor: (delta, max) =>
    set((s) => {
      if (max <= 0) return { cursor: -1 };
      const next = s.cursor < 0 ? 0 : s.cursor + delta;
      return { cursor: Math.min(max - 1, Math.max(0, next)) };
    }),
  openDetail: (h, hits, trake) => set((s) => ({
    detail: h,
    detailHits: hits ?? s.detailHits,
    detailTrake: h && trake
      ? {
          nEvents: trake.nEvents,
          picks: trake.initialPicks ?? Array(trake.nEvents).fill(null),
          activeEvent: trake.activeEvent ?? 0,
          onSubmit: trake.onSubmit,
        }
      : null,
  })),
  openWorkbench: (v) => set({ workbenchVideo: v }),
  setDetailTrakeActiveEvent: (i) =>
    set((s) => (s.detailTrake ? { detailTrake: { ...s.detailTrake, activeEvent: i } } : s)),
  pickDetailTrakeFrame: (frameIdx) =>
    set((s) => {
      if (!s.detailTrake) return s;
      const picks = [...s.detailTrake.picks];
      picks[s.detailTrake.activeEvent] = frameIdx;
      // Tự nhảy sang sự kiện kế tiếp CHƯA chọn để bớt thao tác chuyển tab tay.
      const next = picks.findIndex((p) => p == null);
      return {
        detailTrake: {
          ...s.detailTrake, picks,
          activeEvent: next >= 0 ? next : s.detailTrake.activeEvent,
        },
      };
    }),
  toggleCompare: (h) =>
    set((s) => {
      const has = s.compare.some((x) => x.id === h.id);
      if (has) return { compare: s.compare.filter((x) => x.id !== h.id) };
      return { compare: s.compare.length >= 4 ? s.compare : [...s.compare, h] };
    }),
  clearCompare: () => set({ compare: [] }),
  setBulkMode: (b) => set({ bulkMode: b, bulkSelection: b ? [] : [] }),
  toggleBulkId: (id) =>
    set((s) => ({
      bulkSelection: s.bulkSelection.includes(id)
        ? s.bulkSelection.filter((x) => x !== id)
        : [...s.bulkSelection, id],
    })),
  addBulkIds: (ids) =>
    set((s) => {
      const have = new Set(s.bulkSelection);
      const add = ids.filter((id) => !have.has(id));
      return add.length ? { bulkSelection: [...s.bulkSelection, ...add] } : s;
    }),
  clearBulk: () => set({ bulkSelection: [] }),
  setConnectionOpen: (b) => set({ connectionOpen: b }),
  setShortcutsOpen: (b) => set({ shortcutsOpen: b }),
  setPaletteOpen: (b) => set({ paletteOpen: b }),
  setCsvPreviewOpen: (b) => set({ csvPreviewOpen: b }),
}));
