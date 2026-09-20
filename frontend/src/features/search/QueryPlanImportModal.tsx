import { Clipboard, Download, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api } from "../../api/client";
import { Button, Label, Modal, TextArea, copyToClipboard } from "../../components/ui";
import type { VisualQueryPlan } from "../../types/api";

function parseJsonBlock(raw: string): Record<string, unknown> {
  const text = raw.trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("Không tìm thấy một JSON object trong nội dung đã dán.");
  const value: unknown = JSON.parse(text.slice(start, end + 1));
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Kế hoạch phải là một JSON object.");
  return value as Record<string, unknown>;
}

export function QueryPlanImportModal({ open, onOpenChange, sourceQuery, onApply }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sourceQuery: string;
  onApply: (plan: VisualQueryPlan) => void;
}) {
  const [raw, setRaw] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setError("");
  }, [open]);

  const copyQuestion = async () => {
    if (!sourceQuery.trim()) {
      toast.error("Chưa có câu hỏi gốc để sao chép.");
      return;
    }
    const ok = await copyToClipboard(
      `Phân tích đề bài dưới đây thành kế hoạch truy vấn thị giác và chỉ trả JSON đúng schema đã được cấu hình:\n\n${sourceQuery.trim()}`,
    );
    if (ok) toast.success("Đã chép câu hỏi để gửi cho AIC Visual Query Expert.");
    else toast.error("Trình duyệt không cho phép sao chép tự động.");
  };

  const importPlan = async () => {
    setError("");
    setBusy(true);
    try {
      const parsed = parseJsonBlock(raw);
      const result = await api.validateQueryPlan(parsed);
      onApply(result.plan);
      onOpenChange(false);
      if (result.warnings.length)
        toast.warning(`Đã nhập kế hoạch; ${result.warnings.join(" ")}`);
      else
        toast.success(`Đã nhập ${result.plan.events.length} sự kiện từ GPT.`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Không đọc được kế hoạch GPT.";
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Nhập kế hoạch từ GPT Explore" wide>
      <div className="grid gap-4 md:grid-cols-[1fr_1.4fr]">
        <div className="space-y-3 text-[12px] leading-relaxed text-[var(--color-fg-dim)]">
          <div>
            <Label>1. Gửi câu gốc cho GPT</Label>
            <p>
              Dùng GPT <strong className="text-[var(--color-fg)]">AIC Visual Query Expert</strong> đã
              nạp instructions trong thư mục <code>gpt_explore/</code>. GPT mạnh chỉ phân tích;
              RTC vẫn là nơi chạy retrieval.
            </p>
          </div>
          <Button onClick={copyQuestion} disabled={!sourceQuery.trim()}>
            <Clipboard size={11} /> Chép câu gốc cho GPT
          </Button>
          <div>
            <Label>2. Dán nguyên JSON GPT trả về</Label>
            <p>
              Có thể dán cả khối <code>```json</code>. Server sẽ kiểm tra sự kiện, bản dịch,
              số neo và giới hạn thời gian trước khi áp dụng.
            </p>
          </div>
          <p className="rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-panel-2)] p-2 text-[10.5px]">
            Kế hoạch có một sự kiện phù hợp Search; từ hai sự kiện trở lên phù hợp Temporal.
            Nhãn QA/KIS của đề không tham gia quyết định này.
          </p>
        </div>

        <div className="flex min-w-0 flex-col gap-2">
          <Label>JSON kế hoạch truy vấn</Label>
          <TextArea
            rows={16}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder={'{"context":{"vi":"...","en":"..."},"events":[{"vi":"...","en":"...","anchor":true}]}'}
            className="font-mono text-[11px]"
          />
          {error && (
            <div role="alert" className="rounded-[var(--radius-sm)] border border-[var(--color-err)]/50 bg-[var(--color-err)]/10 px-2 py-1.5 text-[11px] text-[var(--color-err)]">
              {error}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>Huỷ</Button>
            <Button variant="primary" onClick={importPlan} disabled={busy || !raw.trim()}>
              {busy ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
              {busy ? "Đang kiểm tra…" : "Kiểm tra và áp dụng"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
