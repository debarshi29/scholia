// "Report draft" from the Session board: one row per flagged finding (location, category,
// why it is a bug and the fix, remove), then the design notes. It is a drawer under the
// code: the bar is always visible, the body opens when there is something to write.
import { useEffect, useRef } from "react";
import type { BugCategory } from "../api/client";
import { baseName, CATEGORIES, CATEGORY_LABEL, lref, plural } from "../lib/format";
import { useDraft, useDraftStore, type DraftFinding } from "../store/draft";
import { Chevron, Flag, Trash } from "./icons";
import { INPUT } from "./ui";

interface Props {
  sessionId: string;
  open: boolean;
  onToggle: () => void;
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
  const empty = f.explanation.trim().length === 0;

  return (
    <li className="rise grid grid-cols-[auto_12.5rem_minmax(0,1fr)_auto] items-start gap-2.5">
      <button
        type="button"
        onClick={props.onJump}
        title={`Show ${f.file} in the editor`}
        className="flex min-h-9 max-w-56 items-center gap-2 rounded-md border border-coral/25 bg-coral/10 px-3 text-left font-mono text-[12.5px] text-coral transition hover:border-coral/60 hover:bg-coral/15"
      >
        <Flag className="size-3.5 shrink-0" />
        <span className="truncate">{location}</span>
      </button>
      <label>
        <span className="sr-only">Category for {location}</span>
        <select
          className={`${INPUT} min-h-9 cursor-pointer`}
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
          className={`${INPUT} block max-h-40 min-h-9 resize-none py-3 [field-sizing:content] ${
            empty ? "border-amber/40" : ""
          }`}
          value={f.explanation}
          placeholder="Why it is a bug, and the fix"
          onChange={(e) => update(sessionId, f.key, { explanation: e.target.value })}
        />
      </label>
      <button
        type="button"
        onClick={() => remove(sessionId, f.key)}
        aria-label={`Remove ${location}`}
        title="Remove"
        className="flex size-9 items-center justify-center rounded-md text-mute transition hover:bg-coral/10 hover:text-coral"
      >
        <Trash className="size-[18px]" />
      </button>
    </li>
  );
}

export default function ReportForm(props: Props) {
  const { sessionId, open, onToggle, focusKey, onJump } = props;
  const draft = useDraft(sessionId);
  const setDesignNotes = useDraftStore((s) => s.setDesignNotes);
  const count = draft.findings.length;
  const hasNotes = draft.designNotes.trim().length > 0;

  return (
    <section
      aria-label="Report draft"
      className="flex min-h-0 flex-col border-t border-line bg-panel/80"
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex min-h-9 w-full items-center justify-between gap-3 px-5 text-left transition hover:bg-ink/[0.03]"
      >
        <span className="flex items-center gap-3">
          <span className="font-semibold">Report draft</span>
          <span
            className={`rounded-full px-2 py-0.5 font-mono text-[12px] leading-none ${
              count > 0 ? "bg-coral/15 text-coral" : "bg-ink/[0.07] text-mute"
            }`}
          >
            {plural(count, "finding")}
          </span>
          {hasNotes && <span className="text-[12.5px] text-mute">· design notes written</span>}
        </span>
        <span className="flex items-center gap-2 text-[12.5px] text-mute">
          {open ? "Hide" : count === 0 ? "Add design notes" : "Open"}
          <Chevron className={`size-4 transition-transform duration-300 ${open ? "" : "rotate-180"}`} />
        </span>
      </button>
      {open && (
        <div className="fade flex max-h-[38vh] min-h-0 flex-col gap-3 overflow-y-auto px-5 pt-1 pb-4">
          {count === 0 ? (
            <p className="rounded-md border border-dashed border-line px-4 py-3 text-[13px] text-mute">
              No findings yet. Select the lines of a bug in the code, then choose “Flag as bug”.
            </p>
          ) : (
            <ol className="flex flex-col gap-2.5">
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
              className={`${INPUT} block min-h-[4.5rem] resize-y py-3`}
              value={draft.designNotes}
              placeholder="Design and improvement notes: coupling, testability, failure modes, what you would change first"
              onChange={(e) => setDesignNotes(sessionId, e.target.value)}
            />
          </label>
        </div>
      )}
    </section>
  );
}
