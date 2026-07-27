import type { SignalInfo } from "../../types/search";

interface Props {
  clausesMetaclip2: string[];
  clausesEn: string[];
  ocrKeywords: string[];
  signalsUsed: SignalInfo[];
}

export function SignalsPanel({ clausesMetaclip2, clausesEn, ocrKeywords, signalsUsed }: Props) {
  if (signalsUsed.length === 0 && clausesMetaclip2.length === 0) return null;

  return (
    <details className="signals-panel">
      <summary>Chi tiết truy vấn đã dùng ({signalsUsed.length} nguồn tín hiệu)</summary>
      <div className="signals-panel-body">
        {clausesMetaclip2.length > 0 && (
          <div className="signals-group">
            <span className="signals-group-label">Mệnh đề (metaclip2):</span>
            {clausesMetaclip2.map((c) => <span key={c} className="clause-chip">{c}</span>)}
          </div>
        )}
        {clausesEn.length > 0 && (
          <div className="signals-group">
            <span className="signals-group-label">Mệnh đề tiếng Anh (pecore/beit3):</span>
            {clausesEn.map((c) => <span key={c} className="clause-chip">{c}</span>)}
          </div>
        )}
        {ocrKeywords.length > 0 && (
          <div className="signals-group">
            <span className="signals-group-label">Từ khoá OCR (LLM trích):</span>
            {ocrKeywords.map((c) => <span key={c} className="clause-chip clause-chip-ocr">{c}</span>)}
          </div>
        )}
        <table className="signals-table">
          <thead>
            <tr><th>Nguồn</th><th>Trọng số</th><th>Số khung khớp</th><th>Câu/từ đã tra</th></tr>
          </thead>
          <tbody>
            {signalsUsed.map((s, i) => (
              <tr key={i}>
                <td>{s.name}</td>
                <td>{s.weight.toFixed(2)}</td>
                <td>{s.n_hits}</td>
                <td className="signals-table-query">{s.query_text ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
