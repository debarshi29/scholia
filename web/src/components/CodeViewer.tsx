// Read-only Monaco viewer. The line selection is reported upwards, where it drives the
// "Ask assistant" and "Flag as bug" actions; flagged lines get a coral decoration.
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
  /** Answer-key lines, shown in green on the debrief only. */
  keyLines?: LineRange[];
  onSelect?: (range: LineRange | null) => void;
  /** Bump `nonce` to scroll to `line` again. */
  reveal?: { line: number; nonce: number } | null;
}

type Collection = monaco.editor.IEditorDecorationsCollection;

function decoration(range: LineRange, line: string, glyph: string) {
  return {
    range: new monaco.Range(range.from, 1, range.to, 1),
    options: { isWholeLine: true, className: line, linesDecorationsClassName: glyph },
  };
}

export default function CodeViewer(props: Props) {
  const { modelPath, content, flagged, keyLines, onSelect, reveal } = props;
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const decorations = useRef<Collection | null>(null);
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
    decorations.current = editor.createDecorationsCollection([
      ...(keyLines ?? []).map((r) => decoration(r, "key-line", "key-glyph")),
      ...flagged.map((r) => decoration(r, "flagged-line", "flagged-glyph")),
    ]);
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

  const onMount: OnMount = (editor) => {
    editorRef.current = editor as unknown as monaco.editor.IStandaloneCodeEditor;
    editor.onDidChangeCursorSelection(report);
    editor.onDidChangeModel(() => {
      paint();
      report();
    });
    paint();
    // The first reveal usually arrives before the editor exists.
    if (revealRef.current) editor.revealLineInCenter(revealRef.current.line);
  };

  // Repaint when the flags or the file change.
  const signature = JSON.stringify([modelPath, flagged, keyLines]);
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
        fontSize: 13,
        lineHeight: 20,
        lineNumbersMinChars: 4,
        lineDecorationsWidth: 12,
        glyphMargin: false,
        folding: true,
        renderLineHighlight: "line",
        scrollBeyondLastLine: false,
        contextmenu: false,
        automaticLayout: true,
        occurrencesHighlight: "singleFile",
        selectionHighlight: true,
        renderWhitespace: "none",
        padding: { top: 8, bottom: 8 },
        ariaLabel: `Source code, read only: ${modelPath}`,
      }}
    />
  );
}
