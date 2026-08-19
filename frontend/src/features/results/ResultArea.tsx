/**
 * Vùng kết quả: thanh công cụ + 3 cách xem (lưới / gom theo video / so sánh).
 *
 * Lưới dùng ảo hoá theo HÀNG: mọi keyframe đều tỉ lệ 16:9 nên chiều cao hàng cố
 * định, ảo hoá rất đơn giản và cuộn mượt tuyệt đối. Cố tình KHÔNG dùng kiểu
 * masonry — mắt so sánh các khung hình dễ hơn nhiều khi chúng cùng kích thước;
 * masonry ở đây là trang trí gây hại.
 */
import { useVirtualizer } from "@tanstack/react-virtual";
import { CheckSquare, Columns3, Grid3x3, LayoutList, Loader2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { frameUrl } from "../../api/client";
import { Button, EmptyState, cx } from "../../components/ui";
import { useSession } from "../../stores/sessionStore";
import { useSubmission } from "../../stores/submissionStore";
import { useUi } from "../../stores/uiStore";
import { BRANCHES, BRANCH_COLOR } from "../../types/api";
import type { SearchHit, SearchResponse } from "../../types/api";
import { ResultTile } from "./ResultTile";

const GAP = 8;

function useHitActions() {
  const session = useSession((s) => s.sessions[s.activeId]);
  const patch = useSession((s) => s.patch);
  const togglePin = useSession((s) => s.togglePin);
  const markGood = useSession((s) => s.markGood);
  const markBad = useSession((s) => s.markBad);
  const openDetail = useUi((s) => s.openDetail);
  const toggleCompare = useUi((s) => s.toggleCompare);

  return useMemo(() => ({
    session, patch,
    open: (h: SearchHit, hits?: SearchHit[]) => openDetail(h, hits),
    pin: (h: SearchHit) => togglePin({
      id: h.id, video: h.video, n: h.n, frame_idx: h.frame_idx, pts_time: h.pts_time,
    }),
    ref: (h: SearchHit) => patch({
      refVideo: h.video, refN: h.n, refImageB64: null,
      enabled: { ...session.enabled, dinov3: true },
    }),
    good: (h: SearchHit) => markGood({ video: h.video, n: h.n }),
    bad: (h: SearchHit) => markBad({ video: h.video, n: h.n }),
    compare: (h: SearchHit) => toggleCompare(h),
  }), [session, patch, togglePin, markGood, markBad, openDetail, toggleCompare]);
}

/* ------------------------------ Lưới ảo hoá ------------------------------ */

function VirtualGrid({ hits }: { hits: SearchHit[] }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const tileSize = useUi((s) => s.tileSize);
  const cursor = useUi((s) => s.cursor);
  const setCursor = useUi((s) => s.setCursor);
  const bulkMode = useUi((s) => s.bulkMode);
  const bulkSelection = useUi((s) => s.bulkSelection);
  const toggleBulkId = useUi((s) => s.toggleBulkId);
  const addBulkIds = useUi((s) => s.addBulkIds);
  const clearBulk = useUi((s) => s.clearBulk);
  const files = useSubmission((s) => s.files);
  const activeName = useSubmission((s) => s.activeName);
  const addRow = useSubmission((s) => s.addRow);
  const a = useHitActions();
  const pins = a.session.pins;
  const fbPos = a.session.feedbackPos;
  const fbNeg = a.session.feedbackNeg;

  // Kéo bôi đen hàng loạt — chỉ khởi động khi mousedown rơi đúng vào NỀN (khe
  // hở giữa các ô hoặc vùng trống), không phải lên 1 ô cụ thể, để không đụng
  // độ với việc tick từng ô hay mở khung chi tiết.
  const [dragBox, setDragBox] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  const commitDrag = (box: { x0: number; y0: number; x1: number; y1: number }) => {
    const left = Math.min(box.x0, box.x1), right = Math.max(box.x0, box.x1);
    const top = Math.min(box.y0, box.y1), bottom = Math.max(box.y0, box.y1);
    if (right - left < 4 && bottom - top < 4) return;
    const els = parentRef.current?.querySelectorAll<HTMLElement>("[data-bulk-tile]") ?? [];
    const hitIds = new Set<string>();
    els.forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.left < right && r.right > left && r.top < bottom && r.bottom > top) hitIds.add(el.dataset.bulkTile!);
    });
    // Thứ tự = thứ tự hệ thống đã xếp hạng (thứ tự trong `hits`), KHÔNG phải
    // thứ tự vùng kéo quét qua — đúng yêu cầu "kéo hàng loạt xếp theo gợi ý".
    const ordered = hits.filter((h) => hitIds.has(h.id)).map((h) => h.id);
    if (ordered.length) addBulkIds(ordered);
  };

  const startDrag = (e: React.MouseEvent) => {
    if (!bulkMode || e.target !== e.currentTarget) return;
    e.preventDefault();
    const start = { x0: e.clientX, y0: e.clientY, x1: e.clientX, y1: e.clientY };
    setDragBox(start);
    const onMove = (ev: MouseEvent) => setDragBox((p) => (p ? { ...p, x1: ev.clientX, y1: ev.clientY } : p));
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setDragBox((box) => { if (box) commitDrag(box); return null; });
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const addSelectedToDraft = () => {
    const f = activeName ? files[activeName] : null;
    if (!f) { toast.error("Chưa chọn file nộp bài — mở tab Nộp bài để tạo/chọn."); return; }
    if (f.kind === "trake") {
      toast.error("Chọn hàng loạt chỉ dùng cho KIS/QA (1 khung/dòng) — TRAKE cần ghép nhiều khung vào 1 dòng, dùng tính năng nộp riêng ở Chuỗi sự kiện.");
      return;
    }
    const byId = new Map(hits.map((h) => [h.id, h]));
    let added = 0;
    for (const id of bulkSelection) {
      const h = byId.get(id);
      if (!h) continue;
      addRow(f.name, { video: h.video, frames: [String(h.frame_idx)] });
      added++;
    }
    toast.success(`Đã thêm ${added} khung vào ${f.name}.csv, theo đúng thứ tự đã chọn`);
    clearBulk();
  };

  // Đo bề rộng THẬT và theo dõi khi đổi cỡ cửa sổ / thu gọn cột — nếu chỉ tính
  // một lần lúc dựng, lưới sẽ giữ nguyên số cột cũ và để trống một khoảng lớn.
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const cols = useMemo(
    () => Math.max(1, Math.floor(((width || 1200) + GAP) / (tileSize + GAP))),
    [width, tileSize]);

  const rowCount = Math.ceil(hits.length / cols);
  // ảnh 16:9 + khối chữ ~52px
  const rowHeight = Math.round(tileSize * 9 / 16) + 52 + GAP;

  const rv = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 3,
  });

  // Con trỏ bàn phím di chuyển ra ngoài màn hình -> tự cuộn theo.
  useEffect(() => {
    if (cursor >= 0) rv.scrollToIndex(Math.floor(cursor / cols), { align: "auto" });
  }, [cursor, cols, rv]);

  return (
    <>
      <div ref={parentRef} className="h-full overflow-y-auto px-3 pb-6 pt-2"
           data-result-scroll onMouseDown={startDrag}>
        <div style={{ height: rv.getTotalSize(), position: "relative" }}>
          {rv.getVirtualItems().map((vr) => {
            const start = vr.index * cols;
            return (
              <div
                key={vr.key}
                className="absolute left-0 top-0 grid w-full"
                onMouseDown={startDrag}
                style={{
                  transform: `translateY(${vr.start}px)`,
                  gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
                  gap: GAP,
                }}
              >
                {hits.slice(start, start + cols).map((h, i) => {
                  const idx = start + i;
                  const bulkIdx = bulkSelection.indexOf(h.id);
                  return (
                    <div key={h.id} onMouseDown={() => !bulkMode && setCursor(idx)}>
                      <ResultTile
                        hit={h}
                        selected={cursor === idx}
                        pinned={pins.some((p) => p.id === h.id)}
                        good={fbPos.some((f) => f.video === h.video && f.n === h.n)}
                        bad={fbNeg.some((f) => f.video === h.video && f.n === h.n)}
                        onOpen={() => a.open(h, hits)}
                        onPin={() => a.pin(h)}
                        onRef={() => a.ref(h)}
                        onGood={() => a.good(h)}
                        onBad={() => a.bad(h)}
                        onCompare={() => a.compare(h)}
                        bulkMode={bulkMode}
                        bulkChecked={bulkIdx >= 0}
                        bulkOrder={bulkIdx >= 0 ? bulkIdx + 1 : undefined}
                        onToggleBulk={() => toggleBulkId(h.id)}
                      />
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      {dragBox && (
        <div className="pointer-events-none fixed z-40 border-2 border-[var(--color-focus)] bg-[color-mix(in_srgb,var(--color-focus)_15%,transparent)]"
             style={{
               left: Math.min(dragBox.x0, dragBox.x1), top: Math.min(dragBox.y0, dragBox.y1),
               width: Math.abs(dragBox.x1 - dragBox.x0), height: Math.abs(dragBox.y1 - dragBox.y0),
             }} />
      )}

      {bulkMode && bulkSelection.length > 0 && (
        <div className="fixed bottom-3 left-1/2 z-30 flex -translate-x-1/2 items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-3 py-2 shadow-2xl">
          <span className="font-mono text-[11.5px] tabular-nums text-[var(--color-fg-dim)]">
            Đã chọn {bulkSelection.length} khung
          </span>
          <Button size="sm" variant="primary" onClick={addSelectedToDraft}>Thêm vào bản nháp</Button>
          <Button size="sm" variant="ghost" onClick={clearBulk}><X size={11} /> Bỏ chọn hết</Button>
        </div>
      )}
    </>
  );
}

/* ------------------------------ Gom theo video ------------------------------ */

function GroupedByVideo({ hits }: { hits: SearchHit[] }) {
  const a = useHitActions();
  const groups = useMemo(() => {
    const m = new Map<string, SearchHit[]>();
    for (const h of hits) {
      const arr = m.get(h.video) ?? [];
      arr.push(h);
      m.set(h.video, arr);
    }
    return [...m.entries()]
      .map(([video, list]) => ({
        video,
        list: [...list].sort((x, y) => (x.pts_time ?? 0) - (y.pts_time ?? 0)),
        best: Math.min(...list.map((x) => x.rank)),
      }))
      .sort((x, y) => y.list.length - x.list.length || x.best - y.best);
  }, [hits]);

  return (
    <div className="h-full overflow-y-auto px-3 pb-6 pt-2">
      <p className="mb-2 text-[11px] text-[var(--color-fg-mute)]">
        Video có nhiều khung hình lọt top thường là video đúng — đây là cách nhanh
        nhất để nhận ra nó.
      </p>
      {groups.map((g) => (
        <div key={g.video} className="mb-3">
          <div className="mb-1 flex items-baseline gap-2">
            <span className="font-mono text-[12px] text-[var(--color-fg)]">{g.video}</span>
            <span className="rounded-full bg-[var(--color-panel-3)] px-1.5 text-[10px] tabular-nums text-[var(--color-fg-dim)]">
              {g.list.length} khung
            </span>
            <span className="font-mono text-[10px] text-[var(--color-fg-mute)]">hạng cao nhất #{g.best}</span>
          </div>
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {g.list.map((h) => (
              <button key={h.id} type="button" onClick={() => a.open(h, g.list)}
                      className="shrink-0 rounded-[var(--radius-sm)] border border-[var(--color-line)] hover:border-[var(--color-focus)]">
                <img src={h.thumb_url} alt="" loading="lazy" className="h-[74px] w-[132px] object-cover" />
                <div className="px-1 py-0.5 text-left font-mono text-[9.5px] tabular-nums text-[var(--color-fg-mute)]">
                  #{h.rank} · f{h.frame_idx}
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------ So sánh ------------------------------ */

function CompareView() {
  const compare = useUi((s) => s.compare);
  const clear = useUi((s) => s.clearCompare);
  const toggle = useUi((s) => s.toggleCompare);

  if (compare.length === 0) {
    return (
      <EmptyState
        title="Chưa chọn khung hình nào để so sánh"
        hint="Rê chuột lên một ô kết quả rồi bấm biểu tượng phóng to, hoặc nhấn phím C. Chọn 2–4 khung để đặt cạnh nhau ở ảnh gốc — dành cho những cảnh nhìn gần giống hệt nhau."
      />
    );
  }
  return (
    <div className="h-full overflow-auto p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[11.5px] text-[var(--color-fg-dim)]">
          So sánh {compare.length} khung hình ở ảnh gốc
        </span>
        <Button size="sm" variant="ghost" onClick={clear}>Bỏ hết</Button>
      </div>
      <div className={cx("grid gap-2", compare.length <= 2 ? "grid-cols-2" : "grid-cols-2 xl:grid-cols-4")}>
        {compare.map((h) => (
          <div key={h.id} className="overflow-hidden rounded-[var(--radius-sm)] border border-[var(--color-line)]">
            <img src={frameUrl(h.video, h.n)} alt="" className="w-full bg-black object-contain" />
            <div className="flex items-center justify-between px-2 py-1">
              <span className="font-mono text-[10.5px] tabular-nums text-[var(--color-fg-dim)]">
                {h.video} · f{h.frame_idx}
              </span>
              <Button size="sm" variant="ghost" onClick={() => toggle(h)}>Bỏ</Button>
            </div>
            {h.content?.ocr && (
              <div className="border-t border-[var(--color-line)] px-2 py-1 text-[10.5px] text-[var(--color-fg-mute)]">
                <span className="text-[var(--color-sig-ocr)]">chữ:</span> {h.content.ocr.slice(0, 120)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------ Thanh công cụ + vỏ ------------------------------ */

export function ResultArea({ data, isLoading, error, onRetry }: {
  data?: SearchResponse; isLoading: boolean; error: Error | null; onRetry: () => void;
}) {
  const view = useUi((s) => s.resultView);
  const setView = useUi((s) => s.setResultView);
  const branchTab = useUi((s) => s.branchTab);
  const setBranchTab = useUi((s) => s.setBranchTab);
  const tileSize = useUi((s) => s.tileSize);
  const setTileSize = useUi((s) => s.setTileSize);
  const bulkMode = useUi((s) => s.bulkMode);
  const setBulkMode = useUi((s) => s.setBulkMode);
  const clearBulk = useUi((s) => s.clearBulk);

  const hits = useMemo(() => {
    if (!data) return [];
    if (!branchTab) return data.hits;
    return data.branch_rankings.find((b) => b.branch === branchTab)?.hits ?? [];
  }, [data, branchTab]);

  const activeBranches = data?.branch_rankings.map((b) => b.branch) ?? [];

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--color-line)] px-3 py-1.5">
        {isLoading ? (
          <span className="flex items-center gap-1.5 text-[11.5px] text-[var(--color-fg-dim)]">
            <Loader2 size={12} className="animate-spin" /> Đang tìm…
          </span>
        ) : data ? (
          <span className="font-mono text-[11.5px] tabular-nums text-[var(--color-fg-dim)]">
            {hits.length} kết quả
            <span className="text-[var(--color-fg-mute)]"> / {data.total_candidates} ứng viên · {data.took_ms}ms</span>
          </span>
        ) : null}

        {activeBranches.length > 0 && (
          <div className="flex items-center gap-1">
            <span className="label-xs">Xem nhánh:</span>
            <button type="button" onClick={() => setBranchTab("")}
                    className={cx("rounded-[2px] px-1.5 py-0.5 font-mono text-[10px]",
                      !branchTab ? "bg-[var(--color-panel-3)] text-[var(--color-fg)]" : "text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]")}>
              GỘP
            </button>
            {activeBranches.map((b) => {
              const meta = BRANCHES.find((x) => x.key === b);
              return (
                <button key={b} type="button" onClick={() => setBranchTab(b)}
                        title={`Chỉ xem xếp hạng của ${meta?.label ?? b}`}
                        className={cx("rounded-[2px] px-1.5 py-0.5 font-mono text-[10px] transition-colors",
                          branchTab === b ? "bg-[var(--color-panel-3)]" : "hover:bg-[var(--color-panel-2)]")}
                        style={{ color: branchTab === b ? BRANCH_COLOR[b] : "var(--color-fg-mute)" }}>
                  {meta?.short ?? b}
                </button>
              );
            })}
          </div>
        )}

        <div className="ml-auto flex items-center gap-1">
          {view === "grid" && (
            <button type="button"
                    onClick={() => { setBulkMode(!bulkMode); if (bulkMode) clearBulk(); }}
                    title="Chọn hàng loạt — tick từng ô hoặc kéo bôi đen 1 vùng, dùng khi không chắc đáp án nào đúng"
                    className={cx("mr-1 flex items-center gap-1 rounded-[2px] px-1.5 py-1 text-[10.5px] transition-colors",
                      bulkMode ? "bg-[var(--color-focus)] text-[#0B1220]" : "text-[var(--color-fg-mute)] hover:bg-[var(--color-panel-2)] hover:text-[var(--color-fg-dim)]")}>
              <CheckSquare size={12} /> Chọn hàng loạt
            </button>
          )}
          {([["grid", Grid3x3, "Lưới"], ["byVideo", LayoutList, "Gom theo video"],
             ["compare", Columns3, "So sánh"]] as const).map(([v, Icon, title]) => (
            <button key={v} type="button" onClick={() => setView(v)} title={title} aria-label={title}
                    className={cx("rounded-[2px] p-1 transition-colors",
                      view === v ? "bg-[var(--color-panel-3)] text-[var(--color-fg)]" : "text-[var(--color-fg-mute)] hover:text-[var(--color-fg-dim)]")}>
              <Icon size={13} />
            </button>
          ))}
          {view === "grid" && (
            <input type="range" min={110} max={420} step={10} value={tileSize}
                   onChange={(e) => setTileSize(Number(e.target.value))}
                   title="Cỡ ảnh" aria-label="Cỡ ảnh"
                   className="ml-1 h-1 w-[74px] accent-[var(--color-focus)]" />
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {error ? (
          <EmptyState
            title="Không tìm được"
            hint={
              /encoder|404|Connection|timeout|Max retries/i.test(error.message)
                ? "Không gọi được máy encode trên Kaggle. Mở bảng Kết nối (Ctrl+K → \"kết nối\") và dán URL mới. Các thao tác không cần GPU — lọc theo chữ, xem video, nộp bài — vẫn dùng được."
                : error.message
            }
            action={<Button className="mt-2" onClick={onRetry}>Thử lại</Button>}
          />
        ) : view === "compare" ? (
          <CompareView />
        ) : !data ? (
          <EmptyState
            title="Nhập mô tả cảnh cần tìm rồi nhấn Enter"
            hint="Nhớ chữ xuất hiện trên màn hình thì mở ô Chữ trên hình; nhớ lời người nói thì mở ô Lời thoại. Chúng chỉ chạy khi bạn tự nhập."
          />
        ) : hits.length === 0 ? (
          <EmptyState
            title="Không có khung hình nào khớp"
            hint={
              data.strict_filter_applied
                ? `Đang bật lọc cứng và chỉ còn ${data.strict_filter_pool_size} khung hình để tìm. Nới cách khớp OCR/ASR hoặc chuyển về chế độ Cộng điểm.`
                : "Thử bớt mệnh đề, hạ trọng số nhánh đang lấn át, hoặc bỏ giới hạn phạm vi video."
            }
          />
        ) : view === "byVideo" ? (
          <GroupedByVideo hits={hits} />
        ) : (
          <VirtualGrid hits={hits} />
        )}
      </div>
    </div>
  );
}
