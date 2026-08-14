/**
 * Ô truy vấn + mệnh đề thị giác + bản dịch.
 *
 * Nguyên tắc P4 (tự động = ĐỀ XUẤT, không phải quyết định): LLM tách mệnh đề rồi
 * hiện ra dạng thẻ SỬA/XOÁ/TẮT được. Bản dịch tiếng Anh cũng hiện ra và sửa được
 * — đây là điểm mù lớn nếu để dịch chạy ngầm: dịch sai nghĩa thì hai nhánh
 * PE-Core và BEiT-3 hỏng hoàn toàn mà người dùng không hề biết.
 */
import { Languages, Plus, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, Label, TextArea, TextInput, cx } from "../../components/ui";
import { useSession } from "../../stores/sessionStore";
import { useClauseSuggest } from "./useSearchQuery";

export function QueryPanel({ onSubmit }: { onSubmit: () => void }) {
  const s = useSession((st) => st.sessions[st.activeId]);
  const patch = useSession((st) => st.patch);
  const suggest = useClauseSuggest();
  const [enDraft, setEnDraft] = useState<string[]>([]);

  useEffect(() => { setEnDraft([]); }, [s.id]);

  const doSuggest = async () => {
    if (!s.query.trim()) return;
    const r = await suggest.mutateAsync(s.query);
    patch({
      clauses: r.vi.map((t) => ({ text: t, weight: 1, enabled: true })),
      clausesDirty: true,
    });
    setEnDraft(r.en);
  };

  const setClause = (i: number, upd: Partial<{ text: string; weight: number; enabled: boolean }>) =>
    patch({
      clauses: s.clauses.map((c, k) => (k === i ? { ...c, ...upd } : c)),
      clausesDirty: true,
    });

  const addClause = () =>
    patch({ clauses: [...s.clauses, { text: "", weight: 1, enabled: true }], clausesDirty: true });

  const delClause = (i: number) =>
    patch({ clauses: s.clauses.filter((_, k) => k !== i), clausesDirty: true });

  return (
    <div className="flex flex-col gap-2">
      <TextArea
        rows={3}
        value={s.query}
        onChange={(e) => patch({ query: e.target.value })}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSubmit(); }
        }}
        placeholder="Mô tả cảnh cần tìm bằng tiếng Việt… (Enter để tìm, Shift+Enter xuống dòng)"
        data-query-box
      />

      <div className="flex items-center gap-1.5">
        <Button size="sm" onClick={doSuggest} disabled={!s.query.trim() || suggest.isPending}>
          <Sparkles size={11} />
          {suggest.isPending ? "Đang tách…" : "Tách mệnh đề"}
        </Button>
        <Button size="sm" variant="ghost" onClick={addClause}>
          <Plus size={11} /> Thêm tay
        </Button>
        {s.clauses.length > 0 && (
          <Button size="sm" variant="ghost"
                  onClick={() => patch({ clauses: [], clausesDirty: false })}>
            <Trash2 size={11} /> Xoá hết
          </Button>
        )}
      </div>

      {s.clauses.length > 0 && (
        <div className="flex flex-col gap-1">
          <Label>Mệnh đề thị giác — sửa, tắt hoặc chỉnh trọng số riêng</Label>
          {s.clauses.map((c, i) => (
            <div key={i} className={cx("flex items-center gap-1", !c.enabled && "opacity-45")}>
              <input
                type="checkbox" checked={c.enabled}
                onChange={(e) => setClause(i, { enabled: e.target.checked })}
                aria-label={`Bật mệnh đề ${i + 1}`}
                className="h-3 w-3 shrink-0 accent-[var(--color-focus)]"
              />
              <TextInput
                value={c.text}
                onChange={(e) => setClause(i, { text: e.target.value })}
                placeholder={`Mệnh đề ${i + 1}`}
                className="flex-1 py-1 text-[12px]"
              />
              <input
                type="text" inputMode="decimal" value={c.weight.toFixed(1)}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  if (Number.isFinite(v)) setClause(i, { weight: Math.max(0, Math.min(3, v)) });
                }}
                aria-label={`Trọng số mệnh đề ${i + 1}`}
                className="w-[36px] shrink-0 rounded-[2px] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-1 py-1 text-right font-mono text-[11px] tabular-nums focus:border-[var(--color-focus)] focus:outline-none"
              />
              <button type="button" onClick={() => delClause(i)} aria-label="Xoá mệnh đề"
                      className="shrink-0 p-1 text-[var(--color-fg-mute)] hover:text-[var(--color-err)]">
                <X size={12} />
              </button>
            </div>
          ))}

          <div className="mt-1 flex items-center gap-2">
            <span className="text-[11px] text-[var(--color-fg-dim)]">Gộp mệnh đề: max + α·mean</span>
            <input
              type="range" min={0} max={1} step={0.05} value={s.alpha}
              onChange={(e) => patch({ alpha: Number(e.target.value) })}
              aria-label="Hệ số alpha khi gộp mệnh đề"
              className="h-1 flex-1 accent-[var(--color-focus)]"
            />
            <span className="w-[30px] text-right font-mono text-[11px] tabular-nums text-[var(--color-fg-dim)]">
              {s.alpha.toFixed(2)}
            </span>
          </div>
        </div>
      )}

      {enDraft.length > 0 && (
        <div className="flex flex-col gap-1 rounded-[var(--radius-sm)] border border-dashed border-[var(--color-line)] p-2">
          <Label className="mb-0 flex items-center gap-1">
            <Languages size={10} /> Bản dịch cho PE-Core &amp; BEiT-3 — sửa được
          </Label>
          <p className="mb-1 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
            Hai nhánh này chỉ hiểu tiếng Anh. Dịch sai nghĩa là chúng hỏng lặng lẽ,
            nên bản dịch luôn hiện ra ở đây để bạn kiểm và sửa.
          </p>
          {enDraft.map((t, i) => (
            <TextInput
              key={i} value={s.translations[i] ?? t}
              onChange={(e) =>
                patch({
                  translations: { ...s.translations, [i]: e.target.value },
                  translationsDirty: true,
                })}
              className="py-1 text-[12px]"
            />
          ))}
        </div>
      )}
    </div>
  );
}
