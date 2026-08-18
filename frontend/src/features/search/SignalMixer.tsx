/**
 * BÀN TRỘN TÍN HIỆU — thành phần trung tâm của giao diện.
 *
 * Nguyên tắc: KHÔNG CÓ SỐ NÀO VÔ HÌNH. Mọi trọng số đang áp dụng đều hiện bằng
 * chữ số ngay trên màn hình và sửa được tại chỗ — không nằm trong file config
 * hay menu con nào.
 *
 * Mượn thẳng từ bàn trộn âm thanh thật:
 *  - Công tắc bật/tắt riêng từng kênh. TẮT khác ĐẶT 0: tắt thì bỏ hẳn nhánh khỏi
 *    tính toán (nhanh hơn), đặt 0 vẫn chạy nhưng không góp điểm (để so sánh).
 *  - SOLO (Alt+click): tắt hết nhánh khác để xem riêng nhánh này cho ra gì —
 *    cực hữu ích khi gỡ câu khó.
 *  - Ô số gõ trực tiếp được: dưới áp lực thi đấu, gõ "0.8" nhanh hơn kéo chuột.
 *
 * `MixerStrip` là component THUẦN (điều khiển qua props) — dùng lại được cho
 * cả Search (bọc bởi ChannelStrip, gắn sessionStore) lẫn Temporal (state cục
 * bộ, xem pages/TemporalPage.tsx) — cùng 1 kiểu bàn trộn cho cả 2 màn hình.
 */
import { AlertTriangle, Info } from "lucide-react";
import { useCallback } from "react";

import { Button, Hint, cx } from "../../components/ui";
import { useSession } from "../../stores/sessionStore";
import type { SessionState } from "../../stores/sessionStore";
import { BRANCHES, BRANCH_COLOR, DEFAULT_WEIGHTS } from "../../types/api";

export interface MixerValue { enabled: boolean; weight: number }

export function MixerStrip({ branchKey, value, onToggle, onWeightChange, warn, hint }: {
  branchKey: string;
  value: MixerValue;
  onToggle: (e: React.MouseEvent) => void;
  onWeightChange: (w: number) => void;
  warn?: string | null;
  hint: string;
}) {
  const meta = BRANCHES.find((b) => b.key === branchKey);
  const color = BRANCH_COLOR[branchKey];
  const label = meta?.label ?? branchKey;
  const short = meta?.short ?? branchKey.slice(0, 4).toUpperCase();
  const { enabled, weight } = value;

  return (
    <div className={cx("flex items-center gap-2 py-[3px]", !enabled && "opacity-45")}>
      <button
        type="button"
        onClick={onToggle}
        title={enabled ? "Bấm để tắt · Alt+bấm để chỉ nghe riêng nhánh này" : "Bấm để bật · Alt+bấm để solo"}
        aria-pressed={enabled}
        className="h-2.5 w-2.5 shrink-0 rounded-full border transition-all"
        style={{
          borderColor: color,
          backgroundColor: enabled ? color : "transparent",
          boxShadow: enabled ? `0 0 6px color-mix(in srgb, ${color} 60%, transparent)` : undefined,
        }}
      />

      <span className="w-[34px] shrink-0 font-mono text-[10px] font-semibold" style={{ color }}>
        {short}
      </span>
      <span className="w-[92px] shrink-0 truncate text-[11.5px] text-[var(--color-fg-dim)]">
        {label}
      </span>

      <input
        type="range" min={0} max={2} step={0.05} value={weight}
        disabled={!enabled}
        onChange={(e) => onWeightChange(Number(e.target.value))}
        aria-label={`Trọng số ${label}`}
        className="mixer-fader h-1 flex-1 cursor-pointer appearance-none rounded-full"
        style={{
          background: `linear-gradient(to right, ${color} 0%, ${color} ${(weight / 2) * 100}%, var(--color-line) ${(weight / 2) * 100}%, var(--color-line) 100%)`,
          accentColor: color,
        }}
      />

      <input
        type="text" inputMode="decimal" value={weight.toFixed(2)}
        disabled={!enabled}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (Number.isFinite(v)) onWeightChange(Math.min(2, Math.max(0, v)));
        }}
        aria-label={`Giá trị trọng số ${label}`}
        className="w-[42px] shrink-0 rounded-[2px] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-1 py-[1px] text-right font-mono text-[11px] tabular-nums focus:border-[var(--color-focus)] focus:outline-none"
      />

      {warn && enabled ? (
        <Hint label={warn}>
          <span className="shrink-0 cursor-help text-[var(--color-warn)]"><AlertTriangle size={11} /></span>
        </Hint>
      ) : (
        <Hint label={hint}>
          <span className="shrink-0 cursor-help text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]">
            <Info size={11} />
          </span>
        </Hint>
      )}
    </div>
  );
}

/** Dùng trong Temporal — state CỤC BỘ (không lưu bền), không có logic solo (chỉ
 *  2-3 nhánh phụ nên solo ít cần thiết hơn so với 9 nhánh ở Search). */
export function TemporalMixerStrip({ branchKey, value, onChange }: {
  branchKey: string; value: MixerValue; onChange: (v: MixerValue) => void;
}) {
  const meta = BRANCHES.find((b) => b.key === branchKey);
  return (
    <MixerStrip
      branchKey={branchKey}
      value={value}
      hint={meta?.hint ?? ""}
      onToggle={() => onChange({ ...value, enabled: !value.enabled })}
      onWeightChange={(w) => onChange({ ...value, weight: w })}
    />
  );
}

/* ------------------------------ Bàn trộn của Search (gắn sessionStore) ------------------------------ */

/** Nhánh đã bật nhưng THIẾU đầu vào -> báo trước, đừng để người dùng chờ vô ích. */
function missingInput(key: string, s: SessionState): string | null {
  if (key === "dinov3" && !s.refImageB64 && !(s.refVideo && s.refN != null))
    return "Đang bật nhưng chưa có ảnh mẫu — thêm ảnh tham chiếu hoặc bấm 🔍 trên một khung hình.";
  if (key === "ocr" && !s.ocr.query.trim())
    return "Đang bật nhưng ô chữ trên hình còn trống.";
  if (key === "asr" && !s.asr.query.trim())
    return "Đang bật nhưng ô lời thoại còn trống.";
  if (key === "object" && s.objects.length === 0)
    return "Đang bật nhưng chưa thêm điều kiện vật thể nào.";
  if ((key === "pecore" || key === "beit3") && !s.query.trim())
    return "Cần câu truy vấn để dịch sang tiếng Anh.";
  return null;
}

function ChannelStrip({ branchKey }: { branchKey: string }) {
  const meta = BRANCHES.find((b) => b.key === branchKey)!;

  // Selector nguyên tử — kéo 1 fader không làm 9 kênh render lại.
  const weight = useSession((s) => s.sessions[s.activeId].weights[branchKey] ?? 0);
  const enabled = useSession((s) => !!s.sessions[s.activeId].enabled[branchKey]);
  const warn = useSession((s) => missingInput(branchKey, s.sessions[s.activeId]));
  const patch = useSession((s) => s.patch);
  const session = useSession((s) => s.sessions[s.activeId]);

  const setWeight = useCallback((w: number) => {
    patch({ weights: { ...session.weights, [branchKey]: w } });
  }, [patch, session.weights, branchKey]);

  const toggle = useCallback((e: React.MouseEvent) => {
    if (e.altKey) {
      // SOLO — chỉ nhánh này bật, các nhánh khác tắt hết.
      const next: Record<string, boolean> = {};
      for (const b of BRANCHES) next[b.key] = b.key === branchKey;
      patch({ enabled: next });
      return;
    }
    patch({ enabled: { ...session.enabled, [branchKey]: !enabled } });
  }, [patch, session.enabled, branchKey, enabled]);

  return (
    <MixerStrip branchKey={branchKey} value={{ enabled, weight }} warn={warn}
                hint={meta.hint} onToggle={toggle} onWeightChange={setWeight} />
  );
}

export function SignalMixer() {
  const patch = useSession((s) => s.patch);
  const resetToDefault = useSession((s) => s.resetToDefault);

  const enableAll = () => {
    const next: Record<string, boolean> = {};
    for (const b of BRANCHES) next[b.key] = true;
    patch({ enabled: next });
  };

  return (
    <div className="flex flex-col gap-0.5">
      <div className="mb-1.5 flex items-center gap-1">
        <Button size="sm" variant="ghost" onClick={enableAll}>Bật hết</Button>
        <Button size="sm" variant="ghost" onClick={resetToDefault}
                title="Trọng số về mặc định, tắt+xoá OCR/ASR, bỏ giới hạn Thu hẹp video">
          Mặc định
        </Button>
      </div>

      {BRANCHES.filter((b) => b.kind === "vector").map((b) => (
        <ChannelStrip key={b.key} branchKey={b.key} />
      ))}

      <div className="my-1.5 border-t border-dashed border-[var(--color-line)]" />
      <div className="mb-0.5 label-xs">Tín hiệu chữ — chỉ chạy khi bạn tự nhập</div>

      {BRANCHES.filter((b) => b.kind === "text").map((b) => (
        <ChannelStrip key={b.key} branchKey={b.key} />
      ))}

      <p className="mt-2 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
        Alt+bấm chấm tròn = chỉ chạy riêng nhánh đó. Số mặc định chỉ là điểm xuất
        phát — chỉnh thoải mái theo từng câu.
      </p>
    </div>
  );
}

export { DEFAULT_WEIGHTS };
