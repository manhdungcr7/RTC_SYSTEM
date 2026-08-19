/**
 * Ô kết quả. Mật độ thông tin cao nhất có thể mà không tốn thêm cú bấm nào:
 * ảnh, video+mốc giờ, hạng, điểm, và THANH ĐÓNG GÓP 9 nhánh.
 *
 * Thanh đóng góp là hiện thân của "xếp hạng phải giải thích được": mỗi vạch là
 * một nhánh, tô đúng màu định danh của nhánh đó, cao theo tỉ lệ đóng góp. Liếc
 * qua là biết ô này thắng nhờ OCR (vạch trắng cao) hay nhờ nhiều nhánh cùng
 * đồng thuận (nhiều vạch đều nhau) — không cần mở bảng nào.
 */
import { Check, Maximize2, Pin, Search, X } from "lucide-react";
import { memo } from "react";

import { cx } from "../../components/ui";
import { BRANCHES, BRANCH_COLOR } from "../../types/api";
import type { SearchHit } from "../../types/api";

export function ContributionBar({ hit, height = 14 }: { hit: SearchHit; height?: number }) {
  const branches = hit.explain?.branches;
  if (!branches?.length) return null;
  const max = Math.max(...branches.map((b) => b.rrf), 1e-9);
  const byKey = new Map(branches.map((b) => [b.branch, b]));

  return (
    <div className="flex items-end gap-[1.5px]" style={{ height }} aria-hidden>
      {BRANCHES.map((b) => {
        const c = byKey.get(b.key);
        const h = c ? Math.max(2, (c.rrf / max) * height) : 1;
        return (
          <div
            key={b.key}
            className="flex-1 rounded-[1px] transition-all"
            style={{
              height: h,
              backgroundColor: c ? BRANCH_COLOR[b.key] : "var(--color-line)",
              opacity: c ? 0.92 : 0.35,
            }}
          />
        );
      })}
    </div>
  );
}

const fmtTime = (t: number | null) => {
  if (t == null) return "—";
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

interface Props {
  hit: SearchHit;
  selected: boolean;
  pinned: boolean;
  good: boolean;
  bad: boolean;
  onOpen: () => void;
  onPin: () => void;
  onRef: () => void;
  onGood: () => void;
  onBad: () => void;
  onCompare: () => void;
  bulkMode?: boolean;
  bulkChecked?: boolean;
  bulkOrder?: number;   // 1-based thứ tự sẽ ghi ra dòng CSV, undefined = chưa chọn
  onToggleBulk?: () => void;
}

export const ResultTile = memo(function ResultTile({
  hit, selected, pinned, good, bad, onOpen, onPin, onRef, onGood, onBad, onCompare,
  bulkMode, bulkChecked, bulkOrder, onToggleBulk,
}: Props) {
  return (
    <div
      data-bulk-tile={bulkMode ? hit.id : undefined}
      className={cx(
        "group relative overflow-hidden rounded-[var(--radius-sm)] border bg-[var(--color-panel)] transition-colors",
        bulkChecked
          ? "border-[var(--color-focus)]"
          : selected
            ? "border-[var(--color-focus)]"
            : pinned
              ? "border-[var(--color-pin)]"
              : "border-[var(--color-line)] hover:border-[var(--color-line-hi)]",
      )}
    >
      <button type="button" onClick={bulkMode ? onToggleBulk : onOpen} className="block w-full text-left"
              aria-label={`Mở ${hit.video} khung ${hit.frame_idx}`}>
        <img
          src={hit.thumb_url} alt="" loading="lazy" decoding="async"
          className="aspect-video w-full bg-black object-cover"
        />
      </button>

      {bulkMode && (
        <label className="absolute left-1 top-1 flex h-5 w-5 items-center justify-center rounded-[2px] border bg-black/72"
               style={bulkChecked ? { borderColor: "var(--color-focus)" } : { borderColor: "rgba(255,255,255,.3)" }}
               onClick={(e) => e.stopPropagation()}>
          <input type="checkbox" checked={!!bulkChecked} onChange={onToggleBulk} className="sr-only" />
          <span className="font-mono text-[10px] font-semibold tabular-nums"
                style={{ color: bulkChecked ? "var(--color-focus)" : "var(--color-fg-mute)" }}>
            {bulkChecked ? bulkOrder : ""}
          </span>
        </label>
      )}
      {/* Hạng — luôn thấy, không cần rê chuột */}
      {!bulkMode && (
        <span className="pointer-events-none absolute left-1 top-1 rounded-[2px] bg-black/72 px-1.5 py-[1px] font-mono text-[10px] font-semibold tabular-nums">
          #{hit.rank}
        </span>
      )}

      {(good || bad) && (
        <span
          className="pointer-events-none absolute right-1 top-1 rounded-full p-[3px]"
          style={{ backgroundColor: good ? "var(--color-ok)" : "var(--color-err)" }}
        >
          {good ? <Check size={9} color="#08130D" /> : <X size={9} color="#1A0A0A" />}
        </span>
      )}
      {pinned && !good && !bad && (
        <Pin size={11} className="pointer-events-none absolute right-1 top-1 fill-[var(--color-pin)] text-[var(--color-pin)]" />
      )}

      {/* Hành động — chỉ hiện khi rê chuột, khỏi chiếm chỗ lúc quét mắt */}
      <div className="absolute inset-x-0 bottom-[38px] flex justify-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        {[
          { fn: onGood, icon: <Check size={11} />, title: "Giống cái tôi tìm (A)", on: good, color: "var(--color-ok)" },
          { fn: onBad, icon: <X size={11} />, title: "Không giống (D)", on: bad, color: "var(--color-err)" },
          { fn: onPin, icon: <Pin size={11} />, title: "Ghim (P)", on: pinned, color: "var(--color-pin)" },
          { fn: onRef, icon: <Search size={11} />, title: "Dùng làm ảnh mẫu (R)", on: false },
          { fn: onCompare, icon: <Maximize2 size={11} />, title: "Thêm vào so sánh (C)", on: false },
        ].map((b, i) => (
          <button
            key={i} type="button" title={b.title} aria-label={b.title}
            onClick={(e) => { e.stopPropagation(); b.fn(); }}
            className="rounded-[2px] border border-white/15 bg-black/78 p-1 hover:bg-black"
            style={b.on ? { color: b.color, borderColor: b.color } : undefined}
          >
            {b.icon}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-[3px] px-1.5 pb-1.5 pt-1">
        <div className="flex items-baseline justify-between gap-1">
          <span className="truncate font-mono text-[10px] text-[var(--color-fg-dim)]">{hit.video}</span>
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-[var(--color-fg-mute)]">
            {fmtTime(hit.pts_time)}
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-1">
          <span className="font-mono text-[10px] tabular-nums text-[var(--color-fg-mute)]">
            f{hit.frame_idx}
          </span>
          <span className="font-mono text-[10px] tabular-nums text-[var(--color-fg-mute)]">
            {hit.score.toFixed(4)}
          </span>
        </div>
        <ContributionBar hit={hit} />
      </div>
    </div>
  );
});
