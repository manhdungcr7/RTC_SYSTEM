import { useCallback, useMemo, useState } from "react";

import { SubmissionContext, type SubmissionFile, type SubmissionRow } from "../../services/submission";
import type { QueryKind } from "../../types/search";

export function SubmissionProvider({ children }: { children: React.ReactNode }) {
  const [files, setFiles] = useState<Record<string, SubmissionFile>>({});
  const [activeFile, setActiveFile] = useState("query-p1-1-kis");
  const [activeKind, setActiveKind] = useState<QueryKind>("kis");

  const setActive = useCallback((filename: string, kind: QueryKind) => {
    setActiveFile(filename);
    setActiveKind(kind);
  }, []);

  const addRow = useCallback((filename: string, kind: QueryKind, row: SubmissionRow) => {
    setFiles((prev) => {
      const existing = prev[filename] ?? { kind, rows: [] };
      return { ...prev, [filename]: { kind, rows: [...existing.rows, row] } };
    });
  }, []);

  const removeRow = useCallback((filename: string, index: number) => {
    setFiles((prev) => {
      const existing = prev[filename];
      if (!existing) return prev;
      return { ...prev, [filename]: { ...existing, rows: existing.rows.filter((_, i) => i !== index) } };
    });
  }, []);

  const removeFile = useCallback((filename: string) => {
    setFiles((prev) => {
      const next = { ...prev };
      delete next[filename];
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({ files, addRow, removeRow, removeFile, activeFile, activeKind, setActive }),
    [files, addRow, removeRow, removeFile, activeFile, activeKind, setActive],
  );

  return <SubmissionContext.Provider value={value}>{children}</SubmissionContext.Provider>;
}
