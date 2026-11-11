// "Report draft" from the Session board: one row per flagged finding (location, category,
// why it is a bug and the fix, remove), then the design notes.
import { useEffect, useRef } from "react";
import type { BugCategory } from "../api/client";
import { baseName, CATEGORIES, CATEGORY_LABEL, lref, plural } from "../lib/format";
import { useDraft, useDraftStore, type DraftFinding } from "../store/draft";
import { INPUT } from "./ui";

interface Props {
  sessionId: string;
  /** Key of the finding that was just added, to focus it. */
  focusKey: string | null;
  onJump: (finding: DraftFinding) => void;
}

/** Why a finding cannot be submitted yet, or null when it is complete. */
export function findingProblem(f: DraftFinding): string | null {
  return f.explanation.trim().length === 0 ? "say why it is a bug" : null;
}

function Row(props: { sessionId: string; finding: DraftFinding; focus: boolean; onJump: () => void }) {
  const { sessionId, finding: f } = props;
  const update = useDraftStore((s) => s.updateFinding);
  const remove = useDraftStore((s) => s.removeFinding);
  const text = useRef<HTMLTextAreaElement | null>(null);
  useEffect(() => {
    if (props.focus) {
      text.current?.scrollIntoView({ block: "nearest" });
      text.current?.focus();
    }
  }, [props.focus]);
  const location = `${baseName(f.file)} ${lref(f.line_from, f.line_to)}`;

  return (
    <li className="grid grid-cols-[10.5rem_14rem_minmax(0,1fr)_auto] items-start gap-3">
      <button
        type="button"
        onClick={props.onJump}
        title={`Show ${f.file} in the editor`}
        className="min-h-12 rounded-md text-left font-mono text-[13px] text-coral hover:underline"
      >
        {location}
      </button>
      <label>
        <span className="sr-only">Category for {location}</span>
        <select
          className={`${INPUT} min-h-12`}
          value={f.category}
          onChange={(e) => update(sessionId, f.key, { category: e.target.value as BugCategory })}
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABEL[c]}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="sr-only">Why {location} is a bug, and the fix</span>
        <textarea
          ref={text}
          rows={1}
          className={`${INPUT} block max-h-48 min-h-12 resize-none py-3 [field-sizing:content]`}
          value={f.explanation}
          placeholder="Why it is a bug, and the fix"
          onChange={(e) => update(sessionId, f.key, { explanation: e.target.value })}
        />
      </label>
      <button
        type="button"
        onClick={() => remove(sessionId, f.key)}
        aria-label={`Remove ${location}`}
        className="min-h-12 rounded-md px-3 text-mute hover:text-ink"
      >
        Remove
      </button>
    </li>
  );
}

export default function ReportForm(props: Props) {
  const { sessionId, focusKey, onJump } = props;
  const draft = useDraft(sessionId);
  const setDesignNotes = useDraftStore((s) => s.setDesignNotes);

  return (
    <section
      aria-label="Report draft"
      className="flex min-h-0 flex-col gap-4 overflow-y-auto border-t border-line bg-panel px-6 py-5"
    >
      <h2 className="flex items-baseline gap-4">
        <span className="text-base font-semibold">Report draft</span>
        <span className="text-[13px] font-normal text-mute">
          {plural(draft.findings.length, "finding")}
        </span>
      </h2>
      {draft.findings.length === 0 ? (
        <p className="text-[13px] text-mute">
          Select the lines of a bug in the code, then choose “Flag as bug”.
        </p>
      ) : (
        <ol className="flex flex-col gap-3">
          {draft.findings.map((f) => (
            <Row
              key={f.key}
              sessionId={sessionId}
              finding={f}
              focus={f.key === focusKey}
              onJump={() => onJump(f)}
            />
          ))}
        </ol>
      )}
      <label>
        <span className="sr-only">Design and improvement notes</span>
        <textarea
          className={`${INPUT} block min-h-24 resize-y py-3`}
          value={draft.designNotes}
          placeholder="Design and improvement notes: coupling, testability, failure modes, what you would change first"
          onChange={(e) => setDesignNotes(sessionId, e.target.value)}
        />
      </label>
    </section>
  );
}
