/** Thanh trên cùng: điều hướng, tab câu hỏi, đèn trạng thái dịch vụ.
 *
 *  Đèn trạng thái quan trọng hơn vẻ ngoài: khi encoder Kaggle chết giữa cuộc thi,
 *  người dùng phải thấy NGAY và biết chính xác cái gì còn dùng được — chứ không
 *  ngồi đoán vì sao tìm mãi không ra. */
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileSearch, Keyboard, Plug, Plus, Save, Search, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { toast } from "sonner";

import { api } from "../api/client";
import { Button, Label, Pop, StatusDot, TextInput, cx } from "../components/ui";
import { useSession } from "../stores/sessionStore";
import { useSubmission } from "../stores/submissionStore";
import { isValidMemberId, useTeamIdentity } from "../stores/teamIdentityStore";
import { useUi } from "../stores/uiStore";

/** Tra tay 1 khung hình theo video + frame_idx — không cần gõ mô tả rồi tìm,
 *  dùng khi đã BIẾT CHẮC toạ độ (vd đọc từ đề, hoặc muốn xem lại nhanh 1 khung
 *  đã ghi chú) — P5 "luôn còn 1 đường thủ công". Không nhập frame_idx thì mặc
 *  định 1 (khung đầu tiên), chỉ tên video vẫn tra được ngay. */
function FrameLookup() {
  const [video, setVideo] = useState("");
  const [frameIdx, setFrameIdx] = useState("");
  const openDetail = useUi((s) => s.openDetail);

  const lookup = useMutation({
    mutationFn: () => api.lookupFrame(video.trim(), frameIdx.trim() ? Number(frameIdx) : 1),
    onSuccess: (hit) => openDetail(hit, [hit]),
    onError: (e: Error) => toast.error(e.message || "Không tra được khung hình này"),
  });

  return (
    <Pop width={240} trigger={
      <Button size="sm" variant="default" title="Tra tay 1 khung hình theo video + frame_idx"
              className="border-[var(--color-focus)] text-[var(--color-focus)]">
        <Search size={12} /> Tra khung
      </Button>
    }>
      <Label className="mb-1.5">Tra tay khung hình</Label>
      <div className="flex flex-col gap-1.5">
        <div>
          <span className="mb-0.5 block text-[10.5px] text-[var(--color-fg-mute)]">Tên video</span>
          <TextInput value={video} onChange={(e) => setVideo(e.target.value.trim())}
                     placeholder="L21_V001" className="font-mono text-[12px]"
                     onKeyDown={(e) => e.key === "Enter" && video.trim() && lookup.mutate()} />
        </div>
        <div>
          <span className="mb-0.5 block text-[10.5px] text-[var(--color-fg-mute)]">
            Frame index (bỏ trống = 1)
          </span>
          <TextInput value={frameIdx} inputMode="numeric"
                     onChange={(e) => setFrameIdx(e.target.value.replace(/\D/g, ""))}
                     placeholder="1" className="font-mono text-[12px]"
                     onKeyDown={(e) => e.key === "Enter" && video.trim() && lookup.mutate()} />
        </div>
        <Button size="sm" variant="primary" onClick={() => lookup.mutate()}
                disabled={!video.trim() || lookup.isPending}>
          <Search size={11} /> {lookup.isPending ? "Đang tra…" : "Xem"}
        </Button>
        <p className="text-[10px] leading-snug text-[var(--color-fg-mute)]">
          Keyframe thưa nên tra ra khung GẦN NHẤT với số đã nhập, không phải
          lúc nào cũng khớp tuyệt đối — vẫn xem được video/tua tới đúng giây.
        </p>
      </div>
    </Pop>
  );
}

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

function TeamIdentityPopover() {
  const displayName = useTeamIdentity((s) => s.displayName);
  const memberId = useTeamIdentity((s) => s.memberId);
  const setIdentity = useTeamIdentity((s) => s.setIdentity);
  const [nameDraft, setNameDraft] = useState(displayName);
  const [idDraft, setIdDraft] = useState(memberId);

  useEffect(() => {
    setNameDraft(displayName);
    setIdDraft(memberId);
  }, [displayName, memberId]);

  const save = () => {
    const cleanName = nameDraft.trim();
    const cleanId = idDraft.trim().toLowerCase();
    if (!cleanName) { toast.error("Nhập tên hiển thị trước khi chia sẻ."); return; }
    if (!isValidMemberId(cleanId)) {
      toast.error("Member ID dài 4–64 ký tự, chỉ gồm a-z, 0-9, _ hoặc -.");
      return;
    }
    setIdentity(cleanName, cleanId);
    toast.success("Đã lưu danh tính trên máy này.");
  };

  return (
    <Pop width={280} align="end" trigger={
      <Button size="sm" variant="ghost" title="Cấu hình tên và Member ID để chia sẻ bài nộp">
        <UserRound size={12} />
        <span className="max-w-[78px] truncate">{displayName || "Danh tính"}</span>
      </Button>
    }>
      <Label>Danh tính chia sẻ</Label>
      <p className="mb-2 text-[10.5px] leading-snug text-[var(--color-fg-mute)]">
        Lưu một lần trên máy này. Khi đổi máy, nhập lại đúng Member ID để cập nhật đúng bài đã chia sẻ.
      </p>
      <div className="flex flex-col gap-1.5">
        <TextInput value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} placeholder="Tên hiển thị"
                   className="text-[11.5px]" />
        <TextInput value={idDraft} onChange={(e) => setIdDraft(e.target.value.toLowerCase())}
                   placeholder="Member ID, ví dụ dung-k9f3" className="font-mono text-[11.5px]" />
        <Button size="sm" variant="primary" onClick={save}><Save size={11} /> Lưu danh tính</Button>
      </div>
    </Pop>
  );
}

export function Topbar() {
  const setShortcutsOpen = useUi((s) => s.setShortcutsOpen);
  const setConnectionOpen = useUi((s) => s.setConnectionOpen);
  const setCsvPreviewOpen = useUi((s) => s.setCsvPreviewOpen);
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
        <TeamIdentityPopover />
        <HealthLights />
        <FrameLookup />
        <Button size="sm" variant="ghost" onClick={() => setCsvPreviewOpen(true)}
                title="Xem trước file CSV sắp nộp bằng ảnh, theo đúng thứ tự">
          <FileSearch size={12} />
        </Button>
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
