import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Clipboard, Download, FilePlus2, Pencil, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { api } from "../../api/client";
import { Button, Label, Modal, Select, TextArea, TextInput, copyToClipboard } from "../../components/ui";
import { useSession } from "../../stores/sessionStore";
import type { LiveQuestion, LiveReveal, QueryKind } from "../../types/api";
import { liveGptPrompt, liveSearchText } from "./liveQuestionText";

function clock(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function LiveQuestionsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const sessions = useSession((state) => state.sessions);
  const questions = useQuery({
    queryKey: ["live-questions"], queryFn: ({ signal }) => api.listLiveQuestions(signal),
    enabled: open, refetchInterval: open ? 4_000 : false,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<QueryKind>("kis");
  const [qaQuestion, setQaQuestion] = useState("");
  const [editLabel, setEditLabel] = useState("");
  const [editQaQuestion, setEditQaQuestion] = useState("");
  const [textVi, setTextVi] = useState("");
  const [textEn, setTextEn] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [editingQuestion, setEditingQuestion] = useState(false);
  const restoreRef = useRef<HTMLInputElement>(null);
  const list = questions.data ?? [];
  const selected = list.find((question) => question.id === selectedId) ?? list[0];
  const linkedSession = selected ? Object.values(sessions).find((session) => session.liveQuestionId === selected.id) : undefined;
  const hasNewReveal = Boolean(selected && linkedSession && linkedSession.query !== liveSearchText(selected));

  useEffect(() => {
    if (!selected && selectedId) setSelectedId(null);
  }, [selected, selectedId]);

  const refresh = () => qc.invalidateQueries({ queryKey: ["live-questions"] });
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try { await action(); await refresh(); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Không lưu được nhật ký câu hỏi."); }
    finally { setBusy(false); }
  };

  const create = () => void run(async () => {
    const question = await api.createLiveQuestion({ label, kind, qa_question: kind === "qa" ? qaQuestion : "" });
    setSelectedId(question.id);
    setLabel(""); setQaQuestion("");
    toast.success("Đã tạo câu hỏi chung cho cả đội.");
  });

  const saveQuestion = () => {
    if (!selected) return;
    void run(async () => {
      await api.updateLiveQuestion(selected.id, { label: editLabel, qa_question: selected.kind === "qa" ? editQaQuestion : "" });
      setEditingQuestion(false);
      toast.success("Đã sửa thông tin câu hỏi.");
    });
  };

  const addOrSaveReveal = () => {
    if (!selected) return;
    void run(async () => {
      if (editId == null) await api.addLiveReveal(selected.id, { text_vi: textVi, text_en: textEn });
      else await api.updateLiveReveal(selected.id, editId, { text_vi: textVi, text_en: textEn });
      setTextVi(""); setTextEn(""); setEditId(null);
      toast.success(editId == null ? "Đã thêm mốc công bố; cả đội sẽ thấy trong vài giây." : "Đã sửa mốc công bố.");
    });
  };

  const beginEdit = (reveal: LiveReveal) => {
    setEditId(reveal.id);
    setTextVi(reveal.text_vi);
    setTextEn(reveal.text_en);
  };

  const remove = () => {
    if (!selected || !window.confirm(`Xóa câu “${selected.label}” và toàn bộ hint của nó trên server?`)) return;
    void run(async () => {
      await api.deleteLiveQuestion(selected.id);
      setSelectedId(null);
      toast.success("Đã xóa câu hỏi chung.");
    });
  };

  const copyGpt = async () => {
    if (!selected || selected.reveals.length === 0) return;
    const ok = await copyToClipboard(liveGptPrompt(selected));
    if (ok) toast.success("Đã chép đề hiện tại. Dán vào GPT Explore như một tin nhắn mới.");
    else toast.error("Không sao chép được. Hãy kiểm tra quyền clipboard của trình duyệt.");
  };

  const backup = async () => {
    try {
      const snapshot = await api.backupLiveQuestions();
      const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = "live-questions-backup.json"; link.click();
      URL.revokeObjectURL(url);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Không tải được backup."); }
  };

  const restore = (file: File) => void run(async () => {
    if (file.size > 10 * 1024 * 1024) throw new Error("Backup quá 10 MB.");
    const snapshot: unknown = JSON.parse(await file.text());
    if (!window.confirm("Restore sẽ thay toàn bộ nhật ký câu hỏi chung hiện có trên server. Tiếp tục?")) return;
    await api.restoreLiveQuestions(snapshot, true);
    setSelectedId(null);
    toast.success("Đã khôi phục nhật ký câu hỏi chung.");
  });

  const applyToSearch = (question: LiveQuestion) => {
    const query = liveSearchText(question);
    if (!query) return;
    const state = useSession.getState();
    const old = Object.values(state.sessions).find((session) => session.liveQuestionId === question.id);
    if (old && old.query === query) {
      state.setActive(old.id);
      onOpenChange(false);
      navigate("/");
      return;
    }
    if (old && !window.confirm(
      "Cập nhật ô tìm kiếm theo các hint đã lộ? Mệnh đề và bản dịch của kế hoạch cũ sẽ được xóa để tránh dùng nhầm; khung đã ghim vẫn giữ."
    )) return;
    const id = old?.id ?? state.addSession(question.label);
    const current = useSession.getState();
    current.setActive(id);
    current.patchOf(id, {
      liveQuestionId: question.id, label: question.label, kind: question.kind, query,
      autoSplit: true, clauses: [], clausesDirty: false, translations: {}, translationsDirty: false,
      feedbackPos: [], feedbackNeg: [],
    });
    onOpenChange(false);
    navigate("/");
    toast.success("Đã đưa đề đã lộ vào Search. Có thể cập nhật kế hoạch GPT rồi bấm Tìm.");
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Nhật ký câu hỏi và hint · chung cho cả đội" wide>
      <div className="grid gap-4 md:grid-cols-[220px_1fr]">
        <div className="space-y-3 border-b border-[var(--color-line)] pb-3 md:border-b-0 md:border-r md:pr-4">
          <div>
            <Label>Các câu đang lưu</Label>
            {questions.isLoading && <p className="text-[11px] text-[var(--color-fg-mute)]">Đang tải…</p>}
            {questions.error && <p role="alert" className="text-[11px] text-[var(--color-err)]">Không tải được nhật ký chung.</p>}
            <div className="max-h-48 space-y-1 overflow-y-auto">
              {list.map((question) => <button key={question.id} type="button" onClick={() => {
                setSelectedId(question.id); setEditId(null); setTextVi(""); setTextEn(""); setEditingQuestion(false);
              }} className={`block w-full rounded px-2 py-1.5 text-left text-[11px] ${selected?.id === question.id ? "bg-[var(--color-panel-3)] text-[var(--color-fg)]" : "text-[var(--color-fg-dim)] hover:bg-[var(--color-panel-2)]"}`}>
                <span className="font-medium">{question.label}</span>
                <span className="ml-1 text-[var(--color-fg-mute)]">{question.kind.toUpperCase()} · {question.reveals.length} mốc</span>
              </button>)}
            </div>
          </div>
          <div className="space-y-1.5 border-t border-[var(--color-line)] pt-3">
            <Label>Tạo câu mới, không cần question.zip</Label>
            <TextInput value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Ví dụ: Câu 12" maxLength={120} />
            <Select value={kind} onChange={(event) => setKind(event.target.value as QueryKind)}>
              <option value="kis">KIS</option><option value="qa">Q&A</option><option value="trake">TRAKE</option>
            </Select>
            {kind === "qa" && <TextArea value={qaQuestion} onChange={(event) => setQaQuestion(event.target.value)} rows={2} placeholder="Câu hỏi cần trả lời, BTC cho từ đầu" />}
            <Button size="sm" onClick={create} disabled={busy || !label.trim()}><FilePlus2 size={11} /> Tạo câu</Button>
          </div>
          <div className="flex flex-wrap gap-1 border-t border-[var(--color-line)] pt-3">
            <Button size="sm" variant="ghost" onClick={() => void backup()}><Download size={11} /> Backup</Button>
            <input ref={restoreRef} type="file" accept=".json,application/json" className="hidden"
                   onChange={(event) => { const file = event.target.files?.[0]; event.currentTarget.value = ""; if (file) restore(file); }} />
            <Button size="sm" variant="ghost" onClick={() => restoreRef.current?.click()} disabled={busy}><Upload size={11} /> Restore</Button>
          </div>
        </div>

        <div className="min-w-0 space-y-3">
          {!selected ? <p className="text-[12px] text-[var(--color-fg-mute)]">Tạo một câu, sau đó thêm mô tả mở đầu và từng hint khi BTC công bố.</p> : <>
            <div className="flex flex-wrap items-start gap-2">
              <div className="min-w-0 flex-1">
                <h3 className="text-[14px] font-semibold">{selected.label} <span className="text-[11px] font-normal text-[var(--color-fg-mute)]">· {selected.kind.toUpperCase()}</span></h3>
                {selected.kind === "qa" && <p className="mt-1 whitespace-pre-wrap text-[11px] text-[var(--color-fg-dim)]">Câu hỏi: {selected.qa_question || "Chưa nhập"}</p>}
              </div>
              <Button size="sm" variant="ghost" onClick={() => { setEditLabel(selected.label); setEditQaQuestion(selected.qa_question); setEditingQuestion((value) => !value); }}><Pencil size={11} /> Sửa</Button>
              <Button size="sm" variant="ghost" onClick={remove} disabled={busy} title="Xóa câu hỏi chung"><Trash2 size={11} /></Button>
            </div>
            {editingQuestion && <div className="space-y-1.5 rounded border border-[var(--color-line)] p-2">
              <TextInput value={editLabel} onChange={(event) => setEditLabel(event.target.value)} maxLength={120} />
              {selected.kind === "qa" && <TextArea value={editQaQuestion} onChange={(event) => setEditQaQuestion(event.target.value)} rows={2} placeholder="Câu hỏi cần trả lời" />}
              <Button size="sm" onClick={saveQuestion} disabled={busy || !editLabel.trim()}>Lưu thông tin</Button>
            </div>}

            <div className="max-h-56 space-y-2 overflow-y-auto border-y border-[var(--color-line)] py-2">
              {selected.reveals.length === 0 && <p className="text-[11px] text-[var(--color-fg-mute)]">Chưa có mốc công bố.</p>}
              {selected.reveals.map((reveal) => <div key={reveal.id} className="rounded border border-[var(--color-line)] bg-[var(--color-panel-2)] p-2">
                <div className="mb-1 flex items-center justify-between text-[10px] text-[var(--color-fg-mute)]">
                  <span>{reveal.position === 1 ? "Mô tả mở đầu" : `Hint ${reveal.position - 1}`} · {clock(reveal.created_at)}{reveal.updated_at !== reveal.created_at ? " · đã sửa" : ""}</span>
                  <button type="button" onClick={() => beginEdit(reveal)} className="text-[var(--color-focus)] hover:underline">Sửa chữ</button>
                </div>
                {reveal.text_vi && <p className="whitespace-pre-wrap text-[11px]"><span className="font-mono text-[var(--color-fg-mute)]">VI </span>{reveal.text_vi}</p>}
                {reveal.text_en && <p className="mt-1 whitespace-pre-wrap text-[11px]"><span className="font-mono text-[var(--color-fg-mute)]">EN </span>{reveal.text_en}</p>}
              </div>)}
            </div>

            <div className="space-y-1.5">
              <Label>{editId == null ? (selected.reveals.length ? `Thêm hint ${selected.reveals.length}` : "Thêm mô tả mở đầu") : "Sửa mốc công bố"}</Label>
              <p className="text-[10.5px] text-[var(--color-fg-mute)]">Chỉ dán nguyên văn BTC. Nếu BTC cho hai ngôn ngữ cùng lúc, điền cả hai ô trong một mốc.</p>
              <TextArea value={textVi} onChange={(event) => setTextVi(event.target.value)} rows={2} placeholder="Nguyên văn tiếng Việt (nếu có)" maxLength={30000} />
              <TextArea value={textEn} onChange={(event) => setTextEn(event.target.value)} rows={2} placeholder="Original English (if provided)" maxLength={30000} />
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="primary" onClick={addOrSaveReveal} disabled={busy || (!textVi.trim() && !textEn.trim())}>{editId == null ? "Lưu mốc mới" : "Lưu sửa đổi"}</Button>
                {editId != null && <Button size="sm" variant="ghost" onClick={() => { setEditId(null); setTextVi(""); setTextEn(""); }}>Hủy sửa</Button>}
              </div>
            </div>

            <div className="flex flex-wrap gap-2 border-t border-[var(--color-line)] pt-3">
              {hasNewReveal && <p className="w-full text-[11px] text-[var(--color-warn)]">Phiên Search chưa có hint mới. Hãy cập nhật và xem lại kế hoạch GPT trước khi tìm.</p>}
              <p className="w-full text-[10.5px] text-[var(--color-fg-mute)]">Chép toàn bộ phần đã lộ, dán vào GPT Explore đang dùng như một đề mới. Nút này không gửi dữ liệu hoặc thay đổi GPT.</p>
              <Button size="sm" onClick={() => void copyGpt()} disabled={!selected.reveals.length}><Clipboard size={11} /> Chép đề đã lộ</Button>
              <Button size="sm" onClick={() => applyToSearch(selected)} disabled={!selected.reveals.length}>{linkedSession ? (hasNewReveal ? "Cập nhật Search" : "Mở Search") : "Đưa vào Search"}</Button>
            </div>
          </>}
        </div>
      </div>
    </Modal>
  );
}
