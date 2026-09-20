import { Download } from "lucide-react";
import { useState } from "react";

import { Button } from "../../components/ui";
import { DEFAULT_VIDEO_LIMIT, formatVideoList, rankedVideoList } from "./videoList";

export function VideoListDownload({ videoIds, disabled = false }: {
  videoIds: readonly string[];
  disabled?: boolean;
}) {
  const [limit, setLimit] = useState(DEFAULT_VIDEO_LIMIT);
  const count = rankedVideoList(videoIds, limit).length;

  const download = () => {
    if (disabled || count === 0) return;
    const blob = new Blob([formatVideoList(videoIds, limit)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `videos-top-${limit}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Allow the browser to begin consuming the blob before releasing it.
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="flex items-center gap-1.5">
      <label className="flex items-center gap-1 text-[11px] text-[var(--color-fg-dim)]">
        Top N video
        <input
          type="number" min={1} step={1} value={limit}
          aria-label="Số video tối đa trong danh sách tải xuống"
          onChange={(e) => setLimit(Math.max(1, Math.floor(Number(e.target.value) || 1)))}
          className="w-[58px] rounded-[2px] border border-[var(--color-line)] bg-[var(--color-panel-2)] px-1.5 py-1 font-mono text-[11px]"
        />
      </label>
      <Button size="sm" onClick={download} disabled={disabled || count === 0}
              title="Video duy nhất từ kết quả gộp, theo thứ tự xếp hạng. Chỉ tải các video đã trả về, không truy vấn thêm.">
        <Download size={12} /> Tải danh sách video ({count})
      </Button>
    </div>
  );
}
