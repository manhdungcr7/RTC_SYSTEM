import { useState } from "react";

import { FrameDetailModal } from "../components/search/FrameDetailModal";
import { QueryBox } from "../components/search/QueryBox";
import { ResultGrid } from "../components/search/ResultGrid";
import { SignalsPanel } from "../components/search/SignalsPanel";
import { useSearch } from "../hooks/useSearch";
import type { SearchHit, SearchRequest } from "../types/search";

export function SearchPage() {
  const { hits, loading, error, clausesMetaclip2, clausesEn, ocrKeywords, signalsUsed, runSearch } = useSearch();
  const [selected, setSelected] = useState<SearchHit | null>(null);

  const onSearch = (req: SearchRequest) => runSearch(req);

  return (
    <div className="search-page">
      <QueryBox onSearch={onSearch} loading={loading} />
      {error && <div className="search-error">Lỗi: {error}</div>}
      <SignalsPanel
        clausesMetaclip2={clausesMetaclip2}
        clausesEn={clausesEn}
        ocrKeywords={ocrKeywords}
        signalsUsed={signalsUsed}
      />
      <ResultGrid hits={hits} onSelect={setSelected} />
      {selected && <FrameDetailModal hit={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
