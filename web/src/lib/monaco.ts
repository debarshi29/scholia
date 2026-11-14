// Monaco, bundled locally (no CDN) and trimmed to what a read-only Python viewer needs:
// the editor core, Python highlighting, find, folding, go-to-line and bracket matching.
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/editor/editor.api";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
import "monaco-editor/editor/contrib/bracketMatching/browser/bracketMatching";
import "monaco-editor/editor/contrib/folding/browser/folding";
import "monaco-editor/editor/contrib/wordHighlighter/browser/wordHighlighter";
import "monaco-editor/editor/standalone/browser/quickAccess/standaloneGotoLineQuickAccess";
import "monaco-editor/features/find/register";
import "monaco-editor/languages/definitions/python/register";
// Monaco's icon font (fold arrows, find-widget buttons). The package's export map only
// exposes .js modules, so the stylesheet is imported by path.
import "../../node_modules/monaco-editor/esm/vs/base/browser/ui/codicons/codicon/codicon.css";
import "../../node_modules/monaco-editor/esm/vs/base/browser/ui/codicons/codicon/codicon-modifiers.css";

export const THEMES = { light: "scholia-light", dark: "scholia-dark" } as const;

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };

// The Paper palette (src/index.css). Monaco needs literal colours, so they are repeated here.
monaco.editor.defineTheme(THEMES.light, {
  base: "vs",
  inherit: true,
  rules: [
    { token: "comment", foreground: "8a8170", fontStyle: "italic" },
    { token: "keyword", foreground: "8a3fb0" },
    { token: "identifier", foreground: "2b261f" },
    { token: "delimiter", foreground: "6b6358" },
    { token: "tag", foreground: "1e6e78" },
    { token: "string", foreground: "2f6b4f" },
    { token: "number", foreground: "9a5b00" },
    { token: "type", foreground: "1f5fa8" },
  ],
  colors: {
    "editor.background": "#fffdf9",
    "editor.foreground": "#2b261f",
    "editorLineNumber.foreground": "#b3a995",
    "editorLineNumber.activeForeground": "#1f1b16",
    "editor.lineHighlightBackground": "#f7f4ee",
    "editor.lineHighlightBorder": "#00000000",
    "editor.selectionBackground": "#1e6e7833",
    "editor.inactiveSelectionBackground": "#1e6e7826",
    "editor.wordHighlightBackground": "#1e6e7822",
    "editorCursor.foreground": "#1e6e78",
    "editorIndentGuide.background1": "#ebe4d6",
    "editorWidget.background": "#f1ece2",
    "editorWidget.border": "#e2dacb",
    "input.background": "#fffdf9",
    "input.border": "#e2dacb",
    "focusBorder": "#1e6e78",
    "scrollbarSlider.background": "#6b635866",
    "scrollbarSlider.hoverBackground": "#6b6358aa",
  },
});

monaco.editor.defineTheme(THEMES.dark, {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "comment", foreground: "7d7262", fontStyle: "italic" },
    { token: "keyword", foreground: "d3a1f0" },
    { token: "identifier", foreground: "e6dccb" },
    { token: "delimiter", foreground: "a69a86" },
    { token: "tag", foreground: "5fb8c2" },
    { token: "string", foreground: "a6d9a0" },
    { token: "number", foreground: "e0b15a" },
    { token: "type", foreground: "8fbcff" },
  ],
  colors: {
    "editor.background": "#1c1712",
    "editor.foreground": "#e6dccb",
    "editorLineNumber.foreground": "#6f6453",
    "editorLineNumber.activeForeground": "#efe6d6",
    "editor.lineHighlightBackground": "#211b15",
    "editor.lineHighlightBorder": "#00000000",
    "editor.selectionBackground": "#5fb8c240",
    "editor.inactiveSelectionBackground": "#5fb8c233",
    "editor.wordHighlightBackground": "#5fb8c222",
    "editorCursor.foreground": "#5fb8c2",
    "editorIndentGuide.background1": "#2f2820",
    "editorWidget.background": "#1f1a15",
    "editorWidget.border": "#2f2820",
    "input.background": "#17130f",
    "input.border": "#2f2820",
    "focusBorder": "#5fb8c2",
    "scrollbarSlider.background": "#a69a8666",
    "scrollbarSlider.hoverBackground": "#a69a86aa",
  },
});

loader.config({ monaco });

export { monaco };
