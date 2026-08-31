import { create } from "zustand";
import { persist } from "zustand/middleware";

interface TeamBoardState {
  activeBatchId: string | null;
  setActiveBatchId: (batchId: string | null) => void;
}

export const useTeamBoard = create<TeamBoardState>()(
  persist(
    (set) => ({ activeBatchId: null, setActiveBatchId: (activeBatchId) => set({ activeBatchId }) }),
    { name: "aic-team-board" },
  ),
);
