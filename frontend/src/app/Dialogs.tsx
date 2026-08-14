/** Bảng Kết nối + bảng tra phím tắt.
 *
 *  Bảng Kết nối tồn tại vì một ràng buộc vận hành THẬT: phiên Kaggle miễn phí
 *  hết giờ là URL đổi. Sửa file .env rồi dựng lại container giữa cuộc thi tốn
 *  vài phút và cả hệ thống đứng — ở đây dán 2 ô rồi bấm là xong, áp dụng ngay. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api } from "../api/client";
import { Button, Label, Modal, StatusDot, TextInput } from "../components/ui";
import { useUi } from "../stores/uiStore";

export function ConnectionDialog() {
  const open = useUi((s) => s.connectionOpen);
  const setOpen = useUi((s) => s.setConnectionOpen);
  const qc = useQueryClient();

  const { data: health, refetch } = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: open ? 10_000 : 30_000,
    retry: false,
  });

  const [url, setUrl] = useState("");
  const [key, setKey] = useState("");

  useEffect(() => {
    if (open) api.getEncoderConfig().then((c) => setUrl(c.url ?? "")).catch(() => {});
  }, [open]);

  const save = useMutation({
    mutationFn: () => api.setEncoderConfig(url.trim(), key.trim()),
    onSuccess: (r) => {
      if (r.ok) {
        toast.success("Đã kết nối máy encode");
        qc.invalidateQueries({ queryKey: ["health"] });
      } else {
        toast.error(`Không kết nối được: ${r.error ?? "không rõ"}`);
      }
      refetch();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const enc = health?.encoder;
  const meili = health?.meili;
  const faiss = health?.faiss;

  return (
    <Modal open={open} onOpenChange={setOpen} title="Kết nối">
      <div className="flex flex-col gap-3">
        <div>
          <Label>Máy encode (Kaggle)</Label>
          <p className="mb-1.5 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
            Mỗi lần khởi động lại notebook Kaggle, dán URL và API key mới vào đây.
            Áp dụng ngay, không cần dựng lại hệ thống.
          </p>
          <TextInput value={url} onChange={(e) => setUrl(e.target.value)}
                     placeholder="https://xxxx.ngrok-free.dev" className="mb-1 font-mono text-[11.5px]" />
          <TextInput value={key} onChange={(e) => setKey(e.target.value)} type="password"
                     placeholder="API key" className="mb-1.5 font-mono text-[11.5px]" />
          <Button size="sm" variant="primary" onClick={() => save.mutate()}
                  disabled={!url.trim() || save.isPending}>
            {save.isPending ? "Đang kết nối…" : "Lưu và kiểm tra"}
          </Button>
        </div>

        <div className="flex flex-col gap-1.5 border-t border-[var(--color-line)] pt-3">
          <div className="flex items-center gap-2 text-[11.5px]">
            <StatusDot ok={enc?.ok ?? null} />
            <span className="w-[92px] text-[var(--color-fg-dim)]">Máy encode</span>
            <span className="font-mono tabular-nums text-[var(--color-fg-mute)]">
              {enc?.ok ? `sống · ${enc.latency_ms}ms` : "không kết nối được"}
            </span>
          </div>
          {!enc?.ok && (
            <p className="ml-4 text-[10.5px] leading-snug text-[var(--color-warn)]">
              Tìm bằng câu chữ mới sẽ không chạy. Nhưng lọc theo chữ trên hình, lời
              thoại, xem video, khay ghim và nộp bài vẫn dùng bình thường.
            </p>
          )}

          <div className="flex items-center gap-2 text-[11.5px]">
            <StatusDot ok={meili?.ok ?? null} />
            <span className="w-[92px] text-[var(--color-fg-dim)]">Tra cứu chữ</span>
            <span className="font-mono tabular-nums text-[var(--color-fg-mute)]">
              {meili?.ok
                ? `${(meili.docs?.frames ?? 0).toLocaleString()} khung · ${(meili.docs?.asr ?? 0).toLocaleString()} đoạn thoại`
                : "không kết nối được"}
            </span>
          </div>

          <div className="flex items-center gap-2 text-[11.5px]">
            <StatusDot ok={faiss?.ok ?? null} />
            <span className="w-[92px] text-[var(--color-fg-dim)]">Chỉ mục ảnh</span>
            <span className="font-mono tabular-nums text-[var(--color-fg-mute)]">
              {faiss ? `${Object.keys(faiss.branches).length} nhánh đã nạp` : "—"}
            </span>
          </div>
        </div>
      </div>
    </Modal>
  );
}

const SHORTCUTS: [string, string][] = [
  ["/", "Nhảy vào ô tìm kiếm"],
  ["Enter", "Tìm (trong ô truy vấn) · Mở chi tiết (trong lưới)"],
  ["← → ↑ ↓", "Di chuyển trong lưới kết quả"],
  ["P", "Ghim / bỏ ghim khung hình"],
  ["A / D", "Đánh dấu giống ✓ / không giống ✗ rồi tìm lại"],
  ["R", "Đặt làm ảnh mẫu (tìm ảnh giống)"],
  ["C", "Thêm vào so sánh"],
  ["W", "Mở toàn bộ video (Workbench)"],
  ["S", "Đưa vào bản nháp nộp bài"],
  [", .", "Lùi / tiến 1 khung hình (trong khung chi tiết)"],
  ["J / L", "Lùi / tiến 1 giây"],
  ["Space", "Phát / dừng video"],
  ["1 – 9", "Bật tắt nhánh tín hiệu tương ứng"],
  ["[ ]", "Thu gọn cột trái / phải"],
  ["Esc", "Đóng khung đang mở"],
  ["?", "Bảng phím tắt này"],
];

export function ShortcutsDialog() {
  const open = useUi((s) => s.shortcutsOpen);
  const setOpen = useUi((s) => s.setShortcutsOpen);
  return (
    <Modal open={open} onOpenChange={setOpen} title="Phím tắt">
      <div className="grid grid-cols-2 gap-x-5 gap-y-1">
        {SHORTCUTS.map(([k, d]) => (
          <div key={k} className="flex items-baseline gap-2">
            <kbd className="shrink-0 rounded-[2px] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-1.5 py-0.5 font-mono text-[10.5px] text-[var(--color-fg)]">
              {k}
            </kbd>
            <span className="text-[11.5px] leading-snug text-[var(--color-fg-dim)]">{d}</span>
          </div>
        ))}
      </div>
    </Modal>
  );
}
