// Dark IDE palette and fonts from CLAUDE.md §8.
// Tailwind 3 on purpose: Tailwind 4's native class scanner is blocked by Windows Smart App
// Control on the owner's machine, and its WebAssembly fallback finds no classes.
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#06080b",
        panel: "#0c1015",
        raised: "#141a22",
        line: "#1d2530",
        ink: "#e6eaf0",
        mute: "#9aa6b5",
        cyan: "#5cc8e8",
        amber: "#f2b24a",
        coral: "#ff7a6b",
        green: "#6fd08c",
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", '"Cascadia Mono"', "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
