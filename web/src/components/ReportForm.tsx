// The report form under the editor: one card per flagged finding, plus design notes.
import { useEffect, useRef } from "react";
import type { BugCategory } from "../api/client";
import { baseName, CATEGORIES, CATEGORY_LABEL } from "../lib/format";
import { useDraft, useDraftStore, type DraftFinding } from "../store/draft";
import { Button, INPUT } from "./ui";

interface Props {
  sessionId: string;
  /** Lines per file, to keep edited ranges inside the file. */
  lineCounts: Record<string, number>;
  /** Key of the finding that was just added, to focus it. */
  focusKey: string | null;
  onJump: (finding: DraftFinding) => void;
}

/** Why a finding cannot be submitted yet, or null when it is complete. */
export function findingProblem(f: DraftFinding, lineCounts: Record<string, number>): string | null {
  const max = lineCounts[f.file];
  if (!Number.isInteger(f.line_from) || !Number.isInteger(f.line_to)) return "Enter whole line numbers.";
  if (f.line_from < 1 || f.line_to < f.line_from) return "The line range is not valid.";
  if (max !== undefined && f.line_to > max) return `This file has ${max} lines.`;
  if (f.explanation.trim().length === 0) return "Add an explanation.";
  return null;
}

function FindingCard(props: {
  sessionId: string;
  index: number;
  finding: DraftFinding;
  problem: string | null;
  focus: boolean;
  onJump: () => void;
}) {
  const { sessionId, index, finding: f, problem } = props;
  const update = useDraftStore((s) => s.updateFinding);
  const remove = useDraftStore((s) => s.removeFinding);
  const explanation = useRef<HTMLTextAreaElement | null>(null);
  const card = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    if (props.focus) {
      card.current?.scrollIntoView({ block: "nearest" });
      explanation.current?.focus();
    }
  }, [props.focus]);
  const set = (patch: Partial<DraftFinding>) => update(sessionId, f.key, patch);
  const id = `finding-${f.key}`;

  return (
    <li ref={card} className="rounded-md border border-line border-l-[3px] border-l-coral bg-bg p-3">
      <div className="flex flex-wrap items-end gap-3">
        <button
          type="button"
          onClick={props.onJump}
          title={`Show ${f.file} in the editor`}
          className="min-h-11 rounded-md px-2 font-mono text-[13px] text-coral hover:bg-raised"
        >
          #{index + 1} · {baseName(f.file)}
        </button>
        <label className="flex flex-col gap-1">
          <span className="text-[12px] text-mute uppercase">From line</span>
          <input
            className={`${INPUT} w-24 font-mono`}
            type="number"
            min={1}
            value={Number.isNaN(f.line_from) ? "" : f.line_from}
            onChange={(e) => set({ line_from: e.target.valueAsNumber })}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[12px] text-mute uppercase">To line</span>
          <input
            className={`${INPUT} w-24 font-mono`}
            type="number"
            min={1}
            value={Number.isNaN(f.line_to) ? "" : f.line_to}
            onChange={(e) => set({ line_to: e.target.valueAsNumber })}
          />
        </label>
        <label className="flex min-w-48 flex-1 flex-col gap-1">
          <span className="text-[12px] text-mute uppercase">Category</span>
          <select
            className={INPUT}
            value={f.category}
            onChange={(e) => set({ category: e.target.value as BugCategory })}
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[c]}
              </option>
            ))}
          </select>
        </label>
        <Button tone="mute" variant="outline" compact onClick={() => remove(sessionId, f.key)}>
          Remove
        </Button>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="text-[12px] text-mute uppercase">What goes wrong, and when</span>
          <textarea
            ref={explanation}
            className={`${INPUT} min-h-20 resize-y py-2`}
            value={f.explanation}
            aria-describedby={problem ? `${id}-problem` : undefined}
            onChange={(e) => set({ explanation: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[12px] text-mute uppercase">Fix (optional)</span>
          <textarea
            className={`${INPUT} min-h-20 resize-y py-2`}
            value={f.fix}
            onChange={(e) => set({ fix: e.target.value })}
          />
        </label>
      </div>
      {problem && (
        <p id={`${id}-problem`} className="mt-2 text-[12px] text-amber">
          {problem}
        </p>
      )}
    </li>
  );
}

export default function ReportForm(props: Props) {
  const { sessionId, lineCounts, focusKey, onJump } = props;
  const draft = useDraft(sessionId);
  const setDesignNotes = useDraftStore((s) => s.setDesignNotes);

  return (
    <section aria-label="Report" className="flex min-h-0 flex-col border-t border-line bg-panel">
      <header className="flex min-h-11 items-center justify-between border-b border-line px-3">
        <h2 className="text-[13px] font-semibold tracking-wide text-mute uppercase">
          Report · {draft.findings.length} {draft.findings.length === 1 ? "finding" : "findings"}
        </h2>
        <span className="text-[12px] text-mute">Saved in this browser until you submit.</span>
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
        {draft.findings.length === 0 ? (
          <p className="text-[13px] text-mute">
            No findings yet. Select the lines of a bug in the code and choose “Flag as bug”.
          </p>
        ) : (
          <ol className="flex flex-col gap-3">
            {draft.findings.map((f, i) => (
              <FindingCard
                key={f.key}
                sessionId={sessionId}
                index={i}
                finding={f}
                problem={findingProblem(f, lineCounts)}
                focus={f.key === focusKey}
                onJump={() => onJump(f)}
              />
            ))}
          </ol>
        )}
        <label className="flex flex-col gap-1">
          <span className="text-[12px] text-mute uppercase">Design notes</span>
          <textarea
            className={`${INPUT} min-h-20 resize-y py-2`}
            value={draft.designNotes}
            placeholder="What would you change about how this code is structured, and why?"
            onChange={(e) => setDesignNotes(sessionId, e.target.value)}
          />
        </label>
      </div>
    </section>
  );
}
