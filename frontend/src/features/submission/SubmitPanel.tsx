/**
 * BẢN NHÁP NỘP BÀI — nhập tay là chính, con người xác nhận từng dòng.
 *
 * Luật BTC được giao diện tự lo, người dùng không phải nhớ:
 *  - Thứ tự dòng CÓ Ý NGHĨA (tin cậy giảm dần) -> kéo thả đổi thứ tự.
 *  - Trần 100 dòng/file -> đếm ngay tại chỗ, đổi màu khi gần chạm.
 *  - Q&A: đáp án tối đa 100 ký tự -> đếm ngược ký tự trong ô.
 *  - TRAKE: số frame phải khớp số sự kiện VÀ tăng dần -> kiểm ngay khi gõ.
 *  - Xem trước CSV THÔ luôn hiển thị: đây là thứ thật sự được nộp, giấu đi là
 *    biến nó thành hộp đen.
 *
 * Cảnh báo là MỀM: hệ thống chỉ nhắc, không bao giờ tự sửa hay tự xoá dòng.
 */
import { DndContext, closestCenter } from "@dnd-kit/core";
import type { DragEndEvent } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Check, Copy, FileDown, GripVertical, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { api } from "../../api/client";
import { Button, Label, Select, TextInput, cx } from "../../components/ui";
import {
  MAX_ANSWER_LEN, MAX_ROWS, framesPerRow, toBackendRows, useSubmission, validateFile,
} from "../../stores/submissionStore";
import type { DraftFile, DraftRow } from "../../stores/submissionStore";
import type { QueryKind } from "../../types/api";

/** Đổi đuôi -kis/-qa/-trake theo loại task đang chọn — người dùng đổi task thì
 *  không phải nhớ tự sửa tay tên file theo, dễ quên -> nộp nhầm đuôi cũ. Tên
 *  không theo đúng mẫu đuôi nào (tự đặt tên khác) thì GIỮ NGUYÊN, không ép. */
const KIND_SUFFIX: Record<QueryKind, string> = { kis: "-kis", qa: "-qa", trake: "-trake" };
function swapKindSuffix(name: string, kind: QueryKind): string {
  const stripped = name.replace(/-(kis|qa|trake)$/i, "");
  return `${stripped}${KIND_SUFFIX[kind]}`;
}

function Row({ file, row, index }: { file: DraftFile; row: DraftRow; index: number }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: row.id });
  const updateRow = useSubmission((s) => s.updateRow);
  const removeRow = useSubmission((s) => s.removeRow);
  const duplicateRow = useSubmission((s) => s.duplicateRow);
  const want = framesPerRow(file);

  const setFrame = (i: number, v: string) => {
    const frames = [...row.frames];
    frames[i] = v.replace(/[^\d]/g, "");
    updateRow(file.name, row.id, { frames });
  };

  return (
    <tr ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }}
        className={cx("border-b border-[var(--color-line)]", isDragging && "opacity-60")}>
      <td className="w-[26px] px-1">
        <div className="flex items-center gap-0.5">
          <button {...attributes} {...listeners} aria-label="Kéo để đổi thứ tự"
                  className="cursor-grab text-[var(--color-fg-mute)] active:cursor-grabbing">
            <GripVertical size={11} />
          </button>
          <span className="font-mono text-[10px] tabular-nums text-[var(--color-fg-mute)]">{index + 1}</span>
        </div>
      </td>
      <td className="px-1 py-1">
        <TextInput value={row.video}
                   onChange={(e) => updateRow(file.name, row.id, { video: e.target.value.trim() })}
                   placeholder="L01_V023"
                   className="w-[104px] px-1 py-0.5 font-mono text-[11px]" />
      </td>
      {Array.from({ length: want }, (_, i) => (
        <td key={i} className="px-1 py-1">
          <TextInput value={row.frames[i] ?? ""} onChange={(e) => setFrame(i, e.target.value)}
                     placeholder={want > 1 ? `E${i + 1}` : "frame_idx"} inputMode="numeric"
                     className="w-[74px] px-1 py-0.5 text-right font-mono text-[11px] tabular-nums" />
        </td>
      ))}
      {file.kind === "qa" && (
        <td className="px-1 py-1">
          <div className="relative">
            <TextInput value={row.answer}
                       onChange={(e) => updateRow(file.name, row.id, { answer: e.target.value })}
                       placeholder="câu trả lời"
                       className="w-full px-1 py-0.5 pr-9 text-[11px]" />
            <span className={cx("absolute right-1 top-1/2 -translate-y-1/2 font-mono text-[9.5px] tabular-nums",
              row.answer.length > MAX_ANSWER_LEN ? "text-[var(--color-err)]" : "text-[var(--color-fg-mute)]")}>
              {row.answer.length}/{MAX_ANSWER_LEN}
            </span>
          </div>
        </td>
      )}
      <td className="w-[52px] px-1">
        <div className="flex gap-0.5">
          <button type="button" onClick={() => duplicateRow(file.name, row.id)}
                  title="Nhân bản dòng — nộp nhiều biến thể quanh cùng một khoảnh khắc"
                  className="p-0.5 text-[var(--color-fg-mute)] hover:text-[var(--color-fg)]">
            <Copy size={11} />
          </button>
          <button type="button" onClick={() => removeRow(file.name, row.id)} title="Xoá dòng"
                  className="p-0.5 text-[var(--color-fg-mute)] hover:text-[var(--color-err)]">
            <Trash2 size={11} />
          </button>
        </div>
      </td>
    </tr>
  );
}

export function SubmitPanel() {
  const files = useSubmission((s) => s.files);
  const order = useSubmission((s) => s.order);
  const activeName = useSubmission((s) => s.activeName);
  const setActiveFile = useSubmission((s) => s.setActiveFile);
  const createFile = useSubmission((s) => s.createFile);
  const removeFile = useSubmission((s) => s.removeFile);
  const renameFile = useSubmission((s) => s.renameFile);
  const patchFile = useSubmission((s) => s.patchFile);
  const addRow = useSubmission((s) => s.addRow);
  const reorderRows = useSubmission((s) => s.reorderRows);

  const [newName, setNewName] = useState("query-p1-1-kis");
  const [newKind, setNewKind] = useState<QueryKind>("kis");

  const file = activeName ? files[activeName] : null;
  const check = useMemo(() => (file ? validateFile(file) : { errors: [], warnings: [] }), [file]);

  const [renameDraft, setRenameDraft] = useState("");
  useEffect(() => { setRenameDraft(file?.name ?? ""); }, [file?.name]);

  const commitRename = () => {
    if (!file || renameDraft.trim() === file.name) return;
    const err = renameFile(file.name, renameDraft.trim());
    if (err) { toast.error(err); setRenameDraft(file.name); }
    else toast.success(`Đã đổi tên thành "${renameDraft.trim()}"`);
  };

  // Nháp cục bộ — KHÔNG bám thẳng vào store mỗi phím gõ: nếu làm vậy, xoá trắng ô
  // để gõ số mới (giá trị tạm rỗng/không hợp lệ) sẽ bị store "bật lại" số cũ ngay
  // lập tức (vì onChange không patch khi rỗng), khiến người dùng cảm giác không
  // gõ được. Chỉ commit khi rời ô (blur) hoặc Enter, giống renameDraft ở trên.
  const [nEventsDraft, setNEventsDraft] = useState("");
  useEffect(() => { setNEventsDraft(String(file?.nEvents ?? 4)); }, [file?.name, file?.nEvents]);

  const commitNEvents = () => {
    if (!file) return;
    const v = parseInt(nEventsDraft, 10);
    if (Number.isFinite(v) && v > 0 && v <= 12) {
      if (v !== file.nEvents) patchFile(file.name, { nEvents: v });
      setNEventsDraft(String(v));
    } else {
      setNEventsDraft(String(file.nEvents));
    }
  };

  // Xem trước CSV do BACKEND dựng — đúng thứ sẽ nộp, kể cả quy tắc bọc ngoặc kép.
  const preview = useMutation({
    mutationFn: async (f: DraftFile) =>
      api.submitPreview(f.kind, toBackendRows(f), f.kind === "trake" ? f.nEvents : null),
  });

  const downloadOne = async (f: DraftFile) => {
    const r = await api.submitPreview(f.kind, toBackendRows(f), f.kind === "trake" ? f.nEvents : null);
    const blob = new Blob([r.csv_text], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${f.name}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast.success(`Đã tải ${f.name}.csv`);
  };

  const onDragEnd = (e: DragEndEvent) => {
    if (!file) return;
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    reorderRows(file.name,
      file.rows.findIndex((r) => r.id === active.id),
      file.rows.findIndex((r) => r.id === over.id));
  };

  return (
    <div className="flex flex-col gap-2 p-3">
      <div className="flex flex-col gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-line)] p-2">
        <Label className="mb-0">Tạo file kết quả</Label>
        <div className="flex gap-1">
          <TextInput value={newName} onChange={(e) => setNewName(e.target.value)}
                     placeholder="query-p1-1-kis"
                     className="flex-1 px-1.5 py-1 font-mono text-[11px]" />
          <Select value={newKind} onChange={(e) => {
                    const k = e.target.value as QueryKind;
                    setNewKind(k);
                    setNewName((prev) => swapKindSuffix(prev, k));
                  }}
                  className="w-[74px] shrink-0 px-1 py-1 text-[11px]">
            <option value="kis">KIS</option>
            <option value="qa">Q&amp;A</option>
            <option value="trake">TRAKE</option>
          </Select>
          <Button size="sm" className="shrink-0"
                  onClick={() => newName.trim() && createFile(newName.trim(), newKind)}>
            <Plus size={11} />
          </Button>
        </div>
        <p className="text-[10px] leading-snug text-[var(--color-fg-mute)]">
          Tên file phải trùng tên câu truy vấn của BTC, không kèm đuôi .csv
        </p>
      </div>

      {order.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {order.map((n) => (
            <button key={n} type="button" onClick={() => setActiveFile(n)}
                    className={cx("rounded-[2px] border px-1.5 py-0.5 font-mono text-[10.5px]",
                      activeName === n
                        ? "border-[var(--color-focus)] text-[var(--color-fg)]"
                        : "border-[var(--color-line)] text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]")}>
              {n} <span className="text-[var(--color-fg-mute)]">({files[n].rows.length})</span>
            </button>
          ))}
        </div>
      )}

      {file && (
        <>
          <div className="flex flex-wrap items-center gap-1.5">
            <TextInput value={renameDraft} onChange={(e) => setRenameDraft(e.target.value)}
                       onBlur={commitRename}
                       onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                       title="Tên file lưu — trùng tên câu truy vấn BTC giao"
                       className="w-[140px] px-1.5 py-0.5 font-mono text-[11px]" />
            {file.kind === "trake" && (
              <label className="flex items-center gap-1 text-[10.5px] text-[var(--color-fg-dim)]">
                số sự kiện
                <TextInput value={nEventsDraft} inputMode="numeric"
                           onChange={(e) => setNEventsDraft(e.target.value.replace(/\D/g, "").slice(0, 2))}
                           onBlur={commitNEvents}
                           onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                           className="w-[38px] px-1 py-0.5 text-center font-mono text-[11px]" />
              </label>
            )}
            <span className={cx("ml-auto font-mono text-[10.5px] tabular-nums",
              file.rows.length >= MAX_ROWS ? "text-[var(--color-err)]"
                : file.rows.length >= 90 ? "text-[var(--color-warn)]" : "text-[var(--color-fg-mute)]")}>
              {file.rows.length}/{MAX_ROWS} dòng
            </span>
          </div>

          <p className="text-[10px] leading-snug text-[var(--color-fg-mute)]">
            Thứ tự dòng có tính điểm — dòng trên cùng là đáp án bạn tin nhất. Kéo biểu tượng bên trái để đổi.
          </p>

          {/* Hàng RIÊNG, vị trí CỐ ĐỊNH — trước gộp chung hàng với loại/số sự kiện
              nên vị trí nút nhảy qua nhảy lại tuỳ có hiện ô "số sự kiện" hay
              không, dễ bấm nhầm. */}
          <div>
            <Button size="sm" variant="ghost" onClick={() => removeFile(file.name)}
                    className="border border-[var(--color-line)] text-[var(--color-err)] hover:border-[var(--color-err)] hover:bg-[color-mix(in_srgb,var(--color-err)_10%,transparent)]">
              <Trash2 size={11} /> Xoá file "{file.name}"
            </Button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="label-xs">
                  <th className="px-1 pb-1 text-left">#</th>
                  <th className="px-1 pb-1 text-left">video</th>
                  {Array.from({ length: framesPerRow(file) }, (_, i) => (
                    <th key={i} className="px-1 pb-1 text-left">
                      {framesPerRow(file) > 1 ? `frame ${i + 1}` : "frame_idx"}
                    </th>
                  ))}
                  {file.kind === "qa" && <th className="px-1 pb-1 text-left">đáp án</th>}
                  <th />
                </tr>
              </thead>
              <DndContext collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                <SortableContext items={file.rows.map((r) => r.id)} strategy={verticalListSortingStrategy}>
                  <tbody>
                    {file.rows.map((r, i) => (
                      <Row key={r.id} file={file} row={r} index={i} />
                    ))}
                  </tbody>
                </SortableContext>
              </DndContext>
            </table>
          </div>

          <Button size="sm" variant="ghost" onClick={() => addRow(file.name)}
                  disabled={file.rows.length >= MAX_ROWS}>
            <Plus size={11} /> Thêm dòng
          </Button>

          {check.errors.length > 0 && (
            <div className="rounded-[var(--radius-sm)] border border-[var(--color-err)] bg-[color-mix(in_srgb,var(--color-err)_10%,transparent)] p-2">
              <div className="mb-0.5 flex items-center gap-1 text-[11px] font-semibold text-[var(--color-err)]">
                <AlertTriangle size={11} /> Cần sửa trước khi nộp
              </div>
              <ul className="list-inside list-disc text-[10.5px] leading-snug text-[var(--color-err)]">
                {check.errors.slice(0, 8).map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </div>
          )}
          {check.warnings.length > 0 && (
            <div className="rounded-[var(--radius-sm)] border border-[var(--color-warn)] bg-[color-mix(in_srgb,var(--color-warn)_10%,transparent)] p-2">
              <div className="mb-0.5 flex items-center gap-1 text-[11px] text-[var(--color-warn)]">
                <AlertTriangle size={11} /> Nhắc nhở (không chặn nộp)
              </div>
              <ul className="list-inside list-disc text-[10.5px] leading-snug text-[var(--color-warn)]">
                {check.warnings.slice(0, 5).map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
          {check.errors.length === 0 && file.rows.length > 0 && (
            <div className="flex items-center gap-1 text-[11px] text-[var(--color-ok)]">
              <Check size={12} /> Hợp lệ — {file.rows.length} dòng, UTF-8, không header
            </div>
          )}

          <div>
            <div className="mb-1 flex items-center gap-2">
              <Label className="mb-0">Xem trước CSV (đúng nội dung sẽ nộp)</Label>
              <Button size="sm" variant="ghost" onClick={() => preview.mutate(file)}>Cập nhật</Button>
            </div>
            <pre className="max-h-[140px] overflow-auto rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-bg)] p-2 font-mono text-[10.5px] leading-relaxed text-[var(--color-fg-dim)]">
              {preview.data?.csv_text || "Bấm Cập nhật để xem"}
            </pre>
          </div>

          <Button size="sm" variant="primary" onClick={() => downloadOne(file)} disabled={check.errors.length > 0}>
            <FileDown size={11} /> Tải {file.name}.csv
          </Button>
        </>
      )}

      {order.length === 0 && (
        <p className="px-1 py-6 text-center text-[11.5px] leading-relaxed text-[var(--color-fg-mute)]">
          Tạo một file kết quả ở trên để bắt đầu.<br />
          Tên file đặt trùng tên câu truy vấn BTC giao, ví dụ <span className="font-mono">query-p1-1-kis</span>.
        </p>
      )}
    </div>
  );
}
