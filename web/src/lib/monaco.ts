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

export const THEME = "scholia";

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };

monaco.editor.defineTheme(THEME, {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "comment", foreground: "6b7785", fontStyle: "italic" },
    { token: "keyword", foreground: "5cc8e8" },
    { token: "string", foreground: "6fd08c" },
    { token: "number", foreground: "f2b24a" },
    { token: "type", foreground: "e6eaf0" },
  ],
  colors: {
    "editor.background": "#0e1116",
    "editor.foreground": "#e6eaf0",
    "editorLineNumber.foreground": "#5b6675",
    "editorLineNumber.activeForeground": "#e6eaf0",
    "editor.lineHighlightBackground": "#151a21",
    "editor.lineHighlightBorder": "#00000000",
    "editor.selectionBackground": "#5cc8e84d",
    "editor.inactiveSelectionBackground": "#5cc8e833",
    "editor.wordHighlightBackground": "#5cc8e822",
    "editorCursor.foreground": "#5cc8e8",
    "editorIndentGuide.background1": "#1b222b",
    "editorWidget.background": "#151a21",
    "editorWidget.border": "#2a333f",
    "input.background": "#0e1116",
    "input.border": "#2a333f",
    "focusBorder": "#5cc8e8",
    "scrollbarSlider.background": "#2a333f80",
    "scrollbarSlider.hoverBackground": "#2a333fcc",
  },
});

loader.config({ monaco });

export { monaco };
