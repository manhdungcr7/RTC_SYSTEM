/** Thành phần dùng chung. Xây trên Radix (xử lý đúng tiêu điểm bàn phím, Esc,
 *  vị trí popover — thứ rất tốn công nếu tự viết) nhưng tự tạo kiểu hoàn toàn để
 *  giữ mật độ thông tin cao, hợp công cụ thi đấu. */
import * as Dialog from "@radix-ui/react-dialog";
import * as Popover from "@radix-ui/react-popover";
import * as Tooltip from "@radix-ui/react-tooltip";
import { ChevronDown, X } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

export const cx = (...parts: (string | false | null | undefined)[]) =>
  parts.filter(Boolean).join(" ");

/* ---------------- Khối gập được (dùng cho mọi panel ở rail trái) ---------------- */

export function Section({ title, children, defaultOpen = true, right, dense }: {
  title: string; children: ReactNode; defaultOpen?: boolean;
  right?: ReactNode; dense?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="border-b border-[var(--color-line)]">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex flex-1 items-center gap-1.5 text-left label-xs hover:text-[var(--color-fg)]"
          aria-expanded={open}
        >
          <ChevronDown
            size={12}
            className={cx("transition-transform", !open && "-rotate-90")}
          />
          {title}
        </button>
        {right}
      </div>
      {open && <div className={cx("px-3", dense ? "pb-2" : "pb-3")}>{children}</div>}
    </section>
  );
}

/* ---------------- Nhập liệu ---------------- */

const inputBase =
  "w-full rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-panel-2)] " +
  "px-2 py-1.5 text-[13px] text-[var(--color-fg)] placeholder:text-[var(--color-fg-mute)] " +
  "focus:border-[var(--color-focus)] focus:outline-none";

export function TextInput({ className, ...p }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={cx(inputBase, className)} />;
}

export function TextArea({ className, ...p }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...p} className={cx(inputBase, "resize-y leading-snug", className)} />;
}

/** Ô nhập SỐ dùng font mono — mọi con số trong hệ thống đều đẳng chiều. */
export function NumInput({ className, ...p }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} inputMode="decimal" className={cx(inputBase, "font-mono", className)} />;
}

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...p} className={cx(inputBase, "cursor-pointer", className)}>
      {children}
    </select>
  );
}

/* ---------------- Nút ---------------- */

type BtnVariant = "default" | "primary" | "ghost" | "danger";

export function Button({ variant = "default", className, size = "md", ...p }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md" }) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-sm)] border font-medium " +
    "transition-colors disabled:cursor-not-allowed disabled:opacity-40 whitespace-nowrap";
  const sizes = { sm: "px-2 py-1 text-[11px]", md: "px-2.5 py-1.5 text-[12px]" };
  const variants: Record<BtnVariant, string> = {
    default:
      "border-[var(--color-line)] bg-[var(--color-panel-2)] text-[var(--color-fg)] " +
      "hover:border-[var(--color-line-hi)] hover:bg-[var(--color-panel-3)]",
    primary:
      "border-[var(--color-focus)] bg-[var(--color-focus)] text-[#0B1220] hover:brightness-110",
    ghost:
      "border-transparent bg-transparent text-[var(--color-fg-dim)] hover:text-[var(--color-fg)] " +
      "hover:bg-[var(--color-panel-2)]",
    danger:
      "border-[var(--color-line)] bg-transparent text-[var(--color-err)] " +
      "hover:border-[var(--color-err)] hover:bg-[color-mix(in_srgb,var(--color-err)_12%,transparent)]",
  };
  return <button {...p} className={cx(base, sizes[size], variants[variant], className)} />;
}

/* ---------------- Nhãn / chip ---------------- */

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("label-xs mb-1", className)}>{children}</div>;
}

export function Chip({ active, color, children, ...p }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean; color?: string }) {
  return (
    <button
      {...p}
      className={cx(
        "rounded-full border px-2 py-0.5 text-[11px] transition-colors",
        active
          ? "border-current font-semibold"
          : "border-[var(--color-line)] text-[var(--color-fg-dim)] hover:border-[var(--color-line-hi)]",
      )}
      style={active && color ? { color, backgroundColor: `color-mix(in srgb, ${color} 14%, transparent)` } : undefined}
    >
      {children}
    </button>
  );
}

/** Nhãn trạng thái có màu ngữ nghĩa (khác hẳn màu định danh nhánh). */
export function StatusDot({ ok, className }: { ok: boolean | null; className?: string }) {
  const color = ok === null ? "var(--color-fg-mute)" : ok ? "var(--color-ok)" : "var(--color-err)";
  return (
    <span className={cx("inline-block h-1.5 w-1.5 shrink-0 rounded-full", className)}
          style={{ backgroundColor: color }} />
  );
}

/* ---------------- Chú thích khi rê chuột ---------------- */

export function Hint({ children, label }: { children: ReactNode; label: string }) {
  return (
    <Tooltip.Provider delayDuration={250}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side="right" sideOffset={6}
            className="z-50 max-w-[280px] rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-panel-3)] px-2.5 py-1.5 text-[12px] leading-snug text-[var(--color-fg)] shadow-xl"
          >
            {label}
            <Tooltip.Arrow className="fill-[var(--color-line)]" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

/* ---------------- Popover ---------------- */

export function Pop({ trigger, children, width = 320, align = "start" }: {
  trigger: ReactNode; children: ReactNode; width?: number;
  align?: "start" | "center" | "end";
}) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>{trigger}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align={align} sideOffset={6} style={{ width }}
          className="z-50 rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-panel)] p-3 shadow-2xl"
        >
          {children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/* ---------------- Hộp thoại ---------------- */

export function Modal({ open, onOpenChange, title, children, wide }: {
  open: boolean; onOpenChange: (b: boolean) => void;
  title: string; children: ReactNode; wide?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/70" />
        <Dialog.Content
          className={cx(
            "fixed left-1/2 top-1/2 z-50 max-h-[88vh] -translate-x-1/2 -translate-y-1/2 overflow-auto",
            "rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-panel)] shadow-2xl",
            wide ? "w-[min(1100px,94vw)]" : "w-[min(560px,94vw)]",
          )}
        >
          <div className="flex items-center justify-between border-b border-[var(--color-line)] px-4 py-2.5">
            <Dialog.Title className="text-[13px] font-semibold">{title}</Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="sm" aria-label="Đóng"><X size={14} /></Button>
            </Dialog.Close>
          </div>
          <div className="p-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* ---------------- Trạng thái rỗng: hướng dẫn HÀNH ĐỘNG, không xin lỗi ---------------- */

export function EmptyState({ title, hint, action }: {
  title: string; hint?: string; action?: ReactNode;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-8 py-16 text-center">
      <div className="text-[13px] text-[var(--color-fg)]">{title}</div>
      {hint && <div className="max-w-md text-[12px] leading-relaxed text-[var(--color-fg-dim)]">{hint}</div>}
      {action}
    </div>
  );
}
