/** Thanh trên cùng: điều hướng, tab câu hỏi, đèn trạng thái dịch vụ.
 *
 *  Đèn trạng thái quan trọng hơn vẻ ngoài: khi encoder Kaggle chết giữa cuộc thi,
 *  người dùng phải thấy NGAY và biết chính xác cái gì còn dùng được — chứ không
 *  ngồi đoán vì sao tìm mãi không ra. */
import { useQuery } from "@tanstack/react-query";
import { Keyboard, Plug, Plus, X } from "lucide-react";
import { NavLink } from "react-router-dom";

import { api } from "../api/client";
import { Button, StatusDot, cx } from "../components/ui";
import { useSession } from "../stores/sessionStore";
import { useSubmission } from "../stores/submissionStore";
import { useUi } from "../stores/uiStore";

function SessionTabs() {
  const order = useSession((s) => s.order);
  const sessions = useSession((s) => s.sessions);
  const activeId = useSession((s) => s.activeId);
  const setActive = useSession((s) => s.setActive);
  const addSession = useSession((s) => s.addSession);
  const removeSession = useSession((s) => s.removeSession);

  return (
    <div className="flex min-w-0 items-center gap-0.5 overflow-x-auto">
      {order.map((id) => (
        <div key={id}
             className={cx("group flex shrink-0 items-center rounded-[2px] transition-colors",
               activeId === id ? "bg-[var(--color-panel-3)]" : "hover:bg-[var(--color-panel-2)]")}>
          <button type="button" onClick={() => setActive(id)}
                  className={cx("py-1 pl-2 font-mono text-[11px]",
                    activeId === id ? "text-[var(--color-fg)]" : "text-[var(--color-fg-mute)]")}>
            {sessions[id].label}
            {sessions[id].pins.length > 0 && (
              <span className="ml-1 text-[9px] text-[var(--color-pin)]">●{sessions[id].pins.length}</span>
            )}
          </button>
          {order.length > 1 && (
            <button type="button" onClick={() => removeSession(id)} aria-label={`Đóng ${id}`}
                    className="px-1 text-[var(--color-fg-mute)] opacity-0 transition-opacity hover:text-[var(--color-err)] group-hover:opacity-100">
              <X size={10} />
            </button>
          )}
        </div>
      ))}
      <button type="button" onClick={() => addSession()} title="Thêm câu hỏi mới"
              className="shrink-0 rounded-[2px] p-1 text-[var(--color-fg-mute)] hover:bg-[var(--color-panel-2)] hover:text-[var(--color-fg)]">
        <Plus size={12} />
      </button>
    </div>
  );
}

function HealthLights() {
  const setConnectionOpen = useUi((s) => s.setConnectionOpen);
  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: 30_000,
    retry: false,
  });

  const encOk = data?.encoder?.ok ?? null;
  const meiliOk = data?.meili?.ok ?? null;

  return (
    <button type="button" onClick={() => setConnectionOpen(true)}
            title="Mở bảng Kết nối"
            className="flex items-center gap-2 rounded-[2px] px-1.5 py-1 hover:bg-[var(--color-panel-2)]">
      <span className="flex items-center gap-1 font-mono text-[10.5px] text-[var(--color-fg-mute)]">
        <StatusDot ok={encOk} /> GPU
        {data?.encoder?.latency_ms != null && (
          <span className="tabular-nums">{data.encoder.latency_ms}ms</span>
        )}
      </span>
      <span className="flex items-center gap-1 font-mono text-[10.5px] text-[var(--color-fg-mute)]">
        <StatusDot ok={meiliOk} /> Chữ
      </span>
    </button>
  );
}

export function Topbar() {
  const setShortcutsOpen = useUi((s) => s.setShortcutsOpen);
  const setConnectionOpen = useUi((s) => s.setConnectionOpen);
  const files = useSubmission((s) => s.files);
  const totalRows = Object.values(files).reduce((a, f) => a + f.rows.length, 0);

  const link = ({ isActive }: { isActive: boolean }) =>
    cx("rounded-[2px] px-2 py-1 text-[12px] transition-colors",
      isActive ? "bg-[var(--color-panel-3)] text-[var(--color-fg)]"
               : "text-[var(--color-fg-dim)] hover:text-[var(--color-fg)]");

  return (
    <header className="flex h-[40px] shrink-0 items-center gap-3 border-b border-[var(--color-line)] bg-[var(--color-panel)] px-3">
      <span className="shrink-0 font-mono text-[12px] font-bold tracking-wider text-[var(--color-focus)]">AIC</span>

      <nav className="flex shrink-0 gap-0.5">
        <NavLink to="/" end className={link}>Tìm khung hình</NavLink>
        <NavLink to="/temporal" className={link}>Chuỗi sự kiện</NavLink>
      </nav>

      <div className="mx-1 h-4 w-px shrink-0 bg-[var(--color-line)]" />
      <SessionTabs />

      <div className="ml-auto flex shrink-0 items-center gap-1">
        {totalRows > 0 && (
          <span className="font-mono text-[10.5px] tabular-nums text-[var(--color-fg-mute)]">
            nháp {totalRows}
          </span>
        )}
        <HealthLights />
        <Button size="sm" variant="ghost" onClick={() => setConnectionOpen(true)} title="Bảng Kết nối">
          <Plug size={12} />
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setShortcutsOpen(true)} title="Phím tắt (?)">
          <Keyboard size={12} />
        </Button>
      </div>
    </header>
  );
}
