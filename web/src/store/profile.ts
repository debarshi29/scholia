// Which local profile this browser is using. Sent as `X-Profile` on every API call.
// There is no login: profiles keep progress apart, they do not protect it.
import { create } from "zustand";
import { persist } from "zustand/middleware";

export const DEFAULT_PROFILE = "default";

interface ProfileState {
  id: string;
  setProfile: (id: string) => void;
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set) => ({ id: DEFAULT_PROFILE, setProfile: (id) => set({ id }) }),
    { name: "scholia-profile", version: 1 },
  ),
);
