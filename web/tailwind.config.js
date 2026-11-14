// Paper palette in light and dark, from CSS variables (see src/index.css) so one class
// works in both themes. Colours are space-separated RGB channels, which keeps Tailwind's
// opacity modifiers (`bg-cyan/10`) working. `cyan` is the accent (teal), kept by name.
// Tailwind 3 on purpose: Tailwind 4's native class scanner is blocked by Windows Smart App
// Control on the owner's machine, and its WebAssembly fallback finds no classes.
const c = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: c("bg"),
        panel: c("panel"),
        raised: c("raised"),
        line: c("line"),
        ink: c("ink"),
        mute: c("mute"),
        cyan: c("accent"),
        amber: c("amber"),
        coral: c("coral"),
        green: c("green"),
        on: c("on"),
      },
      borderRadius: { md: "4px", lg: "6px", xl: "8px" },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["Newsreader", "Georgia", "ui-serif", "serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", '"Cascadia Mono"', "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
