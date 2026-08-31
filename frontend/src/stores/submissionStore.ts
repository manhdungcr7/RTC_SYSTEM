/**
 * BẢN NHÁP NỘP BÀI — các dòng CSV sẽ nộp, đúng thứ tự, do NGƯỜI DÙNG xác nhận.
 *
 * Tách bạch với khay ghim (Pinboard) có chủ đích:
 *   Pinboard      = "ứng viên đang cân nhắc"
 *   Submission    = "đáp án đã chốt, sẽ nộp"
 * Chuyển từ ghim sang nháp là một hành động CÓ CHỦ Ý của con người, không tự động.
 *
 * Luật nộp bài (BTC, xem cach_nop_bai.txt):
 *   KIS   : <video>,<frame_idx>
 *   QA    : <video>,<frame_idx>,<answer>       answer <= 100 ký tự
 *   TRAKE : <video>,<frame_1>,...,<frame_N>    N khớp đúng số sự kiện, tăng dần
 *   Tối đa 100 dòng/file, KHÔNG header, UTF-8, tên video KHÔNG có .mp4.
 *   THỨ TỰ DÒNG CÓ Ý NGHĨA (độ tin cậy giảm dần).
 *
 * Lưu bền localStorage: mất bản nháp giữa cuộc thi là mất trắng công sức, và
 * mỗi gói chỉ được nộp tối đa 3 lần.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { QueryKind } from "../types/api";

export const MAX_ROWS = 100;
export const MAX_ANSWER_LEN = 100;

export interface DraftRow {
  id: string;
  video: string;
  frames: string[];      // KIS/QA: 1 phần tử; TRAKE: N phần tử. Giữ CHUỖI để
                          // người dùng gõ dở dang không bị ép về số.
  answer: string;        // chỉ dùng cho QA
}

export interface DraftFile {
  name: string;          // tên file KHÔNG có .csv, vd "query-p1-1-kis"
  kind: QueryKind;
  nEvents: number;       // chỉ có nghĩa với TRAKE
  rows: DraftRow[];
  submitCount: number;   // người dùng tự bấm sau mỗi lần nộp lên Codabench
}

const rid = () => Math.random().toString(36).slice(2, 10);

export const emptyRow = (nFrames: number): DraftRow => ({
  id: rid(), video: "", frames: Array(nFrames).fill(""), answer: "",
});

export function makeFile(name: string, kind: QueryKind, nEvents = 4): DraftFile {
  return {
    name, kind, nEvents,
    rows: [emptyRow(kind === "trake" ? nEvents : 1)],
    submitCount: 0,
  };
}

/** Số ô frame mỗi dòng cần có, theo loại task. */
export const framesPerRow = (f: Pick<DraftFile, "kind" | "nEvents">) =>
  f.kind === "trake" ? Math.max(1, f.nEvents) : 1;

interface Store {
  files: Record<string, DraftFile>;
  order: string[];
  activeName: string | null;

  createFile: (name: string, kind: QueryKind, nEvents?: number) => void;
  removeFile: (name: string) => void;
  renameFile: (oldName: string, newName: string) => string | null;
  setActiveFile: (name: string | null) => void;
  patchFile: (name: string, patch: Partial<DraftFile>) => void;

  addRow: (name: string, row?: Partial<DraftRow>) => void;
  updateRow: (name: string, rowId: string, patch: Partial<DraftRow>) => void;
  removeRow: (name: string, rowId: string) => void;
  duplicateRow: (name: string, rowId: string) => void;
  reorderRows: (name: string, from: number, to: number) => void;
  /** Chi duoc goi sau khi nguoi dung bam "Nhan vao ban nhap" tu bang chung. */
  replaceFileFromShared: (name: string, kind: QueryKind, nEvents: number,
                          rows: Omit<DraftRow, "id">[]) => void;
  bumpSubmitCount: (name: string) => void;
}

export const useSubmission = create<Store>()(
  persist(
    (set) => ({
      files: {},
      order: [],
      activeName: null,

      createFile: (name, kind, nEvents = 4) =>
        set((s) => {
          if (s.files[name]) return { ...s, activeName: name };
          return {
            files: { ...s.files, [name]: makeFile(name, kind, nEvents) },
            order: [...s.order, name],
            activeName: name,
          };
        }),

      removeFile: (name) =>
        set((s) => {
          const { [name]: _d, ...rest } = s.files;
          const order = s.order.filter((x) => x !== name);
          return {
            files: rest, order,
            activeName: s.activeName === name ? (order[0] ?? null) : s.activeName,
          };
        }),

      // Trả về thông báo lỗi (string) nếu không đổi được, null nếu thành công —
      // gọi nơi dùng tự quyết định hiển thị lỗi thế nào (toast, inline...).
      renameFile: (oldName, newName) => {
        const clean = newName.trim();
        let err: string | null = null;
        set((s) => {
          const f = s.files[oldName];
          if (!f) { err = "Không tìm thấy file."; return s; }
          if (!clean) { err = "Tên file không được để trống."; return s; }
          if (clean !== oldName && s.files[clean]) { err = `Đã có file tên "${clean}".`; return s; }
          if (clean === oldName) return s;
          const { [oldName]: renamed, ...rest } = s.files;
          const files = { ...rest, [clean]: { ...renamed, name: clean } };
          const order = s.order.map((x) => (x === oldName ? clean : x));
          const activeName = s.activeName === oldName ? clean : s.activeName;
          return { files, order, activeName };
        });
        return err;
      },

      setActiveFile: (name) => set({ activeName: name }),

      patchFile: (name, patch) =>
        set((s) => {
          const f = s.files[name];
          if (!f) return s;
          const next = { ...f, ...patch };
          // Đổi loại task hoặc số sự kiện -> chỉnh lại số ô frame của MỌI dòng,
          // giữ nguyên giá trị đã gõ ở các ô còn lại (không xoá công sức người dùng).
          const want = framesPerRow(next);
          next.rows = next.rows.map((r) => {
            if (r.frames.length === want) return r;
            const frames = r.frames.slice(0, want);
            while (frames.length < want) frames.push("");
            return { ...r, frames };
          });
          return { files: { ...s.files, [name]: next } };
        }),

      addRow: (name, row) =>
        set((s) => {
          const f = s.files[name];
          if (!f) return s;
          // Có dữ liệu thật để điền (gọi từ "Đưa vào bản nháp"/copy-frame, không
          // phải bấm tay "+ Thêm dòng") VÀ đang có sẵn dòng trống (thường là
          // dòng đầu khi file vừa tạo) -> điền vào dòng trống đó thay vì luôn
          // thêm dòng mới, tránh để lại dòng trống vô dụng mãi ở đầu file.
          if (row) {
            const emptyIdx = f.rows.findIndex(
              (r) => !r.video.trim() && r.frames.every((x) => !x.trim()) && !r.answer.trim());
            if (emptyIdx >= 0) {
              const rows = f.rows.map((r, i) => (i === emptyIdx ? { ...r, ...row } : r));
              return { files: { ...s.files, [name]: { ...f, rows } } };
            }
          }
          if (f.rows.length >= MAX_ROWS) return s;
          const base = emptyRow(framesPerRow(f));
          return {
            files: { ...s.files, [name]: { ...f, rows: [...f.rows, { ...base, ...row, id: rid() }] } },
          };
        }),

      updateRow: (name, rowId, patch) =>
        set((s) => {
          const f = s.files[name];
          if (!f) return s;
          return {
            files: {
              ...s.files,
              [name]: {
                ...f,
                rows: f.rows.map((r) => (r.id === rowId ? { ...r, ...patch } : r)),
              },
            },
          };
        }),

      removeRow: (name, rowId) =>
        set((s) => {
          const f = s.files[name];
          if (!f) return s;
          return {
            files: { ...s.files, [name]: { ...f, rows: f.rows.filter((r) => r.id !== rowId) } },
          };
        }),

      // Nhân bản dòng — thao tác dùng liên tục: nộp nhiều biến thể frame_idx
      // quanh cùng một khoảnh khắc để tăng cơ hội trúng.
      duplicateRow: (name, rowId) =>
        set((s) => {
          const f = s.files[name];
          if (!f || f.rows.length >= MAX_ROWS) return s;
          const i = f.rows.findIndex((r) => r.id === rowId);
          if (i < 0) return s;
          const copy = { ...f.rows[i], id: rid(), frames: [...f.rows[i].frames] };
          const rows = [...f.rows];
          rows.splice(i + 1, 0, copy);
          return { files: { ...s.files, [name]: { ...f, rows } } };
        }),

      reorderRows: (name, from, to) =>
        set((s) => {
          const f = s.files[name];
          if (!f) return s;
          const rows = [...f.rows];
          const [m] = rows.splice(from, 1);
          rows.splice(to, 0, m);
          return { files: { ...s.files, [name]: { ...f, rows } } };
        }),

      replaceFileFromShared: (name, kind, nEvents, rows) =>
        set((s) => {
          const old = s.files[name];
          const want = kind === "trake" ? Math.max(1, nEvents) : 1;
          const safeRows = rows.slice(0, MAX_ROWS).map((row) => {
            const frames = row.frames.slice(0, want);
            while (frames.length < want) frames.push("");
            return { ...row, id: rid(), frames };
          });
          const file: DraftFile = {
            name, kind, nEvents: kind === "trake" ? want : 4,
            rows: safeRows.length ? safeRows : [emptyRow(want)],
            // So lan nop la thong tin cua may local, khong lay theo bai chia se.
            submitCount: old?.submitCount ?? 0,
          };
          return {
            files: { ...s.files, [name]: file },
            order: old ? s.order : [...s.order, name],
            activeName: name,
          };
        }),

      bumpSubmitCount: (name) =>
        set((s) => {
          const f = s.files[name];
          if (!f) return s;
          return { files: { ...s.files, [name]: { ...f, submitCount: f.submitCount + 1 } } };
        }),
    }),
    { name: "aic-submission", version: 1 },
  ),
);

/** Kiểm tra tại chỗ — CẢNH BÁO MỀM, không bao giờ tự sửa/tự xoá dòng của người dùng. */
export function validateFile(f: DraftFile): { errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];
  const want = framesPerRow(f);

  if (f.rows.length === 0) errors.push("Chưa có dòng nào.");
  if (f.rows.length > MAX_ROWS) errors.push(`${f.rows.length} dòng, vượt trần ${MAX_ROWS}.`);

  const seen = new Map<string, number>();
  f.rows.forEach((r, i) => {
    const no = i + 1;
    if (!r.video.trim()) { errors.push(`Dòng ${no}: chưa nhập tên video.`); return; }
    if (r.video.trim().toLowerCase().endsWith(".mp4"))
      errors.push(`Dòng ${no}: tên video không được có đuôi .mp4.`);

    const nums: number[] = [];
    r.frames.slice(0, want).forEach((v, k) => {
      const t = v.trim();
      if (!t) { errors.push(`Dòng ${no}: thiếu frame ${want > 1 ? k + 1 : ""}`.trim() + "."); return; }
      if (!/^\d+$/.test(t)) { errors.push(`Dòng ${no}: "${t}" không phải số nguyên.`); return; }
      nums.push(Number(t));
    });

    if (f.kind === "trake" && nums.length === want) {
      for (let k = 1; k < nums.length; k++) {
        if (nums[k] <= nums[k - 1]) {
          errors.push(`Dòng ${no}: frame phải tăng dần theo thời gian (${nums[k - 1]} → ${nums[k]}).`);
          break;
        }
      }
    }

    if (f.kind === "qa") {
      if (!r.answer.trim()) errors.push(`Dòng ${no}: chưa nhập câu trả lời.`);
      else if (r.answer.length > MAX_ANSWER_LEN)
        errors.push(`Dòng ${no}: câu trả lời ${r.answer.length} ký tự, vượt ${MAX_ANSWER_LEN}.`);
    }

    const key = `${r.video.trim()}|${r.frames.slice(0, want).join(",")}`;
    if (seen.has(key)) warnings.push(`Dòng ${no} trùng hệt dòng ${seen.get(key)}.`);
    else seen.set(key, no);
  });

  // Nghi ngờ trùng lặp: cùng video, frame sát nhau -> gần như chắc chắn cùng cảnh.
  for (let i = 0; i < f.rows.length; i++) {
    for (let j = i + 1; j < f.rows.length; j++) {
      const a = f.rows[i], b = f.rows[j];
      if (a.video.trim() !== b.video.trim() || !a.video.trim()) continue;
      const fa = Number(a.frames[0]), fb = Number(b.frames[0]);
      if (Number.isFinite(fa) && Number.isFinite(fb) && fa !== fb && Math.abs(fa - fb) <= 10) {
        warnings.push(`Dòng ${i + 1} và ${j + 1} chỉ cách nhau ${Math.abs(fa - fb)} khung — có thể là cùng một cảnh.`);
      }
    }
  }
  return { errors, warnings };
}

/** Dựng đúng mảng rows mà backend /submit/build mong đợi. */
export function toBackendRows(f: DraftFile): (string | number)[][] {
  const want = framesPerRow(f);
  return f.rows.map((r) => {
    const frames = r.frames.slice(0, want).map((v) => Number(v.trim() || 0));
    return f.kind === "qa"
      ? [r.video.trim(), frames[0], r.answer]
      : [r.video.trim(), ...frames];
  });
}
