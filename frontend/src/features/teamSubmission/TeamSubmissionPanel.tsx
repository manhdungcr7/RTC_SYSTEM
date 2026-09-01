/** Bang chia se bai nop: doc server, khong tu dong dong bo ban nhap local. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Check, ChevronDown, ChevronRight, Circle, Download, FileText, Trash2, Upload, Users, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "../../api/client";
import { Button, EmptyState, Label, Select, TextArea } from "../../components/ui";
import { useSubmission } from "../../stores/submissionStore";
import { useTeamBoard } from "../../stores/teamBoardStore";
import { isValidMemberId, useTeamIdentity } from "../../stores/teamIdentityStore";
import { useUi } from "../../stores/uiStore";
import type { TeamCheckStatus, TeamQuestion, TeamSharedAnswer } from "../../types/api";

const statusMeta: Record<TeamCheckStatus, { label: string; className: string }> = {
  unchecked: { label: "Chưa kiểm tra", className: "text-[var(--color-fg-mute)]" },
  checked: { label: "Đã kiểm tra", className: "text-[var(--color-ok)]" },
  needs_rework: { label: "Cần làm lại", className: "text-[var(--color-err)]" },
};

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** CSV nho, can xu ly dap an QA co dau phay va ngoac kep. */
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++; }
      else quoted = !quoted;
    } else if (char === "," && !quoted) { row.push(cell); cell = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = []; cell = "";
    } else cell += char;
  }
  row.push(cell);
  if (row.some((value) => value.length > 0)) rows.push(row);
  return rows;
}

function formatTime(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

function identityReady(displayName: string, memberId: string) {
  return Boolean(displayName.trim()) && isValidMemberId(memberId);
}

function AnswerCard({ batchId, question, answer }: { batchId: string; question: TeamQuestion; answer: TeamSharedAnswer }) {
  const qc = useQueryClient();
  const displayName = useTeamIdentity((s) => s.displayName);
  const memberId = useTeamIdentity((s) => s.memberId);
  const files = useSubmission((s) => s.files);
  const replaceFileFromShared = useSubmission((s) => s.replaceFileFromShared);
  const setSharedCsvPreview = useUi((s) => s.setSharedCsvPreview);
  const [note, setNote] = useState(answer.note);
  const ready = identityReady(displayName, memberId);
  const invalidates = () => qc.invalidateQueries({ queryKey: ["team-batch", batchId] });

  useEffect(() => { setNote(answer.note); }, [answer.note]);

  const patch = useMutation({
    mutationFn: (data: { note?: string; check_status?: TeamCheckStatus }) =>
      api.updateTeamAnswer(batchId, question.number, answer.member_id, {
        actor_member_id: memberId, actor_display_name: displayName, ...data,
      }),
    onSuccess: invalidates,
    onError: (error: Error) => toast.error(error.message || "Không cập nhật được bài chia sẻ."),
  });
  const choose = useMutation({
    mutationFn: () => api.chooseTeamAnswer(batchId, question.number, {
      member_id: answer.member_id, actor_member_id: memberId, actor_display_name: displayName,
    }),
    onSuccess: () => { invalidates(); toast.success(`Đã chọn đáp án của ${answer.display_name}.`); },
    onError: (error: Error) => toast.error(error.message),
  });

  const receive = () => {
    const localName = question.filename.replace(/\.csv$/i, "");
    if (files[localName] && !window.confirm(`Bản nháp local ${localName}.csv sẽ được thay bằng bài của ${answer.display_name}. Tiếp tục?`)) return;
    const rows = parseCsv(answer.csv_text);
    const nEvents = question.kind === "trake"
      ? (question.trake_event_count ?? Math.max(1, (rows[0]?.length ?? 2) - 1)) : 4;
    replaceFileFromShared(localName, question.kind, nEvents, rows.map((row) => ({
      video: row[0] ?? "",
      frames: question.kind === "trake" ? row.slice(1) : [row[1] ?? ""],
      answer: question.kind === "qa" ? (row[2] ?? "") : "",
    })));
    toast.success(`Đã đưa ${answer.display_name} · câu ${question.number} vào bản nháp local.`);
  };

  const commitNote = () => {
    if (note === answer.note || !ready) return;
    patch.mutate({ note });
  };
  const setStatus = (check_status: TeamCheckStatus) => {
    if (!ready) { toast.error("Hãy cấu hình Danh tính ở góc trên phải trước."); return; }
    patch.mutate({ check_status });
  };

  const selected = question.selected_member_id === answer.member_id;
  return (
    <div className="rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-bg)] p-2">
      <div className="flex items-center gap-1.5">
        <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium" title={answer.member_id}>
          {answer.display_name} <span className="font-mono text-[12px] text-[var(--color-fg-mute)]">· {answer.member_id.slice(0, 10)}</span>
        </span>
        {selected && <span className="rounded border border-[var(--color-focus)] px-1 py-0.5 text-[12px] text-[var(--color-focus)]">đáp án tổng hợp</span>}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1 text-[12px] text-[var(--color-fg-mute)]">
        <span className={statusMeta[answer.check_status].className}>{statusMeta[answer.check_status].label}</span>
        {answer.checked_by_name && <span>· {answer.checked_by_name}</span>}
        <span>· cập nhật {formatTime(answer.updated_at)}</span>
      </div>
      <TextArea value={note} onChange={(e) => setNote(e.target.value)} onBlur={commitNote}
                disabled={!ready || patch.isPending} placeholder="Ghi chú / nhận xét khi check…"
                className="mt-1 min-h-[40px] text-[12px]" />
      <div className="mt-1.5 flex flex-wrap gap-1">
        <Button size="sm" variant="ghost"
                onClick={() => setSharedCsvPreview({
                  name: question.filename, kind: question.kind, text: answer.csv_text,
                  question: question.description,
                })}>
          <FileText size={11} /> Xem CSV
        </Button>
        <Button size="sm" variant="ghost" onClick={receive}><Download size={11} /> Nhận</Button>
        <Button size="sm" variant="ghost" title="Đã kiểm tra" disabled={!ready || patch.isPending}
                onClick={() => setStatus("checked")} className="text-[var(--color-ok)]"><Check size={11} /></Button>
        <Button size="sm" variant="ghost" title="Cần làm lại" disabled={!ready || patch.isPending}
                onClick={() => setStatus("needs_rework")} className="text-[var(--color-err)]"><X size={11} /></Button>
        <Button size="sm" variant="ghost" title="Chưa kiểm tra" disabled={!ready || patch.isPending}
                onClick={() => setStatus("unchecked")}><Circle size={10} /></Button>
        <Button size="sm" variant={selected ? "primary" : "ghost"} disabled={!ready || choose.isPending}
                onClick={() => choose.mutate()}>Chọn nộp</Button>
      </div>
    </div>
  );
}

function QuestionRow({ batchId, question }: { batchId: string; question: TeamQuestion }) {
  const [open, setOpen] = useState(false);
  const [descriptionOpen, setDescriptionOpen] = useState(false);
  const count = question.answers.length;
  const uncheckedCount = question.answers.filter((answer) => answer.check_status === "unchecked").length;
  return (
    <section className="border-b border-[var(--color-line)]">
      <div className="flex items-center gap-1.5 px-3 py-2">
        <button type="button" onClick={() => setOpen((value) => !value)} className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <span className="font-mono text-[10.5px] text-[var(--color-fg-mute)]">#{question.number}</span>
          <span className="min-w-0 flex-1 truncate font-mono text-[10.5px]">{question.filename}</span>
          {uncheckedCount > 0 && (
            <span className="shrink-0 rounded border border-[color-mix(in_srgb,var(--color-err)_70%,var(--color-line))] bg-[color-mix(in_srgb,var(--color-err)_14%,transparent)] px-1.5 py-0.5 text-[11px] font-bold tracking-wide text-[var(--color-err)]">
              CẦN CHECK
            </span>
          )}
          <span className="rounded border border-[var(--color-line)] px-1 py-0.5 text-[9px] text-[var(--color-fg-dim)]">{question.kind.toUpperCase()}</span>
          <span className="font-mono text-[12px] text-[var(--color-fg-mute)]">{count}</span>
        </button>
        <button type="button" onClick={() => setDescriptionOpen((value) => !value)} title="Xem mô tả câu hỏi"
                className="text-[10px] text-[var(--color-focus)] hover:underline">đề</button>
      </div>
      {descriptionOpen && <p className="border-t border-[var(--color-line)] px-3 py-2 text-[10.5px] leading-snug text-[var(--color-fg-dim)] whitespace-pre-wrap">{question.description}</p>}
      {open && (
        <div className="flex flex-col gap-1.5 border-t border-[var(--color-line)] bg-[var(--color-panel-2)] p-2">
          {count === 0
            ? <p className="py-1 text-center text-[10.5px] text-[var(--color-fg-mute)]">Chưa có ai chia sẻ bài này.</p>
            : question.answers.map((answer) => <AnswerCard key={answer.member_id} batchId={batchId} question={question} answer={answer} />)}
        </div>
      )}
    </section>
  );
}

export function TeamSubmissionPanel() {
  const qc = useQueryClient();
  const activeBatchId = useTeamBoard((s) => s.activeBatchId);
  const setActiveBatchId = useTeamBoard((s) => s.setActiveBatchId);
  const importRef = useRef<HTMLInputElement>(null);
  const restoreRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const batches = useQuery({ queryKey: ["team-batches"], queryFn: ({ signal }) => api.listTeamBatches(signal), refetchInterval: 4_000 });
  const currentBatchId = activeBatchId && batches.data?.some((item) => item.id === activeBatchId)
    ? activeBatchId : (batches.data?.[0]?.id ?? null);
  const board = useQuery({
    queryKey: ["team-batch", currentBatchId],
    queryFn: ({ signal }) => api.getTeamBatch(currentBatchId!, signal),
    enabled: Boolean(currentBatchId), refetchInterval: 4_000,
  });

  useEffect(() => {
    if (currentBatchId && currentBatchId !== activeBatchId) setActiveBatchId(currentBatchId);
  }, [activeBatchId, currentBatchId, setActiveBatchId]);

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["team-batches"] });
    await qc.invalidateQueries({ queryKey: ["team-batch"] });
  };
  const importQuestions = async (file: File, replaceExisting = false) => {
    setUploading(true);
    try {
      const result = await api.importQuestions(file, replaceExisting);
      setActiveBatchId(result.batch.id);
      await refresh();
      toast.success(result.imported ? `Đã tạo bảng ${result.batch.id}: ${result.batch.question_count} câu.` : "Bảng đề này đã được khởi tạo.");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && window.confirm(`${error.message}\n\nThay thế batch cũ sẽ xóa các bài chia sẻ. Bạn có chắc?`)) {
        await importQuestions(file, true);
        return;
      }
      toast.error(error instanceof Error ? error.message : "Không import được question.zip.");
    } finally { setUploading(false); }
  };
  const restore = async (file: File, replaceExisting = false) => {
    setRestoring(true);
    try {
      const result = await api.restoreTeamBackup(file, replaceExisting);
      setActiveBatchId(result.batch.id);
      await refresh();
      toast.success(`Đã khôi phục batch ${result.batch.id}.`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && window.confirm(`${error.message}\n\nThay thế batch hiện tại?`)) {
        await restore(file, true);
        return;
      }
      toast.error(error instanceof Error ? error.message : "Không khôi phục được backup.");
    } finally { setRestoring(false); }
  };
  const downloadBackup = async () => {
    if (!currentBatchId) return;
    try { saveBlob(await api.teamBackup(currentBatchId), `${currentBatchId}-team-backup.zip`); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Không tạo được backup."); }
  };
  const exportSubmission = async () => {
    if (!currentBatchId) return;
    try { saveBlob(await api.exportTeamSubmission(currentBatchId), "submission.zip"); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Chưa export được gói nộp."); }
  };
  const deleteCurrentBatch = async () => {
    if (!currentBatchId) return;
    if (!window.confirm(
      `Xóa đề ${currentBatchId} sẽ xóa toàn bộ câu hỏi, bài chia sẻ và lựa chọn nộp trên server. Bản nháp local không bị xóa. Tiếp tục?`,
    )) return;
    if (window.prompt(`Gõ đúng mã đề "${currentBatchId}" để xác nhận xóa:`)?.trim().toLowerCase() !== currentBatchId) {
      toast.message("Đã hủy xóa đề.");
      return;
    }
    setDeleting(true);
    try {
      await api.deleteTeamBatch(currentBatchId);
      setActiveBatchId(null);
      qc.removeQueries({ queryKey: ["team-batch", currentBatchId] });
      await refresh();
      toast.success(`Đã xóa đề ${currentBatchId} khỏi bảng chia sẻ.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không xóa được đề.");
    } finally { setDeleting(false); }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-col gap-1.5 border-b border-[var(--color-line)] p-3">
        <div className="flex items-center gap-1.5">
          <Users size={12} className="text-[var(--color-focus)]" />
          <Label className="mb-0 flex-1">Bài chia sẻ nhóm</Label>
          <Button size="sm" variant="ghost" onClick={() => importRef.current?.click()} disabled={uploading}><Upload size={11} /> Đề</Button>
        </div>
        <input ref={importRef} type="file" accept=".zip,application/zip" className="hidden"
               onChange={(event) => { const file = event.target.files?.[0]; event.currentTarget.value = ""; if (file) void importQuestions(file); }} />
        <input ref={restoreRef} type="file" accept=".zip,application/zip" className="hidden"
               onChange={(event) => { const file = event.target.files?.[0]; event.currentTarget.value = ""; if (file) void restore(file); }} />
        {batches.data?.length ? (
          <Select value={currentBatchId ?? ""} onChange={(event) => setActiveBatchId(event.target.value)} className="font-mono text-[11px]">
            {batches.data.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.question_count} câu</option>)}
          </Select>
        ) : <p className="text-[10.5px] leading-snug text-[var(--color-fg-mute)]">Upload <span className="font-mono">question.zip</span> một lần để tạo bảng chung.</p>}
        {currentBatchId && <div className="flex flex-wrap gap-1">
          <Button size="sm" variant="ghost" onClick={downloadBackup}><Download size={11} /> Backup</Button>
          <Button size="sm" variant="ghost" onClick={() => restoreRef.current?.click()} disabled={restoring}><ArchiveRestore size={11} /> Restore</Button>
          <Button size="sm" variant="primary" onClick={exportSubmission}><Download size={11} /> Export ZIP</Button>
          <Button size="sm" variant="ghost" onClick={() => void deleteCurrentBatch()} disabled={deleting}
                  className="text-[var(--color-err)] hover:text-[var(--color-err)]">
            <Trash2 size={11} /> {deleting ? "Đang xóa…" : "Xóa đề"}
          </Button>
        </div>}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {board.isLoading && <p className="p-3 text-[11px] text-[var(--color-fg-mute)]">Đang tải bảng chia sẻ…</p>}
        {board.error && <p className="p-3 text-[11px] text-[var(--color-err)]">{(board.error as Error).message}</p>}
        {board.data && board.data.questions.map((question) => <QuestionRow key={question.number} batchId={board.data!.id} question={question} />)}
        {!board.data && !board.isLoading && !board.error && <EmptyState title="Chưa có bảng chung" hint="Một thành viên upload question.zip để toàn nhóm có cùng danh sách câu hỏi." />}
      </div>
    </div>
  );
}
