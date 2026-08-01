import { useState } from "react";

import { FrameDetailModal } from "../components/search/FrameDetailModal";
import { ImageSearchBox } from "../components/search/ImageSearchBox";
import { QueryBox } from "../components/search/QueryBox";
import { ResultGrid } from "../components/search/ResultGrid";
import { SignalsPanel } from "../components/search/SignalsPanel";
import { VideoFilterPanel } from "../components/search/VideoFilterPanel";
import { useImageSearch } from "../hooks/useImageSearch";
import { useSearch } from "../hooks/useSearch";
import type { SearchHit, SearchRequest } from "../types/search";

export function SearchPage() {
  const {
    hits, loading, error, clausesMetaclip2, clausesEn, ocrKeywords, signalsUsed,
    strictFilterApplied, strictFilterPoolSize, runSearch,
  } = useSearch();
  const imageSearch = useImageSearch();
  const [selected, setSelected] = useState<SearchHit | null>(null);
  const [videoScope, setVideoScope] = useState<string[] | null>(null);

  const onSearch = (req: SearchRequest) => runSearch(req);

  return (
    <div className="search-page">
      <VideoFilterPanel onUseAsScope={setVideoScope} />
      <QueryBox onSearch={onSearch} loading={loading} videoScope={videoScope} onClearScope={() => setVideoScope(null)} />
      {error && <div className="search-error">Lỗi: {error}</div>}
      {strictFilterApplied && (
        <div className="strict-filter-banner">
          ✓ Đã kích hoạt lọc chắc chắn OCR/ASR — các nhánh khác chỉ tìm trong {strictFilterPoolSize} khung hình đã khớp.
        </div>
      )}
      <SignalsPanel
        clausesMetaclip2={clausesMetaclip2}
        clausesEn={clausesEn}
        ocrKeywords={ocrKeywords}
        signalsUsed={signalsUsed}
      />
      <ResultGrid hits={hits} onSelect={setSelected} />

      <ImageSearchBox onSearch={imageSearch.runImageSearch} loading={imageSearch.loading} />
      {imageSearch.error && <div className="search-error">Lỗi: {imageSearch.error}</div>}
      {imageSearch.hits.length > 0 && (
        <>
          <div className="image-search-results-title">Kết quả tìm theo ảnh:</div>
          <ResultGrid hits={imageSearch.hits} onSelect={setSelected} />
        </>
      )}

      {selected && <FrameDetailModal hit={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
