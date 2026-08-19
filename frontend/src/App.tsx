import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { Toaster } from "sonner";

import { ConnectionDialog, ShortcutsDialog } from "./app/Dialogs";
import { Topbar } from "./app/Topbar";
import { CsvPreviewModal } from "./features/submission/CsvPreviewModal";
import { DetailOverlay } from "./features/viewer/DetailOverlay";
import { WorkbenchOverlay } from "./features/workbench/WorkbenchOverlay";
import { SearchPage } from "./pages/SearchPage";
import { TemporalPage } from "./pages/TemporalPage";
import { useUi } from "./stores/uiStore";

// staleTime dài: trong lúc thi, cùng một truy vấn được xem đi xem lại nhiều lần
// — không có lý do gọi lại máy chủ. retry=0 vì lỗi ở đây thường là encoder chết,
// thử lại tự động chỉ làm người dùng chờ lâu hơn mà không sửa được gì.
const qc = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60_000, gcTime: 30 * 60_000, retry: 0, refetchOnWindowFocus: false },
  },
});

/** Cả 2 trang LUÔN mounted, chỉ ẩn/hiện bằng CSS (display:contents/none) thay
 *  vì để React Router unmount trang không active — chuyển tab trước đây làm
 *  MẤT SẠCH state cục bộ của trang kia (câu query, kết quả tìm, chuỗi sự kiện
 *  đang soạn...) vì component bị huỷ hoàn toàn rồi tạo lại từ đầu lúc quay lại.
 *  `display:contents` khi đang hiện để trang bên trong vẫn là flex item trực
 *  tiếp của khung cha (không tạo thêm 1 lớp box chen vào layout). */
function Pages() {
  const { pathname } = useLocation();
  return (
    <>
      <div style={{ display: pathname === "/" ? "contents" : "none" }}>
        <SearchPage />
      </div>
      <div style={{ display: pathname === "/temporal" ? "contents" : "none" }}>
        <TemporalPage />
      </div>
    </>
  );
}

export function App() {
  const csvPreviewOpen = useUi((s) => s.csvPreviewOpen);
  const setCsvPreviewOpen = useUi((s) => s.setCsvPreviewOpen);
  return (
    <QueryClientProvider client={qc}>
      <div className="flex h-full flex-col">
        <Topbar />
        <Pages />
      </div>
      <DetailOverlay />
      <WorkbenchOverlay />
      <ConnectionDialog />
      <ShortcutsDialog />
      <CsvPreviewModal open={csvPreviewOpen} onOpenChange={setCsvPreviewOpen} />
      <Toaster theme="dark" position="bottom-center" richColors closeButton
               toastOptions={{ style: { fontSize: "12px" } }} />
    </QueryClientProvider>
  );
}
