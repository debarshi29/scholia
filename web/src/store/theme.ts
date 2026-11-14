// Light or dark. The first visit follows the operating system; the toggle then stores an
// explicit choice. index.html applies the stored theme before first paint (no flash).
import { useEffect, useSyncExternalStore } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "light" | "dark";
type Mode = Theme | "system";

interface ThemeState {
  mode: Mode;
  setMode: (mode: Mode) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist((set) => ({ mode: "system", setMode: (mode) => set({ mode }) }), {
    name: "scholia-theme",
    version: 1,
  }),
);

const query = () => window.matchMedia("(prefers-color-scheme: dark)");

function systemTheme(): Theme {
  return query().matches ? "dark" : "light";
}

function subscribeSystem(listener: () => void): () => void {
  const q = query();
  q.addEventListener("change", listener);
  return () => q.removeEventListener("change", listener);
}

/** The theme in effect, and a function that flips it. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  const system = useSyncExternalStore(subscribeSystem, systemTheme, () => "dark" as Theme);
  const theme: Theme = mode === "system" ? system : mode;
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return { theme, toggle: () => setMode(theme === "dark" ? "light" : "dark") };
}
