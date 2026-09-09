import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface TeamIdentityState {
  displayName: string;
  memberId: string;
  setIdentity: (displayName: string, memberId: string) => void;
}

export const useTeamIdentity = create<TeamIdentityState>()(
  persist(
    (set) => ({
      displayName: "",
      memberId: "",
      setIdentity: (displayName, memberId) => set({ displayName: displayName.trim(), memberId: memberId.trim().toLowerCase() }),
    }),
    { name: "aic-team-identity" },
  ),
);

export const isValidMemberId = (value: string) => /^[a-z0-9_-]{4,64}$/.test(value.trim().toLowerCase());
