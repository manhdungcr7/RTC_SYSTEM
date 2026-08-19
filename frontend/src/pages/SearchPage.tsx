/** Trang tìm khung hình — bố cục 3 cột cố định, mỗi cột cuộn riêng, trang không
 *  bao giờ cuộn. Mọi đòn bẩy điều khiển nằm ở cột trái trong tầm tay, kết quả
 *  chiếm phần lớn màn hình, tra cứu ở cột phải. */
import { PanelLeftClose, PanelRightClose, Search as SearchIcon, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";
import { useHotkeys } from "react-hotkeys-hook";

import { Button, ResizeHandle, Section, cx } from "../components/ui";
import { Inspector } from "../features/inspector/Inspector";
import { ResultArea } from "../features/results/ResultArea";
import { QueryPanel } from "../features/search/QueryPanel";
import { RefImagePanel, SessionVideoScopePanel } from "../features/search/ScopePanels";
import { SignalMixer } from "../features/search/SignalMixer";
import { AsrPanel, NegativePanel, ObjectGridPicker, OcrPanel } from "../features/search/TextPanels";
import { buildRequest, useSearchRunner } from "../features/search/useSearchQuery";
import { SubmitPanel } from "../features/submission/SubmitPanel";
import { useSession } from "../stores/sessionStore";
import { useSubmission, framesPerRow } from "../stores/submissionStore";
import { useUi } from "../stores/uiStore";
import { BRANCHES } from "../types/api";

function FeedbackBar({ onRerun }: { onRerun: () => void }) {
  const pos = useSession((s) => s.sessions[s.activeId].feedbackPos);
  const neg = useSession((s) => s.sessions[s.activeId].feedbackNeg);
  const clear = useSession((s) => s.clearFeedback);
  if (pos.length === 0 && neg.length === 0) return null;

  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-[var(--color-line)] bg-[var(--color-panel)] px-3 py-1.5">
      <span className="flex items-center gap-1 text-[11px] text-[var(--color-ok)]">
        <ThumbsUp size={11} /> {pos.length} giống
      </span>
      <span className="flex items-center gap-1 text-[11px] text-[var(--color-err)]">
        <ThumbsDown size={11} /> {neg.length} không giống
      </span>
      <span className="text-[10.5px] text-[var(--color-fg-mute)]">
        Hệ thống sẽ kéo kết quả về phía những khung bạn đánh dấu ✓
      </span>
      <div className="ml-auto flex gap-1">
        <Button size="sm" variant="primary" onClick={onRerun}>Tìm lại với phản hồi</Button>
        <Button size="sm" variant="ghost" onClick={clear}><X size={11} /></Button>
      </div>
    </div>
  );
}

export function SearchPage() {
  const session = useSession((s) => s.sessions[s.activeId]);
  const patch = useSession((s) => s.patch);
  const togglePin = useSession((s) => s.togglePin);
  const markGood = useSession((s) => s.markGood);
  const markBad = useSession((s) => s.markBad);

  const leftOpen = useUi((s) => s.leftOpen);
  const rightOpen = useUi((s) => s.rightOpen);
  const leftWidth = useUi((s) => s.leftWidth);
  const rightWidth = useUi((s) => s.rightWidth);
  const setLeftWidth = useUi((s) => s.setLeftWidth);
  const setRightWidth = useUi((s) => s.setRightWidth);
  const toggleLeft = useUi((s) => s.toggleLeft);
  const toggleRight = useUi((s) => s.toggleRight);
  const cursor = useUi((s) => s.cursor);
  const moveCursor = useUi((s) => s.moveCursor);
  const openDetail = useUi((s) => s.openDetail);
  const openWorkbench = useUi((s) => s.openWorkbench);
  const toggleCompare = useUi((s) => s.toggleCompare);
  const branchTab = useUi((s) => s.branchTab);
  const setInspectorTab = useUi((s) => s.setInspectorTab);

  const files = useSubmission((s) => s.files);
  const activeName = useSubmission((s) => s.activeName);
  const addRow = useSubmission((s) => s.addRow);

  const runner = useSearchRunner();

  const submit = useCallback(() => {
    runner.run(buildRequest(session));
  }, [runner, session]);

  const hits = useMemo(() => {
    if (!runner.data) return [];
    if (!branchTab) return runner.data.hits;
    return runner.data.branch_rankings.find((b) => b.branch === branchTab)?.hits ?? [];
  }, [runner.data, branchTab]);

  const current = cursor >= 0 && cursor < hits.length ? hits[cursor] : (hits[0] ?? null);

  /* ---------------- Phím tắt ---------------- */
  const inField = () => {
    const t = document.activeElement?.tagName;
    return t === "INPUT" || t === "TEXTAREA" || t === "SELECT";
  };

  useHotkeys("/", (e) => {
    e.preventDefault();
    (document.querySelector("[data-query-box]") as HTMLTextAreaElement)?.focus();
  }, { enableOnFormTags: true });

  useHotkeys("left", () => !inField() && moveCursor(-1, hits.length), [hits.length]);
  useHotkeys("right", () => !inField() && moveCursor(1, hits.length), [hits.length]);
  useHotkeys("up", (e) => { if (!inField()) { e.preventDefault(); moveCursor(-6, hits.length); } }, [hits.length]);
  useHotkeys("down", (e) => { if (!inField()) { e.preventDefault(); moveCursor(6, hits.length); } }, [hits.length]);
  useHotkeys("enter", () => { if (!inField() && current) openDetail(current, hits); }, [current, hits]);
  useHotkeys("p", () => {
    if (inField() || !current) return;
    togglePin({ id: current.id, video: current.video, n: current.n,
                frame_idx: current.frame_idx, pts_time: current.pts_time });
  }, [current]);
  useHotkeys("a", () => { if (!inField() && current) markGood({ video: current.video, n: current.n }); }, [current]);
  useHotkeys("d", () => { if (!inField() && current) markBad({ video: current.video, n: current.n }); }, [current]);
  useHotkeys("r", () => {
    if (inField() || !current) return;
    patch({ refVideo: current.video, refN: current.n, refImageB64: null,
            enabled: { ...session.enabled, dinov3: true } });
  }, [current, session.enabled]);
  useHotkeys("c", () => { if (!inField() && current) toggleCompare(current); }, [current]);
  useHotkeys("w", () => { if (!inField() && current) openWorkbench(current.video); }, [current]);
  useHotkeys("s", () => {
    if (inField() || !current) return;
    const f = activeName ? files[activeName] : null;
    if (!f) return;
    addRow(f.name, {
      video: current.video,
      frames: [String(current.frame_idx), ...Array(Math.max(0, framesPerRow(f) - 1)).fill("")],
    });
    setInspectorTab("submit");
  }, [current, activeName, files]);
  useHotkeys("bracketLeft", () => !inField() && toggleLeft());
  useHotkeys("bracketRight", () => !inField() && toggleRight());
  useHotkeys("shift+slash", () => useUi.getState().setShortcutsOpen(true));

  // 1–9 bật/tắt nhánh theo thứ tự trên bàn trộn
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (inField() || e.altKey || e.ctrlKey || e.metaKey) return;
      const n = parseInt(e.key, 10);
      if (!Number.isFinite(n) || n < 1 || n > BRANCHES.length) return;
      const key = BRANCHES[n - 1].key;
      patch({ enabled: { ...session.enabled, [key]: !session.enabled[key] } });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [session.enabled, patch]);

  return (
    <>
      <div className="flex min-h-0 flex-1">
        {/* ---------- Cột trái: bàn trộn + mọi đòn bẩy ---------- */}
        {leftOpen && (
          <>
          <aside style={{ width: leftWidth }}
                 className="flex shrink-0 flex-col overflow-y-auto border-r border-[var(--color-line)] bg-[var(--color-panel)]">
            <div className="border-b border-[var(--color-line)] p-3">
              <QueryPanel onSubmit={submit} />
              <Button variant="primary" className="mt-2 w-full" onClick={submit}
                      disabled={runner.isLoading}>
                <SearchIcon size={12} />
                {runner.isLoading ? "Đang tìm…" : "Tìm kiếm"}
              </Button>
            </div>

            <Section title="Bàn trộn tín hiệu"><SignalMixer /></Section>
            <Section title="Chữ trên hình" defaultOpen={false}><OcrPanel /></Section>
            <Section title="Lời thoại" defaultOpen={false}><AsrPanel /></Section>
            <Section title="Vật thể · màu · vị trí" defaultOpen={false}><ObjectGridPicker /></Section>
            <Section title="Ảnh tham chiếu" defaultOpen={false}><RefImagePanel /></Section>
            <Section title="Loại trừ" defaultOpen={false}><NegativePanel /></Section>
            <Section title="Thu hẹp video" defaultOpen={false}><SessionVideoScopePanel /></Section>
            <Section title="Gộp điểm &amp; chống trùng" defaultOpen={false}>
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <span className="w-[120px] text-[11px] text-[var(--color-fg-dim)]">Tối đa khung/video</span>
                  <input type="range" min={1} max={20} value={session.perVideoCap}
                         onChange={(e) => patch({ perVideoCap: Number(e.target.value) })}
                         className="h-1 flex-1 accent-[var(--color-focus)]" />
                  <span className="w-[22px] text-right font-mono text-[11px] tabular-nums">{session.perVideoCap}</span>
                </div>
                <p className="text-[10px] leading-snug text-[var(--color-fg-mute)]">
                  Để 1 khi đang quét rộng tìm đúng video; tăng lên khi đã biết video và cần soi kỹ.
                </p>
                <div className="flex items-center gap-2">
                  <span className="w-[120px] text-[11px] text-[var(--color-fg-dim)]">Gộp khung gần nhau</span>
                  <input type="range" min={0} max={10} step={0.5} value={session.dedupSeconds}
                         onChange={(e) => patch({ dedupSeconds: Number(e.target.value) })}
                         className="h-1 flex-1 accent-[var(--color-focus)]" />
                  <span className="w-[30px] text-right font-mono text-[11px] tabular-nums">
                    {session.dedupSeconds}s
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-[120px] text-[11px] text-[var(--color-fg-dim)]">Số kết quả</span>
                  <input type="range" min={50} max={500} step={50} value={session.topk}
                         onChange={(e) => patch({ topk: Number(e.target.value) })}
                         className="h-1 flex-1 accent-[var(--color-focus)]" />
                  <span className="w-[30px] text-right font-mono text-[11px] tabular-nums">{session.topk}</span>
                </div>
              </div>
            </Section>
          </aside>
          <ResizeHandle side="left" width={leftWidth} onResize={setLeftWidth} />
          </>
        )}

        {/* ---------- Giữa: kết quả ---------- */}
        <main className="flex min-w-0 flex-1 flex-col">
          <FeedbackBar onRerun={submit} />
          <div className="min-h-0 flex-1">
            <ResultArea data={runner.data} isLoading={runner.isLoading}
                        error={runner.error} onRetry={submit} />
          </div>
        </main>

        {/* ---------- Cột phải: tra cứu ---------- */}
        {rightOpen && (
          <>
          <ResizeHandle side="right" width={rightWidth} onResize={setRightWidth} />
          <aside style={{ width: rightWidth }}
                 className="shrink-0 border-l border-[var(--color-line)] bg-[var(--color-panel)]">
            <Inspector current={current} submitPanel={<SubmitPanel />} />
          </aside>
          </>
        )}
      </div>

      {/* Nút thu gọn cột — luôn có, kể cả khi cột đã đóng */}
      <button type="button" onClick={toggleLeft} title="Thu gọn cột trái ([)"
              className={cx("fixed bottom-3 left-3 z-30 rounded-[2px] border border-[var(--color-line)] bg-[var(--color-panel-2)] p-1.5 text-[var(--color-fg-mute)] hover:text-[var(--color-fg)]",
                leftOpen && "opacity-40 hover:opacity-100")}>
        <PanelLeftClose size={13} />
      </button>
      <button type="button" onClick={toggleRight} title="Thu gọn cột phải (])"
              className={cx("fixed bottom-3 right-3 z-30 rounded-[2px] border border-[var(--color-line)] bg-[var(--color-panel-2)] p-1.5 text-[var(--color-fg-mute)] hover:text-[var(--color-fg)]",
                rightOpen && "opacity-40 hover:opacity-100")}>
        <PanelRightClose size={13} />
      </button>
    </>
  );
}
