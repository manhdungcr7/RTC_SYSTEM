import { Route, Routes } from "react-router-dom";

import { SubmissionProvider } from "./components/submit/SubmissionProvider";
import { Header } from "./components/layout/Header";
import { SearchPage } from "./pages/SearchPage";
import { SubmitPage } from "./pages/SubmitPage";
import { TemporalPage } from "./pages/TemporalPage";

export function App() {
  return (
    <SubmissionProvider>
      <Header />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/temporal" element={<TemporalPage />} />
          <Route path="/submit" element={<SubmitPage />} />
        </Routes>
      </main>
    </SubmissionProvider>
  );
}
