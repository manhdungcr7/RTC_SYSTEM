/** Chỉ giữ lựa chọn giao diện; token DRES nằm trong RAM backend dùng chung. */
import { create } from "zustand";

interface DresState {
  sessionVersion: number;
  evaluationId: string;
  submittedAnswers: string[];
  syncSession: (version: number) => void;
  setEvaluationId: (id: string) => void;
  markSubmitted: (key: string) => void;
}

export const useDres = create<DresState>((set) => ({
  sessionVersion: -1, evaluationId: "", submittedAnswers: [],
  syncSession: (version) => set((state) => state.sessionVersion === version ? state : ({
    sessionVersion: version, evaluationId: "", submittedAnswers: [],
  })),
  setEvaluationId: (evaluationId) => set({ evaluationId }),
  markSubmitted: (key) => set((state) => ({
    submittedAnswers: state.submittedAnswers.includes(key)
      ? state.submittedAnswers : [...state.submittedAnswers, key],
  })),
}));
