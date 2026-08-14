/**
 * Các panel tín hiệu CHỮ: OCR, lời thoại, vật thể, loại trừ.
 *
 * Điểm chung: CHỈ chạy khi người dùng tự nhập — hệ thống không đoán hộ. Mỗi panel
 * có lựa chọn "cộng điểm" vs "lọc cứng" hiện rõ, vì đây là hai chiến thuật khác
 * hẳn nhau: cộng điểm khi không chắc, lọc cứng khi chắc chắn.
 */
import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Button, Label, NumInput, Select, TextInput, cx } from "../../components/ui";
import { useSession } from "../../stores/sessionStore";
import type { TextMode } from "../../types/api";

/* ------------------------------ chung ------------------------------ */

function ModeSwitch({ value, onChange, filterHint }: {
  value: TextMode; onChange: (v: TextMode) => void; filterHint: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-1">
        {(["score", "filter"] as TextMode[]).map((m) => (
          <button
            key={m} type="button" onClick={() => onChange(m)}
            className={cx(
              "flex-1 rounded-[var(--radius-sm)] border px-2 py-1 text-[11px] transition-colors",
              value === m
                ? "border-[var(--color-focus)] bg-[color-mix(in_srgb,var(--color-focus)_15%,transparent)] text-[var(--color-fg)]"
                : "border-[var(--color-line)] text-[var(--color-fg-dim)] hover:border-[var(--color-line-hi)]",
            )}
          >
            {m === "score" ? "Cộng điểm" : "Lọc cứng"}
          </button>
        ))}
      </div>
      {value === "filter" && (
        <p className="text-[10.5px] leading-snug text-[var(--color-warn)]">{filterHint}</p>
      )}
    </div>
  );
}

/* ------------------------------ OCR ------------------------------ */

export function OcrPanel() {
  const ocr = useSession((s) => s.sessions[s.activeId].ocr);
  const enabled = useSession((s) => !!s.sessions[s.activeId].enabled.ocr);
  const patch = useSession((s) => s.patch);
  const session = useSession((s) => s.sessions[s.activeId]);

  const set = (u: Partial<typeof ocr>) => {
    patch({ ocr: { ...ocr, ...u } });
    // Gõ chữ vào là tự bật nhánh — không bắt người dùng nhớ bật thêm công tắc.
    if (u.query && u.query.trim() && !enabled)
      patch({ enabled: { ...session.enabled, ocr: true } });
  };

  return (
    <div className="flex flex-col gap-2">
      <TextInput
        value={ocr.query}
        onChange={(e) => set({ query: e.target.value })}
        placeholder="Vài chữ bạn NHỚ được trong khung hình, vd: THỜI SỰ, HTV1…"
      />
      <p className="text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
        Chỉ cần gõ những từ bạn nhớ — không cần biết hết chữ trong ảnh, thứ tự tự
        do, và tự động chấp nhận sai chính tả nhẹ cho từng từ.
      </p>
      <ModeSwitch
        value={ocr.mode} onChange={(m) => set({ mode: m })}
        filterHint="Các nhánh khác sẽ CHỈ tìm trong những khung hình khớp chữ này. Ra 0 kết quả thì chuyển về Cộng điểm."
      />
    </div>
  );
}

/* ------------------------------ Lời thoại ------------------------------ */

export function AsrPanel() {
  const asr = useSession((s) => s.sessions[s.activeId].asr);
  const patch = useSession((s) => s.patch);
  const session = useSession((s) => s.sessions[s.activeId]);

  const set = (u: Partial<typeof asr>) => {
    patch({ asr: { ...asr, ...u } });
    if (u.query && u.query.trim() && !session.enabled.asr)
      patch({ enabled: { ...session.enabled, asr: true } });
  };

  return (
    <div className="flex flex-col gap-2">
      <TextInput
        value={asr.query}
        onChange={(e) => set({ query: e.target.value })}
        placeholder="Lời người trong video nói, vd: giá xăng tăng…"
      />
      <div className="flex gap-3">
        <label className="flex items-center gap-1.5 text-[11px] text-[var(--color-fg-dim)]">
          <input type="checkbox" checked={asr.lexical}
                 onChange={(e) => set({ lexical: e.target.checked })}
                 className="h-3 w-3 accent-[var(--color-focus)]" />
          Khớp đúng từ
        </label>
        <label className="flex items-center gap-1.5 text-[11px] text-[var(--color-fg-dim)]">
          <input type="checkbox" checked={asr.semantic}
                 onChange={(e) => set({ semantic: e.target.checked })}
                 className="h-3 w-3 accent-[var(--color-focus)]" />
          Khớp ý nghĩa
        </label>
      </div>

      <div className="flex flex-col gap-1">
        <Label className="mb-0">Cửa sổ thời gian quanh đoạn nói</Label>
        <div className="flex items-center gap-2">
          <span className="w-[38px] text-[10.5px] text-[var(--color-fg-mute)]">trước</span>
          <input type="range" min={0} max={15} step={0.5} value={asr.window_before}
                 onChange={(e) => set({ window_before: Number(e.target.value) })}
                 className="h-1 flex-1 accent-[var(--color-focus)]"
                 aria-label="Cửa sổ trước" />
          <span className="w-[34px] text-right font-mono text-[11px] tabular-nums">{asr.window_before}s</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-[38px] text-[10.5px] text-[var(--color-fg-mute)]">sau</span>
          <input type="range" min={0} max={15} step={0.5} value={asr.window_after}
                 onChange={(e) => set({ window_after: Number(e.target.value) })}
                 className="h-1 flex-1 accent-[var(--color-focus)]"
                 aria-label="Cửa sổ sau" />
          <span className="w-[34px] text-right font-mono text-[11px] tabular-nums">{asr.window_after}s</span>
        </div>
        <p className="text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
          Lời dẫn thường nói TRƯỚC rồi hình mới lên, nên cửa sổ "sau" hay cần rộng hơn.
        </p>
      </div>

      <ModeSwitch
        value={asr.mode} onChange={(m) => set({ mode: m })}
        filterHint="Các nhánh khác sẽ CHỈ tìm trong khung hình quanh đoạn lời thoại khớp."
      />
    </div>
  );
}

/* ------------------------------ Vật thể + màu + vị trí ------------------------------ */

const COMMON_CLASSES = ["person", "car", "truck", "motorcycle", "bicycle", "bus", "dog", "cat",
  "chair", "bottle", "boat", "bird", "horse", "cow", "tv", "laptop", "cell phone", "book"];
const COLORS = ["red", "orange", "yellow", "green", "blue", "purple", "pink",
  "white", "black", "gray", "brown"];

export function ObjectGridPicker() {
  const objects = useSession((s) => s.sessions[s.activeId].objects);
  const session = useSession((s) => s.sessions[s.activeId]);
  const patch = useSession((s) => s.patch);

  const [cls, setCls] = useState("person");
  const [color, setColor] = useState("");

  const add = () => {
    if (!cls.trim()) return;
    patch({
      objects: [...objects, { cls: cls.trim(), color: color || null, min_count: 1 }],
      enabled: { ...session.enabled, object: true },
    });
    setColor("");
  };

  const del = (i: number) => patch({ objects: objects.filter((_, k) => k !== i) });

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
        Dùng khi hai cảnh nhìn gần giống nhau và chỉ khác một chi tiết — mô tả bằng
        cấu trúc thay vì câu chữ: "có vật màu đỏ".
      </p>

      <div className="flex flex-col gap-1">
        <input
          list="obj-classes" value={cls} onChange={(e) => setCls(e.target.value)}
          placeholder="vật thể (person, car…)"
          className="w-full rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-2 py-1 text-[12px] focus:border-[var(--color-focus)] focus:outline-none"
        />
        <datalist id="obj-classes">
          {COMMON_CLASSES.map((c) => <option key={c} value={c} />)}
        </datalist>
        <Select value={color} onChange={(e) => setColor(e.target.value)} className="py-1 text-[12px]">
          <option value="">— màu bất kỳ —</option>
          {COLORS.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </div>

      <Button size="sm" onClick={add} disabled={!cls.trim()}>
        <Plus size={11} /> Thêm điều kiện
      </Button>

      {objects.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {objects.map((o, i) => (
            <span key={i}
                  className="flex items-center gap-1 rounded-full border border-[var(--color-sig-object)] px-2 py-0.5 text-[11px]"
                  style={{ color: "var(--color-sig-object)" }}>
              {o.cls}{o.color ? ` · ${o.color}` : ""}
              <button type="button" onClick={() => del(i)} aria-label="Xoá điều kiện"
                      className="hover:text-[var(--color-err)]"><X size={10} /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------ Mệnh đề loại trừ ------------------------------ */

export function NegativePanel() {
  const neg = useSession((s) => s.sessions[s.activeId].negative);
  const patch = useSession((s) => s.patch);
  const set = (u: Partial<typeof neg>) => patch({ negative: { ...neg, ...u } });

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
        Khi cả trang kết quả toàn cảnh sai, đẩy nhóm sai xuống thường hiệu quả hơn
        là cố mô tả kỹ hơn cảnh đúng.
      </p>
      <TextInput
        value={neg.text}
        onChange={(e) => set({ text: e.target.value })}
        placeholder="Cảnh KHÔNG muốn thấy, vd: cảnh trong phòng họp"
      />
      <div className="flex items-center gap-2">
        <span className="w-[52px] text-[10.5px] text-[var(--color-fg-mute)]">trừ điểm</span>
        <input type="range" min={0} max={1.5} step={0.05} value={neg.weight}
               onChange={(e) => set({ weight: Number(e.target.value) })}
               className="h-1 flex-1 accent-[var(--color-err)]"
               aria-label="Mức trừ điểm" />
        <span className="w-[34px] text-right font-mono text-[11px] tabular-nums">{neg.weight.toFixed(2)}</span>
      </div>
      <label className="flex items-center gap-1.5 text-[11px] text-[var(--color-fg-dim)]">
        <input
          type="checkbox" checked={neg.hardThreshold != null}
          onChange={(e) => set({ hardThreshold: e.target.checked ? 0.8 : null })}
          className="h-3 w-3 accent-[var(--color-focus)]"
        />
        Loại hẳn khung vượt ngưỡng giống
      </label>
      {neg.hardThreshold != null && (
        <NumInput
          value={neg.hardThreshold}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            if (Number.isFinite(v)) set({ hardThreshold: Math.min(1, Math.max(0, v)) });
          }}
          className="py-1 text-[12px]"
        />
      )}
    </div>
  );
}
