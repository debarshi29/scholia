// Light/dark switch for every top bar. It shows the theme you would switch to.
import { useTheme } from "../store/theme";
import { Moon, Sun } from "./icons";

export default function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      className="flex size-9 items-center justify-center rounded-md border border-line text-mute transition hover:border-mute/60 hover:bg-raised hover:text-ink"
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}
