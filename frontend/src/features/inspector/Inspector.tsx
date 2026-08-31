/**
 * Rail phải — 4 tab tra cứu.
 *
 * "Vì sao" là hiện thân của nguyên tắc xếp hạng phải giải thích được: mọi khung
 * hình đều trả lời được câu "vì sao nó đứng đây". Dòng "theo mệnh đề" là công cụ
 * chẩn đoán mạnh nhất — thấy mệnh đề nào yếu là biết ngay nên viết lại nó hay hạ
 * trọng số, thay vì chỉ biết "kết quả sai" mà không rõ sai ở đâu.
 */
import { DndContext, closestCenter } from "@dnd-kit/core";
import type { DragEndEvent } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { thumbUrl } from "../../api/client";
import { Button, EmptyState, Label, TextArea, TextInput, cx } from "../../components/ui";
import { useSession } from "../../stores/sessionStore";
import type { PinnedFrame } from "../../stores/sessionStore";
import { framesPerRow, useSubmission } from "../../stores/submissionStore";
import { useUi } from "../../stores/uiStore";
import { TeamSubmissionPanel } from "../teamSubmission/TeamSubmissionPanel";
import { BRANCHES, BRANCH_COLOR } from "../../types/api";
import type { SearchHit } from "../../types/api";

/* ------------------------------ Vì sao ------------------------------ */

function WhyPanel({ hit }: { hit: SearchHit | null }) {
  if (!hit) {
    return (
      <EmptyState
        title="Chọn một khung hình"
        hint="Bấm vào một ô kết quả (hoặc dùng phím mũi tên) để xem vì sao nó được xếp ở vị trí đó."
      />
    );
  }
  const ex = hit.explain;
  const total = ex?.branches.reduce((a, b) => a + b.rrf, 0) ?? hit.score;

  return (
    <div className="flex flex-col gap-3 p-3">
      <div>
        <div className="font-mono text-[12px]">{hit.video}</div>
        <div className="font-mono text-[11px] tabular-nums text-[var(--color-fg-mute)]">
          hạng #{hit.rank} · frame {hit.frame_idx} · điểm {hit.score.toFixed(5)}
        </div>
      </div>

      <img src={thumbUrl(hit.video, hit.n)} alt=""
           className="w-full rounded-[var(--radius-sm)] border border-[var(--color-line)]" />

      {ex?.branches?.length ? (
        <div>
          <Label>Đóng góp của từng nhánh</Label>
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-[var(--color-fg-mute)]">
                <th className="pb-1 text-left font-normal">Nhánh</th>
                <th className="pb-1 text-right font-normal">Hạng</th>
                <th className="pb-1 text-right font-normal">Điểm gốc</th>
                <th className="pb-1 text-right font-normal">Trọng số</th>
                <th className="pb-1 text-right font-normal">Góp</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {ex.branches.map((b) => {
                const meta = BRANCHES.find((x) => x.key === b.branch);
                return (
                  <tr key={b.branch} className="border-t border-[var(--color-line)]">
                    <td className="py-1">
                      <span className="inline-flex items-center gap-1">
                        <span className="h-1.5 w-1.5 rounded-full"
                              style={{ backgroundColor: BRANCH_COLOR[b.branch] }} />
                        <span style={{ color: BRANCH_COLOR[b.branch] }}>{meta?.short ?? b.branch}</span>
                      </span>
                    </td>
                    <td className="py-1 text-right text-[var(--color-fg-dim)]">{b.rank}</td>
                    <td className="py-1 text-right text-[var(--color-fg-dim)]">{b.raw.toFixed(3)}</td>
                    <td className="py-1 text-right text-[var(--color-fg-dim)]">{b.weight.toFixed(2)}</td>
                    <td className="py-1 text-right">{b.rrf.toFixed(5)}</td>
                  </tr>
                );
              })}
              {Object.entries(ex.penalties ?? {}).map(([k, v]) => (
                <tr key={k} className="border-t border-[var(--color-line)] text-[var(--color-err)]">
                  <td className="py-1" colSpan={4}>{k}</td>
                  <td className="py-1 text-right">{v.toFixed(5)}</td>
                </tr>
              ))}
              <tr className="border-t border-[var(--color-line-hi)] font-semibold">
                <td className="py-1" colSpan={4}>Tổng</td>
                <td className="py-1 text-right">{total.toFixed(5)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-[11px] text-[var(--color-fg-mute)]">
          Chưa có phân rã — chạy lại tìm kiếm để lấy chi tiết.
        </p>
      )}

      {!!ex?.clauses?.length && (
        <div>
          <Label>Theo từng mệnh đề</Label>
          <p className="mb-1 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
            Mệnh đề nào điểm thấp là chỗ nên viết lại hoặc hạ trọng số.
          </p>
          <div className="flex flex-col gap-1">
            {ex.clauses.map((c, i) => {
              const max = Math.max(...ex.clauses.map((x) => x.score), 1e-9);
              const weak = c.score < max * 0.45;
              return (
                <div key={i} className="flex items-center gap-1.5">
                  <span className="w-[104px] shrink-0 truncate text-[11px]" title={c.text}>{c.text}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-line)]">
                    <div className="h-full rounded-full"
                         style={{ width: `${(c.score / max) * 100}%`,
                                  backgroundColor: weak ? "var(--color-warn)" : "var(--color-sig-metaclip2)" }} />
                  </div>
                  <span className="w-[34px] shrink-0 text-right font-mono text-[10px] tabular-nums text-[var(--color-fg-mute)]">
                    {c.score.toFixed(2)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {hit.content?.ocr && (
        <div>
          <Label className="mb-0.5" >Chữ trên hình</Label>
          <p className="whitespace-pre-wrap text-[11px] leading-snug text-[var(--color-fg-dim)]">{hit.content.ocr}</p>
        </div>
      )}
      {hit.content?.caption && (
        <div>
          <Label className="mb-0.5">Mô tả cảnh</Label>
          <p className="text-[11px] leading-snug text-[var(--color-fg-dim)]">{hit.content.caption}</p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------ Khay ghim ------------------------------ */

function PinRow({ pin }: { pin: PinnedFrame }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: pin.id });
  const setPinNote = useSession((s) => s.setPinNote);
  const togglePin = useSession((s) => s.togglePin);
  const openDetail = useUi((s) => s.openDetail);
  const files = useSubmission((s) => s.files);
  const activeName = useSubmission((s) => s.activeName);
  const addRow = useSubmission((s) => s.addRow);

  const toDraft = () => {
    const f = activeName ? files[activeName] : null;
    if (!f) { toast.error("Chưa chọn file nộp bài."); return; }
    const want = framesPerRow(f);
    addRow(f.name, {
      video: pin.video,
      frames: [String(pin.frame_idx), ...Array(Math.max(0, want - 1)).fill("")],
    });
    toast.success(`Đã đưa vào ${f.name}.csv`);
  };

  return (
    <div ref={setNodeRef}
         style={{ transform: CSS.Transform.toString(transform), transition }}
         className={cx("flex gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-line)] p-1.5",
           isDragging && "opacity-60")}>
      <button {...attributes} {...listeners} aria-label="Kéo để sắp xếp"
              className="cursor-grab text-[var(--color-fg-mute)] active:cursor-grabbing">
        <GripVertical size={12} />
      </button>
      <img src={thumbUrl(pin.video, pin.n)} alt="" loading="lazy"
           onClick={() => openDetail({
             id: pin.id, video: pin.video, n: pin.n, frame_idx: pin.frame_idx,
             score: 0, thumb_url: thumbUrl(pin.video, pin.n), pts_time: pin.pts_time, rank: 0,
           })}
           className="h-[40px] w-[71px] shrink-0 cursor-pointer rounded-[2px] object-cover" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="truncate font-mono text-[10px] tabular-nums text-[var(--color-fg-dim)]">
          {pin.video} · f{pin.frame_idx}
        </div>
        <TextInput value={pin.note} onChange={(e) => setPinNote(pin.id, e.target.value)}
                   placeholder="ghi chú…" className="px-1 py-0.5 text-[10.5px]" />
      </div>
      <div className="flex flex-col gap-0.5">
        <Button size="sm" variant="ghost" onClick={toDraft} title="Đưa vào bản nháp nộp bài">→</Button>
        <Button size="sm" variant="ghost" onClick={() =>
          togglePin({ id: pin.id, video: pin.video, n: pin.n, frame_idx: pin.frame_idx, pts_time: pin.pts_time })}>
          <X size={11} />
        </Button>
      </div>
    </div>
  );
}

function PinboardPanel() {
  const pins = useSession((s) => s.sessions[s.activeId].pins);
  const reorderPins = useSession((s) => s.reorderPins);
  const clearPins = useSession((s) => s.clearPins);

  if (pins.length === 0) {
    return (
      <EmptyState
        title="Chưa ghim khung hình nào"
        hint="Nhấn P trên một khung hình để ghim. Khay ghim là chỗ để dành các ứng viên đang cân nhắc — tách bạch với bản nháp nộp bài, nơi chỉ chứa đáp án đã chốt."
      />
    );
  }

  const onEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    reorderPins(pins.findIndex((p) => p.id === active.id), pins.findIndex((p) => p.id === over.id));
  };

  return (
    <div className="flex flex-col gap-1.5 p-3">
      <div className="flex items-center gap-2">
        <span className="flex-1 text-[11px] text-[var(--color-fg-dim)]">{pins.length} khung đã ghim</span>
        <Button size="sm" variant="ghost" onClick={clearPins}><Trash2 size={11} /> Bỏ hết</Button>
      </div>
      <DndContext collisionDetection={closestCenter} onDragEnd={onEnd}>
        <SortableContext items={pins.map((p) => p.id)} strategy={verticalListSortingStrategy}>
          {pins.map((p) => <PinRow key={p.id} pin={p} />)}
        </SortableContext>
      </DndContext>
    </div>
  );
}

/* ------------------------------ Ghi chú ------------------------------ */

function NotesPanel() {
  const notes = useSession((s) => s.sessions[s.activeId].notes);
  const patch = useSession((s) => s.patch);
  return (
    <div className="flex h-full flex-col gap-1 p-3">
      <p className="text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
        Ghi lại đã thử gì cho câu này. Khi làm 30 câu trong 2 tiếng, "câu 12 đã thử
        gì rồi" là thông tin sống còn.
      </p>
      <TextArea value={notes} onChange={(e) => patch({ notes: e.target.value })}
                placeholder="vd: đã thử 'người mặc áo đỏ' → toàn ra cảnh trong nhà. Bật loại trừ 'phòng họp' thì khá hơn…"
                className="min-h-[220px] flex-1 text-[12px]" />
    </div>
  );
}

/* ------------------------------ Vỏ ngoài ------------------------------ */

const TABS = [
  { key: "explain", label: "Giải thích" },
  { key: "pins", label: "Ghim" },
  { key: "submit", label: "Nộp bài" },
  { key: "share", label: "Chia sẻ" },
  { key: "notes", label: "Ghi chú" },
] as const;

export function Inspector({ current, submitPanel }: {
  current: SearchHit | null; submitPanel: React.ReactNode;
}) {
  const tab = useUi((s) => s.inspectorTab);
  const setTab = useUi((s) => s.setInspectorTab);
  const pinCount = useSession((s) => s.sessions[s.activeId].pins.length);

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 border-b border-[var(--color-line)]">
        {TABS.map((t) => (
          <button key={t.key} type="button" onClick={() => setTab(t.key)}
                  className={cx("flex-1 border-b-2 px-2 py-1.5 text-[11.5px] transition-colors",
                    tab === t.key
                      ? "border-[var(--color-focus)] text-[var(--color-fg)]"
                      : "border-transparent text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]")}>
            {t.label}
            {t.key === "pins" && pinCount > 0 && (
              <span className="ml-1 rounded-full bg-[var(--color-pin)] px-1 font-mono text-[9px] text-black">
                {pinCount}
              </span>
            )}
          </button>
        ))}
      </div>
      <div className={cx("min-h-0 flex-1", (tab === "submit" || tab === "share") ? "overflow-hidden" : "overflow-y-auto")}>
        {tab === "explain" && <WhyPanel hit={current} />}
        {tab === "pins" && <PinboardPanel />}
        {tab === "submit" && submitPanel}
        {tab === "share" && <TeamSubmissionPanel />}
        {tab === "notes" && <NotesPanel />}
      </div>
    </div>
  );
}
