import { createContext, useContext } from "react";

import type { QueryKind } from "../types/search";

export interface SubmissionRow {
  video: string;
  frame_idx: number;
}

export interface SubmissionFile {
  kind: QueryKind;
  rows: SubmissionRow[];
}

export interface SubmissionStore {
  files: Record<string, SubmissionFile>;   // key = tên file KHÔNG đuôi, vd "query-p1-1-kis"
  addRow: (filename: string, kind: QueryKind, row: SubmissionRow) => void;
  removeRow: (filename: string, index: number) => void;
  removeFile: (filename: string) => void;
  // "File đang chọn" — trang Submit đặt, các nút "Thêm vào submission" ở Search/
  // Temporal đọc để biết thêm vào đâu mà không cần điều hướng qua trang Submit.
  activeFile: string;
  activeKind: QueryKind;
  setActive: (filename: string, kind: QueryKind) => void;
}

export const SubmissionContext = createContext<SubmissionStore | null>(null);

export function useSubmissionStore(): SubmissionStore {
  const ctx = useContext(SubmissionContext);
  if (!ctx) throw new Error("useSubmissionStore phải dùng trong <SubmissionProvider>");
  return ctx;
}
