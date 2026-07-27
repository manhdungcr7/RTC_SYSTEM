import { useState } from "react";

import { useSubmissionStore } from "../services/submission";
import type { QueryKind } from "../types/search";

interface BuildResult {
  csv_text: string;
  errors: string[];
}

export function SubmitPage() {
  const { files, activeFile, activeKind, setActive, removeRow, removeFile } = useSubmissionStore();
  const [newFileName, setNewFileName] = useState("query-p1-1-kis");
  const [newKind, setNewKind] = useState<QueryKind>("kis");
  const [builds, setBuilds] = useState<Record<string, BuildResult>>({});
  const [packing, setPacking] = useState(false);

  const buildOne = async (filename: string) => {
    const file = files[filename];
    if (!file) return;
    const rows = file.rows.map((r) => [r.video, r.frame_idx]);
    const res = await fetch("/api/submit/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: file.kind, rows }),
    });
    const data: BuildResult = await res.json();
    setBuilds((prev) => ({ ...prev, [filename]: data }));
  };

  const packAll = async () => {
    setPacking(true);
    try {
      const filesToPack: Record<string, string> = {};
      for (const [filename, file] of Object.entries(files)) {
        const rows = file.rows.map((r) => [r.video, r.frame_idx]);
        const res = await fetch("/api/submit/build", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: file.kind, rows }),
        });
        const data: BuildResult = await res.json();
        filesToPack[`${filename}.csv`] = data.csv_text;
      }
      const packRes = await fetch("/api/submit/pack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: filesToPack }),
      });
      const blob = await packRes.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "submission.zip";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setPacking(false);
    }
  };

  return (
    <div className="submit-page">
      <div className="submit-new-file">
        <input value={newFileName} onChange={(e) => setNewFileName(e.target.value)} placeholder="tên file (không .csv)" />
        <select value={newKind} onChange={(e) => setNewKind(e.target.value as QueryKind)}>
          <option value="kis">KIS</option>
          <option value="qa">QA</option>
          <option value="trake">TRAKE</option>
        </select>
        <button onClick={() => setActive(newFileName, newKind)}>Đặt làm file đang chọn</button>
        <span>Đang chọn: <code>{activeFile}.csv</code> ({activeKind})</span>
      </div>

      {Object.keys(files).length === 0 && (
        <div className="result-grid-empty">
          Chưa có file nào — sang trang Search/Temporal, mở chi tiết 1 frame rồi bấm "+ Thêm frame này".
        </div>
      )}

      {Object.entries(files).map(([filename, file]) => (
        <div className="submit-file-card" key={filename}>
          <div className="submit-file-header">
            <strong>{filename}.csv</strong> ({file.kind}, {file.rows.length} dòng)
            <button onClick={() => removeFile(filename)}>Xoá file</button>
            <button onClick={() => buildOne(filename)}>Xem trước CSV</button>
          </div>
          <table>
            <tbody>
              {file.rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.video}</td>
                  <td>{r.frame_idx}</td>
                  <td><button onClick={() => removeRow(filename, i)}>Xoá</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {builds[filename] && (
            <div className="submit-preview">
              {builds[filename].errors.length > 0 ? (
                <ul className="submit-errors">
                  {builds[filename].errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              ) : (
                <pre>{builds[filename].csv_text}</pre>
              )}
            </div>
          )}
        </div>
      ))}

      {Object.keys(files).length > 0 && (
        <button className="submit-pack-btn" onClick={packAll} disabled={packing}>
          {packing ? "Đang đóng gói..." : "Đóng gói ZIP (submission/)"}
        </button>
      )}
    </div>
  );
}
