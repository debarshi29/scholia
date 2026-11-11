// Read-only Monaco viewer. Click a line number, then another, to select a range (dragging
// works too). The selection is reported upwards, where it drives asking and flagging.
// Flagged lines get a coral tint and a dot in the margin.
import Editor, { type OnMount } from "@monaco-editor/react";
import { useEffect, useRef } from "react";
import { monaco, THEME } from "../lib/monaco";

export interface LineRange {
  from: number;
  to: number;
}

interface Props {
  /** Unique per file, so Monaco keeps a scroll position and selection for each one. */
  modelPath: string;
  content: string;
  flagged: LineRange[];
  onSelect?: (range: LineRange | null) => void;
  /** Bump `nonce` to scroll to `line` again. */
  reveal?: { line: number; nonce: number } | null;
}

type Collection = monaco.editor.IEditorDecorationsCollection;

export default function CodeViewer(props: Props) {
  const { modelPath, content, flagged, onSelect, reveal } = props;
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const decorations = useRef<Collection | null>(null);
  const anchor = useRef<number | null>(null);
  const onSelectRef = useRef(onSelect);
  const revealRef = useRef(reveal);
  useEffect(() => {
    onSelectRef.current = onSelect;
    revealRef.current = reveal;
  }, [onSelect, reveal]);

  const paint = () => {
    const editor = editorRef.current;
    if (!editor) return;
    decorations.current?.clear();
    decorations.current = editor.createDecorationsCollection(
      flagged.flatMap((r) => [
        {
          range: new monaco.Range(r.from, 1, r.to, 1),
          options: { isWholeLine: true, className: "flagged-line" },
        },
        // One dot per finding, on its first line.
        {
          range: new monaco.Range(r.from, 1, r.from, 1),
          options: { glyphMarginClassName: "flagged-dot" },
        },
      ]),
    );
  };

  const report = () => {
    const sel = editorRef.current?.getSelection();
    if (!sel || sel.isEmpty()) {
      onSelectRef.current?.(null);
      return;
    }
    // Dragging over whole lines leaves the caret at column 1 of the next line.
    const endsAtLineStart = sel.endColumn === 1 && sel.endLineNumber > sel.startLineNumber;
    onSelectRef.current?.({
      from: sel.startLineNumber,
      to: endsAtLineStart ? sel.endLineNumber - 1 : sel.endLineNumber,
    });
  };

  const onMount: OnMount = (mounted) => {
    const editor = mounted as unknown as monaco.editor.IStandaloneCodeEditor;
    editorRef.current = editor;
    editor.onDidChangeCursorSelection(report);
    editor.onDidChangeModel(() => {
      anchor.current = null;
      paint();
      report();
    });
    // First click on a line number selects that line; the next click extends to it.
    editor.onMouseDown((e) => {
      const line = e.target.position?.lineNumber;
      const onNumber =
        e.target.type === monaco.editor.MouseTargetType.GUTTER_LINE_NUMBERS ||
        e.target.type === monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN;
      if (!onNumber || line === undefined) {
        anchor.current = null;
        return;
      }
      const start = anchor.current ?? line;
      anchor.current = anchor.current === null ? line : null;
      const from = Math.min(start, line);
      const to = Math.max(start, line);
      // After Monaco's own handler, which selects just the clicked line.
      setTimeout(() => {
        const model = editor.getModel();
        if (model) editor.setSelection(new monaco.Range(from, 1, to, model.getLineMaxColumn(to)));
      }, 0);
    });
    paint();
    // The first reveal usually arrives before the editor exists.
    if (revealRef.current) editor.revealLineInCenter(revealRef.current.line);
  };

  // Repaint when the flags or the file change.
  const signature = JSON.stringify([modelPath, flagged]);
  useEffect(paint, [signature]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (reveal) editorRef.current?.revealLineInCenter(reveal.line);
  }, [reveal, modelPath]);

  return (
    <Editor
      path={modelPath}
      value={content}
      language="python"
      theme={THEME}
      onMount={onMount}
      loading={<p className="p-4 text-mute">Loading the editor…</p>}
      options={{
        readOnly: true,
        domReadOnly: true,
        minimap: { enabled: false },
        fontFamily: '"IBM Plex Mono", ui-monospace, Consolas, monospace',
        fontSize: 13.5,
        lineHeight: 22,
        lineNumbersMinChars: 4,
        lineDecorationsWidth: 14,
        glyphMargin: true,
        folding: false,
        renderLineHighlight: "none",
        scrollBeyondLastLine: false,
        contextmenu: false,
        automaticLayout: true,
        occurrencesHighlight: "singleFile",
        selectionHighlight: true,
        renderWhitespace: "none",
        guides: { indentation: false },
        padding: { top: 10, bottom: 10 },
        ariaLabel: `Source code, read only: ${modelPath}`,
      }}
    />
  );
}
