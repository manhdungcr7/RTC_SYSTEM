import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { ConnectionDialog, ShortcutsDialog } from "./app/Dialogs";
import { Topbar } from "./app/Topbar";
import { DetailOverlay } from "./features/viewer/DetailOverlay";
import { WorkbenchOverlay } from "./features/workbench/WorkbenchOverlay";
import { SearchPage } from "./pages/SearchPage";
import { TemporalPage } from "./pages/TemporalPage";

// staleTime dài: trong lúc thi, cùng một truy vấn được xem đi xem lại nhiều lần
// — không có lý do gọi lại máy chủ. retry=0 vì lỗi ở đây thường là encoder chết,
// thử lại tự động chỉ làm người dùng chờ lâu hơn mà không sửa được gì.
const qc = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60_000, gcTime: 30 * 60_000, retry: 0, refetchOnWindowFocus: false },
  },
});

export function App() {
  return (
    <QueryClientProvider client={qc}>
      <div className="flex h-full flex-col">
        <Topbar />
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/temporal" element={<TemporalPage />} />
        </Routes>
      </div>
      <DetailOverlay />
      <WorkbenchOverlay />
      <ConnectionDialog />
      <ShortcutsDialog />
      <Toaster theme="dark" position="bottom-center" richColors closeButton
               toastOptions={{ style: { fontSize: "12px" } }} />
    </QueryClientProvider>
  );
}
