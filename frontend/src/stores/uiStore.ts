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
  /** Video đang mở ở Workbench. */
  workbenchVideo: string | null;
  /** Danh sách khung hình đang so sánh cạnh nhau (tối đa 4). */
  compare: SearchHit[];

  connectionOpen: boolean;
  shortcutsOpen: boolean;
  paletteOpen: boolean;

  toggleLeft: () => void;
  toggleRight: () => void;
  setInspectorTab: (t: InspectorTab) => void;
  setBranchTab: (b: string) => void;
  setResultView: (v: ResultView) => void;
  setTileSize: (n: number) => void;
  setCursor: (n: number) => void;
  moveCursor: (delta: number, max: number) => void;
  openDetail: (h: SearchHit | null, hits?: SearchHit[]) => void;
  openWorkbench: (v: string | null) => void;
  toggleCompare: (h: SearchHit) => void;
  clearCompare: () => void;
  setConnectionOpen: (b: boolean) => void;
  setShortcutsOpen: (b: boolean) => void;
  setPaletteOpen: (b: boolean) => void;
}

export const useUi = create<UiState>((set) => ({
  leftOpen: true,
  rightOpen: true,
  inspectorTab: "explain",
  branchTab: "",
  resultView: "grid",
  tileSize: 190,
  cursor: -1,
  detail: null,
  detailHits: [],
  workbenchVideo: null,
  compare: [],
  connectionOpen: false,
  shortcutsOpen: false,
  paletteOpen: false,

  toggleLeft: () => set((s) => ({ leftOpen: !s.leftOpen })),
  toggleRight: () => set((s) => ({ rightOpen: !s.rightOpen })),
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
  openDetail: (h, hits) => set((s) => ({ detail: h, detailHits: hits ?? s.detailHits })),
  openWorkbench: (v) => set({ workbenchVideo: v }),
  toggleCompare: (h) =>
    set((s) => {
      const has = s.compare.some((x) => x.id === h.id);
      if (has) return { compare: s.compare.filter((x) => x.id !== h.id) };
      return { compare: s.compare.length >= 4 ? s.compare : [...s.compare, h] };
    }),
  clearCompare: () => set({ compare: [] }),
  setConnectionOpen: (b) => set({ connectionOpen: b }),
  setShortcutsOpen: (b) => set({ shortcutsOpen: b }),
  setPaletteOpen: (b) => set({ paletteOpen: b }),
}));
